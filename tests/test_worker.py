"""Tests du worker d'ingestion (lecture des .ibt remplacée par des données synthétiques)."""

import os
import sys
import time
from datetime import UTC, datetime

import pytest

from raceboard import quarantine, worker
from raceboard.db import ConfigError, count_rows, quarantined_files
from raceboard.extract_laps import Lap
from raceboard.import_ibt import IbtContent
from raceboard.worker import get_guard_minutes, get_telemetry_dir, run_worker


def make_finished_file(path):
    """Crée un faux .ibt modifié il y a une heure : un enregistrement terminé (ADR 0006)."""
    path.touch()
    one_hour_ago = time.time() - 3600
    os.utime(path, (one_hour_ago, one_hour_ago))


@pytest.fixture
def telemetry_dir(tmp_path, monkeypatch, ibt_info):
    """Dossier contenant 3 faux .ibt terminés et un fichier d'un autre format.

    « casse.ibt » est illisible ; les autres donnent 2 tours chacun.
    """
    folder = tmp_path / "telemetry"
    folder.mkdir()
    for name in ["a.ibt", "b.ibt", "casse.ibt", "notes.ld"]:
        make_finished_file(folder / name)

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
    make_finished_file(telemetry_dir / "c.ibt")

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
        "3 fichiers .ibt : 2 importés, 0 déjà en base, 1 mis en quarantaine, "
        "0 déjà en quarantaine, 0 en cours d'écriture",
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
        "3 fichiers .ibt : 0 importés, 2 déjà en base, 0 mis en quarantaine, "
        "1 déjà en quarantaine, 0 en cours d'écriture",
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


# --- ADR 0006 : fichiers en cours d'écriture ---------------------------------------------------


def test_guard_minutes_default(monkeypatch):
    monkeypatch.delenv("RACEBOARD_FILE_GUARD_MINUTES", raising=False)
    assert get_guard_minutes() == 15


@pytest.mark.parametrize("value, expected", [("0", 0), ("30", 30)])
def test_guard_minutes_from_variable(monkeypatch, value, expected):
    monkeypatch.setenv("RACEBOARD_FILE_GUARD_MINUTES", value)
    assert get_guard_minutes() == expected


@pytest.mark.parametrize("value", ["abc", "-1", "1.5"])
def test_guard_minutes_invalid(monkeypatch, value):
    monkeypatch.setenv("RACEBOARD_FILE_GUARD_MINUTES", value)
    with pytest.raises(ConfigError, match="RACEBOARD_FILE_GUARD_MINUTES"):
        get_guard_minutes()


def test_recent_file_is_left_aside_then_imported_later(connection, telemetry_dir):
    recent = telemetry_dir / "en_cours.ibt"
    recent.touch()  # modifié à l'instant : iRacing est peut-être encore en train d'écrire

    report = run_worker(connection, telemetry_dir, guard_minutes=15)

    assert report.pending == [("en_cours.ibt", "modifié il y a moins de 15 min")]
    assert report.imported == ["a.ibt", "b.ibt"]
    assert quarantined_files(connection) == {"casse.ibt"}  # le fichier récent n'y est pas

    # Plus tard, le fichier n'est plus modifié depuis plus de 15 minutes : il est importé.
    make_finished_file(recent)
    report = run_worker(connection, telemetry_dir, guard_minutes=15)

    assert report.imported == ["en_cours.ibt"]
    assert report.pending == []


def test_zero_guard_imports_recent_file(connection, telemetry_dir):
    (telemetry_dir / "en_cours.ibt").touch()

    report = run_worker(connection, telemetry_dir, guard_minutes=0)

    assert report.imported == ["a.ibt", "b.ibt", "en_cours.ibt"]
    assert report.pending == []


def test_locked_file_is_left_aside_without_quarantine(connection, telemetry_dir, monkeypatch):
    make_finished_file(telemetry_dir / "verrou.ibt")
    read_unlocked_file = worker.read_ibt

    def read_ibt_with_lock(path):
        if path.name == "verrou.ibt":
            raise PermissionError(13, "Permission denied", str(path))
        return read_unlocked_file(path)

    monkeypatch.setattr(worker, "read_ibt", read_ibt_with_lock)

    report = run_worker(connection, telemetry_dir)

    assert report.pending == [("verrou.ibt", "fichier verrouillé")]
    assert quarantined_files(connection) == {"casse.ibt"}
    # Pas en quarantaine : il est retenté au passage suivant.
    assert run_worker(connection, telemetry_dir).pending == [("verrou.ibt", "fichier verrouillé")]


def test_main_recent_file_returns_0(monkeypatch, capsys, tmp_path, telemetry_dir):
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(tmp_path / "raceboard.db"))
    monkeypatch.setenv("RACEBOARD_TELEMETRY_DIR", str(telemetry_dir))
    monkeypatch.delenv("RACEBOARD_FILE_GUARD_MINUTES", raising=False)
    worker.main()  # 1er passage : casse.ibt part en quarantaine
    capsys.readouterr()
    (telemetry_dir / "en_cours.ibt").touch()

    assert worker.main() == 0
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "en attente  en_cours.ibt : modifié il y a moins de 15 min",
        "4 fichiers .ibt : 0 importés, 2 déjà en base, 0 mis en quarantaine, "
        "1 déjà en quarantaine, 1 en cours d'écriture",
        "Base raceboard.db : 2 sessions, 4 tours, 1 fichiers en quarantaine",
    ]
    assert captured.err == ""


def test_main_with_invalid_guard(monkeypatch, capsys, tmp_path, telemetry_dir):
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(tmp_path / "raceboard.db"))
    monkeypatch.setenv("RACEBOARD_TELEMETRY_DIR", str(telemetry_dir))
    monkeypatch.setenv("RACEBOARD_FILE_GUARD_MINUTES", "quinze")

    assert worker.main() == 1
    assert "RACEBOARD_FILE_GUARD_MINUTES" in capsys.readouterr().err


def test_file_removed_with_quarantine_command_is_imported(monkeypatch, capsys, tmp_path, telemetry_dir, ibt_info):
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(tmp_path / "raceboard.db"))
    monkeypatch.setenv("RACEBOARD_TELEMETRY_DIR", str(telemetry_dir))
    assert worker.main() == 1  # casse.ibt part en quarantaine

    # Le fichier est en fait sain (cas du fichier Ferrari rejeté avant l'ADR 0006).
    monkeypatch.setattr(worker, "read_ibt", lambda path: IbtContent(ibt_info, [0], [Lap(0, 1, 100.0, True, True, 0)]))
    monkeypatch.setattr(sys, "argv", ["quarantine", "remove", str(telemetry_dir / "casse.ibt")])
    assert quarantine.main() == 0
    capsys.readouterr()

    assert worker.main() == 0
    output = capsys.readouterr().out.splitlines()
    assert output[0] == "importé  casse.ibt : 1 tours"
    assert output[-1] == "Base raceboard.db : 3 sessions, 5 tours, 0 fichiers en quarantaine"
