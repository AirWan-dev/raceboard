"""Liste les variables (canaux de télémétrie) disponibles dans un fichier .ibt.

Usage :
    py -m raceboard.list_ibt_vars "C:/chemin/vers/session.ibt"
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import irsdk


@dataclass
class IbtVariable:
    name: str
    unit: str
    count: int  # nombre de valeurs par échantillon (> 1 pour un tableau, ex. une valeur par voiture)
    description: str


def list_variables(ibt_path: Path) -> list[IbtVariable]:
    """Ouvre le fichier .ibt et renvoie ses variables, dans l'ordre du fichier."""
    ibt = irsdk.IBT()
    ibt.open(str(ibt_path))
    try:
        # pyirsdk n'expose publiquement que les noms ; unité et description
        # sont lues dans _var_headers (version de pyirsdk figée dans requirements.txt).
        return [
            IbtVariable(
                name=header.name,
                unit=header.unit,
                count=header.count,
                description=header.desc,
            )
            for header in ibt._var_headers
        ]
    finally:
        ibt.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Liste les variables d'un fichier .ibt iRacing.")
    parser.add_argument("ibt_path", type=Path, help="chemin du fichier .ibt")
    args = parser.parse_args()

    if not args.ibt_path.is_file():
        print(f"Fichier introuvable : {args.ibt_path}", file=sys.stderr)
        return 1

    variables = list_variables(args.ibt_path)

    print(f"{'Variable':<32} {'Unité':<20} {'Nb':>4}  Description")
    print("-" * 110)
    for var in variables:
        print(f"{var.name:<32} {var.unit:<20} {var.count:>4}  {var.description}")
    print("-" * 110)
    print(f"{len(variables)} variables dans {args.ibt_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
