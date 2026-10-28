from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


CHANNEL_LABELS = {
    "Speed": ("Speed (km/h)", "Speed"),
    "Throttle": ("Throttle (%)", "Throttle"),
    "Brake": ("Brake applied (0/1)", "Brake"),
    "nGear": ("Gear", "Gear"),
    "Acceleration": ("Acceleration (m/s²)", "Acceleration"),
}


def telemetry_figure(comparison: pd.DataFrame, channel: str, name_a: str, name_b: str) -> go.Figure:
    if channel not in CHANNEL_LABELS:
        channel = "Speed"
    label, _ = CHANNEL_LABELS[channel]
    fig = go.Figure()
    for suffix, name in [("A", name_a), ("B", name_b)]:
        col = f"{channel}_{suffix}"
        if col in comparison:
            fig.add_trace(go.Scatter(x=comparison["Distance"], y=comparison[col],
                                     mode="lines", name=name, connectgaps=False))
    fig.update_layout(template="plotly_dark", height=420, hovermode="x unified",
                      xaxis_title="Distance around lap (m)", yaxis_title=label,
                      legend_title="Driver")
    return fig


def delta_figure(comparison: pd.DataFrame, name_a: str, name_b: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=comparison["Distance"], y=comparison["Delta_A_minus_B"],
                             mode="lines", name=f"{name_a} minus {name_b}"))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(template="plotly_dark", height=320, hovermode="x unified",
                      xaxis_title="Distance around lap (m)",
                      yaxis_title="Elapsed-time delta (s)",
                      title="Positive = Driver A is behind Driver B")
    return fig


def event_table_figure(events: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for driver, group in events.groupby("driver"):
        for event_name, subgroup in group.groupby("event"):
            fig.add_trace(go.Scatter(x=subgroup["distance_m"], y=subgroup["speed_kmh"],
                                     mode="markers", name=f"{driver}: {event_name}",
                                     text=[event_name] * len(subgroup),
                                     hovertemplate="%{text}<br>Distance: %{x:.0f} m<br>Speed: %{y:.1f} km/h<extra></extra>"))
    fig.update_layout(template="plotly_dark", height=350,
                      xaxis_title="Distance around lap (m)", yaxis_title="Speed at event (km/h)")
    return fig


def energy_figure(data: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    units = {
        "BatterySOC": ("Battery state of charge", "%"),
        "DeploymentPower_kW": ("Deployment power", "kW"),
        "HarvestPower_kW": ("Harvest power", "kW"),
        "EnergyMJ": ("Energy", "MJ"),
    }
    for col, (label, unit) in units.items():
        if col in data.columns:
            fig.add_trace(go.Scatter(x=data["Distance"], y=data[col], mode="lines",
                                     name=label, yaxis=None,
                                     hovertemplate=f"Distance: %{{x:.0f}} m<br>{label}: %{{y:.3f}} {unit}<extra></extra>"))
    fig.update_layout(template="plotly_dark", height=400, hovermode="x unified",
                      xaxis_title="Distance (m)", yaxis_title="Value (check units per trace)",
                      title="Externally supplied energy telemetry")
    return fig


def corner_min_speed_figure(corners: pd.DataFrame, name_a: str, name_b: str) -> go.Figure:
    """Grouped bar chart of minimum speed measured near each corner marker."""
    fig = go.Figure()
    for suffix, name in [("A", name_a), ("B", name_b)]:
        column = f"minimum_speed_{suffix}_kmh"
        if column in corners.columns:
            fig.add_trace(go.Bar(x=corners["corner"], y=corners[column], name=name,
                                 hovertemplate="%{x}<br>Minimum speed: %{y:.1f} km/h<extra></extra>"))
    fig.update_layout(template="plotly_dark", height=390, barmode="group",
                      xaxis_title="Circuit corner marker", yaxis_title="Minimum speed in marker window (km/h)",
                      title="Corner-by-corner minimum speed", hovermode="x unified")
    return fig


def track_figure(telemetry_a: pd.DataFrame, telemetry_b: pd.DataFrame, corners: pd.DataFrame,
                 name_a: str, name_b: str) -> go.Figure | None:
    """Plot the two selected lap paths if X/Y position data is available."""
    if not {"X", "Y"}.issubset(telemetry_a.columns) or not {"X", "Y"}.issubset(telemetry_b.columns):
        return None
    a = telemetry_a[["X", "Y", "Speed"]].apply(pd.to_numeric, errors="coerce").dropna(subset=["X", "Y"])
    b = telemetry_b[["X", "Y", "Speed"]].apply(pd.to_numeric, errors="coerce").dropna(subset=["X", "Y"])
    if len(a) < 2 or len(b) < 2:
        return None
    fig = go.Figure()
    for data, name in [(a, name_a), (b, name_b)]:
        fig.add_trace(go.Scatter(
            x=data["X"], y=data["Y"], mode="lines", name=name,
            line={"width": 4},
            customdata=data[["Speed"]],
            hovertemplate=f"{name}<br>X: %{{x:.0f}}<br>Y: %{{y:.0f}}<br>Speed: %{{customdata[0]:.1f}} km/h<extra></extra>",
        ))
    if corners is not None and not corners.empty and {"X", "Y"}.issubset(corners.columns):
        c = corners.copy()
        c["X"] = pd.to_numeric(c["X"], errors="coerce")
        c["Y"] = pd.to_numeric(c["Y"], errors="coerce")
        c = c.dropna(subset=["X", "Y"])
        labels = []
        for _, row in c.iterrows():
            number = row.get("Number", "")
            letter = row.get("Letter", "")
            labels.append(f"T{int(number)}{letter}" if pd.notna(number) and str(number).strip() else "Corner")
        if not c.empty:
            fig.add_trace(go.Scatter(x=c["X"], y=c["Y"], mode="markers+text",
                                     text=labels, textposition="top center", name="Corner markers",
                                     marker={"size": 7, "symbol": "circle-open"},
                                     hovertemplate="%{text}<extra></extra>"))
    fig.update_layout(template="plotly_dark", height=620, hovermode="closest",
                      xaxis_title="Track position X (m; local coordinates)",
                      yaxis_title="Track position Y (m; local coordinates)",
                      title="Lap paths and circuit corner references",
                      yaxis={"scaleanchor": "x", "scaleratio": 1})
    return fig


def sector_comparison_figure(sectors: pd.DataFrame, name_a: str, name_b: str) -> go.Figure:
    """Compare official timing sector durations where the session provides them."""
    fig = go.Figure()
    for suffix, name in [("A", name_a), ("B", name_b)]:
        col = f"time_{suffix}_s"
        if col in sectors:
            fig.add_trace(go.Bar(x=sectors["sector"], y=sectors[col], name=name,
                                 hovertemplate="%{x}<br>Time: %{y:.3f} s<extra></extra>"))
    fig.update_layout(template="plotly_dark", height=340, barmode="group",
                      xaxis_title="Timing sector", yaxis_title="Sector time (s)",
                      title="Official timing-sector comparison")
    return fig
