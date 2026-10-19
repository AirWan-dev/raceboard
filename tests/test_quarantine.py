"""Tests de la commande quarantine (list / remove), sur une base SQLite temporaire."""

import sys
from datetime import UTC, datetime

import pytest

from raceboard import quarantine
from raceboard.db import add_to_quarantine, connect, create_schema, quarantined_files

PORSCHE = "porsche992rgt3_miami gp 2025-12-19 20-57-27.ibt"
FERRARI = "ferrari296gt3_spielberg gp 2026-10-10 17-13-21.ibt"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Base temporaire avec deux fichiers en quarantaine."""
    path = tmp_path / "raceboard.db"
    connection = connect(path)
    create_schema(connection)
    ferrari_rejected = datetime(2026, 10, 10, 15, 13, 31, tzinfo=UTC)
    porsche_rejected = datetime(2026, 10, 10, 15, 13, 30, tzinfo=UTC)
    add_to_quarantine(connection, FERRARI, "PermissionError: fichier verrouillé", ferrari_rejected)
    add_to_quarantine(connection, PORSCHE, "ValueError: aucune donnée", porsche_rejected)
    connection.close()
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(path))
    return path


def run_command(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["quarantine", *args])
    return quarantine.main()


def files_in_quarantine(db_path):
    connection = connect(db_path)
    try:
        return quarantined_files(connection)
    finally:
        connection.close()


def test_list(monkeypatch, capsys, db_path):
    assert run_command(monkeypatch, "list") == 0
    assert capsys.readouterr().out.splitlines() == [
        f"2026-10-10 15:13:30  {PORSCHE}",
        "                     ValueError: aucune donnée",
        f"2026-10-10 15:13:31  {FERRARI}",
        "                     PermissionError: fichier verrouillé",
        "2 fichiers en quarantaine (dates en UTC)",
    ]


def test_list_empty(monkeypatch, capsys, tmp_path):
    path = tmp_path / "vide.db"
    connection = connect(path)
    create_schema(connection)
    connection.close()
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(path))

    assert run_command(monkeypatch, "list") == 0
    assert capsys.readouterr().out == "Aucun fichier en quarantaine\n"


def test_remove_by_file_name(monkeypatch, capsys, db_path):
    assert run_command(monkeypatch, "remove", FERRARI) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"Retiré de la quarantaine : {FERRARI}",
        "Le worker le retraitera à son prochain passage.",
    ]
    assert files_in_quarantine(db_path) == {PORSCHE}


def test_remove_by_full_path(monkeypatch, db_path, tmp_path):
    full_path = tmp_path / "iRacing" / "telemetry" / FERRARI  # le fichier n'a pas besoin d'exister
    assert run_command(monkeypatch, "remove", str(full_path)) == 0
    assert files_in_quarantine(db_path) == {PORSCHE}


def test_remove_unknown_file(monkeypatch, capsys, db_path):
    assert run_command(monkeypatch, "remove", "inconnu.ibt") == 1
    assert capsys.readouterr().err.splitlines() == [
        "Pas en quarantaine : inconnu.ibt",
        "Liste des fichiers en quarantaine : py -m raceboard.quarantine list",
    ]
    assert files_in_quarantine(db_path) == {PORSCHE, FERRARI}


def test_without_database_variable(monkeypatch, capsys):
    monkeypatch.delenv("RACEBOARD_DB_PATH", raising=False)
    assert run_command(monkeypatch, "list") == 1
    assert "RACEBOARD_DB_PATH" in capsys.readouterr().err


def test_database_file_missing(monkeypatch, capsys, tmp_path):
    missing = tmp_path / "absente.db"
    monkeypatch.setenv("RACEBOARD_DB_PATH", str(missing))
    assert run_command(monkeypatch, "list") == 1
    assert capsys.readouterr().err == f"Base introuvable : {missing}\n"


def test_subcommand_is_required(monkeypatch, db_path):
    with pytest.raises(SystemExit):  # argparse affiche l'usage et sort en erreur
        run_command(monkeypatch)
