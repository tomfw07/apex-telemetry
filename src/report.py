from __future__ import annotations

from html import escape
from typing import Any
import math
import pandas as pd


def _seconds(value: Any) -> float:
    if value is None:
        return math.nan
    try:
        if pd.isna(value):
            return math.nan
    except (TypeError, ValueError):
        pass
    if hasattr(value, "total_seconds"):
        return float(value.total_seconds())
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def format_time(value: Any) -> str:
    seconds = _seconds(value)
    if not math.isfinite(seconds):
        return "N/A"
    minutes, remainder = divmod(max(0.0, seconds), 60.0)
    return f"{int(minutes)}:{remainder:06.3f}" if minutes else f"{remainder:.3f} s"


def build_performance_report(*, event_name: str, season: int, session_name: str,
    driver_a: str, driver_b: str, lap_a: int, lap_b: int,
    lap_time_a: Any, lap_time_b: Any, summary_a: dict[str, Any], summary_b: dict[str, Any],
    sectors: pd.DataFrame | None = None, corners: pd.DataFrame | None = None) -> dict[str, Any]:
    """Build evidence-based findings and a standalone HTML report.

    Positive lap/sector/corner time deltas mean Driver A took longer; negative means
    Driver A was quicker. Corner markers are approximate references, not exact apexes.
    """
    a_time, b_time = _seconds(lap_time_a), _seconds(lap_time_b)
    lap_delta = a_time - b_time if math.isfinite(a_time) and math.isfinite(b_time) else math.nan
    findings: list[str] = []
    if math.isfinite(lap_delta):
        if abs(lap_delta) < 0.001:
            findings.append(f"Lap times were effectively tied ({format_time(a_time)} vs {format_time(b_time)}).")
        elif lap_delta < 0:
            findings.append(f"{driver_a} was quicker overall by {abs(lap_delta):.3f} s.")
        else:
            findings.append(f"{driver_b} was quicker overall by {abs(lap_delta):.3f} s.")
    else:
        findings.append("A reliable lap-time comparison was not available for both selected laps.")

    sector_rows: list[dict[str, Any]] = []
    if sectors is not None and not sectors.empty:
        for _, row in sectors.iterrows():
            sector_rows.append({"sector": str(row.get("sector", "Sector")),
                "a": _seconds(row.get("time_A_s")), "b": _seconds(row.get("time_B_s")),
                "delta": _seconds(row.get("delta_A_minus_B_s"))})
        valid = [r for r in sector_rows if math.isfinite(r["delta"])]
        if valid:
            best_a, best_b = min(valid, key=lambda r: r["delta"]), max(valid, key=lambda r: r["delta"])
            if best_a["delta"] < -0.001:
                findings.append(f"{driver_a}'s strongest sector relative to {driver_b} was {best_a['sector']} ({abs(best_a['delta']):.3f} s quicker).")
            if best_b["delta"] > 0.001:
                findings.append(f"{driver_b}'s strongest sector relative to {driver_a} was {best_b['sector']} ({abs(best_b['delta']):.3f} s quicker).")

    corner_rows: list[dict[str, Any]] = []
    if corners is not None and not corners.empty:
        for _, row in corners.iterrows():
            corner_rows.append({"corner": str(row.get("corner", "Corner")),
                "distance": _seconds(row.get("distance_m")),
                "delta": _seconds(row.get("delta_A_minus_B_s")),
                "speed_delta": _seconds(row.get("minimum_speed_advantage_A_minus_B_kmh"))})
        valid = [r for r in corner_rows if math.isfinite(r["delta"])]
        if valid:
            largest = max(valid, key=lambda r: abs(r["delta"]))
            if abs(largest["delta"]) >= 0.01:
                winner = driver_a if largest["delta"] < 0 else driver_b
                findings.append(f"At {largest['corner']}, {winner} was ahead by {abs(largest['delta']):.3f} s at the sampled marker distance; this is not a causal estimate of corner time loss.")
        valid_speeds = [r for r in corner_rows if math.isfinite(r["speed_delta"])]
        if valid_speeds:
            high, low = max(valid_speeds, key=lambda r: r["speed_delta"]), min(valid_speeds, key=lambda r: r["speed_delta"])
            if high["speed_delta"] >= 1.0:
                findings.append(f"{driver_a} had the higher sampled minimum speed at {high['corner']} by {high['speed_delta']:.1f} km/h.")
            if low["speed_delta"] <= -1.0:
                findings.append(f"{driver_b} had the higher sampled minimum speed at {low['corner']} by {abs(low['speed_delta']):.1f} km/h.")

    for driver, summary in [(driver_a, summary_a), (driver_b, summary_b)]:
        low, high = _seconds(summary.get("min_speed")), _seconds(summary.get("max_speed"))
        if math.isfinite(low) and math.isfinite(high):
            findings.append(f"{driver}'s selected lap ranged from {low:.1f} to {high:.1f} km/h in the available speed samples.")
    findings = findings[:8] or ["There were not enough valid measurements to generate findings for this comparison."]

    def fmt(value: Any, suffix: str = "") -> str:
        number = _seconds(value)
        return f"{number:.3f}{suffix}" if math.isfinite(number) else "N/A"

    sector_html = "<p>No comparable official sector times were available.</p>"
    if sector_rows:
        rows = "".join("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            escape(r["sector"]), fmt(r["a"], " s"), fmt(r["b"], " s"), fmt(r["delta"], " s")) for r in sector_rows)
        sector_html = "<table><thead><tr><th>Sector</th><th>{}</th><th>{}</th><th>A − B</th></tr></thead><tbody>{}</tbody></table>".format(escape(driver_a), escape(driver_b), rows)
    corner_html = "<p>No usable corner-marker comparison was available.</p>"
    if corner_rows:
        rows = "".join("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            escape(r["corner"]), fmt(r["distance"], " m"), fmt(r["delta"], " s"), fmt(r["speed_delta"], " km/h")) for r in corner_rows)
        corner_html = "<table><thead><tr><th>Marker</th><th>Distance</th><th>Elapsed-time delta A − B</th><th>Minimum-speed delta A − B</th></tr></thead><tbody>{}</tbody></table>".format(rows)

    findings_html = "".join(f"<li>{escape(item)}</li>" for item in findings)
    delta_text = f"{lap_delta:+.3f} s (A − B)" if math.isfinite(lap_delta) else "Unavailable"
    title = f"{event_name} {season} — Driver Performance Report"
    html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>
:root{{color-scheme:light}}body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:1050px;margin:40px auto;padding:0 22px;color:#17202a;line-height:1.55}}
h1{{margin-bottom:4px}}.sub{{color:#536273;margin-top:0}}.metrics{{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}}.metric{{border:1px solid #d6dde5;border-radius:10px;padding:14px 18px;min-width:155px}}.metric strong{{display:block;font-size:1.2rem}}table{{border-collapse:collapse;width:100%;margin:12px 0 24px}}th,td{{border:1px solid #d6dde5;padding:9px;text-align:left}}th{{background:#f0f3f7}}.note{{background:#f6f8fa;border-left:4px solid #8293a5;padding:12px 16px}}footer{{margin-top:36px;border-top:1px solid #d6dde5;padding-top:12px;color:#536273;font-size:.9rem}}@media print{{body{{margin:0;max-width:none}}}}
</style></head><body>
<h1>🏎️ {escape(title)}</h1><p class="sub">{escape(session_name)} · {escape(driver_a)} lap {int(lap_a)} vs {escape(driver_b)} lap {int(lap_b)}</p>
<div class="metrics"><div class="metric"><span>{escape(driver_a)} lap time</span><strong>{escape(format_time(lap_time_a))}</strong></div><div class="metric"><span>{escape(driver_b)} lap time</span><strong>{escape(format_time(lap_time_b))}</strong></div><div class="metric"><span>Lap delta (A − B)</span><strong>{escape(delta_text)}</strong></div></div>
<h2>Key findings</h2><ol>{findings_html}</ol><h2>Sector comparison</h2>{sector_html}<h2>Corner-marker comparison</h2>{corner_html}
<div class="note"><strong>Methodology and limitations:</strong> This report compares the selected laps using publicly available FastF1 data. Sector values are session timing values where present. Corner references and sampled speeds are approximate; a time delta at a marker is not a causal estimate of time lost in that corner. Weather, tyre age, traffic, track evolution, fuel load and setup can affect comparisons. This is not official team telemetry.</div>
<footer>Generated by F1 Telemetry Lab · For educational and portfolio use. Findings are descriptive, not proof of cause.</footer></body></html>'''
    return {"findings": findings, "lap_delta_s": lap_delta, "html": html, "title": title}
