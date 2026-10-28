from io import BytesIO
from zipfile import ZipFile

import pandas as pd
from PIL import Image

from src.social_content import build_instagram_carousel


def sample_corners():
    return pd.DataFrame([
        {
            "corner": "T1", "distance_m": 500,
            "minimum_speed_A_kmh": 122.0, "minimum_speed_B_kmh": 118.0,
            "minimum_speed_advantage_A_minus_B_kmh": 4.0,
            "delta_A_minus_B_s": -0.12,
            "brake_onset_A_m": 420, "brake_onset_B_m": 430,
        },
        {
            "corner": "T2", "distance_m": 900,
            "minimum_speed_A_kmh": 91.0, "minimum_speed_B_kmh": 95.0,
            "minimum_speed_advantage_A_minus_B_kmh": -4.0,
            "delta_A_minus_B_s": 0.08,
            "brake_onset_A_m": 820, "brake_onset_B_m": 810,
        },
    ])


def test_instagram_carousel_contains_five_valid_portrait_pngs_and_caption():
    result = build_instagram_carousel(
        event_name="Example Grand Prix", season=2025, session_name="Qualifying",
        driver_a="AAA", driver_b="BBB", lap_a=5, lap_b=6,
        lap_time_a=90.1, lap_time_b=90.5, corners=sample_corners(),
    )
    assert len(result["slides"]) == 5
    for filename, content in result["slides"]:
        assert filename.endswith(".png")
        image = Image.open(BytesIO(content))
        assert image.size == (1080, 1350)
    assert "AAA was faster by 0.400 s" in result["caption"]
    assert "T1" in result["caption"] or "T2" in result["caption"]
    assert "not confirmed causes" in result["caption"]


def test_zip_contains_ordered_slides_caption_and_corner_csv():
    result = build_instagram_carousel(
        event_name="Example GP", season=2025, session_name="Race",
        driver_a="AAA", driver_b="BBB", lap_a=1, lap_b=2,
        lap_time_a=91.0, lap_time_b=92.0, corners=sample_corners(),
    )
    with ZipFile(BytesIO(result["zip_bytes"])) as archive:
        names = archive.namelist()
    assert names[:5] == [f"slide-{i:02d}.png" for i in range(1, 6)]
    assert "caption.txt" in names
    assert "corner-data.csv" in names
    assert "README.txt" in names


def test_missing_corner_data_does_not_invent_measurements():
    result = build_instagram_carousel(
        event_name="Example GP", season=2025, session_name="Race",
        driver_a="AAA", driver_b="BBB", lap_a=1, lap_b=2,
        lap_time_a=float("nan"), lap_time_b=float("nan"), corners=pd.DataFrame(),
    )
    assert "No valid sampled corner minimum-speed differences were available" in result["caption"]
    assert "Lap time unavailable" not in result["caption"]
    cover = Image.open(BytesIO(result["slides"][0][1]))
    assert cover.size == (1080, 1350)


def test_caption_escapes_or_treats_session_text_as_plain_text():
    result = build_instagram_carousel(
        event_name="Example <GP>", season=2025, session_name="Race",
        driver_a="AAA", driver_b="BBB", lap_a=1, lap_b=2,
        lap_time_a=90.0, lap_time_b=90.0, corners=sample_corners(),
    )
    # The caption is plain text rather than HTML; untrusted text remains literal text.
    assert "Example <GP>" in result["caption"]
