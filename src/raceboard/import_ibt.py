"""Enregistre en base les sessions et les tours d'un fichier .ibt.

Le chemin de la base est lu dans la variable d'environnement RACEBOARD_DB_PATH.

Usage :
    py -m raceboard.import_ibt "C:/chemin/vers/session.ibt"
"""

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from raceboard.db import ConfigError, connect, create_schema, get_db_path, save_session
from raceboard.extract_laps import Lap, extract_laps, read_lap_channels
from raceboard.session_info import IbtInfo, read_ibt_info


@dataclass
class IbtContent:
    info: IbtInfo
    session_nums: list[int]  # sessions présentes dans la télémétrie du fichier
    laps: list[Lap]          # tours terminés, toutes sessions confondues


def read_ibt(ibt_path: Path) -> IbtContent:
    """Lit un fichier .ibt : informations générales, sessions et tours terminés."""
    channels = read_lap_channels(ibt_path)
    if not channels["SessionNum"]:
        # Sans échantillon, rien ne serait écrit en base et le fichier serait retraité à chaque fois.
        raise ValueError(f"Aucune donnée de télémétrie dans le fichier : {ibt_path.name}")
    info = read_ibt_info(ibt_path)
    return IbtContent(
        info=info,
        session_nums=sorted(set(channels["SessionNum"])),
        laps=extract_laps(channels).laps,
    )


def save_ibt(
    connection: sqlite3.Connection, source_file: str, info: IbtInfo, session_nums: list[int], laps: list[Lap]
) -> dict[int, int]:
    """Enregistre toutes les sessions du fichier et leurs tours, en une seule transaction.

    Renvoie le nombre de tours enregistrés par numéro de session.
    """
    lap_counts = {}
    with connection:  # tout ou rien : en cas d'erreur, rien n'est écrit
        for session_num in session_nums:
            session_laps = [lap for lap in laps if lap.session_num == session_num]
            save_session(connection, source_file, session_num, info, session_laps)
            lap_counts[session_num] = len(session_laps)
    return lap_counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Enregistre en base les tours d'un fichier .ibt iRacing.")
    parser.add_argument("ibt_path", type=Path, help="chemin du fichier .ibt")
    args = parser.parse_args()

    if not args.ibt_path.is_file():
        print(f"Fichier introuvable : {args.ibt_path}", file=sys.stderr)
        return 1

    try:
        db_path = get_db_path()
        content = read_ibt(args.ibt_path)
    except (ConfigError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    info = content.info
    connection = connect(db_path)
    try:
        create_schema(connection)
        lap_counts = save_ibt(connection, args.ibt_path.name, info, content.session_nums, content.laps)
    except sqlite3.IntegrityError as error:
        print(f"Insertion refusée par la base (fichier déjà importé ?) : {error}", file=sys.stderr)
        return 1
    finally:
        connection.close()

    print(f"{args.ibt_path.name} : {info.car_name}, {info.track_name} ({info.track_config})")
    for session_num, count in lap_counts.items():
        session_type = info.session_types.get(session_num, "inconnu")
        print(f"  session {session_num} ({session_type}) : {count} tours enregistrés")
    print(f"Base : {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
