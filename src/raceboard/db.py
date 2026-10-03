"""Accès à la base de données : connexion, schéma, écriture et lecture des tours.

SQL portable (SQLite aujourd'hui, PostgreSQL prévu en v0.2), à une exception près,
signalée dans SCHEMA : l'auto-incrément de sessions.id.
"""

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from raceboard.extract_laps import Lap
from raceboard.session_info import IbtInfo

DB_PATH_VARIABLE = "RACEBOARD_DB_PATH"

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id            INTEGER PRIMARY KEY,  -- auto-incrément SQLite ; PostgreSQL : GENERATED ALWAYS AS IDENTITY
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
]

LAPS_QUERY = """
    SELECT s.recorded_at, s.car_name, s.session_num, s.session_type,
           l.lap_num, l.lap_time_ms, l.time_is_official, l.is_valid, l.incidents
    FROM laps l
    JOIN sessions s ON s.id = l.session_id
    ORDER BY s.recorded_at, s.session_num, l.lap_num
"""


class ConfigError(Exception):
    """Configuration manquante ou incorrecte (variable d'environnement, dossier)."""


@dataclass
class StoredLap:
    recorded_at: str
    car_name: str
    session_num: int
    session_type: str
    lap_num: int
    lap_time_ms: int
    time_is_official: bool
    is_valid: bool
    incidents: int


def get_db_path() -> Path:
    """Chemin du fichier de base, lu dans la variable d'environnement RACEBOARD_DB_PATH."""
    value = os.environ.get(DB_PATH_VARIABLE)
    if not value:
        raise ConfigError(f"Variable d'environnement {DB_PATH_VARIABLE} non définie (chemin du fichier de base)")
    path = Path(value)
    if not path.parent.is_dir():
        raise ConfigError(f"Dossier de la base introuvable : {path.parent}")
    return path


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    # SQLite ne vérifie les clés étrangères que si on le lui demande, à chaque connexion.
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    """Crée les tables si elles n'existent pas encore."""
    with connection:
        for statement in SCHEMA:
            connection.execute(statement)


def save_session(
    connection: sqlite3.Connection, source_file: str, session_num: int, info: IbtInfo, laps: list[Lap]
) -> int:
    """Insère une session et ses tours ; renvoie l'id de la session.

    Ne valide pas la transaction : c'est à l'appelant de le faire (with connection: …).
    """
    session_id = connection.execute(
        """
        INSERT INTO sessions (source_file, session_num, session_type, track_name, track_config, car_name, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            source_file,
            session_num,
            info.session_types.get(session_num, "inconnu"),
            info.track_name,
            info.track_config,
            info.car_name,
            info.recorded_at.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    ).fetchone()[0]

    connection.executemany(
        """
        INSERT INTO laps (session_id, lap_num, lap_time_ms, time_is_official, is_valid, incidents)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (session_id, lap.lap_num, round(lap.time_s * 1000), lap.time_is_official, lap.valid, lap.incidents)
            for lap in laps
        ],
    )
    return session_id


def fetch_laps(connection: sqlite3.Connection) -> list[StoredLap]:
    """Tous les tours de la base, avec les informations de leur session."""
    rows = connection.execute(LAPS_QUERY).fetchall()
    return [
        StoredLap(
            recorded_at=str(recorded_at),
            car_name=car_name,
            session_num=session_num,
            session_type=session_type,
            lap_num=lap_num,
            lap_time_ms=lap_time_ms,
            # SQLite renvoie les booléens sous forme de 0/1.
            time_is_official=bool(time_is_official),
            is_valid=bool(is_valid),
            incidents=incidents,
        )
        for (recorded_at, car_name, session_num, session_type,
             lap_num, lap_time_ms, time_is_official, is_valid, incidents) in rows
    ]
