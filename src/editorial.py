from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
import math
import re
import hashlib
from typing import Any

import pandas as pd


def _number(value: Any) -> float:
    try:
        number = float(value.total_seconds() if hasattr(value, "total_seconds") else value)
        return number if math.isfinite(number) else math.nan
    except (TypeError, ValueError):
        return math.nan


def _slug(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value)).strip("-").lower()[:60] or "story"


def _format_time(seconds: float) -> str:
    if not math.isfinite(seconds):
        return "unavailable"
    if abs(seconds) < 60:
        return f"{seconds:.3f} s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}:{remainder:06.3f}"


def _make_candidate(*, context: dict[str, Any], story_type: str, source_key: str,
                    headline: str, hook: str, evidence: list[str], caveat: str,
                    magnitude: float, score: float) -> dict[str, Any]:
    session_key = "|".join(str(context.get(key, "")) for key in
                           ("season", "event_name", "session_name", "driver_a", "lap_a", "driver_b", "lap_b"))
    identity = f"{session_key}|{story_type}|{source_key}"
    story_id = f"{_slug(identity)[:48]}-{hashlib.sha1(identity.encode('utf-8')).hexdigest()[:8]}"
    fact_block = "\n".join(f"• {item}" for item in evidence)
    context_line = (f"{context.get('event_name', 'F1 session')} {context.get('season', '')} · "
                    f"{context.get('session_name', '')} · "
                    f"{context.get('driver_a', 'Driver A')} lap {context.get('lap_a', '?')} vs "
                    f"{context.get('driver_b', 'Driver B')} lap {context.get('lap_b', '?')}")
    caption = (
        f"{context_line}\n\n{headline}\n\n{hook}\n\n"
        f"WHAT THE DATA SHOWS\n{fact_block}\n\n"
        f"WHAT IT DOESN'T PROVE\n{caveat}\n\n"
        f"Independent analysis using public session data. Corner references and sampled values are approximate.\n\n"
        "#F1 #Formula1 #Motorsport #Telemetry #RaceEngineering #DataAnalysis"
    )
    return {
        "id": story_id,
        "story_type": story_type,
        "headline": headline,
        "hook": hook,
        "evidence": evidence,
        "caveat": caveat,
        "caption": caption,
        "magnitude": magnitude,
        "score": round(float(score), 1),
        "score_explanation": "Heuristic editorial priority: relative strength within this story type plus a small format bonus. It is not a measure of sporting importance.",
        "approved": False,
        "status": "Needs review",
    }


