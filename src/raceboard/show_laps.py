"""Affiche les tours enregistrés en base (requête SQL, sans lire aucun .ibt).

Le chemin de la base est lu dans la variable d'environnement RACEBOARD_DB_PATH.

Usage :
    py -m raceboard.show_laps
"""

import sys

from raceboard.db import ConfigError, connect, fetch_laps, get_db_path
from raceboard.extract_laps import format_lap_time


def main() -> int:
    try:
        db_path = get_db_path()
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    if not db_path.is_file():
        print(f"Base introuvable : {db_path}", file=sys.stderr)
        return 1

    connection = connect(db_path)
    try:
        laps = fetch_laps(connection)
    finally:
        connection.close()

    print(f"{'Enregistré (UTC)':<19}  {'Voiture':<24}  {'Session':>7}  {'Tour':>4}  {'Temps':>10}  {'Valide':<6}  Incidents")
    print("-" * 100)
    for lap in laps:
        time_text = format_lap_time(lap.lap_time_ms / 1000) + ("" if lap.time_is_official else "*")
        print(
            f"{lap.recorded_at:<19}  {lap.car_name:<24}  {lap.session_num:>7}  {lap.lap_num:>4}  "
            f"{time_text:>10}  {'oui' if lap.is_valid else 'non':<6}  {lap.incidents:>9}"
        )
    print("-" * 100)
    print("* temps mesuré entre deux passages de ligne (indicatif)")
    print(f"{len(laps)} tours dans {db_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
