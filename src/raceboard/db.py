"""Accès à la base PostgreSQL : connexion, schéma, écriture et lecture des tours, quarantaine.

Seul ce module connaît le pilote (psycopg 3) : les autres passent par ses fonctions et ses
types (Connection, IntegrityError). Le SQL reste standard ; seuls les paramètres s'écrivent
%s, notation imposée par le pilote.

La connexion est lue dans la variable d'environnement RACEBOARD_DATABASE_URL, au format
postgresql://<utilisateur>:<mot de passe>@<serveur>:5432/<base>. Elle contient le mot de
passe : aucun message ne l'affiche.
"""

import os
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg
from psycopg.conninfo import conninfo_to_dict

from raceboard.extract_laps import Lap
from raceboard.session_info import IbtInfo

DATABASE_URL_VARIABLE = "RACEBOARD_DATABASE_URL"
URL_FORMAT = "postgresql://<utilisateur>:<mot de passe>@<serveur>:5432/<base>"

# Types du pilote, exposés ici pour que les autres modules n'importent jamais psycopg.
Connection = psycopg.Connection
IntegrityError = psycopg.IntegrityError  # insertion refusée : doublon, clé étrangère absente…

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        source_file   VARCHAR(255) NOT NULL,  -- nom du fichier .ibt, sans le dossier
        session_num   INTEGER NOT NULL,       -- numéro de la session dans le fichier
        session_type  VARCHAR(50) NOT NULL,   -- ex. "Offline Testing", "Race"
        track_name    VARCHAR(100) NOT NULL,
        track_config  VARCHAR(100) NOT NULL,
        car_name      VARCHAR(100) NOT NULL,
        recorded_at   TIMESTAMP NOT NULL,     -- début de l'enregistrement, UTC
        UNIQUE (source_file, session_num)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS laps (
        session_id        INTEGER NOT NULL REFERENCES sessions (id),
        lap_num           INTEGER NOT NULL,
        lap_time_ms       INTEGER NOT NULL,  -- temps au tour en millisecondes
        time_is_official  BOOLEAN NOT NULL,  -- TRUE : temps iRacing ; FALSE : temps mesuré (indicatif)
        is_valid          BOOLEAN NOT NULL,
        incidents         INTEGER NOT NULL,  -- points d'incident pris pendant le tour
        PRIMARY KEY (session_id, lap_num)
    )
    """,
    # Fichiers rejetés par le worker (ADR 0005). Pour retenter un fichier, supprimer sa ligne.
    """
    CREATE TABLE IF NOT EXISTS quarantine (
        source_file    VARCHAR(255) PRIMARY KEY,  -- nom du fichier .ibt, sans le dossier
        error_message  TEXT NOT NULL,
        rejected_at    TIMESTAMP NOT NULL         -- date du rejet, UTC
    )
    """,
]

# Les dates sont stockées en TIMESTAMP sans fuseau, en UTC par convention, à la seconde près.
# Les fonctions de lecture les renvoient en texte, dans ce format.
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

LAPS_SELECT = """
    SELECT s.recorded_at, s.car_name, s.session_num, s.session_type,
           l.lap_num, l.lap_time_ms, l.time_is_official, l.is_valid, l.incidents
    FROM laps l
    JOIN sessions s ON s.id = l.session_id
"""
LAPS_QUERY = LAPS_SELECT + "ORDER BY s.recorded_at, s.session_num, l.lap_num"
SESSION_LAPS_QUERY = LAPS_SELECT + "WHERE l.session_id = %s ORDER BY l.lap_num"

# Sessions avec leur nombre de tours, de tours valides et leur meilleur tour valide
# (LEFT JOIN : une session sans tour donne 0, 0 et NULL).
SESSIONS_QUERY = """
    SELECT s.id, s.recorded_at, s.car_name, s.track_name, s.track_config, s.session_type,
           COUNT(l.lap_num),
           SUM(CASE WHEN l.is_valid = TRUE THEN 1 ELSE 0 END),
           MIN(CASE WHEN l.is_valid = TRUE THEN l.lap_time_ms END)
    FROM sessions s
    LEFT JOIN laps l ON l.session_id = s.id
    GROUP BY s.id, s.recorded_at, s.car_name, s.track_name, s.track_config, s.session_type
    ORDER BY s.recorded_at DESC, s.id DESC