def build_editorial_queue(*, event_name: str, season: int, session_name: str,
                          driver_a: str, driver_b: str, lap_a: int, lap_b: int,
                          lap_time_a: Any, lap_time_b: Any,
                          sectors: pd.DataFrame | None = None,
                          corners: pd.DataFrame | None = None,
                          max_stories: int = 12) -> list[dict[str, Any]]:
    """Build a ranked, evidence-grounded editorial queue from loaded session metrics.

    Scores rank findings for review; they do not estimate sporting significance.
    No telemetry values are inferred when the corresponding field is missing.
    """
    context = {"event_name": event_name, "season": int(season), "session_name": session_name,
               "driver_a": driver_a, "driver_b": driver_b, "lap_a": lap_a, "lap_b": lap_b}
    candidates: list[dict[str, Any]] = []

    time_a, time_b = _number(lap_time_a), _number(lap_time_b)
    if math.isfinite(time_a) and math.isfinite(time_b):
        delta = time_a - time_b
        if abs(delta) < 0.001:
            headline = f"{driver_a} and {driver_b}: a near-even lap-time comparison"
            hook = "The selected lap times are equal to within 0.001 seconds. What do the sector and corner measurements show?"
            evidence = [f"{driver_a}, lap {lap_a}: {_format_time(time_a)}.",
                        f"{driver_b}, lap {lap_b}: {_format_time(time_b)}.",
                        f"Lap-time difference (A − B): {delta:+.3f} s."]
        else:
            faster, slower = (driver_a, driver_b) if delta < 0 else (driver_b, driver_a)
            headline = f"Where did {faster} find the lap-time advantage?"
            hook = f"On these selected laps, {faster} was quicker overall. The next question is where the difference appears—not what caused it."
            evidence = [f"{driver_a}, lap {lap_a}: {_format_time(time_a)}.",
                        f"{driver_b}, lap {lap_b}: {_format_time(time_b)}.",
                        f"Lap-time difference (A − B): {delta:+.3f} s; {faster} was quicker by {abs(delta):.3f} s."]
        candidates.append(_make_candidate(
            context=context, story_type="Lap comparison", source_key="lap-time",
            headline=headline, hook=hook, evidence=evidence,
            caveat="This compares the two selected laps only. It does not control for tyre age, fuel load, traffic, track evolution, yellow flags or setup.",
            magnitude=abs(delta), score=78.0 + min(abs(delta), 2.0) * 2.0,
        ))

    sector_rows: list[dict[str, Any]] = []
    if sectors is not None and not sectors.empty:
        for _, row in sectors.iterrows():
            delta = _number(row.get("delta_A_minus_B_s"))
            if math.isfinite(delta):
                sector_rows.append({"sector": str(row.get("sector", "Sector")), "delta": delta})
    if sector_rows:
        max_magnitude = max(abs(row["delta"]) for row in sector_rows) or 1.0
        for row in sector_rows:
            delta = row["delta"]
            if abs(delta) < 0.001:
                headline = f"{row['sector']}: {driver_a} and {driver_b} are nearly level"
                hook = "The official sector times show little separation at the displayed precision. Check the other sectors for a larger difference."
            else:
                faster, slower = (driver_a, driver_b) if delta < 0 else (driver_b, driver_a)
                headline = f"{row['sector']}: {faster} is {abs(delta):.3f} s quicker"
                hook = f"This sector is one measured piece of the lap. Compare the telemetry to investigate where the difference develops."
            evidence = [f"Official sector time difference (A − B): {delta:+.3f} s."]
            a_s, b_s = _number(next((x.get("time_A_s") for x in sectors.to_dict("records") if str(x.get("sector")) == row["sector"]), math.nan)), _number(next((x.get("time_B_s") for x in sectors.to_dict("records") if str(x.get("sector")) == row["sector"]), math.nan))
            if math.isfinite(a_s): evidence.append(f"{driver_a} sector time: {a_s:.3f} s.")
            if math.isfinite(b_s): evidence.append(f"{driver_b} sector time: {b_s:.3f} s.")
            score = 60.0 + 30.0 * abs(delta) / max_magnitude + 3.0
            candidates.append(_make_candidate(
                context=context, story_type="Sector comparison", source_key=row["sector"],
                headline=headline, hook=hook, evidence=evidence,
                caveat="Sector timing identifies where elapsed time differs, but does not identify the driving input or prove a cause. Conditions and lap context may differ.",
                magnitude=abs(delta), score=score,
            ))

    corner_rows: list[dict[str, Any]] = []
    if corners is not None and not corners.empty:
        for _, row in corners.iterrows():
            speed_delta = _number(row.get("minimum_speed_advantage_A_minus_B_kmh"))
            time_delta = _number(row.get("delta_A_minus_B_s"))
            if math.isfinite(speed_delta) or math.isfinite(time_delta):
                corner_rows.append({"corner": str(row.get("corner", "Corner")), "speed_delta": speed_delta, "time_delta": time_delta})
    max_speed = max((abs(r["speed_delta"]) for r in corner_rows if math.isfinite(r["speed_delta"])), default=0.0) or 1.0
    max_delta = max((abs(r["time_delta"]) for r in corner_rows if math.isfinite(r["time_delta"])), default=0.0) or 1.0
    for row in corner_rows:
        speed_delta, time_delta = row["speed_delta"], row["time_delta"]
        evidence: list[str] = []
        if math.isfinite(speed_delta):
            if abs(speed_delta) < 0.05:
                evidence.append(f"Sampled minimum speeds at {row['corner']} were equal to displayed precision.")
            else:
                higher = driver_a if speed_delta > 0 else driver_b
                evidence.append(f"{higher} had a {abs(speed_delta):.1f} km/h higher sampled minimum speed near {row['corner']}.")
        if math.isfinite(time_delta):
            ahead = driver_a if time_delta < 0 else driver_b
            evidence.append(f"Elapsed-time delta (A − B) at the {row['corner']} marker: {time_delta:+.3f} s; {ahead} was ahead at that sampled marker when the delta is non-zero.")
        headline = f"Corner comparison: what stands out at {row['corner']}?"
        hook = "The sampled speed and elapsed-time measurements give us a focused place to investigate—but not a complete explanation by themselves."
        score = 57.0
        if math.isfinite(speed_delta): score += 25.0 * abs(speed_delta) / max_speed
        if math.isfinite(time_delta): score += 15.0 * abs(time_delta) / max_delta
        candidates.append(_make_candidate(
            context=context, story_type="Corner comparison", source_key=row["corner"],
            headline=headline, hook=hook, evidence=evidence,
            caveat="FastF1 corner markers are approximate references, not guaranteed apex locations. Minimum speed is sampled in a window around the marker; elapsed-time delta at a marker is not time lost solely in that corner. Neither metric proves a cause.",
            magnitude=max(abs(speed_delta) if math.isfinite(speed_delta) else 0.0, abs(time_delta) if math.isfinite(time_delta) else 0.0),
            score=score,
        ))

    candidates.sort(key=lambda item: (item["score"], item["story_type"], item["headline"]), reverse=True)
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank
    return candidates[:max(1, int(max_stories))]


def export_editorial_queue(stories: list[dict[str, Any]], *, approved_only: bool = False) -> dict[str, Any]:
    """Package story drafts for human review; this function never publishes them."""
    selected = [story for story in stories if story.get("approved")] if approved_only else list(stories)
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("editorial-queue.csv", pd.DataFrame([
            {"rank": s.get("rank"), "score": s.get("score"), "status": s.get("status"),
             "story_type": s.get("story_type"), "headline": s.get("headline"),
             "evidence": " | ".join(s.get("evidence", [])), "caveat": s.get("caveat", "")}
            for s in selected
        ]).to_csv(index=False))
        for index, story in enumerate(selected, start=1):
            filename = f"draft-{index:02d}-{_slug(story.get('headline', 'story'))}.md"
            body = (f"# {story.get('headline', 'Untitled story')}\n\n"
                    f"**Review status:** {story.get('status', 'Needs review')}\n\n"
                    f"**Editorial priority:** {story.get('score', 'N/A')} / heuristic score\n\n"
                    f"{story.get('caption', '')}\n\n---\n\n"
                    f"**Evidence caveat:** {story.get('caveat', '')}\n")
            archive.writestr(filename, body)
        archive.writestr("README.txt", "Editorial drafts generated from the selected loaded session data. Human review is required. Approval is a local workflow state only; no social platform API is called and nothing is published automatically. Verify every claim and source/platform terms before publishing.\n")
    return {"zip_bytes": buffer.getvalue(), "count": len(selected),
            "zip_name": "apex-telemetry-approved-drafts.zip" if approved_only else "apex-telemetry-editorial-queue.zip"}
