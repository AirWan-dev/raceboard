"""Tests de la sortie console des deux scripts, sur données synthétiques (aucun vrai .ibt).

La lecture du fichier est remplacée par des données inventées (monkeypatch) : on vérifie
uniquement l'affichage, qui ne doit pas changer sans décision explicite.
"""

import sys

from raceboard import extract_laps, list_ibt_vars
from raceboard.list_ibt_vars import IbtVariable


def run_main(module, monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", [module.__name__, *args])
    return module.main()


def test_list_ibt_vars_output(monkeypatch, capsys, tmp_path):
    fake_ibt = tmp_path / "fake.ibt"
    fake_ibt.touch()
    variables = [
        IbtVariable("SessionTime", "s", 1, "Seconds since session start"),
        IbtVariable("SessionState", "irsdk_SessionState", 1, "Session state"),
        IbtVariable("SteeringWheelTorque_ST", "N*m", 6, "Output torque on steering shaft at 360 Hz"),
    ]
    monkeypatch.setattr(list_ibt_vars, "list_variables", lambda path: variables)

    assert run_main(list_ibt_vars, monkeypatch, str(fake_ibt)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Variable                         Unité                  Nb  Description",
        "-" * 110,
        "SessionTime                      s                       1  Seconds since session start",
        "SessionState                     irsdk_SessionState      1  Session state",
        "SteeringWheelTorque_ST           N*m                     6  Output torque on steering shaft at 360 Hz",
        "-" * 110,
        "3 variables dans fake.ibt",
    ]


def test_extract_laps_output(monkeypatch, capsys, tmp_path):
    fake_ibt = tmp_path / "fake.ibt"
    fake_ibt.touch()
    rows = [
        # session, temps, tour, dernier temps iRacing, stands, incidents
        (0, 0.0, 0, 0.0, True, 0),         # tour de sortie des stands
        (0, 60.0, 1, 0.0, False, 0),
        (0, 160.0, 2, 0.0, False, 0),
        (0, 160.5, 2, 100.123, False, 0),  # temps iRacing du tour 1
        (0, 259.0, 3, 100.123, False, 0),  # fin du fichier avant le temps iRacing du tour 2
    ]
    columns = ["SessionNum", "SessionTime", "Lap", "LapLastLapTime", "OnPitRoad", "PlayerCarMyIncidentCount"]
    channels = {name: [row[i] for row in rows] for i, name in enumerate(columns)}
    channels["LapBestLapTime"] = [0.0, 0.0, 0.0, 100.123, 100.123]
    monkeypatch.setattr(extract_laps, "read_lap_channels", lambda path: channels)

    assert run_main(extract_laps, monkeypatch, str(fake_ibt)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Session  Tour       Temps  Valide  Remarque",
        "-" * 70,
        "      0     0   1:00.000*  non     pas de temps iRacing, passage aux stands",
        "      0     1    1:40.123  oui     ",
        "      0     2   1:39.000*  non     temps iRacing pas encore enregistré",
        "-" * 70,
        "* temps mesuré entre deux passages de ligne (indicatif, précision ~1/60 s)",
        "3 tours terminés, dont 1 valides",
        "Meilleur tour valide : tour 1, 1:40.123",
        "Meilleur tour selon iRacing : 1:40.123",
        "Tour 3 (session 0) non terminé dans le fichier : ignoré",
    ]


def test_missing_file_returns_error(monkeypatch, capsys, tmp_path):
    missing = tmp_path / "absent.ibt"
    for module in (list_ibt_vars, extract_laps):
        assert run_main(module, monkeypatch, str(missing)) == 1
        assert capsys.readouterr().err == f"Fichier introuvable : {missing}\n"
