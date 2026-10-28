from io import BytesIO
from zipfile import ZipFile

import pandas as pd

from src.editorial import build_editorial_queue, export_editorial_queue


def sample_sectors():
    return pd.DataFrame([
        {"sector": "Sector 1", "time_A_s": 28.1, "time_B_s": 28.4, "delta_A_minus_B_s": -0.3},
        {"sector": "Sector 2", "time_A_s": 31.2, "time_B_s": 31.0, "delta_A_minus_B_s": 0.2},
    ])


def sample_corners():
    return pd.DataFrame([
        {"corner": "T1", "minimum_speed_advantage_A_minus_B_kmh": 4.2, "delta_A_minus_B_s": -0.12},
        {"corner": "T2", "minimum_speed_advantage_A_minus_B_kmh": -2.0, "delta_A_minus_B_s": 0.08},
    ])


def test_queue_contains_only_data_supported_story_claims_and_stable_ids():
    args = dict(event_name="Example GP", season=2025, session_name="Qualifying",
                driver_a="AAA", driver_b="BBB", lap_a=5, lap_b=6,
                lap_time_a=90.1, lap_time_b=90.5,
                sectors=sample_sectors(), corners=sample_corners())
    queue = build_editorial_queue(**args)
    assert queue
    assert [x["rank"] for x in queue] == list(range(1, len(queue) + 1))
    assert len({x["id"] for x in queue}) == len(queue)
    assert any("0.400 s" in " ".join(x["evidence"]) for x in queue)
    assert all("doesn't prove" in x["caption"].lower() for x in queue)
    assert queue == build_editorial_queue(**args)


def test_missing_values_do_not_create_lap_story_or_fake_corner_numbers():
    queue = build_editorial_queue(event_name="Example GP", season=2025, session_name="Race",
                                  driver_a="AAA", driver_b="BBB", lap_a=1, lap_b=2,
                                  lap_time_a=float("nan"), lap_time_b=float("nan"),
                                  sectors=pd.DataFrame(), corners=pd.DataFrame([
                                      {"corner": "T1", "minimum_speed_advantage_A_minus_B_kmh": float("nan"), "delta_A_minus_B_s": float("nan")}
                                  ]))
    assert not any(x["story_type"] == "Lap comparison" for x in queue)
    assert not any(x["story_type"] == "Corner comparison" for x in queue)


def test_approved_export_contains_only_approved_drafts():
    queue = build_editorial_queue(event_name="Example GP", season=2025, session_name="Race",
                                  driver_a="AAA", driver_b="BBB", lap_a=1, lap_b=2,
                                  lap_time_a=91.0, lap_time_b=92.0)
    queue[0]["approved"] = True
    queue[0]["status"] = "Approved for publishing"
    export = export_editorial_queue(queue, approved_only=True)
    with ZipFile(BytesIO(export["zip_bytes"])) as archive:
        names = archive.namelist()
        readme = archive.read("README.txt").decode()
    assert export["count"] == 1
    assert any(name.endswith(".md") for name in names)
    assert "nothing is published automatically" in readme.lower()
