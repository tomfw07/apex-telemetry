from __future__ import annotations

import numpy as np
import pandas as pd

CHANNELS = ["Speed", "Throttle", "Brake", "nGear", "Acceleration"]


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def prepare_telemetry(telemetry: pd.DataFrame) -> pd.DataFrame:
    """Clean telemetry and add derived acceleration in m/s²."""
    df = telemetry.copy()
    for col in ["Distance", "Speed", "Throttle", "Brake", "nGear"]:
        if col not in df:
            df[col] = np.nan
        df[col] = _numeric(df[col])
    if "Time" in df:
        time_s = pd.to_timedelta(df["Time"], errors="coerce").dt.total_seconds()
    elif "SessionTime" in df:
        time_s = pd.to_timedelta(df["SessionTime"], errors="coerce").dt.total_seconds()
    else:
        time_s = pd.Series(np.arange(len(df), dtype=float), index=df.index)
    df["_time_s"] = time_s
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["Distance", "Speed"])
    df = df.sort_values("Distance").drop_duplicates("Distance").reset_index(drop=True)
    if len(df) >= 2:
        seconds = df["_time_s"].to_numpy(dtype=float)
        speed_ms = df["Speed"].to_numpy(dtype=float) / 3.6
        if np.isfinite(seconds).sum() >= 2 and np.nanmax(seconds) > np.nanmin(seconds):
            seconds = pd.Series(seconds).interpolate(limit_direction="both").to_numpy()
            df["Acceleration"] = np.gradient(speed_ms, seconds)
        else:
            distance_m = df["Distance"].to_numpy(dtype=float)
            dt_est = np.gradient(distance_m) / np.maximum(speed_ms, 1.0)
            elapsed = np.cumsum(np.maximum(dt_est, 1e-3))
            df["Acceleration"] = np.gradient(speed_ms, elapsed)
    else:
        df["Acceleration"] = np.nan
    return df


def compare_telemetry(a: pd.DataFrame, b: pd.DataFrame, points: int = 1000) -> pd.DataFrame:
    """Interpolate both laps to a common distance axis and calculate elapsed-time delta."""
    da, db = prepare_telemetry(a), prepare_telemetry(b)
    if len(da) < 2 or len(db) < 2:
        raise ValueError("Each lap needs at least two valid telemetry samples.")
    end = min(float(da["Distance"].max()), float(db["Distance"].max()))
    start = max(float(da["Distance"].min()), float(db["Distance"].min()))
    if end <= start:
        raise ValueError("The laps do not share a usable distance range.")
    grid = np.linspace(start, end, max(50, int(points)))
    result = pd.DataFrame({"Distance": grid})
    for suffix, df in [("A", da), ("B", db)]:
        x = df["Distance"].to_numpy(dtype=float)
        for channel in ["Speed", "Throttle", "Brake", "nGear", "Acceleration"]:
            y = df[channel].to_numpy(dtype=float)
            valid = np.isfinite(x) & np.isfinite(y)
            result[f"{channel}_{suffix}"] = np.interp(grid, x[valid], y[valid]) if valid.sum() >= 2 else np.nan
        t = df["_time_s"].to_numpy(dtype=float)
        valid_t = np.isfinite(x) & np.isfinite(t)
        result[f"Elapsed_{suffix}"] = np.interp(grid, x[valid_t], t[valid_t]) if valid_t.sum() >= 2 else np.nan
    result["Delta_A_minus_B"] = result["Elapsed_A"] - result["Elapsed_B"]
    return result


def summarize_lap(telemetry: pd.DataFrame) -> dict:
    df = prepare_telemetry(telemetry)
    speed = df["Speed"].dropna()
    return {
        "min_speed": float(speed.min()) if not speed.empty else np.nan,
        "max_speed": float(speed.max()) if not speed.empty else np.nan,
        "mean_speed": float(speed.mean()) if not speed.empty else np.nan,
        "distance_m": float(df["Distance"].max() - df["Distance"].min()) if len(df) else np.nan,
    }


def detect_events(telemetry: pd.DataFrame, driver: str = "Driver", brake_min_samples: int = 2,
                  throttle_low: float = 20.0, throttle_high: float = 70.0) -> pd.DataFrame:
    """Detect approximate brake-onset and throttle-pickup events."""
    df = prepare_telemetry(telemetry)
    if df.empty:
        return pd.DataFrame(columns=["driver", "event", "distance_m", "speed_kmh"])
    events = []
    brake = df["Brake"].fillna(0).astype(float).to_numpy() > 0
    throttle = df["Throttle"].fillna(0).astype(float).to_numpy()
    distance = df["Distance"].to_numpy(dtype=float)
    speed = df["Speed"].to_numpy(dtype=float)

    transitions = np.where(brake & ~np.r_[False, brake[:-1]])[0]
    for idx in transitions:
        if brake[idx:idx + max(1, brake_min_samples)].sum() >= max(1, brake_min_samples):
            events.append({"driver": driver, "event": "Brake onset",
                           "distance_m": distance[idx], "speed_kmh": speed[idx]})

    low_seen = False
    for idx, value in enumerate(throttle):
        if value <= throttle_low:
            low_seen = True
        elif low_seen and value >= throttle_high and (idx == 0 or throttle[idx - 1] < throttle_high):
            events.append({"driver": driver, "event": "Throttle pickup",
                           "distance_m": distance[idx], "speed_kmh": speed[idx]})
            low_seen = False

    if not events:
        return pd.DataFrame(columns=["driver", "event", "distance_m", "speed_kmh"])
    return pd.DataFrame(events).sort_values("distance_m").reset_index(drop=True)


