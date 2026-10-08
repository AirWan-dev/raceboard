"""Tests de l'accès à la base, sur une base SQLite temporaire."""

import sqlite3

import pytest

from raceboard.db import ConfigError, count_rows, create_schema, fetch_laps, get_db_path, imported_files, save_session


def test_get_db_path_reads_environment_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(tmp_path / "raceboard.db"))
    assert get_db_path() == tmp_path / "raceboard.db"


def test_get_db_path_without_variable(monkeypatch):
    monkeypatch.delenv("RACEBOARD_DB_PATH", raising=False)
    with pytest.raises(ConfigError, match="RACEBOARD_DB_PATH"):
        get_db_path()


def test_get_db_path_with_missing_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(tmp_path / "absent" / "raceboard.db"))
    with pytest.raises(ConfigError, match="Dossier de la base introuvable"):
        get_db_path()


def test_create_schema_can_run_twice(connection):
    create_schema(connection)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"sessions", "laps"} <= tables


def test_saved_laps_are_returned_by_query(connection, ibt_info, sample_laps):
    with connection:
        save_session(connection, "session.ibt", 0, ibt_info, sample_laps)

    laps = fetch_laps(connection)

    assert [(lap.lap_num, lap.lap_time_ms, lap.time_is_official, lap.is_valid, lap.incidents) for lap in laps] == [
        (0, 128300, False, False, 4),
        (1, 101395, True, True, 0),
        (2, 98716, True, True, 0),
        (3, 102850, False, False, 1),
    ]
    assert {(lap.recorded_at, lap.car_name, lap.session_num, lap.session_type) for lap in laps} == {
        ("2026-09-26 19:41:02", "McLaren 720S GT3 EVO", 0, "Offline Testing"),
    }


def test_session_row_content(connection, ibt_info):
    with connection:
        session_id = save_session(connection, "session.ibt", 0, ibt_info, [])

    row = connection.execute(
        "SELECT source_file, session_num, session_type, track_name, track_config, car_name, recorded_at "
        "FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    assert row == (
        "session.ibt", 0, "Offline Testing", "Fuji Speedway", "Grand Prix", "McLaren 720S GT3 EVO", "2026-09-26 19:41:02",
    )


def test_unknown_session_type(connection, ibt_info):
    with connection:
        save_session(connection, "session.ibt", 3, ibt_info, [])
    assert connection.execute("SELECT session_type FROM sessions").fetchone() == ("inconnu",)


def test_same_session_cannot_be_saved_twice(connection, ibt_info, sample_laps):
    with connection:
        save_session(connection, "session.ibt", 0, ibt_info, sample_laps)
    with pytest.raises(sqlite3.IntegrityError):
        with connection:
            save_session(connection, "session.ibt", 0, ibt_info, sample_laps)
    assert len(fetch_laps(connection)) == len(sample_laps)


def test_lap_requires_existing_session(connection):
    with pytest.raises(sqlite3.IntegrityError):
        with connection:
            connection.execute(
                "INSERT INTO laps (session_id, lap_num, lap_time_ms, time_is_official, is_valid, incidents) "
                "VALUES (999, 1, 100000, TRUE, TRUE, 0)"
            )


def test_imported_files_and_row_counts(connection, ibt_info, sample_laps):
    assert imported_files(connection) == set()
    assert count_rows(connection) == (0, 0)

    with connection:
        save_session(connection, "a.ibt", 0, ibt_info, sample_laps)
        save_session(connection, "a.ibt", 1, ibt_info, [])
        save_session(connection, "b.ibt", 0, ibt_info, sample_laps[:1])

    assert imported_files(connection) == {"a.ibt", "b.ibt"}
    assert count_rows(connection) == (3, 5)
