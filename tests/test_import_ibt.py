"""Tests de l'enregistrement d'un .ibt en base (lecture du fichier remplacée par des données synthétiques)."""

import sqlite3
import sys

import pytest

from raceboard import import_ibt
from raceboard.db import fetch_laps
from raceboard.import_ibt import read_ibt, save_ibt

# Échantillons synthétiques : session, temps, tour, dernier temps iRacing, stands, incidents.
ROWS = [
    (0, 0.0, 0, 0.0, True, 0),
    (0, 60.0, 1, 0.0, False, 0),
    (0, 160.0, 2, 0.0, False, 0),
    (0, 160.5, 2, 100.123, False, 0),
    (0, 259.0, 3, 100.123, False, 0),
]
COLUMNS = ["SessionNum", "SessionTime", "Lap", "LapLastLapTime", "OnPitRoad", "PlayerCarMyIncidentCount"]


def fake_channels():
    channels = {name: [row[i] for row in ROWS] for i, name in enumerate(COLUMNS)}
    channels["LapBestLapTime"] = [0.0] * len(ROWS)
    return channels


@pytest.fixture
def fake_ibt(tmp_path, monkeypatch, ibt_info):
    """Un fichier .ibt factice : sa lecture renvoie les données synthétiques ci-dessus."""
    path = tmp_path / "session.ibt"
    path.touch()
    monkeypatch.setattr(import_ibt, "read_lap_channels", lambda p: fake_channels())
    monkeypatch.setattr(import_ibt, "read_ibt_info", lambda p: ibt_info)
    return path


def run_main(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["import_ibt", *args])
    return import_ibt.main()


def test_save_ibt_is_all_or_nothing(connection, ibt_info, sample_laps):
    # La session 0 apparaît deux fois : la seconde insertion échoue, la première est annulée.
    with pytest.raises(sqlite3.IntegrityError):
        save_ibt(connection, "session.ibt", ibt_info, [0, 0], sample_laps)
    assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone() == (0,)
    assert fetch_laps(connection) == []


def test_import_writes_laps(monkeypatch, capsys, tmp_path, fake_ibt):
    db_path = tmp_path / "raceboard.db"
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(db_path))

    assert run_main(monkeypatch, str(fake_ibt)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "session.ibt : McLaren 720S GT3 EVO, Fuji Speedway (Grand Prix)",
        "  session 0 (Offline Testing) : 3 tours enregistrés",
        f"Base : {db_path}",
    ]
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute("SELECT lap_num, lap_time_ms, is_valid FROM laps ORDER BY lap_num").fetchall()
    finally:
        connection.close()
    assert rows == [(0, 60000, 0), (1, 100123, 1), (2, 99000, 0)]


def test_second_import_of_same_file_is_refused(monkeypatch, capsys, tmp_path, fake_ibt):
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(tmp_path / "raceboard.db"))
    assert run_main(monkeypatch, str(fake_ibt)) == 0
    capsys.readouterr()

    assert run_main(monkeypatch, str(fake_ibt)) == 1
    assert "fichier déjà importé" in capsys.readouterr().err


def test_import_without_database_variable(monkeypatch, capsys, fake_ibt):
    monkeypatch.delenv("RACEBOARD_DB_PATH", raising=False)
    assert run_main(monkeypatch, str(fake_ibt)) == 1
    assert "RACEBOARD_DB_PATH" in capsys.readouterr().err


def test_import_missing_file(monkeypatch, capsys, tmp_path):
    missing = tmp_path / "absent.ibt"
    assert run_main(monkeypatch, str(missing)) == 1
    assert capsys.readouterr().err == f"Fichier introuvable : {missing}\n"


def test_read_ibt_without_telemetry(monkeypatch, tmp_path):
    empty_channels = {name: [] for name in COLUMNS + ["LapBestLapTime"]}
    monkeypatch.setattr(import_ibt, "read_lap_channels", lambda p: empty_channels)
    with pytest.raises(ValueError, match="Aucune donnée de télémétrie"):
        read_ibt(tmp_path / "vide.ibt")


def test_read_ibt(fake_ibt, ibt_info):
    content = read_ibt(fake_ibt)
    assert content.info == ibt_info
    assert content.session_nums == [0]
    assert [lap.lap_num for lap in content.laps] == [0, 1, 2]
