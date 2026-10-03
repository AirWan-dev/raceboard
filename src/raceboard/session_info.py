"""Lit les informations générales d'un fichier .ibt : circuit, voiture, sessions, date."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import irsdk


@dataclass
class IbtInfo:
    track_name: str                 # ex. "Fuji Speedway"
    track_config: str               # ex. "Grand Prix"
    car_name: str                   # voiture du pilote, ex. "McLaren 720S GT3 EVO"
    recorded_at: datetime           # début de l'enregistrement, en UTC
    session_types: dict[int, str]   # numéro de session -> type, ex. {0: "Offline Testing"}


def build_ibt_info(weekend_info: dict, driver_info: dict, session_info: dict, start_timestamp: int) -> IbtInfo:
    """Construit IbtInfo à partir des sections de l'en-tête YAML et de l'horodatage du fichier."""
    player_car_idx = driver_info["DriverCarIdx"]
    player = next(driver for driver in driver_info["Drivers"] if driver["CarIdx"] == player_car_idx)
    return IbtInfo(
        track_name=weekend_info["TrackDisplayName"],
        track_config=weekend_info["TrackConfigName"],
        car_name=player["CarScreenName"],
        recorded_at=datetime.fromtimestamp(start_timestamp, UTC),
        session_types={session["SessionNum"]: session["SessionType"] for session in session_info["Sessions"]},
    )


def read_ibt_info(ibt_path: Path) -> IbtInfo:
    """Lit l'en-tête du fichier .ibt."""
    # L'en-tête YAML se lit avec l'API publique de pyirsdk : IRSDK accepte un fichier
    # à la place de la mémoire partagée du simulateur (aucun appel propre à Windows dans ce cas).
    sdk = irsdk.IRSDK()
    if not sdk.startup(test_file=str(ibt_path)):
        raise ValueError(f"En-tête illisible : {ibt_path}")
    try:
        weekend_info = sdk["WeekendInfo"]
        driver_info = sdk["DriverInfo"]
        session_info = sdk["SessionInfo"]
    finally:
        sdk.shutdown()

    # La date de début d'enregistrement n'est que dans l'en-tête disque, lu via _disk_header
    # (attribut interne ; version de pyirsdk figée).
    ibt = irsdk.IBT()
    ibt.open(str(ibt_path))
    try:
        start_timestamp = ibt._disk_header.session_start_date
    finally:
        ibt.close()

    return build_ibt_info(weekend_info, driver_info, session_info, start_timestamp)
