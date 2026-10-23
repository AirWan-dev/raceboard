"""Tests de l'accès à la base, sur une base SQLite temporaire."""

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from raceboard.db import (
    ConfigError,
    add_to_quarantine,
    count_rows,
    connect,
    create_schema,
    fetch_laps,
    fetch_quarantine,
    fetch_session_laps,
    fetch_sessions,
    get_db_path,
    imported_files,
    quarantined_files,
    remove_from_quarantine,
    save_session,
)


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


def test_quarantine(connection):
    assert quarantined_files(connection) == set()

    add_to_quarantine(connection, "vide.ibt", "ValueError: vide", datetime(2026, 10, 10, 20, 30, 0, tzinfo=UTC))

    assert quarantined_files(connection) == {"vide.ibt"}
    assert connection.execute("SELECT source_file, error_message, rejected_at FROM quarantine").fetchall() == [
        ("vide.ibt", "ValueError: vide", "2026-10-10 20:30:00"),
    ]
    # La quarantaine ne compte ni comme session ni comme tour.
    assert imported_files(connection) == set()
    assert count_rows(connection) == (0, 0)


def test_same_file_cannot_be_quarantined_twice(connection):
    rejected_at = datetime(2026, 10, 10, tzinfo=UTC)
    add_to_quarantine(connection, "vide.ibt", "ValueError: vide", rejected_at)
    with pytest.raises(sqlite3.IntegrityError):
        add_to_quarantine(connection, "vide.ibt", "ValueError: vide", rejected_at)


def test_fetch_and_remove_quarantine(connection):
    add_to_quarantine(connection, "b.ibt", "ValueError: b", datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC))
    add_to_quarantine(connection, "a.ibt", "ValueError: a", datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC))

    assert [(f.source_file, f.error_message, f.rejected_at) for f in fetch_quarantine(connection)] == [
        ("b.ibt", "ValueError: b", "2026-10-10 12:00:00"),  # du rejet le plus ancien au plus récent
        ("a.ibt", "ValueError: a", "2026-10-11 12:00:00"),
    ]

    assert remove_from_quarantine(connection, "b.ibt") is True
    assert remove_from_quarantine(connection, "b.ibt") is False  # déjà retiré
    assert remove_from_quarantine(connection, "inconnu.ibt") is False
    assert quarantined_files(connection) == {"a.ibt"}


def test_fetch_sessions(connection, ibt_info, sample_laps):
    older = replace(ibt_info, recorded_at=datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC))
    with connection:
        save_session(connection, "recent.ibt", 0, ibt_info, sample_laps)
        save_session(connection, "ancien.ibt", 0, older, sample_laps[:1])  # un seul tour, non valide
        save_session(connection, "vide.ibt", 1, older, [])

    sessions = fetch_sessions(connection)

    # De la plus récente à la plus ancienne ; une session sans tour donne 0, 0 et None.
    assert [(s.recorded_at, s.lap_count, s.valid_lap_count, s.best_valid_lap_ms) for s in sessions] == [
        ("2026-09-26 19:41:02", 4, 2, 98716),
        ("2026-09-01 10:00:00", 0, 0, None),
        ("2026-09-01 10:00:00", 1, 0, None),
    ]
    assert (sessions[0].car_name, sessions[0].track_name, sessions[0].track_config, sessions[0].session_type) == (
        "McLaren 720S GT3 EVO", "Fuji Speedway", "Grand Prix", "Offline Testing",
    )


def test_fetch_session_laps(connection, ibt_info, sample_laps):
    with connection:
        first = save_session(connection, "a.ibt", 0, ibt_info, sample_laps)
        second = save_session(connection, "b.ibt", 0, ibt_info, sample_laps[:2])

    assert [lap.lap_num for lap in fetch_session_laps(connection, first)] == [0, 1, 2, 3]
    assert [(lap.lap_num, lap.lap_time_ms) for lap in fetch_session_laps(connection, second)] == [
        (0, 128300),
        (1, 101395),
    ]
    assert fetch_session_laps(connection, 999) == []


def test_read_only_connection(tmp_path, ibt_info):
    path = tmp_path / "raceboard.db"
    connection = connect(path)
    create_schema(connection)
    with connection:
        save_session(connection, "a.ibt", 0, ibt_info, [])
    connection.close()

    read_only = connect(path, read_only=True)
    try:
        assert len(fetch_sessions(read_only)) == 1
        with pytest.raises(sqlite3.OperationalError):
            read_only.execute("DELETE FROM sessions")
    finally:
        read_only.close()


def test_read_only_connection_does_not_create_missing_database(tmp_path):
    missing = tmp_path / "absente.db"
    with pytest.raises(sqlite3.OperationalError):
        connect(missing, read_only=True)
    assert not missing.exists()
