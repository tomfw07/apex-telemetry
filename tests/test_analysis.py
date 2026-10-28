import numpy as np
import pandas as pd
import pytest

from src.analysis import compare_telemetry, compare_corners, detect_events, prepare_energy_data, summarize_lap


def sample(distance_offset=0.0):
    return pd.DataFrame({
        "Distance": np.array([0, 10, 20, 30, 40, 50], dtype=float) + distance_offset,
        "Speed": [100, 120, 130, 90, 70, 110],
        "Throttle": [10, 80, 100, 10, 5, 90],
        "Brake": [0, 0, 0, 1, 1, 0],
        "nGear": [2, 3, 4, 3, 2, 3],
        "Time": pd.to_timedelta([0, 1, 2, 3, 4, 5], unit="s"),
    })


def test_compare_telemetry_has_common_distance_grid():
    result = compare_telemetry(sample(), sample(), points=100)
    assert len(result) == 100
    assert result["Distance"].is_monotonic_increasing
    assert np.nanmax(np.abs(result["Delta_A_minus_B"])) < 1e-8


def test_summary_returns_speed_metrics():
    result = summarize_lap(sample())
    assert result["min_speed"] == 70
    assert result["max_speed"] == 130
    assert result["distance_m"] == 50


def test_event_detection_finds_braking_and_throttle_pickup():
    result = detect_events(sample(), "AAA", brake_min_samples=2)
    assert "Brake onset" in result["event"].tolist()
    assert "Throttle pickup" in result["event"].tolist()
    assert (result["driver"] == "AAA").all()


def test_energy_data_requires_distance():
    with pytest.raises(ValueError):
        prepare_energy_data(pd.DataFrame({"BatterySOC": [50]}))


def test_energy_data_rejects_unknown_only_channels():
    result = prepare_energy_data(pd.DataFrame({"Distance": [0, 1], "Speed": [100, 110]}))
    assert result.empty


def test_energy_data_keeps_documented_measurements():
    result = prepare_energy_data(pd.DataFrame({
        "Distance": [0, 10], "BatterySOC": [55, 54],
        "DeploymentPower_kW": [100, 200]
    }))
    assert list(result.columns) == ["Distance", "BatterySOC", "DeploymentPower_kW"]
    assert len(result) == 2


def test_corner_comparison_reports_speed_and_delta():
    comparison = compare_telemetry(sample(), sample(), points=100)
    corners = pd.DataFrame({"Number": [1, 2], "Letter": ["", ""], "Distance": [20, 40]})
    result = compare_corners(comparison, corners)
    assert result["corner"].tolist() == ["T1", "T2"]
    assert "minimum_speed_A_kmh" in result.columns
    assert np.allclose(result["minimum_speed_advantage_A_minus_B_kmh"], 0, equal_nan=True)
    assert np.allclose(result["delta_A_minus_B_s"], 0, atol=1e-6, equal_nan=True)

def test_corner_comparison_handles_missing_markers():
    comparison = compare_telemetry(sample(), sample(), points=100)
    result = compare_corners(comparison, pd.DataFrame({"Distance": []}))
    assert result.empty


def test_track_figure_handles_position_data():
    from src.plots import track_figure

    telemetry_a = sample().assign(X=[0, 10, 20, 30, 40, 50], Y=[0, 5, 10, 5, 0, -5])
    telemetry_b = sample().assign(X=[0, 11, 21, 31, 41, 51], Y=[0, 4, 9, 4, -1, -6])
    corners = pd.DataFrame({"Number": [1], "Letter": [""], "X": [20], "Y": [10]})
    fig = track_figure(telemetry_a, telemetry_b, corners, "AAA", "BBB")
    assert fig is not None
    assert len(fig.data) == 3


def test_track_figure_returns_none_without_position_data():
    from src.plots import track_figure

    fig = track_figure(sample(), sample(), pd.DataFrame(), "AAA", "BBB")
    assert fig is None


def test_performance_report_identifies_faster_driver_and_exports_html():
    from src.report import build_performance_report

    result = build_performance_report(
        event_name="Example GP", season=2025, session_name="Race",
        driver_a="AAA", driver_b="BBB", lap_a=10, lap_b=11,
        lap_time_a=90.0, lap_time_b=91.2,
        summary_a={"min_speed": 70, "max_speed": 320},
        summary_b={"min_speed": 68, "max_speed": 318},
        sectors=pd.DataFrame([
            {"sector": "Sector 1", "time_A_s": 28.0, "time_B_s": 28.4, "delta_A_minus_B_s": -0.4},
            {"sector": "Sector 2", "time_A_s": 31.0, "time_B_s": 30.8, "delta_A_minus_B_s": 0.2},
        ]),
        corners=pd.DataFrame([{
            "corner": "T1", "distance_m": 500, "delta_A_minus_B_s": -0.15,
            "minimum_speed_advantage_A_minus_B_kmh": 3.0,
        }]),
    )
    assert result["lap_delta_s"] == pytest.approx(-1.2)
    assert any("AAA was quicker overall" in item for item in result["findings"])
    assert "Driver Performance Report" in result["html"]
    assert "Sector 1" in result["html"]
    assert "Methodology and limitations" in result["html"]


def test_performance_report_escapes_untrusted_names_and_handles_missing_times():
    from src.report import build_performance_report

    result = build_performance_report(
        event_name="<script>alert(1)</script>", season=2025, session_name="Race",
        driver_a="A<AA>", driver_b="BBB", lap_a=1, lap_b=2,
        lap_time_a=pd.NaT, lap_time_b=pd.NaT,
        summary_a={}, summary_b={},
    )
    assert "<script>alert(1)</script>" not in result["html"]
    assert "&lt;script&gt;" in result["html"]
    assert "Unavailable" in result["html"]
