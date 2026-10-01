"""Tests de l'extraction des tours, sur des données synthétiques (aucun .ibt nécessaire)."""

from raceboard.extract_laps import extract_laps, format_lap_time

# Colonnes d'un échantillon synthétique, dans l'ordre des tuples ci-dessous.
COLUMNS = ["SessionNum", "SessionTime", "Lap", "LapLastLapTime", "OnPitRoad", "PlayerCarMyIncidentCount"]


def build_channels(rows):
    """Transforme une liste d'échantillons (tuples) en canaux, comme read_lap_channels()."""
    channels = {name: [row[i] for row in rows] for i, name in enumerate(COLUMNS)}
    channels["LapBestLapTime"] = [0.0] * len(rows)
    return channels


def test_clean_laps_use_official_time_and_are_valid():
    rows = [
        # session, temps, tour, dernier temps iRacing, stands, incidents
        (0, 0.0, 1, 0.0, False, 0),
        (0, 50.0, 1, 0.0, False, 0),
        (0, 100.0, 2, 0.0, False, 0),     # passage de ligne : la mise à jour arrive juste après
        (0, 100.5, 2, 100.123, False, 0),
        (0, 199.0, 3, 100.123, False, 0),
        (0, 199.5, 3, 99.456, False, 0),
    ]
    result = extract_laps(build_channels(rows))

    assert [(lap.lap_num, lap.time_s, lap.valid) for lap in result.laps] == [
        (1, 100.123, True),
        (2, 99.456, True),
    ]
    assert all(lap.time_is_official for lap in result.laps)
    assert result.incomplete_laps == [(0, 3)]


def test_out_lap_from_pits_is_invalid_with_measured_time():
    rows = [
        (0, 0.0, 0, 0.0, True, 0),        # départ du stand
        (0, 30.0, 0, 0.0, False, 0),
        (0, 120.0, 1, 0.0, False, 0),     # iRacing ne chronomètre pas le tour de sortie
        (0, 220.0, 2, 0.0, False, 0),
        (0, 220.5, 2, 100.0, False, 0),
    ]
    lap0 = extract_laps(build_channels(rows)).laps[0]

    assert lap0.lap_num == 0
    assert lap0.time_s == 120.0
    assert not lap0.time_is_official
    assert not lap0.valid
    assert "passage aux stands" in lap0.remarks


def test_lap_with_incident_is_invalid_even_with_official_time():
    rows = [
        (0, 0.0, 1, 0.0, False, 0),
        (0, 40.0, 1, 0.0, False, 2),      # incident 2x pendant le tour
        (0, 100.0, 2, 0.0, False, 2),
        (0, 100.5, 2, 100.0, False, 2),
        (0, 200.0, 3, 100.0, False, 2),
    ]
    lap1 = extract_laps(build_channels(rows)).laps[0]

    assert lap1.time_s == 100.0
    assert not lap1.valid
    assert lap1.remarks == ["incident +2x"]


def test_consecutive_laps_without_official_time():
    # Deux tours de suite à -1 : la valeur ne change pas, mais le tour 2 est bien terminé.
    rows = [
        (0, 0.0, 1, 0.0, False, 0),
        (0, 100.0, 2, 0.0, False, 0),
        (0, 100.5, 2, -1.0, False, 0),
        (0, 205.0, 3, -1.0, False, 0),
        (0, 300.0, 4, -1.0, False, 0),
    ]
    laps = extract_laps(build_channels(rows)).laps

    assert [(lap.lap_num, lap.time_s, lap.valid) for lap in laps] == [
        (1, 100.0, False),
        (2, 105.0, False),
        (3, 95.0, False),
    ]
    assert laps[2].remarks == ["temps iRacing pas encore enregistré"]


def test_recording_ends_before_official_time_update():
    rows = [
        (0, 0.0, 1, 0.0, False, 0),
        (0, 100.0, 2, 0.0, False, 0),
        (0, 100.5, 2, 100.0, False, 0),
        (0, 199.0, 3, 100.0, False, 0),   # fin du fichier avant la mise à jour du tour 2
    ]
    lap2 = extract_laps(build_channels(rows)).laps[1]

    assert lap2.time_s == 99.0
    assert not lap2.time_is_official
    assert not lap2.valid
    assert lap2.remarks == ["temps iRacing pas encore enregistré"]


def test_session_change_does_not_create_a_lap():
    rows = [
        (0, 0.0, 1, 0.0, False, 0),
        (0, 100.0, 2, 0.0, False, 0),
        (0, 100.5, 2, 100.0, False, 0),
        (1, 0.0, 0, 0.0, True, 0),        # nouvelle session : le tour 2 de la session 0 est coupé
        (1, 120.0, 1, 0.0, False, 0),
    ]
    result = extract_laps(build_channels(rows))

    assert [(lap.session_num, lap.lap_num) for lap in result.laps] == [(0, 1), (1, 0)]
    assert result.incomplete_laps == [(0, 2), (1, 1)]


def test_format_lap_time():
    assert format_lap_time(98.716) == "1:38.716"
    assert format_lap_time(59.5) == "0:59.500"
    assert format_lap_time(128.3) == "2:08.300"
    assert format_lap_time(59.9996) == "1:00.000"
