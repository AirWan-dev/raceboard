"""Extrait les temps au tour d'une session enregistrée dans un fichier .ibt.

Usage :
    py -m raceboard.extract_laps "C:/chemin/vers/session.ibt"
"""

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import irsdk

# Canaux du .ibt nécessaires à l'extraction des tours.
LAP_CHANNELS = [
    "SessionNum",                # numéro de la session (essais, qualif, course…) dans le fichier
    "SessionTime",               # secondes depuis le début de la session
    "Lap",                       # numéro du tour en cours (0 = tour de sortie des stands)
    "LapLastLapTime",            # temps du dernier tour selon iRacing (<= 0 : pas de temps)
    "OnPitRoad",                 # voiture sur la voie des stands
    "PlayerCarMyIncidentCount",  # compteur d'incidents du pilote
    "LapBestLapTime",            # meilleur tour selon iRacing (sert de contrôle)
]


@dataclass
class Lap:
    session_num: int
    lap_num: int
    time_s: float
    time_is_official: bool  # True : temps iRacing ; False : temps mesuré entre deux passages de ligne
    valid: bool
    incidents: int  # points d'incident pris pendant le tour
    remarks: list[str] = field(default_factory=list)


@dataclass
class LapExtraction:
    laps: list[Lap]
    incomplete_laps: list[tuple[int, int]]  # (session, tour) commencés mais non terminés dans le fichier


def read_lap_channels(ibt_path: Path) -> dict[str, list]:
    """Lit dans le .ibt les canaux de LAP_CHANNELS (une liste de valeurs par canal)."""
    ibt = irsdk.IBT()
    ibt.open(str(ibt_path))
    try:
        missing = [name for name in LAP_CHANNELS if name not in ibt.var_headers_names]
        if missing:
            raise ValueError(f"Canaux absents du fichier : {', '.join(missing)}")
        return {name: ibt.get_all(name) for name in LAP_CHANNELS}
    finally:
        ibt.close()


def _split_into_runs(channels: dict[str, list]) -> list[tuple[int, int]]:
    """Découpe les échantillons en blocs consécutifs de même (session, tour).

    Renvoie la liste des (index de début, index de fin exclu) de chaque bloc.
    """
    sessions = channels["SessionNum"]
    laps = channels["Lap"]
    runs = []
    start = 0
    for i in range(1, len(laps)):
        if sessions[i] != sessions[start] or laps[i] != laps[start]:
            runs.append((start, i))
            start = i
    if laps:
        runs.append((start, len(laps)))
    return runs


def _official_time(channels: dict[str, list], run: tuple[int, int], next_run_is_last: bool) -> float | None:
    """Temps iRacing du tour qui précède le bloc `run`, ou None s'il n'est pas encore connu.

    iRacing met à jour LapLastLapTime quelques échantillons après le passage de la ligne.
    On prend donc la première valeur différente de celle du tour précédent. Si la valeur
    ne change pas, c'est soit le même temps (ex. -1 deux fois de suite), soit une mise à jour
    pas encore arrivée : on ne peut trancher que si le bloc est allé jusqu'à son terme.
    """
    start, end = run
    last_lap_times = channels["LapLastLapTime"]
    previous_value = last_lap_times[start - 1]
    for value in last_lap_times[start:end]:
        if value != previous_value:
            return value
    return None if next_run_is_last else previous_value


def extract_laps(channels: dict[str, list]) -> LapExtraction:
    """Construit la liste des tours terminés à partir des canaux lus dans le .ibt."""
    runs = _split_into_runs(channels)
    session_nums = channels["SessionNum"]
    lap_nums = channels["Lap"]
    session_times = channels["SessionTime"]
    on_pit_road = channels["OnPitRoad"]
    incidents = channels["PlayerCarMyIncidentCount"]

    laps = []
    incomplete = []
    for index, (start, end) in enumerate(runs):
        session_num, lap_num = session_nums[start], lap_nums[start]
        next_run = runs[index + 1] if index + 1 < len(runs) else None

        # Le tour n'est terminé que si l'on voit ensuite le tour suivant de la même session.
        if (
            next_run is None
            or session_nums[next_run[0]] != session_num
            or lap_nums[next_run[0]] != lap_num + 1
        ):
            incomplete.append((session_num, lap_num))
            continue

        remarks = []
        measured = session_times[next_run[0]] - session_times[start]
        official = _official_time(channels, next_run, next_run_is_last=(index + 2 == len(runs)))

        if official is None:
            time_s, time_is_official = measured, False
            remarks.append("temps iRacing pas encore enregistré")
        elif official > 0:
            time_s, time_is_official = official, True
        else:
            time_s, time_is_official = measured, False
            remarks.append("pas de temps iRacing")

        went_through_pits = any(on_pit_road[start:next_run[0] + 1])
        if went_through_pits:
            remarks.append("passage aux stands")

        new_incidents = incidents[next_run[0]] - incidents[start]
        if new_incidents > 0:
            remarks.append(f"incident +{new_incidents}x")

        # Valide = chronométré par iRacing, sans passage aux stands ni incident.
        valid = time_is_official and not went_through_pits and new_incidents == 0
        laps.append(Lap(session_num, lap_num, time_s, time_is_official, valid, new_incidents, remarks))

    return LapExtraction(laps, incomplete)


def format_lap_time(seconds: float) -> str:
    """Formate un temps en m:ss.mmm (ex. 98.716 -> 1:38.716)."""
    minutes, rest = divmod(round(seconds, 3), 60)
    return f"{int(minutes)}:{rest:06.3f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Affiche les temps au tour d'un fichier .ibt iRacing.")
    parser.add_argument("ibt_path", type=Path, help="chemin du fichier .ibt")
    args = parser.parse_args()

    if not args.ibt_path.is_file():
        print(f"Fichier introuvable : {args.ibt_path}", file=sys.stderr)
        return 1

    try:
        channels = read_lap_channels(args.ibt_path)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    result = extract_laps(channels)

    print(f"{'Session':>7}  {'Tour':>4}  {'Temps':>10}  {'Valide':<6}  Remarque")
    print("-" * 70)
    for lap in result.laps:
        time_text = format_lap_time(lap.time_s) + ("" if lap.time_is_official else "*")
        print(
            f"{lap.session_num:>7}  {lap.lap_num:>4}  {time_text:>10}  "
            f"{'oui' if lap.valid else 'non':<6}  {', '.join(lap.remarks)}"
        )
    print("-" * 70)
    print("* temps mesuré entre deux passages de ligne (indicatif, précision ~1/60 s)")

    valid_laps = [lap for lap in result.laps if lap.valid]
    print(f"{len(result.laps)} tours terminés, dont {len(valid_laps)} valides")
    if valid_laps:
        best = min(valid_laps, key=lambda lap: lap.time_s)
        print(f"Meilleur tour valide : tour {best.lap_num}, {format_lap_time(best.time_s)}")
    iracing_best = channels["LapBestLapTime"][-1]
    if iracing_best > 0:
        print(f"Meilleur tour selon iRacing : {format_lap_time(iracing_best)}")
    for session_num, lap_num in result.incomplete_laps:
        print(f"Tour {lap_num} (session {session_num}) non terminé dans le fichier : ignoré")
    return 0


if __name__ == "__main__":
    sys.exit(main())
