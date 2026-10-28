from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import fastf1
import pandas as pd

from src.data_loader import load_session, available_drivers, available_laps, get_lap_telemetry
from src.analysis import compare_telemetry, summarize_lap, detect_events, prepare_energy_data, compare_corners
from src.plots import telemetry_figure, delta_figure, event_table_figure, energy_figure, corner_min_speed_figure, track_figure, sector_comparison_figure
from src.report import build_performance_report
from src.social_content import build_instagram_carousel
from src.editorial import build_editorial_queue, export_editorial_queue



EDITORIAL_STATE_PATH = Path(__file__).resolve().parent / "output" / "editorial_state.json"

def _load_editorial_state() -> dict:
    try:
        return json.loads(EDITORIAL_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"approvals": {}, "captions": {}}

def _save_editorial_state(approvals: dict, captions: dict) -> None:
    try:
        EDITORIAL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EDITORIAL_STATE_PATH.write_text(
            json.dumps({"approvals": approvals, "captions": captions}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        st.warning(f"Editorial state could not be saved locally: {exc}")


st.set_page_config(page_title="F1 Telemetry Lab", page_icon="🏎️", layout="wide")
st.title("🏎️ F1 Telemetry & Energy Analysis")
st.caption("Compare laps, investigate braking and cornering, and inspect energy data only where measurements support it.")

with st.sidebar:
    st.header("Session")
    year = st.number_input("Season", min_value=2018, max_value=2026, value=2025, step=1)
    try:
        schedule = fastf1.get_event_schedule(int(year), include_testing=False)
        event_names = schedule["EventName"].dropna().tolist()
    except Exception as exc:
        st.error(f"Could not load the {year} schedule. Check your connection and FastF1 installation.")
        st.exception(exc)
        st.stop()

    event_name = st.selectbox("Grand Prix", event_names)
    session_name = st.selectbox("Session", ["Practice 1", "Practice 2", "Practice 3", "Qualifying", "Sprint", "Race"])
    load_button = st.button("Load session", type="primary", use_container_width=True)

if "session_key" not in st.session_state:
    st.session_state.session_key = None
if load_button:
    with st.spinner("Loading session data from FastF1. The first load may take a while..."):
        try:
            session = load_session(int(year), event_name, session_name)
            st.session_state.session_obj = session
            st.session_state.session_key = f"{year}|{event_name}|{session_name}"
        except Exception as exc:
            st.error("FastF1 could not load this session. Some sessions may not have data yet, and upstream data can occasionally be unavailable.")
            st.exception(exc)
            st.stop()

if st.session_state.session_key is None:
    st.info("Choose a season, Grand Prix and session in the sidebar, then select **Load session**.")
    st.markdown("""
    **What this app analyses**
    - Speed, throttle, brake, gear and derived acceleration against distance.
    - Estimated brake onset, throttle pickup and minimum-speed events.
    - Lap-time delta between two selected laps.
    - Optional externally supplied energy measurements, with units explicitly declared.
    """)
    st.stop()

session = st.session_state.session_obj
drivers = available_drivers(session)
if len(drivers) < 2:
    st.warning("This session does not contain enough drivers with timing data to compare.")
    st.stop()

st.caption(f"{session.event['EventName']} · {session.name} · {session.event['EventDate'].strftime('%Y') if pd.notna(session.event.get('EventDate')) else year}")
c1, c2 = st.columns(2)
with c1:
    driver_a = st.selectbox("Driver A", drivers, index=0, format_func=lambda d: f"{d} — {session.get_driver(d).get('Abbreviation', d)}")
with c2:
    default_b = 1 if len(drivers) > 1 else 0
    driver_b = st.selectbox("Driver B", drivers, index=default_b, format_func=lambda d: f"{d} — {session.get_driver(d).get('Abbreviation', d)}")

if driver_a == driver_b:
    st.warning("Choose two different drivers.")
    st.stop()

laps_a = available_laps(session, driver_a)
laps_b = available_laps(session, driver_b)
if not laps_a or not laps_b:
    st.warning("No usable laps were found for one or both selected drivers.")
    st.stop()

la, lb = st.columns(2)
with la:
    lap_num_a = st.selectbox("Driver A lap", laps_a, index=max(0, len(laps_a)-1))
with lb:
    lap_num_b = st.selectbox("Driver B lap", laps_b, index=max(0, len(laps_b)-1))

with st.spinner("Preparing telemetry..."):
    try:
        lap_a = session.laps.pick_driver(driver_a).loc[lambda x: x["LapNumber"] == lap_num_a].iloc[0]
        lap_b = session.laps.pick_driver(driver_b).loc[lambda x: x["LapNumber"] == lap_num_b].iloc[0]
        tel_a = get_lap_telemetry(lap_a)
        tel_b = get_lap_telemetry(lap_b)
        comparison = compare_telemetry(tel_a, tel_b)
    except Exception as exc:
        st.error("Could not prepare telemetry for these laps. Try different laps or another session.")
        st.exception(exc)
        st.stop()

name_a = session.get_driver(driver_a).get("Abbreviation", str(driver_a))
name_b = session.get_driver(driver_b).get("Abbreviation", str(driver_b))
summary_a = summarize_lap(tel_a)
summary_b = summarize_lap(tel_b)

st.subheader("Sector performance")
sector_rows = []
for idx, sector_name in enumerate(["Sector1Time", "Sector2Time", "Sector3Time"], start=1):
    value_a = lap_a.get(sector_name, pd.NaT)
    value_b = lap_b.get(sector_name, pd.NaT)
    seconds_a = value_a.total_seconds() if pd.notna(value_a) and hasattr(value_a, "total_seconds") else float("nan")
    seconds_b = value_b.total_seconds() if pd.notna(value_b) and hasattr(value_b, "total_seconds") else float("nan")
    sector_rows.append({"sector": f"Sector {idx}", "time_A_s": seconds_a, "time_B_s": seconds_b,
                        "delta_A_minus_B_s": seconds_a - seconds_b if pd.notna(seconds_a) and pd.notna(seconds_b) else float("nan")})
sector_df = pd.DataFrame(sector_rows)
if sector_df[["time_A_s", "time_B_s"]].notna().any().any():
    st.plotly_chart(sector_comparison_figure(sector_df, name_a, name_b), use_container_width=True)
    st.dataframe(sector_df.round(3), use_container_width=True, hide_index=True)
    st.caption("Sector times come from the session timing data when available; missing sectors are left blank rather than estimated.")
else:
    st.info("Official sector timing values are not available for these selected laps.")

m1, m2, m3, m4 = st.columns(4)
m1.metric(f"{name_a} lap time", str(lap_a["LapTime"]).split(" days ")[-1] if pd.notna(lap_a["LapTime"]) else "N/A")
m2.metric(f"{name_b} lap time", str(lap_b["LapTime"]).split(" days ")[-1] if pd.notna(lap_b["LapTime"]) else "N/A")
m3.metric(f"{name_a} minimum speed", f"{summary_a['min_speed']:.1f} km/h" if pd.notna(summary_a["min_speed"]) else "N/A")
m4.metric(f"{name_b} minimum speed", f"{summary_b['min_speed']:.1f} km/h" if pd.notna(summary_b["min_speed"]) else "N/A")

st.subheader("Telemetry comparison")
metric = st.selectbox("Channel", ["Speed", "Throttle", "Brake", "nGear", "Acceleration"], index=0)
fig = telemetry_figure(comparison, metric, name_a, name_b)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Lap-time delta")
st.plotly_chart(delta_figure(comparison, name_a, name_b), use_container_width=True)
st.caption("Delta is computed from each lap's elapsed time at matching distance. Positive values mean Driver A is taking longer than Driver B at that distance.")

st.subheader("Track map")
try:
    circuit_info_for_map = session.get_circuit_info()
    track_fig = track_figure(tel_a, tel_b, getattr(circuit_info_for_map, "corners", None), name_a, name_b)
    if track_fig is None:
        st.info("Position (X/Y) data is not available for this session, so a track map cannot be drawn.")
    else:
        st.plotly_chart(track_fig, use_container_width=True)
        st.caption("The paths use public position telemetry. Corner labels are approximate circuit references, not exact apex annotations.")
except Exception:
    st.info("Track-map data could not be read for this session. The telemetry and corner comparisons remain available.")

st.subheader("Corner-by-corner comparison")
corner_results = pd.DataFrame()
st.caption("Corner markers are FastF1 circuit references, not guaranteed exact apex locations. Entry/exit speeds are sampled around each marker; minimum speed is measured within a short window around it.")
try:
    circuit_info = session.get_circuit_info()
    corner_markers = getattr(circuit_info, "corners", None)
    if corner_markers is None or corner_markers.empty or "Distance" not in corner_markers.columns:
        st.info("FastF1 did not provide usable distance-based corner markers for this circuit/session.")
    else:
        corner_results = compare_corners(comparison, corner_markers)
        if corner_results.empty:
            st.info("No circuit corner markers fell inside the shared telemetry distance range for these laps.")
        else:
            st.plotly_chart(corner_min_speed_figure(corner_results, name_a, name_b), use_container_width=True)
            display_columns = [
                "corner", "distance_m",
                "entry_speed_A_kmh", "entry_speed_B_kmh",
                "minimum_speed_A_kmh", "minimum_speed_B_kmh",
                "minimum_speed_advantage_A_minus_B_kmh",
                "exit_speed_A_kmh", "exit_speed_B_kmh",
                "brake_onset_A_m", "brake_onset_B_m",
                "throttle_70_distance_A_m", "throttle_70_distance_B_m",
                "delta_A_minus_B_s",
            ]
            st.dataframe(corner_results[display_columns].round(1), use_container_width=True, hide_index=True)
            st.download_button(
                "Download corner comparison CSV",
                data=corner_results.to_csv(index=False).encode("utf-8"),
                file_name=f"corner-comparison-{name_a}-{name_b}.csv",
                mime="text/csv",
            )
except Exception as exc:
    st.info("Corner-by-corner analysis is unavailable for this session because circuit marker data could not be read.")
    st.caption(f"Details: {exc}")

st.subheader("Detected driving events")
st.caption("These are algorithmic estimates from public telemetry, not official FIA-defined braking points. Brake data is an on/off signal, not brake pressure.")
events = pd.concat([
    detect_events(tel_a, name_a).assign(driver=name_a),
    detect_events(tel_b, name_b).assign(driver=name_b),
], ignore_index=True)
if events.empty:
    st.info("No events passed the current detection thresholds for these laps.")
else:
    st.dataframe(events.round(2), use_container_width=True, hide_index=True)
    st.plotly_chart(event_table_figure(events), use_container_width=True)

st.subheader("Driver performance report")
st.caption("Generate a shareable, standalone HTML report with lap-level findings, sector comparison, and the largest measured corner-marker differences.")
try:
    report = build_performance_report(
        event_name=str(session.event.get("EventName", event_name)),
        season=int(year), session_name=str(session.name),
        driver_a=name_a, driver_b=name_b,
        lap_a=int(lap_num_a), lap_b=int(lap_num_b),
        lap_time_a=lap_a.get("LapTime", pd.NaT), lap_time_b=lap_b.get("LapTime", pd.NaT),
        summary_a=summary_a, summary_b=summary_b,
        sectors=sector_df, corners=corner_results,
    )
    st.markdown("**Key findings**")
    for finding in report["findings"]:
        st.markdown(f"- {finding}")
    if pd.notna(lap_a.get("LapTime", pd.NaT)) and pd.notna(lap_b.get("LapTime", pd.NaT)):
        st.metric("Lap-time delta (Driver A − Driver B)", f"{report['lap_delta_s']:+.3f} s")
    st.download_button(
        "Download driver performance report (HTML)",
        data=report["html"].encode("utf-8"),
        file_name=f"performance-report-{int(year)}-{name_a}-{name_b}.html",
        mime="text/html",
        help="Save this standalone report and open it in a browser, or print it to PDF.",
    )
except Exception as exc:
    st.warning("The performance report could not be generated for this selection.")
    st.caption(f"Details: {exc}")

st.subheader("Instagram carousel generator")
st.caption("Create a five-slide 4:5 PNG carousel and evidence-based caption from the currently selected session, laps and corner measurements. Review before publishing.")
if corner_results.empty:
    st.info("Load a session with usable circuit corner markers to generate a corner-comparison carousel. The generator will not invent missing measurements.")
else:
    if st.button("Generate Instagram corner-comparison carousel", type="primary"):
        with st.spinner("Building carousel slides from the selected session data..."):
            try:
                st.session_state.instagram_carousel = build_instagram_carousel(
                    event_name=str(session.event.get("EventName", event_name)),
                    season=int(year), session_name=str(session.name),
                    driver_a=name_a, driver_b=name_b,
                    lap_a=int(lap_num_a), lap_b=int(lap_num_b),
                    lap_time_a=lap_a.get("LapTime", pd.NaT),
                    lap_time_b=lap_b.get("LapTime", pd.NaT),
                    corners=corner_results,
                )
                st.session_state.instagram_carousel_key = f"{year}|{event_name}|{session_name}|{driver_a}|{lap_num_a}|{driver_b}|{lap_num_b}"
            except Exception as exc:
                st.error("The Instagram carousel could not be generated for this selection.")
                st.caption(f"Details: {exc}")
    current_carousel_key = f"{year}|{event_name}|{session_name}|{driver_a}|{lap_num_a}|{driver_b}|{lap_num_b}"
    carousel_export = st.session_state.get("instagram_carousel") if st.session_state.get("instagram_carousel_key") == current_carousel_key else None
    if carousel_export:
        st.success("Carousel generated. Slides are 1080 × 1350 PNGs (4:5 portrait).")
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "Download carousel ZIP (5 slides + caption)",
                data=carousel_export["zip_bytes"],
                file_name=carousel_export["zip_name"],
                mime="application/zip",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                "Download caption only (.txt)",
                data=carousel_export["caption"].encode("utf-8"),
                file_name="instagram-caption.txt",
                mime="text/plain",
                use_container_width=True,
            )
        with st.expander("Preview carousel slides"):
            preview_cols = st.columns(2)
            for index, (slide_name, slide_bytes) in enumerate(carousel_export["slides"]):
                with preview_cols[index % 2]:
                    st.image(slide_bytes, caption=slide_name, use_container_width=True)
        with st.expander("Review generated caption"):
            st.text_area("Caption", value=carousel_export["caption"], height=250, key="instagram_caption_preview")
        st.caption("Before posting: verify the selected session and laps, check the interpretation, and ensure your use of data and assets follows the relevant source/platform terms. The caption separates measurements from possible explanations.")

st.subheader("Editorial newsroom — ranked story drafts")
st.caption("Automatically ranks potential stories from the currently loaded lap, sector and corner measurements. Scores are editorial heuristics, not measures of sporting importance. Approval is a local review state; nothing is published automatically.")
try:
    editorial_queue = build_editorial_queue(
        event_name=str(session.event.get("EventName", event_name)), season=int(year),
        session_name=str(session.name), driver_a=name_a, driver_b=name_b,
        lap_a=int(lap_num_a), lap_b=int(lap_num_b),
        lap_time_a=lap_a.get("LapTime", pd.NaT), lap_time_b=lap_b.get("LapTime", pd.NaT),
        sectors=sector_df, corners=corner_results, max_stories=12,
    )
    if "editorial_state_loaded" not in st.session_state:
        saved_editorial_state = _load_editorial_state()
        st.session_state.editorial_approvals = saved_editorial_state.get("approvals", {})
        st.session_state.editorial_caption_edits = saved_editorial_state.get("captions", {})
        st.session_state.editorial_state_loaded = True

    for story in editorial_queue:
        story_id = story["id"]
        story["approved"] = bool(st.session_state.editorial_approvals.get(story_id, False))
        story["status"] = "Approved for publishing" if story["approved"] else "Needs review"
        edit_key = f"editorial_caption_{story_id}"
        story["caption"] = st.session_state.get(
            edit_key, st.session_state.editorial_caption_edits.get(story_id, story["caption"])
        )

    approved_count = sum(bool(story["approved"]) for story in editorial_queue)
    st.write(f"**{len(editorial_queue)} draft opportunities** · **{approved_count} approved**")
    if not editorial_queue:
        st.info("No usable lap, sector or corner findings were available to draft a story. Try another pair of laps or a session with more timing data.")
    else:
        st.markdown("Rank is based on measured differences within each story type, with a small editorial format weighting. Review the evidence and caveats before approving.")
        for story in editorial_queue:
            approved = bool(st.session_state.editorial_approvals.get(story["id"], False))
            status_label = "✓ APPROVED" if approved else "NEEDS REVIEW"
            with st.expander(f"#{story['rank']} · {story['headline']} · score {story['score']:.1f} · {status_label}", expanded=(story['rank'] == 1)):
                st.caption(f"{story['story_type']} · {story['score_explanation']}")
                st.markdown(f"**Editorial hook:** {story['hook']}")
                st.markdown("**Evidence from selected data**")
                for item in story["evidence"]:
                    st.markdown(f"- {item}")
                st.markdown(f"**Caveat:** {story['caveat']}")
                caption = st.text_area("Edit draft caption before approval", value=story["caption"], height=230, key=f"editorial_caption_{story['id']}")
                story["caption"] = caption
                st.session_state.editorial_caption_edits[story["id"]] = caption
                b1, b2 = st.columns(2)
                with b1:
                    if not approved and st.button("Approve draft", key=f"editorial_approve_{story['id']}", type="primary", use_container_width=True):
                        st.session_state.editorial_approvals[story["id"]] = True
                        _save_editorial_state(st.session_state.editorial_approvals, st.session_state.editorial_caption_edits)
                        st.rerun()
                with b2:
                    if approved and st.button("Revoke approval", key=f"editorial_revoke_{story['id']}", use_container_width=True):
                        st.session_state.editorial_approvals[story["id"]] = False
                        _save_editorial_state(st.session_state.editorial_approvals, st.session_state.editorial_caption_edits)
                        st.rerun()

        for story in editorial_queue:
            story["approved"] = bool(st.session_state.editorial_approvals.get(story["id"], False))
            story["status"] = "Approved for publishing" if story["approved"] else "Needs review"
            story["caption"] = st.session_state.get(f"editorial_caption_{story['id']}", story["caption"])
        _save_editorial_state(st.session_state.editorial_approvals, st.session_state.editorial_caption_edits)
        export_all = export_editorial_queue(editorial_queue, approved_only=False)
        export_approved = export_editorial_queue(editorial_queue, approved_only=True)
        ex1, ex2 = st.columns(2)
        with ex1:
            st.download_button("Download full editorial queue", data=export_all["zip_bytes"],
                               file_name=export_all["zip_name"], mime="application/zip", use_container_width=True)
        with ex2:
            st.download_button("Download approved drafts only", data=export_approved["zip_bytes"],
                               file_name=export_approved["zip_name"], mime="application/zip",
                               use_container_width=True, disabled=approved_count == 0)
        st.caption("Exports include Markdown draft files and a CSV index. Approval does not publish to Instagram; check data, context, rights and platform rules before posting.")
except Exception as exc:
    st.warning("The editorial queue could not be generated for this selection.")
    st.caption(f"Details: {exc}")

st.subheader("2026 energy investigation")
st.warning("FastF1's standard public telemetry channels do not include battery state of charge or direct MGU-K deployment/harvesting power. Speed and throttle alone cannot recover these values reliably. The panel below accepts an external CSV if you have a documented dataset with actual energy measurements.")
st.markdown("Upload a CSV with a `Distance` column (metres) and one or more of `BatterySOC`, `DeploymentPower_kW`, `HarvestPower_kW`, or `EnergyMJ`. Keep the original source and units documented.")
energy_file = st.file_uploader("Optional energy telemetry CSV", type=["csv"])
if energy_file is not None:
    try:
        energy_df = prepare_energy_data(pd.read_csv(energy_file))
        if energy_df.empty:
            st.error("No supported energy columns were found. See the required column names above.")
        else:
            st.plotly_chart(energy_figure(energy_df), use_container_width=True)
            st.dataframe(energy_df.head(100), use_container_width=True)
    except Exception as exc:
        st.error(f"Could not read energy data: {exc}")
else:
    st.info("No direct battery data is plotted because the standard FastF1 channel set does not expose it. Do not interpret inferred acceleration or throttle patterns as measured battery use.")

with st.expander("Methodology and limitations"):
    st.markdown("""
    - Telemetry is resampled/interpolated onto a shared distance grid for visual comparison.
    - Acceleration is estimated by differentiating speed (converted to m/s) over time; noise and sampling resolution affect it.
    - Brake onset is the first sustained transition into the brake-on state after a non-braking sample.
    - Throttle pickup is the first sustained increase above a threshold after a low-throttle region.
    - Minimum speed is a simple lap-wide metric; corner-specific analysis needs reliable corner markers and more robust segmentation.
    - Public telemetry is not the same as team telemetry. Brake pressure, battery state of charge and direct ERS deployment are not generally available in FastF1's standard channels.
    """)
