"""Worker d'ingestion : importe en base tous les fichiers .ibt d'un dossier.

Les fichiers déjà en base sont sautés : relancer le worker ne crée pas de doublon.
Un passage, puis le worker s'arrête (le déclenchement régulier relève de l'infra).

Configuration par variables d'environnement :
    RACEBOARD_TELEMETRY_DIR  dossier contenant les .ibt (sous-dossiers non parcourus)
    RACEBOARD_DB_PATH        chemin du fichier de base

Usage :
    py -m raceboard.worker
"""

import os
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

from raceboard.db import ConfigError, connect, count_rows, create_schema, get_db_path, imported_files
from raceboard.import_ibt import read_ibt, save_ibt

TELEMETRY_DIR_VARIABLE = "RACEBOARD_TELEMETRY_DIR"


@dataclass
class WorkerReport:
    found: int = 0                                                # fichiers .ibt trouvés dans le dossier
    imported: list[str] = field(default_factory=list)             # fichiers importés pendant ce passage
    skipped: int = 0                                              # fichiers déjà en base
    errors: list[tuple[str, str]] = field(default_factory=list)  # (fichier, message d'erreur)


def get_telemetry_dir() -> Path:
    """Dossier des .ibt, lu dans la variable d'environnement RACEBOARD_TELEMETRY_DIR."""
    value = os.environ.get(TELEMETRY_DIR_VARIABLE)
    if not value:
        raise ConfigError(f"Variable d'environnement {TELEMETRY_DIR_VARIABLE} non définie (dossier des .ibt)")
    path = Path(value)
    if not path.is_dir():
        raise ConfigError(f"Dossier des .ibt introuvable : {path}")
    return path


def run_worker(connection: sqlite3.Connection, telemetry_dir: Path) -> WorkerReport:
    """Importe les .ibt du dossier qui ne sont pas encore en base, un fichier par transaction."""
    report = WorkerReport()
    already_imported = imported_files(connection)

    for ibt_path in sorted(telemetry_dir.glob("*.ibt")):
        report.found += 1
        if ibt_path.name in already_imported:
            report.skipped += 1
            continue
        try:
            content = read_ibt(ibt_path)
            lap_counts = save_ibt(connection, ibt_path.name, content.info, content.session_nums, content.laps)
        except Exception as error:
            # Un fichier illisible ne doit pas bloquer les autres : on le signale et on continue.
            # Rien n'a été écrit pour lui (transaction annulée) : il sera retenté au prochain passage.
            message = f"{type(error).__name__}: {error}"
            report.errors.append((ibt_path.name, message))
            print(f"ERREUR   {ibt_path.name} : {message}", file=sys.stderr)
            continue
        report.imported.append(ibt_path.name)
        print(f"importé  {ibt_path.name} : {sum(lap_counts.values())} tours")

    return report


def main() -> int:
    try:
        db_path = get_db_path()
        telemetry_dir = get_telemetry_dir()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1

    connection = connect(db_path)
    try:
        create_schema(connection)
        report = run_worker(connection, telemetry_dir)
        sessions, laps = count_rows(connection)
    finally:
        connection.close()

    print(
        f"{report.found} fichiers .ibt : {len(report.imported)} importés, "
        f"{report.skipped} déjà en base, {len(report.errors)} en erreur"
    )
    print(f"Base {db_path.name} : {sessions} sessions, {laps} tours")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