"""


class ConfigError(Exception):
    """Configuration manquante ou incorrecte (variable d'environnement, dossier)."""


class DatabaseError(Exception):
    """Base inutilisable : serveur injoignable, mot de passe refusé, base inexistante, tables absentes."""


@dataclass
class StoredLap:
    recorded_at: str  # UTC, format TIMESTAMP_FORMAT
    car_name: str
    session_num: int
    session_type: str
    lap_num: int
    lap_time_ms: int
    time_is_official: bool
    is_valid: bool
    incidents: int


@dataclass
class StoredSession:
    id: int
    recorded_at: str  # UTC, format TIMESTAMP_FORMAT
    car_name: str
    track_name: str
    track_config: str
    session_type: str
    lap_count: int
    valid_lap_count: int
    best_valid_lap_ms: int | None  # None s'il n'y a aucun tour valide


@dataclass
class QuarantinedFile:
    source_file: str
    error_message: str
    rejected_at: str  # UTC, format TIMESTAMP_FORMAT


def get_database_url() -> str:
    """URL de connexion, lue dans la variable d'environnement RACEBOARD_DATABASE_URL.

    Les messages d'erreur ne citent jamais l'URL : elle contient le mot de passe.
    """
    url = os.environ.get(DATABASE_URL_VARIABLE)
    if not url:
        raise ConfigError(f"Variable d'environnement {DATABASE_URL_VARIABLE} non définie (connexion à la base)")
    if not url.startswith(("postgresql://", "postgres://")):
        raise ConfigError(f"{DATABASE_URL_VARIABLE} invalide : format attendu {URL_FORMAT}")
    # Partie « utilisateur:mot de passe », avant le dernier @. Un @ ou un / non encodé y fausse
    # la lecture de l'URL : un morceau du mot de passe serait pris pour le serveur, et finirait
    # affiché dans un message d'erreur de connexion.
    credentials = url.split("://", 1)[1].rpartition("@")[0]
    if "@" in credentials or "/" in credentials:
        raise ConfigError(
            f"{DATABASE_URL_VARIABLE} invalide : dans l'utilisateur ou le mot de passe, "
            "@ et / doivent être encodés (%40 et %2F)"
        )
    try:
        conninfo_to_dict(url)
    except psycopg.ProgrammingError:
        # Le message du pilote n'est pas repris : il peut citer un morceau du mot de passe.
        raise ConfigError(f"{DATABASE_URL_VARIABLE} invalide : format attendu {URL_FORMAT}") from None
    return url


def connect(url: str, read_only: bool = False) -> Connection:
    """Ouvre une connexion à la base ; DatabaseError si c'est impossible.

    Mode autocommit : chaque requête est validée seule. Pour écrire plusieurs lignes en tout ou
    rien, utiliser « with connection.transaction(): ». Attention : avec psycopg,
    « with connection: » ferme la connexion à la sortie du bloc.
    """
    try:
        connection = psycopg.connect(url, autocommit=True)
    except psycopg.OperationalError as error:
        # Message du serveur ou de la bibliothèque client : il ne contient pas le mot de passe.
        raise DatabaseError(f"Connexion à la base impossible : {str(error).strip()}") from None
    if read_only:
        # Toute écriture est refusée sur cette connexion (filet de sécurité du dashboard).
        connection.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    return connection


def database_label(connection: Connection) -> str:
    """Base et serveur, pour les messages, ex. « raceboard (postgres:5432) ».

    Jamais l'utilisateur ni le mot de passe.
    """
    return f"{connection.info.dbname} ({connection.info.host}:{connection.info.port})"


def schema_exists(connection: Connection) -> bool:
    """Vrai si les tables de RaceBoard existent (créées au premier passage du worker)."""
    count = connection.execute(
        """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = CURRENT_SCHEMA AND table_name IN ('sessions', 'laps', 'quarantine')
        """
    ).fetchone()[0]
    return count == 3


def open_existing_database(read_only: bool = False) -> Connection:
    """Connexion à une base déjà initialisée par le worker, pour la consulter.

    Lève ConfigError (variable absente ou invalide) ou DatabaseError (connexion impossible,
    tables absentes), avec un message prêt à afficher.
    """
    connection = connect(get_database_url(), read_only=read_only)
    if not schema_exists(connection):
        label = database_label(connection)
        connection.close()
        raise DatabaseError(f"Base {label} pas encore initialisée : le worker n'y a encore jamais tourné")
    return connection


def create_schema(connection: Connection) -> None:
    """Crée les tables si elles n'existent pas encore."""
    with connection.transaction():
        for statement in SCHEMA:
            connection.execute(statement)


def save_session(connection: Connection, source_file: str, session_num: int, info: IbtInfo, laps: list[Lap]) -> int:
    """Insère une session et ses tours ; renvoie l'id de la session.

    À appeler dans un bloc « with connection.transaction(): », pour que la session et ses tours
    soient écrits ensemble ou pas du tout.
    """
    session_id = connection.execute(
        """
        INSERT INTO sessions (source_file, session_num, session_type, track_name, track_config, car_name, recorded_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            source_file,
            session_num,
            info.session_types.get(session_num, "inconnu"),
            info.track_name,
            info.track_config,
            info.car_name,
            _to_utc(info.recorded_at),
        ),
    ).fetchone()[0]

    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO laps (session_id, lap_num, lap_time_ms, time_is_official, is_valid, incidents)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (session_id, lap.lap_num, round(lap.time_s * 1000), lap.time_is_official, lap.valid, lap.incidents)
                for lap in laps
            ],
        )
    return session_id


def imported_files(connection: Connection) -> set[str]:
    """Noms des fichiers .ibt déjà en base.

    Un fichier est importé en une seule transaction : s'il a au moins une session en base,
    il a été importé en entier.
    """
    return {row[0] for row in connection.execute("SELECT DISTINCT source_file FROM sessions")}


def quarantined_files(connection: Connection) -> set[str]:
    """Noms des fichiers .ibt en quarantaine (rejetés lors d'un passage précédent du worker)."""
    return {row[0] for row in connection.execute("SELECT source_file FROM quarantine")}


def add_to_quarantine(connection: Connection, source_file: str, error_message: str, rejected_at: datetime) -> None:
    """Inscrit un fichier rejeté en quarantaine (validé immédiatement)."""
    connection.execute(
        "INSERT INTO quarantine (source_file, error_message, rejected_at) VALUES (%s, %s, %s)",
        (source_file, error_message, _to_utc(rejected_at)),
    )


def fetch_quarantine(connection: Connection) -> list[QuarantinedFile]:
    """Contenu de la quarantaine, du rejet le plus ancien au plus récent."""
    rows = connection.execute(
        "SELECT source_file, error_message, rejected_at FROM quarantine ORDER BY rejected_at, source_file"
    ).fetchall()
    return [
        QuarantinedFile(source_file=source_file, error_message=error_message, rejected_at=_to_text(rejected_at))
        for source_file, error_message, rejected_at in rows
    ]


def remove_from_quarantine(connection: Connection, source_file: str) -> bool:
    """Retire un fichier de la quarantaine ; renvoie False s'il n'y était pas."""
    cursor = connection.execute("DELETE FROM quarantine WHERE source_file = %s", (source_file,))
    return cursor.rowcount > 0


def count_rows(connection: Connection) -> tuple[int, int]:
    """Nombre de lignes des tables sessions et laps."""
    sessions = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    laps = connection.execute("SELECT COUNT(*) FROM laps").fetchone()[0]
    return sessions, laps


def fetch_sessions(connection: Connection) -> list[StoredSession]:
    """Toutes les sessions, de la plus récente à la plus ancienne, avec le résumé de leurs tours."""
    return [
        StoredSession(
            id=session_id,
            recorded_at=_to_text(recorded_at),
            car_name=car_name,
            track_name=track_name,
            track_config=track_config,
            session_type=session_type,
            lap_count=lap_count,
            valid_lap_count=valid_lap_count,
            best_valid_lap_ms=best_valid_lap_ms,
        )
        for (session_id, recorded_at, car_name, track_name, track_config, session_type,
             lap_count, valid_lap_count, best_valid_lap_ms) in connection.execute(SESSIONS_QUERY)
    ]


def fetch_laps(connection: Connection) -> list[StoredLap]:
    """Tous les tours de la base, avec les informations de leur session."""
    return _to_stored_laps(connection.execute(LAPS_QUERY).fetchall())


def fetch_session_laps(connection: Connection, session_id: int) -> list[StoredLap]:
    """Tours d'une session, dans l'ordre."""
    return _to_stored_laps(connection.execute(SESSION_LAPS_QUERY, (session_id,)).fetchall())


def _to_stored_laps(rows: list[tuple]) -> list[StoredLap]:
    return [
        StoredLap(
            recorded_at=_to_text(recorded_at),
            car_name=car_name,
            session_num=session_num,
            session_type=session_type,
            lap_num=lap_num,
            lap_time_ms=lap_time_ms,
            time_is_official=time_is_official,
            is_valid=is_valid,
            incidents=incidents,
        )
        for (recorded_at, car_name, session_num, session_type,
             lap_num, lap_time_ms, time_is_official, is_valid, incidents) in rows
    ]


def _to_utc(value: datetime) -> datetime:
    """Date avec fuseau → date à écrire en base : UTC, sans fuseau, à la seconde près."""
    return value.astimezone(UTC).replace(tzinfo=None, microsecond=0)


def _to_text(value: datetime) -> str:
    """Date lue en base → texte au format TIMESTAMP_FORMAT."""
    return value.strftime(TIMESTAMP_FORMAT)
