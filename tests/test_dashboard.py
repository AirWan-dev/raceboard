"""Tests du dashboard : fonctions de la page, lanceur, et page entière exécutée sans navigateur.

La page est exécutée avec l'outil de test de Streamlit (AppTest), sur une base synthétique.
"""

import sys
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.web import cli as streamlit_cli

from raceboard import dashboard, dashboard_page
from raceboard.dashboard_page import best_lap_text, lap_rows, session_label
from raceboard.db import StoredLap, StoredSession, connect, create_schema, save_session
from raceboard.extract_laps import Lap

MCLAREN_LABEL = "2026-09-26 19:41 · McLaren 720S GT3 EVO · Fuji Speedway (Grand Prix) · Offline Testing · 4 tours"
FERRARI_LABEL = "2026-10-01 19:52 · Ferrari 296 GT3 · Fuji Speedway (Grand Prix) · Practice · 1 tours"


def make_session(**changes):
    session = StoredSession(
        id=1,
        recorded_at="2026-09-26 19:41:02",
        car_name="McLaren 720S GT3 EVO",
        track_name="Fuji Speedway",
        track_config="Grand Prix",
        session_type="Offline Testing",
        lap_count=7,
        valid_lap_count=5,
        best_valid_lap_ms=98716,
    )
    return replace(session, **changes)


# --- Fonctions de la page -------------------------------------------------------------------


def test_session_label():
    assert session_label(make_session()) == (
        "2026-09-26 19:41 · McLaren 720S GT3 EVO · Fuji Speedway (Grand Prix) · Offline Testing · 7 tours"
    )


def test_session_label_track_without_configuration():
    session = make_session(track_name="Circuit des 24 Heures du Mans", track_config="")
    assert " · Circuit des 24 Heures du Mans · " in session_label(session)


def test_best_lap_text():
    assert best_lap_text(make_session()) == "1:38.716"
    assert best_lap_text(make_session(valid_lap_count=0, best_valid_lap_ms=None)) == "aucun"


def test_lap_rows():
    laps = [
        StoredLap("2026-09-26 19:41:02", "McLaren", 0, "Offline Testing", 0, 128300, False, False, 4),
        StoredLap("2026-09-26 19:41:02", "McLaren", 0, "Offline Testing", 1, 98716, True, True, 0),
    ]
    assert lap_rows(laps) == [
        {"Tour": 0, "Temps": "2:08.300*", "Valide": "non", "Incidents": 4},
        {"Tour": 1, "Temps": "1:38.716", "Valide": "oui", "Incidents": 0},
    ]


# --- Lanceur ----------------------------------------------------------------------------------


def test_launcher_arguments_are_accepted_by_streamlit():
    arguments = dashboard.streamlit_arguments()
    assert arguments[:2] == ["streamlit", "run"]

    # Streamlit analyse la commande « run » sans lancer le serveur : une option inconnue échouerait.
    params = streamlit_cli.main_run.make_context("run", arguments[2:]).params

    assert params["target"] == str(dashboard.PAGE)
    assert dashboard.PAGE.is_file()
    assert params["server_port"] == 8501
    assert params["browser_gatherUsageStats"] is False
    assert params["server_showEmailPrompt"] is False


def test_launcher_runs_streamlit(monkeypatch):
    calls = []
    monkeypatch.setattr(dashboard.streamlit_cli, "main", lambda: calls.append(list(sys.argv)))

    dashboard.main()

    assert calls == [dashboard.streamlit_arguments()]


# --- Page entière, exécutée sans navigateur ---------------------------------------------------


@pytest.fixture
def db_path(tmp_path, monkeypatch, ibt_info, sample_laps):
    """Base avec 3 sessions : McLaren (4 tours), Ferrari plus récente (1 tour), une session sans tour."""
    path = tmp_path / "raceboard.db"
    connection = connect(path)
    create_schema(connection)
    ferrari = replace(
        ibt_info,
        car_name="Ferrari 296 GT3",
        recorded_at=datetime(2026, 10, 1, 19, 52, 14, tzinfo=UTC),
        session_types={0: "Practice"},
    )
    with connection:
        save_session(connection, "mclaren.ibt", 0, ibt_info, sample_laps)
        save_session(connection, "ferrari.ibt", 0, ferrari, [Lap(0, 1, 99.0, True, False, 2)])
        save_session(connection, "vide.ibt", 0, ibt_info, [])
    connection.close()
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(path))
    return path


def run_page():
    return AppTest.from_file(dashboard_page.__file__, default_timeout=30).run()


def metrics(app):
    return {metric.label: metric.value for metric in app.metric}


def test_page_shows_most_recent_session_first(db_path):
    app = run_page()

    assert not app.exception
    assert app.title[0].value == "RaceBoard — temps au tour"
    assert app.selectbox[0].options == [FERRARI_LABEL, MCLAREN_LABEL]  # la session sans tour est masquée
    assert metrics(app) == {"Tours": "1", "Valides": "0", "Meilleur tour valide": "aucun"}
    assert app.caption[0].value == "2 sessions avec des tours, 1 sessions sans tour terminé masquées · base raceboard.db"


def test_page_shows_laps_of_selected_session(db_path):
    app = run_page()
    app = app.selectbox[0].select(MCLAREN_LABEL).run()

    assert metrics(app) == {"Tours": "4", "Valides": "2", "Meilleur tour valide": "1:38.716"}
    assert app.dataframe[0].value.to_dict("records") == [
        {"Tour": 0, "Temps": "2:08.300*", "Valide": "non", "Incidents": 4},
        {"Tour": 1, "Temps": "1:41.395", "Valide": "oui", "Incidents": 0},
        {"Tour": 2, "Temps": "1:38.716", "Valide": "oui", "Incidents": 0},
        {"Tour": 3, "Temps": "1:42.850*", "Valide": "non", "Incidents": 1},
    ]


def test_page_does_not_modify_database(db_path):
    content_before = db_path.read_bytes()
    app = run_page()
    app.selectbox[0].select(MCLAREN_LABEL).run()
    assert db_path.read_bytes() == content_before


def test_page_without_database_variable(monkeypatch):
    monkeypatch.delenv("RACEBOARD_DB_PATH", raising=False)
    app = run_page()
    assert "RACEBOARD_DB_PATH" in app.error[0].value
    assert not app.selectbox


def test_page_with_missing_database(monkeypatch, tmp_path):
    missing = tmp_path / "absente.db"
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(missing))

    app = run_page()

    assert app.error[0].value == f"Base introuvable : {missing}"
    assert not missing.exists()  # aucune base vide créée


def test_page_with_no_lap_in_database(monkeypatch, tmp_path, ibt_info):
    path = tmp_path / "sans_tour.db"
    connection = connect(path)
    create_schema(connection)
    with connection:
        save_session(connection, "vide.ibt", 0, ibt_info, [])
    connection.close()
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(path))

    app = run_page()

    assert app.info[0].value == "Aucune session avec des tours terminés dans la base."
    assert not app.selectbox
