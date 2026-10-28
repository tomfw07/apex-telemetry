from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from html import escape
import math
import re
from typing import Any

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1350
BG = (12, 18, 29)
PANEL = (24, 34, 50)
WHITE = (245, 248, 252)
MUTED = (169, 184, 204)
CYAN = (76, 211, 255)
ORANGE = (255, 177, 92)
GREEN = (111, 224, 174)
RED = (255, 118, 128)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates += ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"]
    candidates += ["DejaVuSans.ttf", "arial.ttf", "Arial.ttf"]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value)).strip("-").lower()
    return slug[:48] or "f1-session"


def _number(value: Any) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else math.nan
    except (TypeError, ValueError):
        return math.nan


def _fmt_time(value: Any) -> str:
    try:
        if value is None or pd.isna(value):
            return "N/A"
        seconds = float(value.total_seconds() if hasattr(value, "total_seconds") else value)
    except (TypeError, ValueError):
        return "N/A"
    if not math.isfinite(seconds):
        return "N/A"
    minutes, remainder = divmod(max(seconds, 0), 60)
    return f"{int(minutes)}:{remainder:06.3f}" if minutes else f"{remainder:.3f} s"


def _new_slide(kicker: str, title: str, subtitle: str = "") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    # Branded accent rails and header
    draw.rectangle((0, 0, WIDTH, 14), fill=CYAN)
    draw.text((72, 56), "APEX TELEMETRY  /  DATA EXPLAINED", font=_font(25, True), fill=CYAN)
    draw.text((72, 112), kicker.upper(), font=_font(22, True), fill=ORANGE)
    draw.multiline_text((72, 160), title, font=_font(55, True), fill=WHITE, spacing=6)
    if subtitle:
        draw.multiline_text((74, 300), subtitle, font=_font(25), fill=MUTED, spacing=7)
    draw.line((72, 1240, WIDTH - 72, 1240), fill=(54, 69, 89), width=2)
    draw.text((72, 1265), "PUBLIC SESSION DATA  ·  DESCRIPTIVE, NOT CAUSAL", font=_font(17, True), fill=MUTED)
    return image, draw


def _rounded_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill=PANEL) -> None:
    draw.rounded_rectangle(box, radius=22, fill=fill)


