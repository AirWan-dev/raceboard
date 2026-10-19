"""Worker d'ingestion : importe en base tous les fichiers .ibt d'un dossier.

Les fichiers déjà en base sont sautés : relancer le worker ne crée pas de doublon.
Un fichier en cours d'écriture (modifié récemment, ou verrouillé) est laissé de côté sans
erreur et repris à un passage suivant (ADR 0006). Tout autre fichier en erreur est inscrit
en quarantaine (table quarantine, ADR 0005) et n'est plus retraité ensuite ; pour le
retenter : py -m raceboard.quarantine remove "<fichier>".
Le worker ne modifie ni ne supprime jamais un fichier source.
Un passage, puis le worker s'arrête (le déclenchement régulier relève de l'infra).

Code retour : 1 si un fichier a été mis en quarantaine pendant ce passage (nouvelle alerte)
ou si la configuration est incorrecte ; 0 sinon, même s'il reste des fichiers en quarantaine
ou en cours d'écriture.

Configuration par variables d'environnement :
    RACEBOARD_TELEMETRY_DIR       dossier contenant les .ibt (sous-dossiers non parcourus)
    RACEBOARD_DB_PATH             chemin du fichier de base
    RACEBOARD_FILE_GUARD_MINUTES  délai de garde en minutes (facultatif, 15 par défaut) :
                                  un fichier modifié plus récemment est considéré en cours d'écriture

Usage :
    py -m raceboard.worker
"""

import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from raceboard.db import (
    ConfigError,
    add_to_quarantine,
    connect,
    count_rows,
    create_schema,
    get_db_path,
    imported_files,
    quarantined_files,
)
from raceboard.import_ibt import read_ibt, save_ibt

TELEMETRY_DIR_VARIABLE = "RACEBOARD_TELEMETRY_DIR"
GUARD_MINUTES_VARIABLE = "RACEBOARD_FILE_GUARD_MINUTES"
DEFAULT_GUARD_MINUTES = 15


@dataclass
class WorkerReport:
    found: int = 0                                                 # fichiers .ibt trouvés dans le dossier
    imported: list[str] = field(default_factory=list)              # fichiers importés pendant ce passage
    skipped: int = 0                                               # fichiers déjà en base
    quarantined: int = 0                                           # fichiers sautés car déjà en quarantaine
    errors: list[tuple[str, str]] = field(default_factory=list)   # nouveaux échecs, mis en quarantaine
    pending: list[tuple[str, str]] = field(default_factory=list)  # (fichier, raison) en cours d'écriture


def get_telemetry_dir() -> Path:
    """Dossier des .ibt, lu dans la variable d'environnement RACEBOARD_TELEMETRY_DIR."""
    value = os.environ.get(TELEMETRY_DIR_VARIABLE)
    if not value:
        raise ConfigError(f"Variable d'environnement {TELEMETRY_DIR_VARIABLE} non définie (dossier des .ibt)")
    path = Path(value)
    if not path.is_dir():
        raise ConfigError(f"Dossier des .ibt introuvable : {path}")
    return path


def get_guard_minutes() -> int:
    """Délai de garde, lu dans RACEBOARD_FILE_GUARD_MINUTES (entier >= 0, 15 par défaut)."""
    value = os.environ.get(GUARD_MINUTES_VARIABLE)
    if not value:
        return DEFAULT_GUARD_MINUTES
    try:
        minutes = int(value)
    except ValueError:
        minutes = -1
    if minutes < 0:
        raise ConfigError(f"{GUARD_MINUTES_VARIABLE} doit être un nombre entier de minutes >= 0 (valeur : {value!r})")
    return minutes


def run_worker(
    connection: sqlite3.Connection, telemetry_dir: Path, guard_minutes: int = DEFAULT_GUARD_MINUTES
) -> WorkerReport:
    """Importe les .ibt du dossier qui ne sont ni en base ni en quarantaine, un fichier par transaction."""
    report = WorkerReport()
    already_imported = imported_files(connection)
    in_quarantine = quarantined_files(connection)
    now = time.time()

    for ibt_path in sorted(telemetry_dir.glob("*.ibt")):
        report.found += 1
        if ibt_path.name in already_imported:
            report.skipped += 1
            continue
        if ibt_path.name in in_quarantine:
            report.quarantined += 1
            continue
        try:
            # Modifié il y a moins de guard_minutes : iRacing est sans doute encore en train d'écrire.
            # Un délai de 0 désactive la vérification (sous Windows, la date d'un fichier tout juste
            # écrit peut être en avance de quelques millisecondes sur time.time()).
            if guard_minutes > 0 and now - ibt_path.stat().st_mtime < guard_minutes * 60:
                _leave_aside(report, ibt_path.name, f"modifié il y a moins de {guard_minutes} min")
                continue
            content = read_ibt(ibt_path)
            lap_counts = save_ibt(connection, ibt_path.name, content.info, content.session_nums, content.laps)
        except PermissionError:
            # Fichier verrouillé (iRacing écrit encore dedans) : erreur temporaire, pas de quarantaine.
            _leave_aside(report, ibt_path.name, "fichier verrouillé")
            continue
        except Exception as error:
            # Un fichier illisible ne doit pas bloquer les autres. Rien n'a été écrit pour lui
            # (transaction annulée) : on l'inscrit en quarantaine et on continue.
            message = f"{type(error).__name__}: {error}"
            add_to_quarantine(connection, ibt_path.name, message, datetime.now(UTC))
            report.errors.append((ibt_path.name, message))
            print(f"ERREUR   {ibt_path.name} : {message}", file=sys.stderr)
            continue
        report.imported.append(ibt_path.name)
        print(f"importé  {ibt_path.name} : {sum(lap_counts.values())} tours")

    return report


def _leave_aside(report: WorkerReport, file_name: str, reason: str) -> None:
    """Laisse de côté un fichier en cours d'écriture : ni erreur ni quarantaine, repris plus tard."""
    report.pending.append((file_name, reason))
    print(f"en attente  {file_name} : {reason}")


def main() -> int:
    try:
        db_path = get_db_path()
        telemetry_dir = get_telemetry_dir()
        guard_minutes = get_guard_minutes()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1

    connection = connect(db_path)
    try:
        create_schema(connection)
        report = run_worker(connection, telemetry_dir, guard_minutes)
        sessions, laps = count_rows(connection)
        quarantine = len(quarantined_files(connection))
    finally:
        connection.close()

    print(
        f"{report.found} fichiers .ibt : {len(report.imported)} importés, "
        f"{report.skipped} déjà en base, {len(report.errors)} mis en quarantaine, "
        f"{report.quarantined} déjà en quarantaine, {len(report.pending)} en cours d'écriture"
    )
    print(f"Base {db_path.name} : {sessions} sessions, {laps} tours, {quarantine} fichiers en quarantaine")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
