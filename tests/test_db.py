"""Tests de l'accès à la base, sur la base PostgreSQL de test (voir conftest.py)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from urllib.parse import urlsplit

import pytest
from psycopg.errors import ReadOnlySqlTransaction

from raceboard.db import (
    ConfigError,
    DatabaseError,
    IntegrityError,
    add_to_quarantine,
    count_rows,
    connect,
    create_schema,
    database_label,
    fetch_laps,
    fetch_quarantine,
    fetch_session_laps,
    fetch_sessions,
    get_database_url,
    imported_files,
    open_existing_database,
    quarantined_files,
    remove_from_quarantine,
    save_session,
    schema_exists,
)


def test_get_database_url_reads_environment_variable(monkeypatch):
    url = "postgresql://raceboard:MotDePasse@postgres:5432/raceboard"
    monkeypatch.setenv("RACEBOARD_DATABASE_URL", url)
    assert get_database_url() == url


def test_get_database_url_without_variable(monkeypatch):
    monkeypatch.delenv("RACEBOARD_DATABASE_URL", raising=False)
    with pytest.raises(ConfigError, match="RACEBOARD_DATABASE_URL"):
        get_database_url()


def test_get_database_url_rejects_sqlite_path(monkeypatch):
    monkeypatch.setenv("RACEBOARD_DATABASE_URL", "/data/raceboard.db")  # ancienne valeur de RACEBOARD_DB_PATH
    with pytest.raises(ConfigError, match="format attendu postgresql://"):
        get_database_url()


@pytest.mark.parametrize(
    "password",
    [
        "Mot%zzDePasse",  # encodage invalide : le message du pilote citerait ce morceau du mot de passe
        "Mot@DePasse",    # @ non encodé : « DePasse@postgres » serait pris pour le serveur
        "Mot/DePasse",    # / non encodé : « DePasse@postgres/raceboard » serait pris pour la base
    ],
)
def test_invalid_url_message_does_not_show_password(monkeypatch, password):
    monkeypatch.setenv("RACEBOARD_DATABASE_URL", f"postgresql://raceboard:{password}@postgres:5432/raceboard")
    with pytest.raises(ConfigError, match="RACEBOARD_DATABASE_URL invalide") as error:
        get_database_url()
    assert "Mot" not in str(error.value) and "DePasse" not in str(error.value)


def test_encoded_special_characters_are_accepted(monkeypatch):
    url = "postgresql://raceboard:Mot%40De%2FPasse@postgres:5432/raceboard"  # mot de passe Mot@De/Passe
    monkeypatch.setenv("RACEBOARD_DATABASE_URL", url)
    assert get_database_url() == url


def test_connect_to_missing_database(missing_database_url):
    with pytest.raises(DatabaseError, match="^Connexion à la base impossible : ") as error:
        connect(missing_database_url)
    # Ni l'URL, ni « utilisateur:mot de passe@ ». On ne cherche pas le mot de passe seul : celui de
    # test peut être un mot courant, présent ailleurs dans le message (ex. « test » dans le nom de la base).
    url = urlsplit(missing_database_url)
    assert missing_database_url not in str(error.value)
    assert f"{url.username}:{url.password}@" not in str(error.value)


def test_database_label(database_url):
    connection = connect(database_url)
    try:
        label = database_label(connection)
    finally:
        connection.close()
    url = urlsplit(database_url)
    assert label == f"{url.path[1:]} ({url.hostname}:{url.port or 5432})"  # ni utilisateur ni mot de passe


def test_schema_exists(database_url):
    connection = connect(database_url)  # base de test vide, sans tables
    try:
        assert schema_exists(connection) is False
        create_schema(connection)
        assert schema_exists(connection) is True
    finally:
        connection.close()


def test_open_existing_database_without_tables(database_url, db_label):
    with pytest.raises(DatabaseError) as error:
        open_existing_database()
    assert str(error.value) == f"Base {db_label} pas encore initialisée : le worker n'y a encore jamais tourné"


def test_create_schema_can_run_twice(connection):
    create_schema(connection)
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = CURRENT_SCHEMA"
        )
    }
    assert {"sessions", "laps", "quarantine"} <= tables


def test_saved_laps_are_returned_by_query(connection, ibt_info, sample_laps):
    with connection.transaction():
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
    with connection.transaction():
        session_id = save_session(connection, "session.ibt", 0, ibt_info, [])

    row = connection.execute(
        "SELECT source_file, session_num, session_type, track_name, track_config, car_name, recorded_at "
        "FROM sessions WHERE id = %s",
        (session_id,),
    ).fetchone()
    assert row == (
        "session.ibt", 0, "Offline Testing", "Fuji Speedway", "Grand Prix", "McLaren 720S GT3 EVO",
        datetime(2026, 9, 26, 19, 41, 2),  # PostgreSQL renvoie une vraie date (UTC, sans fuseau)
    )


def test_dates_are_stored_in_utc(connection, ibt_info):
    paris_summer_time = timezone(timedelta(hours=2))
    in_paris = replace(ibt_info, recorded_at=datetime(2026, 9, 26, 21, 41, 2, tzinfo=paris_summer_time))
    with connection.transaction():
        save_session(connection, "session.ibt", 0, in_paris, [])
    assert fetch_sessions(connection)[0].recorded_at == "2026-09-26 19:41:02"


def test_unknown_session_type(connection, ibt_info):
    with connection.transaction():
        save_session(connection, "session.ibt", 3, ibt_info, [])
    assert connection.execute("SELECT session_type FROM sessions").fetchone() == ("inconnu",)


def test_same_session_cannot_be_saved_twice(connection, ibt_info, sample_laps):
    with connection.transaction():
        save_session(connection, "session.ibt", 0, ibt_info, sample_laps)
    with pytest.raises(IntegrityError):
        with connection.transaction():
            save_session(connection, "session.ibt", 0, ibt_info, sample_laps)
    assert len(fetch_laps(connection)) == len(sample_laps)


def test_lap_requires_existing_session(connection):
    with pytest.raises(IntegrityError):
        with connection.transaction():
            connection.execute(
                "INSERT INTO laps (session_id, lap_num, lap_time_ms, time_is_official, is_valid, incidents) "
                "VALUES (999, 1, 100000, TRUE, TRUE, 0)"
            )


def test_imported_files_and_row_counts(connection, ibt_info, sample_laps):
    assert imported_files(connection) == set()
    assert count_rows(connection) == (0, 0)

    with connection.transaction():
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
        ("vide.ibt", "ValueError: vide", datetime(2026, 10, 10, 20, 30, 0)),  # vraie date, UTC sans fuseau
    ]
    # La quarantaine ne compte ni comme session ni comme tour.
    assert imported_files(connection) == set()
    assert count_rows(connection) == (0, 0)


def test_same_file_cannot_be_quarantined_twice(connection):
    rejected_at = datetime(2026, 10, 10, tzinfo=UTC)
    add_to_quarantine(connection, "vide.ibt", "ValueError: vide", rejected_at)
    with pytest.raises(IntegrityError):
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
    with connection.transaction():
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
    with connection.transaction():
        first = save_session(connection, "a.ibt", 0, ibt_info, sample_laps)
        second = save_session(connection, "b.ibt", 0, ibt_info, sample_laps[:2])

    assert [lap.lap_num for lap in fetch_session_laps(connection, first)] == [0, 1, 2, 3]
    assert [(lap.lap_num, lap.lap_time_ms) for lap in fetch_session_laps(connection, second)] == [
        (0, 128300),
        (1, 101395),
    ]
    assert fetch_session_laps(connection, 999) == []


def test_read_only_connection(connection, database_url, ibt_info):
    with connection.transaction():
        save_session(connection, "a.ibt", 0, ibt_info, [])

    read_only = connect(database_url, read_only=True)
    try:
        assert len(fetch_sessions(read_only)) == 1
        with pytest.raises(ReadOnlySqlTransaction):
            read_only.execute("DELETE FROM sessions")
        assert len(fetch_sessions(read_only)) == 1
    finally:
        read_only.close()
