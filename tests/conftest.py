"""Données et fixtures partagées par les tests (aucun vrai .ibt).

Les tests qui touchent la base utilisent un serveur PostgreSQL de test, désigné par la variable
d'environnement RACEBOARD_TEST_DATABASE_URL (jamais la base de l'appli). Avant chaque test, les
tables de la base de test sont supprimées : chaque test part d'une base vide.
Garde-fou : le nom de la base de test doit finir par « _test ».
"""

import os
from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest

from raceboard.db import DATABASE_URL_VARIABLE, connect, create_schema, database_label
from raceboard.extract_laps import Lap
from raceboard.session_info import IbtInfo

TEST_DATABASE_URL_VARIABLE = "RACEBOARD_TEST_DATABASE_URL"


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
def database_url(monkeypatch):
    """URL de la base de test, vidée de ses tables, et donnée aux commandes via RACEBOARD_DATABASE_URL.

    Variable absente : le test est en erreur (pas sauté), pour qu'une suite verte veuille
    toujours dire que la base a été testée.
    """
    url = os.environ.get(TEST_DATABASE_URL_VARIABLE)
    if not url:
        pytest.fail(
            f"Variable d'environnement {TEST_DATABASE_URL_VARIABLE} non définie : ce test a besoin "
            "d'un serveur PostgreSQL de test (base dont le nom finit par _test)",
            pytrace=False,
        )
    connection = connect(url)
    try:
        if not connection.info.dbname.endswith("_test"):
            pytest.fail(
                f"{TEST_DATABASE_URL_VARIABLE} désigne la base « {connection.info.dbname} » : les tests "
                "suppriment les tables, ils ne tournent que sur une base dont le nom finit par _test",
                pytrace=False,
            )
        with connection.transaction():
            for table in ["laps", "sessions", "quarantine"]:  # laps d'abord : elle dépend de sessions
                connection.execute(f"DROP TABLE IF EXISTS {table}")
    finally:
        connection.close()
    monkeypatch.setenv(DATABASE_URL_VARIABLE, url)
    return url


@pytest.fixture
def connection(database_url):
    """Connexion à la base de test, avec les tables créées et vides."""
    connection = connect(database_url)
    create_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def db_label(database_url):
    """Libellé de la base de test dans les messages, ex. « raceboard_test (localhost:5433) »."""
    connection = connect(database_url)
    try:
        return database_label(connection)
    finally:
        connection.close()


@pytest.fixture
def missing_database_url(database_url):
    """URL d'une base qui n'existe pas sur le serveur de test (même utilisateur, même mot de passe)."""
    return urlsplit(database_url)._replace(path="/raceboard_absente_test").geturl()
