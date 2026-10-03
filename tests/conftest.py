"""Données et fixtures partagées par les tests (aucun vrai .ibt)."""

from datetime import UTC, datetime

import pytest

from raceboard.db import connect, create_schema
from raceboard.extract_laps import Lap
from raceboard.session_info import IbtInfo


@pytest.fixture
def ibt_info():
    return IbtInfo(
        track_name="Fuji Speedway",
        track_config="Grand Prix",
        car_name="McLaren 720S GT3 EVO",
        recorded_at=datetime(2026, 9, 26, 19, 41, 2, tzinfo=UTC),
        session_types={0: "Offline Testing"},
    )


@pytest.fixture
def sample_laps():
    # session, tour, temps, temps officiel, valide, incidents
    return [
        Lap(0, 0, 128.3, False, False, 4),
        Lap(0, 1, 101.39500427246094, True, True, 0),  # float32 d'iRacing, arrondi au millième en base
        Lap(0, 2, 98.71600341796875, True, True, 0),
        Lap(0, 3, 102.85, False, False, 1),
    ]


@pytest.fixture
def connection(tmp_path):
    connection = connect(tmp_path / "test.db")
    create_schema(connection)
    yield connection
    connection.close()
