"""Tests de l'affichage des tours lus en base."""

from raceboard import show_laps
from raceboard.db import connect, create_schema, save_session


def test_show_laps_output(monkeypatch, capsys, tmp_path, ibt_info, sample_laps):
    db_path = tmp_path / "test.db"
    connection = connect(db_path)
    create_schema(connection)
    with connection:
        save_session(connection, "session.ibt", 0, ibt_info, sample_laps)
    connection.close()
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(db_path))

    assert show_laps.main() == 0
    assert capsys.readouterr().out.splitlines() == [
        "Enregistré (UTC)     Voiture                   Session  Tour       Temps  Valide  Incidents",
        "-" * 100,
        "2026-09-26 19:41:02  McLaren 720S GT3 EVO            0     0   2:08.300*  non             4",
        "2026-09-26 19:41:02  McLaren 720S GT3 EVO            0     1    1:41.395  oui             0",
        "2026-09-26 19:41:02  McLaren 720S GT3 EVO            0     2    1:38.716  oui             0",
        "2026-09-26 19:41:02  McLaren 720S GT3 EVO            0     3   1:42.850*  non             1",
        "-" * 100,
        "* temps mesuré entre deux passages de ligne (indicatif)",
        "4 tours dans test.db",
    ]


def test_show_laps_without_database_file(monkeypatch, capsys, tmp_path):
    missing = tmp_path / "absent.db"
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(missing))
    assert show_laps.main() == 1
    assert capsys.readouterr().err == f"Base introuvable : {missing}\n"
