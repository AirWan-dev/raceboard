"""Tests de la lecture des informations générales d'un .ibt (sections YAML synthétiques)."""

from datetime import UTC, datetime

from raceboard.session_info import build_ibt_info


def test_build_ibt_info():
    weekend_info = {"TrackDisplayName": "Fuji Speedway", "TrackConfigName": "Grand Prix", "TrackName": "fuji gp"}
    driver_info = {
        "DriverCarIdx": 1,  # le pilote n'est pas forcément la première voiture de la liste
        "Drivers": [
            {"CarIdx": 0, "CarScreenName": "Safety Car"},
            {"CarIdx": 1, "CarScreenName": "Ferrari 296 GT3"},
        ],
    }
    session_info = {
        "Sessions": [
            {"SessionNum": 0, "SessionType": "Practice"},
            {"SessionNum": 1, "SessionType": "Race"},
        ]
    }

    info = build_ibt_info(weekend_info, driver_info, session_info, start_timestamp=1790884334)

    assert info.track_name == "Fuji Speedway"
    assert info.track_config == "Grand Prix"
    assert info.car_name == "Ferrari 296 GT3"
    assert info.recorded_at == datetime(2026, 10, 1, 19, 52, 14, tzinfo=UTC)
    assert info.session_types == {0: "Practice", 1: "Race"}


def test_track_without_configuration():
    # Pour un circuit sans configuration (ex. Le Mans), TrackConfigName est vide dans l'en-tête.
    weekend_info = {"TrackDisplayName": "Circuit des 24 Heures du Mans", "TrackConfigName": None}
    driver_info = {"DriverCarIdx": 0, "Drivers": [{"CarIdx": 0, "CarScreenName": "Aston Martin Vantage GT3 EVO"}]}
    session_info = {"Sessions": [{"SessionNum": 0, "SessionType": "Offline Testing"}]}

    info = build_ibt_info(weekend_info, driver_info, session_info, start_timestamp=0)

    assert info.track_config == ""