def _wrap(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _write_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _draw_speed_chart(image: Image.Image, corners: pd.DataFrame, driver_a: str, driver_b: str) -> None:
    draw = ImageDraw.Draw(image)
    chart = corners.copy()
    chart["speed_delta"] = pd.to_numeric(chart.get("minimum_speed_advantage_A_minus_B_kmh"), errors="coerce")
    chart = chart.dropna(subset=["speed_delta"])
    chart["abs_delta"] = chart["speed_delta"].abs()
    chart = chart.sort_values("abs_delta", ascending=False).head(5).sort_values("speed_delta")
    if chart.empty:
        _rounded_panel(draw, (72, 370, 1008, 1080))
        draw.text((110, 420), "Not enough valid corner-speed data", font=_font(30, True), fill=WHITE)
        draw.text((110, 475), "No measurements were invented to fill the gap.", font=_font(23), fill=MUTED)
        return
    _rounded_panel(draw, (72, 370, 1008, 1080))
    draw.text((108, 405), "Largest measured minimum-speed differences", font=_font(27, True), fill=WHITE)
    draw.text((108, 450), f"Positive = {driver_a} higher · Negative = {driver_b} higher", font=_font(19), fill=MUTED)
    left, right = 380, 915
    center = (left + right) // 2
    max_abs = max(1.0, float(chart["abs_delta"].max()))
    row_y = 520
    for _, row in chart.iterrows():
        label = str(row.get("corner", "Corner"))
        delta = float(row["speed_delta"])
        draw.text((110, row_y - 5), label[:12], font=_font(23, True), fill=WHITE)
        draw.line((left, row_y + 18, right, row_y + 18), fill=(53, 68, 87), width=12)
        draw.line((center, row_y + 4, center, row_y + 33), fill=(215, 225, 238), width=2)
        bar_len = int((abs(delta) / max_abs) * ((right - left) // 2 - 8))
        color = CYAN if delta >= 0 else ORANGE
        if delta >= 0:
            draw.rounded_rectangle((center, row_y + 9, center + bar_len, row_y + 27), radius=8, fill=color)
            text_x = min(center + bar_len + 10, right - 90)
        else:
            draw.rounded_rectangle((center - bar_len, row_y + 9, center, row_y + 27), radius=8, fill=color)
            text_x = max(center - bar_len - 92, left)
        draw.text((text_x, row_y - 18), f"{delta:+.1f} km/h", font=_font(18, True), fill=color)
        row_y += 100
    draw.text((108, 1030), "These are sampled speeds around approximate circuit markers, not exact apex speeds.", font=_font(17), fill=MUTED)


def build_instagram_carousel(*, event_name: str, season: int, session_name: str,
                             driver_a: str, driver_b: str, lap_a: int, lap_b: int,
                             lap_time_a: Any, lap_time_b: Any,
                             corners: pd.DataFrame | None) -> dict[str, Any]:
    """Build an Instagram-ready 4:5 PNG carousel and factual caption from loaded data.

    Every numeric claim comes from supplied session/lap/corner measurements. Explanations
    are framed as questions to investigate, never asserted as causes.
    """
    corner_df = corners.copy() if corners is not None else pd.DataFrame()
    if not corner_df.empty:
        for column in ["minimum_speed_advantage_A_minus_B_kmh", "delta_A_minus_B_s", "distance_m"]:
            if column in corner_df:
                corner_df[column] = pd.to_numeric(corner_df[column], errors="coerce")
    time_a, time_b = _number(lap_time_a.total_seconds() if hasattr(lap_time_a, "total_seconds") else lap_time_a), _number(lap_time_b.total_seconds() if hasattr(lap_time_b, "total_seconds") else lap_time_b)
    lap_delta = time_a - time_b if math.isfinite(time_a) and math.isfinite(time_b) else math.nan

    # Slide 1: cover, with no inferred claims.
    slide1, d1 = _new_slide("Corner comparison", "WHERE IS THE\nSPEED DIFFERENCE?", f"{event_name} · {season}\n{session_name} · selected laps {lap_a} and {lap_b}")
    _rounded_panel(d1, (72, 455, 1008, 800))
    d1.text((112, 500), driver_a, font=_font(34, True), fill=CYAN)
    d1.text((112, 555), f"Lap {lap_a}  ·  {_fmt_time(lap_time_a)}", font=_font(25), fill=WHITE)
    d1.text((112, 635), driver_b, font=_font(34, True), fill=ORANGE)
    d1.text((112, 690), f"Lap {lap_b}  ·  {_fmt_time(lap_time_b)}", font=_font(25), fill=WHITE)
    if math.isfinite(lap_delta):
        who = f"{driver_a} quicker" if lap_delta < 0 else (f"{driver_b} quicker" if lap_delta > 0 else "Lap times tied")
        delta_line = f"{who} by {abs(lap_delta):.3f} s" if abs(lap_delta) >= 0.0005 else "Lap times equal to displayed precision"
        d1.text((112, 740), delta_line, font=_font(24, True), fill=GREEN if lap_delta < 0 else ORANGE)
    else:
        d1.text((112, 740), "Comparable lap time unavailable", font=_font(23, True), fill=MUTED)

    # Slide 2: explain what was actually measured.
    slide2, d2 = _new_slide("Read the data", "A LAP TIME IS\nMORE THAN ONE CORNER", "This comparison uses the selected laps from the loaded FastF1 session.")
    cards = [
        ("01", "Lap time", "The overall elapsed time for each selected lap."),
        ("02", "Minimum speed", "The lowest sampled speed inside a window around each circuit marker."),
        ("03", "Time delta", "Elapsed-time difference at the marker distance, where available."),
    ]
    y = 430
    for number, title, body in cards:
        _rounded_panel(d2, (72, y, 1008, y + 185))
        d2.text((105, y + 30), number, font=_font(32, True), fill=CYAN)
        d2.text((190, y + 28), title, font=_font(28, True), fill=WHITE)
        for i, line in enumerate(_wrap(body, _font(22), 740, d2)):
            d2.text((190, y + 78 + i * 31), line, font=_font(22), fill=MUTED)
        y += 205

    # Slide 3: measured comparison chart.
    slide3, _ = _new_slide("Measured comparison", "THE BIGGEST\nSPEED DIFFERENCES", f"{driver_a} minus {driver_b} · km/h")
    _draw_speed_chart(slide3, corner_df, driver_a, driver_b)

    # Slide 4: grounded observations plus questions, not causal assertions.
    slide4, d4 = _new_slide("Engineering interpretation", "WHAT SHOULD WE\nINVESTIGATE NEXT?", "Use the measurements to ask better questions—not to guess at the cause.")
    _rounded_panel(d4, (72, 390, 1008, 1000))
    valid_speed = pd.DataFrame()
    if not corner_df.empty and "minimum_speed_advantage_A_minus_B_kmh" in corner_df:
        valid_speed = corner_df.dropna(subset=["minimum_speed_advantage_A_minus_B_kmh"]).copy()
    statements: list[tuple[str, str]] = []
    if not valid_speed.empty:
        max_idx = valid_speed["minimum_speed_advantage_A_minus_B_kmh"].idxmax()
        min_idx = valid_speed["minimum_speed_advantage_A_minus_B_kmh"].idxmin()
        row_a = valid_speed.loc[max_idx]
        row_b = valid_speed.loc[min_idx]
        delta_a = float(row_a["minimum_speed_advantage_A_minus_B_kmh"])
        delta_b = float(row_b["minimum_speed_advantage_A_minus_B_kmh"])
        statements.append(("OBSERVED", f"{driver_a} had the higher sampled minimum speed at {row_a.get('corner', 'a marker')} by {delta_a:.1f} km/h." if delta_a > 0 else f"The largest measured minimum-speed difference was {delta_a:+.1f} km/h at {row_a.get('corner', 'a marker')}."))
        statements.append(("OBSERVED", f"{driver_b} had the higher sampled minimum speed at {row_b.get('corner', 'a marker')} by {abs(delta_b):.1f} km/h." if delta_b < 0 else f"The lowest measured difference was {delta_b:+.1f} km/h at {row_b.get('corner', 'a marker')}."))
    else:
        statements.append(("DATA LIMIT", "No valid corner minimum-speed differences were available for these selected laps."))
    statements.append(("QUESTION", "Do braking onset, throttle pickup and exit speed show a consistent pattern at these markers?"))
    statements.append(("QUESTION", "Could tyre age, traffic, track evolution or setup explain some of the difference? Those factors are not established by this chart."))
    y = 430
    for label, text in statements:
        color = CYAN if label == "OBSERVED" else ORANGE
        d4.text((112, y), label, font=_font(19, True), fill=color)
        for i, line in enumerate(_wrap(text, _font(23), 820, d4)):
            d4.text((112, y + 36 + i * 34), line, font=_font(23), fill=WHITE)
        y += 125 if len(_wrap(text, _font(23), 820, d4)) < 2 else 155

    # Slide 5: methods and transparency.
    slide5, d5 = _new_slide("Methodology", "WHAT THIS DATA\nCAN—and CAN'T—SAY", "A credible engineering explanation includes its limits.")
    _rounded_panel(d5, (72, 390, 1008, 1090))
    notes = [
        ("DATA", "Public FastF1 telemetry and timing data for the selected session and laps."),
        ("APPROXIMATION", "Corner labels are circuit references; sampled minimum speed is measured in a window around each marker."),
        ("NOT CAUSATION", "A speed or time difference does not prove why a driver gained or lost time."),
        ("NOT INCLUDED", "No battery state-of-charge or direct MGU-K power is inferred from throttle or speed."),
    ]
    y = 435
    for label, body in notes:
        d5.text((112, y), label, font=_font(20, True), fill=CYAN if label == "DATA" else ORANGE)
        for i, line in enumerate(_wrap(body, _font(22), 800, d5)):
            d5.text((112, y + 36 + i * 31), line, font=_font(22), fill=WHITE)
        y += 145

    slides = [slide1, slide2, slide3, slide4, slide5]
    filenames = [f"slide-{i:02d}.png" for i in range(1, len(slides) + 1)]
    pngs = [_write_png(img) for img in slides]

    facts = [f"{event_name} {season} {session_name}: {driver_a} lap {lap_a} vs {driver_b} lap {lap_b}."]
    if math.isfinite(time_a) and math.isfinite(time_b):
        if abs(lap_delta) < 0.0005:
            facts.append(f"Selected lap times: {driver_a} {_fmt_time(lap_time_a)}; {driver_b} {_fmt_time(lap_time_b)} (equal to displayed precision).")
        else:
            faster, slower = (driver_a, driver_b) if lap_delta < 0 else (driver_b, driver_a)
            facts.append(f"Selected lap times: {driver_a} {_fmt_time(lap_time_a)}; {driver_b} {_fmt_time(lap_time_b)}. {faster} was faster by {abs(lap_delta):.3f} s on these selected laps.")
    valid = pd.DataFrame()
    if not corner_df.empty and "minimum_speed_advantage_A_minus_B_kmh" in corner_df:
        valid = corner_df.dropna(subset=["minimum_speed_advantage_A_minus_B_kmh"])
    if not valid.empty:
        strongest = valid.loc[valid["minimum_speed_advantage_A_minus_B_kmh"].abs().idxmax()]
        delta = float(strongest["minimum_speed_advantage_A_minus_B_kmh"])
        faster_min = driver_a if delta > 0 else driver_b if delta < 0 else "Neither driver"
        facts.append(f"Largest absolute sampled minimum-speed difference: {abs(delta):.1f} km/h at {strongest.get('corner', 'a circuit marker')}, favouring {faster_min} for this measurement." if delta != 0 else f"No minimum-speed difference at the largest-difference marker ({strongest.get('corner', 'marker')}) to displayed precision.")
    else:
        facts.append("No valid sampled corner minimum-speed differences were available; no corner-speed claim is made.")
    facts.append("Interpretation prompt: compare brake onset, throttle pickup and exit speed before proposing an explanation. Traffic, tyres, track evolution and setup are possible confounders, not confirmed causes.")
    facts.append("Method: public FastF1 data; corner references and local speed windows are approximate. Not official team telemetry.")
    caption = "\n\n".join(facts) + "\n\n#F1 #Formula1 #Motorsport #Telemetry #RaceEngineering #DataAnalysis"

    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, "w", compression=ZIP_DEFLATED) as archive:
        for filename, payload in zip(filenames, pngs):
            archive.writestr(filename, payload)
        archive.writestr("caption.txt", caption)
        archive.writestr("README.txt", "Instagram carousel export: upload slide-01.png through slide-05.png in order. Review the caption and verify session context before publishing. Values are generated from the selected session data; corner markers are approximate and observations are not causal claims.\n")
        if not corner_df.empty:
            archive.writestr("corner-data.csv", corner_df.to_csv(index=False))
    return {
        "slides": list(zip(filenames, pngs)),
        "caption": caption,
        "zip_bytes": zip_buffer.getvalue(),
        "zip_name": f"instagram-corner-carousel-{_safe_slug(event_name)}-{season}-{_safe_slug(driver_a)}-{_safe_slug(driver_b)}.zip",
    }
