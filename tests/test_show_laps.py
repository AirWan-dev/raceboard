"""Tests de l'affichage des tours lus en base."""

from raceboard import show_laps
from raceboard.db import save_session


def test_show_laps_output(capsys, connection, db_label, ibt_info, sample_laps):
    with connection.transaction():
        save_session(connection, "session.ibt", 0, ibt_info, sample_laps)

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
        f"4 tours dans la base {db_label}",
    ]


def test_show_laps_with_missing_database(monkeypatch, capsys, missing_database_url):
    monkeypatch.setenv("RACEBOARD_DATABASE_URL", missing_database_url)
    assert show_laps.main() == 1
    assert capsys.readouterr().err.startswith("Connexion à la base impossible : ")


def test_show_laps_before_first_worker_run(capsys, database_url, db_label):
    assert show_laps.main() == 1
    assert capsys.readouterr().err == f"Base {db_label} pas encore initialisée : le worker n'y a encore jamais tourné\n"
