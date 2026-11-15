"""Affiche les tours enregistrés en base (requête SQL, sans lire aucun .ibt).

La connexion à la base est lue dans la variable d'environnement RACEBOARD_DATABASE_URL.

Usage :
    py -m raceboard.show_laps
"""

import sys

from raceboard.db import ConfigError, DatabaseError, database_label, fetch_laps, open_existing_database
from raceboard.extract_laps import format_lap_time


def main() -> int:
    try:
        connection = open_existing_database()
    except (ConfigError, DatabaseError) as error:
        print(error, file=sys.stderr)
        return 1

    try:
        laps = fetch_laps(connection)
        database = database_label(connection)
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
    print(f"{len(laps)} tours dans la base {database}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