def prepare_energy_data(data: pd.DataFrame) -> pd.DataFrame:
    """Validate externally sourced energy data; never infer battery values from car telemetry."""
    df = data.copy()
    supported = ["BatterySOC", "DeploymentPower_kW", "HarvestPower_kW", "EnergyMJ"]
    if "Distance" not in df.columns:
        raise ValueError("Energy CSV must contain a Distance column in metres.")
    df["Distance"] = _numeric(df["Distance"])
    for col in supported:
        if col in df.columns:
            df[col] = _numeric(df[col])
    columns = ["Distance"] + [col for col in supported if col in df.columns]
    df = df[columns].dropna(subset=["Distance"]).sort_values("Distance").reset_index(drop=True)
    return df if any(col in df.columns for col in supported) else pd.DataFrame()


def compare_corners(
    comparison: pd.DataFrame,
    corners: pd.DataFrame,
    approach_m: float = 100.0,
    apex_window_m: float = 75.0,
    exit_m: float = 100.0,
) -> pd.DataFrame:
    """Summarise two laps around FastF1 circuit corner markers.

    FastF1's corner markers are approximate reference locations, not guaranteed
    geometric apexes. Entry/exit speeds are sampled near fixed distance offsets;
    minimum speed is the minimum in a window around the marker.
    """
    required = {"Distance", "Speed_A", "Speed_B"}
    if not required.issubset(comparison.columns):
        raise ValueError(f"Comparison is missing columns: {sorted(required - set(comparison.columns))}")
    if corners is None or corners.empty or "Distance" not in corners.columns:
        return pd.DataFrame()

    data = comparison.sort_values("Distance").reset_index(drop=True)
    distance = pd.to_numeric(data["Distance"], errors="coerce").to_numpy(dtype=float)
    if len(distance) < 2:
        return pd.DataFrame()

    def sample_at(column: str, target: float) -> float:
        values = pd.to_numeric(data[column], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(distance) & np.isfinite(values)
        if valid.sum() < 1:
            return np.nan
        return float(np.interp(target, distance[valid], values[valid]))

    rows = []
    for _, corner in corners.iterrows():
        marker = pd.to_numeric(pd.Series([corner.get("Distance")]), errors="coerce").iloc[0]
        if not np.isfinite(marker) or marker < distance.min() or marker > distance.max():
            continue
        number = corner.get("Number", "")
        letter = corner.get("Letter", "")
        label = f"T{int(number)}{letter}" if pd.notna(number) and str(number).strip() else f"Corner {len(rows) + 1}"
        row = {"corner": label, "distance_m": float(marker)}
        for suffix in ("A", "B"):
            speed_col = f"Speed_{suffix}"
            local = (distance >= marker - apex_window_m) & (distance <= marker + apex_window_m)
            speeds = pd.to_numeric(data.loc[local, speed_col], errors="coerce").dropna()
            row[f"entry_speed_{suffix}_kmh"] = sample_at(speed_col, max(float(distance.min()), marker - approach_m))
            row[f"minimum_speed_{suffix}_kmh"] = float(speeds.min()) if not speeds.empty else np.nan
            row[f"exit_speed_{suffix}_kmh"] = sample_at(speed_col, min(float(distance.max()), marker + exit_m))
            throttle_col = f"Throttle_{suffix}"
            if throttle_col in data.columns:
                post = data.loc[(distance >= marker) & (distance <= marker + exit_m), ["Distance", throttle_col]]
                post_values = pd.to_numeric(post[throttle_col], errors="coerce")
                pickup = post.loc[post_values >= 70, "Distance"]
                row[f"throttle_70_distance_{suffix}_m"] = float(pickup.iloc[0]) if not pickup.empty else np.nan
            brake_col = f"Brake_{suffix}"
            if brake_col in data.columns:
                before = data.loc[(distance >= marker - 200) & (distance <= marker), ["Distance", brake_col]].copy()
                brake = pd.to_numeric(before[brake_col], errors="coerce").fillna(0).to_numpy() > 0
                idx = np.where(brake & ~np.r_[False, brake[:-1]])[0]
                row[f"brake_onset_{suffix}_m"] = float(before.iloc[idx[0]]["Distance"]) if len(idx) else np.nan
        row["minimum_speed_advantage_A_minus_B_kmh"] = row["minimum_speed_A_kmh"] - row["minimum_speed_B_kmh"]
        row["delta_A_minus_B_s"] = sample_at("Delta_A_minus_B", float(marker)) if "Delta_A_minus_B" in data.columns else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
