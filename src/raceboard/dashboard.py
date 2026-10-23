"""Lance le dashboard Streamlit, puis l'ouvre sur http://localhost:8501.

La page (dashboard_page.py) lit uniquement la base, via la variable d'environnement
RACEBOARD_DB_PATH, jamais les fichiers .ibt. Ctrl+C dans le terminal arrête le serveur.

Usage :
    py -m raceboard.dashboard
"""

import sys
from pathlib import Path

from streamlit.web import cli as streamlit_cli

PORT = 8501
PAGE = Path(__file__).with_name("dashboard_page.py")


def streamlit_arguments() -> list[str]:
    """Équivalent de la commande « streamlit run » sur la page du dashboard."""
    return [
        "streamlit",
        "run",
        str(PAGE),
        "--server.port",
        str(PORT),
        # Par défaut, Streamlit envoie des statistiques d'usage à ses serveurs : désactivé.
        "--browser.gatherUsageStats",
        "false",
        # Au premier lancement, Streamlit demande un e-mail (envoyé à ses serveurs) : désactivé.
        "--server.showEmailPrompt",
        "false",
    ]


def main() -> None:
    sys.argv = streamlit_arguments()
    streamlit_cli.main()


if __name__ == "__main__":
    main()
