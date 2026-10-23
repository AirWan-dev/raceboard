"""Page Streamlit du dashboard : temps au tour lus en base, jamais dans les fichiers .ibt.

Ne se lance pas directement : utiliser py -m raceboard.dashboard (voir dashboard.py),
qui exécute ce fichier avec Streamlit. La base est ouverte en lecture seule (RACEBOARD_DB_PATH).
"""

import streamlit as st

from raceboard.db import (
    ConfigError,
    StoredLap,
    StoredSession,
    connect,
    fetch_session_laps,
    fetch_sessions,
    get_db_path,
)
from raceboard.extract_laps import format_lap_time


def session_label(session: StoredSession) -> str:
    """Libellé d'une session dans la liste de choix, ex. « 2026-09-26 19:41 · McLaren … · 7 tours »."""
    track = f"{session.track_name} ({session.track_config})" if session.track_config else session.track_name
    recorded_at = session.recorded_at[:16]  # à la minute près
    return f"{recorded_at} · {session.car_name} · {track} · {session.session_type} · {session.lap_count} tours"


def best_lap_text(session: StoredSession) -> str:
    if session.best_valid_lap_ms is None:
        return "aucun"
    return format_lap_time(session.best_valid_lap_ms / 1000)


def lap_rows(laps: list[StoredLap]) -> list[dict]:
    """Lignes du tableau des tours."""
    return [
        {
            "Tour": lap.lap_num,
            "Temps": format_lap_time(lap.lap_time_ms / 1000) + ("" if lap.time_is_official else "*"),
            "Valide": "oui" if lap.is_valid else "non",
            "Incidents": lap.incidents,
        }
        for lap in laps
    ]


def render() -> None:
    st.set_page_config(page_title="RaceBoard", layout="wide")
    st.title("RaceBoard — temps au tour")

    try:
        db_path = get_db_path()
    except ConfigError as error:
        st.error(str(error))
        st.stop()
    if not db_path.is_file():
        st.error(f"Base introuvable : {db_path}")
        st.stop()

    connection = connect(db_path, read_only=True)
    try:
        all_sessions = fetch_sessions(connection)
        sessions = {session.id: session for session in all_sessions if session.lap_count > 0}
        if not sessions:
            st.info("Aucune session avec des tours terminés dans la base.")
            st.stop()
        session_id = st.selectbox(
            "Session (tape pour filtrer, ex. « McLaren » ou « Fuji »)",
            options=list(sessions),
            format_func=lambda option: session_label(sessions[option]),
        )
        session = sessions[session_id]
        laps = fetch_session_laps(connection, session_id)
    finally:
        connection.close()

    hidden = len(all_sessions) - len(sessions)
    st.caption(f"{len(sessions)} sessions avec des tours, {hidden} sessions sans tour terminé masquées · base {db_path.name}")

    laps_column, valid_column, best_column = st.columns(3)
    laps_column.metric("Tours", session.lap_count)
    valid_column.metric("Valides", session.valid_lap_count)
    best_column.metric("Meilleur tour valide", best_lap_text(session))

    st.dataframe(lap_rows(laps), hide_index=True)
    st.caption("* temps mesuré entre deux passages de ligne (indicatif) : iRacing n'a pas chronométré ce tour")


# Streamlit exécute ce fichier sous le nom « __main__ » ; un simple import (tests) n'affiche rien.
if __name__ == "__main__":
    render()
