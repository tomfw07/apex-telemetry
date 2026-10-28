from __future__ import annotations

from pathlib import Path
import fastf1
import pandas as pd

CACHE_DIR = Path(".fastf1_cache")


def load_session(year: int, event: str, session_name: str):
    """Load a FastF1 session with local caching enabled."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(CACHE_DIR))
    session = fastf1.get_session(int(year), event, session_name)
    session.load( laps=True, telemetry=True, weather=False, messages=False)
    return session


def available_drivers(session) -> list[str]:
    """Return driver numbers that have at least one timed lap."""
    if session.laps is None or session.laps.empty:
        return []
    laps = session.laps
    return sorted(laps.loc[laps["LapTime"].notna(), "Driver"].dropna().astype(str).unique().tolist())


def available_laps(session, driver: str) -> list[int]:
    laps = session.laps.pick_driver(str(driver))
    valid = laps.loc[laps["LapTime"].notna() & laps["LapNumber"].notna(), "LapNumber"]
    return sorted(valid.astype(int).unique().tolist())


def get_lap_telemetry(lap) -> pd.DataFrame:
    """Return telemetry with distance and commonly used channels."""
    telemetry = lap.get_telemetry().copy()
    if telemetry.empty:
        raise ValueError("No telemetry available for the selected lap.")
    if "Distance" not in telemetry.columns:
        telemetry = lap.get_car_data().add_distance()
    telemetry = telemetry.sort_values("Distance").drop_duplicates("Distance")
    required = ["Distance", "Speed", "Throttle", "Brake", "nGear", "Time"]
    # Preserve position channels when FastF1 provides them, for the track map.
    position = [column for column in ["X", "Y"] if column in telemetry.columns]
    for column in required:
        if column not in telemetry.columns:
            telemetry[column] = pd.NA
    return telemetry[required + position].reset_index(drop=True)
