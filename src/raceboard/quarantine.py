"""Consulte la quarantaine du worker et en retire des fichiers (ADR 0005 et 0006).

Retirer un fichier de la quarantaine supprime seulement sa ligne en base : le fichier .ibt
n'est jamais touché, et le worker le retraitera à son prochain passage.

Le chemin de la base est lu dans la variable d'environnement RACEBOARD_DB_PATH.

Usage :
    py -m raceboard.quarantine list
    py -m raceboard.quarantine remove "<fichier>"   (nom du fichier ou chemin complet)
"""

import argparse
import sys
from pathlib import Path

from raceboard.db import ConfigError, connect, create_schema, fetch_quarantine, get_db_path, remove_from_quarantine


def main() -> int:
    parser = argparse.ArgumentParser(description="Quarantaine des fichiers .ibt rejetés par le worker.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="affiche les fichiers en quarantaine")
    remove_parser = commands.add_parser("remove", help="retire un fichier de la quarantaine")
    remove_parser.add_argument("file", help="nom du fichier .ibt, ou son chemin complet")
    args = parser.parse_args()

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
        create_schema(connection)  # base créée avant l'ADR 0005 : ajoute la table quarantine si besoin
        if args.command == "list":
            return list_quarantine(connection)
        return remove_file(connection, args.file)
    finally:
        connection.close()


def list_quarantine(connection) -> int:
    files = fetch_quarantine(connection)
    if not files:
        print("Aucun fichier en quarantaine")
        return 0
    for quarantined in files:
        print(f"{quarantined.rejected_at}  {quarantined.source_file}")
        print(f"                     {quarantined.error_message}")
    print(f"{len(files)} fichiers en quarantaine (dates en UTC)")
    return 0


def remove_file(connection, file: str) -> int:
    # Les fichiers sont identifiés par leur nom seul : on accepte aussi un chemin complet.
    file_name = Path(file).name
    if not remove_from_quarantine(connection, file_name):
        print(f"Pas en quarantaine : {file_name}", file=sys.stderr)
        print("Liste des fichiers en quarantaine : py -m raceboard.quarantine list", file=sys.stderr)
        return 1
    print(f"Retiré de la quarantaine : {file_name}")
    print("Le worker le retraitera à son prochain passage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
