"""Tests du worker d'ingestion (lecture des .ibt remplacée par des données synthétiques)."""

from datetime import UTC, datetime

import pytest

from raceboard import worker
from raceboard.db import ConfigError, count_rows, quarantined_files
from raceboard.extract_laps import Lap
from raceboard.import_ibt import IbtContent
from raceboard.worker import get_telemetry_dir, run_worker


@pytest.fixture
def telemetry_dir(tmp_path, monkeypatch, ibt_info):
    """Dossier contenant 3 faux .ibt et un fichier d'un autre format.

    « casse.ibt » est illisible ; les autres donnent 2 tours chacun.
    """
    folder = tmp_path / "telemetry"
    folder.mkdir()
    for name in ["a.ibt", "b.ibt", "casse.ibt", "notes.ld"]:
        (folder / name).touch()

    def fake_read_ibt(path):
        if path.name == "casse.ibt":
            raise ValueError("fichier illisible")
        return IbtContent(ibt_info, [0], [Lap(0, 1, 100.0, True, True, 0), Lap(0, 2, 99.0, True, True, 0)])

    monkeypatch.setattr(worker, "read_ibt", fake_read_ibt)
    return folder


def test_get_telemetry_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("RACEBOARD_TELEMETRY_DIR", str(tmp_path))
    assert get_telemetry_dir() == tmp_path


def test_get_telemetry_dir_without_variable(monkeypatch):
    monkeypatch.delenv("RACEBOARD_TELEMETRY_DIR", raising=False)
    with pytest.raises(ConfigError, match="RACEBOARD_TELEMETRY_DIR"):
        get_telemetry_dir()


def test_get_telemetry_dir_missing_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("RACEBOARD_TELEMETRY_DIR", str(tmp_path / "absent"))
    with pytest.raises(ConfigError, match="Dossier des .ibt introuvable"):
        get_telemetry_dir()


def test_worker_imports_files_and_isolates_errors(connection, telemetry_dir):
    report = run_worker(connection, telemetry_dir)

    assert report.found == 3  # notes.ld est ignoré
    assert report.imported == ["a.ibt", "b.ibt"]
    assert report.skipped == 0
    assert report.errors == [("casse.ibt", "ValueError: fichier illisible")]
    assert count_rows(connection) == (2, 4)


def test_second_run_adds_nothing(connection, telemetry_dir):
    run_worker(connection, telemetry_dir)
    rows_after_first_run = count_rows(connection)

    report = run_worker(connection, telemetry_dir)

    assert count_rows(connection) == rows_after_first_run
    assert report.imported == []
    assert report.skipped == 2
    # ADR 0005 : casse.ibt est en quarantaine depuis le 1er passage, il n'est plus retraité.
    assert report.quarantined == 1
    assert report.errors == []
    assert quarantined_files(connection) == {"casse.ibt"}


def test_new_file_is_imported_on_next_run(connection, telemetry_dir):
    run_worker(connection, telemetry_dir)
    (telemetry_dir / "c.ibt").touch()

    report = run_worker(connection, telemetry_dir)

    assert report.imported == ["c.ibt"]
    assert count_rows(connection) == (3, 6)


def test_main_output_and_exit_code(monkeypatch, capsys, tmp_path, telemetry_dir):
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(tmp_path / "raceboard.db"))
    monkeypatch.setenv("RACEBOARD_TELEMETRY_DIR", str(telemetry_dir))

    assert worker.main() == 1  # un fichier en erreur
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "importé  a.ibt : 2 tours",
        "importé  b.ibt : 2 tours",
        "3 fichiers .ibt : 2 importés, 0 déjà en base, 1 mis en quarantaine, 0 déjà en quarantaine",
        "Base raceboard.db : 2 sessions, 4 tours, 1 fichiers en quarantaine",
    ]
    assert captured.err == "ERREUR   casse.ibt : ValueError: fichier illisible\n"


def test_main_second_run_returns_0_with_known_quarantine(monkeypatch, capsys, tmp_path, telemetry_dir):
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(tmp_path / "raceboard.db"))
    monkeypatch.setenv("RACEBOARD_TELEMETRY_DIR", str(telemetry_dir))
    worker.main()
    capsys.readouterr()

    assert worker.main() == 0  # aucun nouvel échec : le fichier en quarantaine est un problème connu
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "3 fichiers .ibt : 0 importés, 2 déjà en base, 0 mis en quarantaine, 1 déjà en quarantaine",
        "Base raceboard.db : 2 sessions, 4 tours, 1 fichiers en quarantaine",
    ]
    assert captured.err == ""


def test_failed_file_is_put_in_quarantine(connection, telemetry_dir):
    before = datetime.now(UTC).replace(microsecond=0)
    run_worker(connection, telemetry_dir)

    rows = connection.execute("SELECT source_file, error_message, rejected_at FROM quarantine").fetchall()
    assert len(rows) == 1
    source_file, error_message, rejected_at = rows[0]
    assert (source_file, error_message) == ("casse.ibt", "ValueError: fichier illisible")
    rejected = datetime.strptime(rejected_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    assert before <= rejected <= datetime.now(UTC)
    # Le worker ne supprime ni ne déplace jamais un fichier source.
    assert (telemetry_dir / "casse.ibt").is_file()


def test_file_removed_from_quarantine_is_retried(connection, telemetry_dir):
    run_worker(connection, telemetry_dir)
    with connection:
        connection.execute("DELETE FROM quarantine WHERE source_file = 'casse.ibt'")

    report = run_worker(connection, telemetry_dir)

    assert report.quarantined == 0
    assert [name for name, _ in report.errors] == ["casse.ibt"]  # retenté, de nouveau en quarantaine
    assert quarantined_files(connection) == {"casse.ibt"}


def test_main_without_configuration(monkeypatch, capsys):
    monkeypatch.delenv("RACEBOARD_DB_PATH", raising=False)
    assert worker.main() == 1
    assert "RACEBOARD_DB_PATH" in capsys.readouterr().err
