"""Tests de la commande quarantine (list / remove), sur la base PostgreSQL de test."""

import sys
from datetime import UTC, datetime

import pytest

from raceboard import quarantine
from raceboard.db import add_to_quarantine, quarantined_files

PORSCHE = "porsche992rgt3_miami gp 2025-12-19 20-57-27.ibt"
FERRARI = "ferrari296gt3_spielberg gp 2026-10-10 17-13-21.ibt"


@pytest.fixture
def two_files_in_quarantine(connection):
    """Base de test avec deux fichiers en quarantaine."""
    ferrari_rejected = datetime(2026, 10, 10, 15, 13, 31, tzinfo=UTC)
    porsche_rejected = datetime(2026, 10, 10, 15, 13, 30, tzinfo=UTC)
    add_to_quarantine(connection, FERRARI, "PermissionError: fichier verrouillé", ferrari_rejected)
    add_to_quarantine(connection, PORSCHE, "ValueError: aucune donnée", porsche_rejected)


def run_command(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["quarantine", *args])
    return quarantine.main()


def test_list(monkeypatch, capsys, two_files_in_quarantine):
    assert run_command(monkeypatch, "list") == 0
    assert capsys.readouterr().out.splitlines() == [
        f"2026-10-10 15:13:30  {PORSCHE}",
        "                     ValueError: aucune donnée",
        f"2026-10-10 15:13:31  {FERRARI}",
        "                     PermissionError: fichier verrouillé",
        "2 fichiers en quarantaine (dates en UTC)",
    ]


def test_list_empty(monkeypatch, capsys, connection):
    assert run_command(monkeypatch, "list") == 0
    assert capsys.readouterr().out == "Aucun fichier en quarantaine\n"


def test_remove_by_file_name(monkeypatch, capsys, connection, two_files_in_quarantine):
    assert run_command(monkeypatch, "remove", FERRARI) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"Retiré de la quarantaine : {FERRARI}",
        "Le worker le retraitera à son prochain passage.",
    ]
    assert quarantined_files(connection) == {PORSCHE}


def test_remove_by_full_path(monkeypatch, tmp_path, connection, two_files_in_quarantine):
    full_path = tmp_path / "iRacing" / "telemetry" / FERRARI  # le fichier n'a pas besoin d'exister
    assert run_command(monkeypatch, "remove", str(full_path)) == 0
    assert quarantined_files(connection) == {PORSCHE}


def test_remove_unknown_file(monkeypatch, capsys, connection, two_files_in_quarantine):
    assert run_command(monkeypatch, "remove", "inconnu.ibt") == 1
    assert capsys.readouterr().err.splitlines() == [
        "Pas en quarantaine : inconnu.ibt",
        "Liste des fichiers en quarantaine : py -m raceboard.quarantine list",
    ]
    assert quarantined_files(connection) == {PORSCHE, FERRARI}


def test_without_database_variable(monkeypatch, capsys):
    monkeypatch.delenv("RACEBOARD_DATABASE_URL", raising=False)
    assert run_command(monkeypatch, "list") == 1
    assert "RACEBOARD_DATABASE_URL" in capsys.readouterr().err


def test_missing_database(monkeypatch, capsys, missing_database_url):
    monkeypatch.setenv("RACEBOARD_DATABASE_URL", missing_database_url)
    assert run_command(monkeypatch, "list") == 1
    assert capsys.readouterr().err.startswith("Connexion à la base impossible : ")


def test_database_not_initialized(monkeypatch, capsys, database_url, db_label):
    assert run_command(monkeypatch, "list") == 1
    assert capsys.readouterr().err == f"Base {db_label} pas encore initialisée : le worker n'y a encore jamais tourné\n"


def test_subcommand_is_required(monkeypatch):
    with pytest.raises(SystemExit):  # argparse affiche l'usage et sort en erreur
        run_command(monkeypatch)
