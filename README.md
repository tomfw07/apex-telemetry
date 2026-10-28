# F1 Telemetry & Energy Analysis

An open-source Python dashboard for comparing Formula 1 laps using FastF1. It visualises speed, throttle, braking, gear and derived acceleration, calculates a distance-aligned lap-time delta, and detects approximate braking and throttle-pickup events.

The project also provides an explicit import path for externally sourced energy telemetry. It **does not invent battery state-of-charge or MGU-K deployment values** when those channels are unavailable.

## Features

- Select a season, Grand Prix, session, driver and lap in Streamlit.
- Compare two drivers on a common distance axis.
- Interactive Plotly charts for speed, throttle, brake, gear and estimated acceleration.
- Lap-time delta against distance.
- Track map showing both selected lap paths, with corner-reference annotations when position data is available.
- Official timing-sector comparison where sector times are available.
- Corner-by-corner entry, minimum and exit speed estimates using FastF1 circuit markers.
- Approximate braking-onset and throttle-pickup distances around each corner, plus CSV export.
- Approximate brake-onset and throttle-pickup event detection.
- Optional CSV input for documented energy measurements.
- Unit tests for core analysis functions.
- FastF1 local cache to reduce repeated downloads.

## Quick start

Requires Python 3.10 or newer (64-bit recommended).

### Windows PowerShell

```powershell
git clone https://github.com/YOUR-USERNAME/f1-telemetry-energy-analysis.git
cd f1-telemetry-energy-analysis

py -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

streamlit run app.py
```

If PowerShell blocks activation, use Command Prompt:

```bat
.venv\Scripts\activate.bat
```

### macOS / Linux

```bash
git clone https://github.com/YOUR-USERNAME/f1-telemetry-energy-analysis.git
cd f1-telemetry-energy-analysis

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

Streamlit prints a local URL, normally `http://localhost:8501`. The first session load may take a while because FastF1 downloads and processes data. Cache files are stored locally in `.fastf1_cache/` and are excluded from Git.

## Run tests

```bash
pytest -q
```

Tests use small synthetic dataframes and do not download live Formula 1 sessions.

## Energy data: important limitation

FastF1's documented standard car telemetry channels include speed, RPM, gear, throttle, brake state, DRS and position channels. Its standard telemetry does not expose battery state of charge or direct ERS/MGU-K deployment and harvesting power as ordinary channels. Public timing and telemetry availability also varies by session.

This dashboard therefore:
1. **Does not** calculate or display a made-up battery percentage.
2. Allows CSV import for an external dataset with documented energy fields.
3. Requires `Distance` in metres and supports these optional columns:
   - `BatterySOC` — state of charge, percentage (0–100) if the source uses percent.
   - `DeploymentPower_kW` — measured deployment power in kW.
   - `HarvestPower_kW` — measured harvesting power in kW.
   - `EnergyMJ` — energy in megajoules.
4. Does not assume a dataset has these measurements merely because it contains 2026 telemetry. Check its data dictionary and provenance first.

Potential sources to investigate include the [TracingInsights 2026 public telemetry repository](https://github.com/TracingInsights/2026) and the [OpenF1 API documentation](https://openf1.org/docs/). Their presence does not guarantee battery or ERS channels; verify the actual schema before using any dataset. The [FastF1 documentation](https://docs.fastf1.dev/) is the reference for FastF1's standard channels.

## Methodology

### Distance alignment

The two laps are interpolated onto a common distance grid so corresponding locations can be compared even if sample timestamps differ. The comparison ends at the shorter lap's maximum distance to avoid extrapolating beyond available data.

### Acceleration

Speed is converted from km/h to m/s and differentiated over elapsed time. This is an estimate affected by telemetry sample rate, interpolation and noise. It is not a substitute for a team's calibrated longitudinal acceleration sensor.

### Braking and throttle events

- Brake onset: a transition from brake-off to brake-on that remains active for a minimum number of samples.
- Throttle pickup: a rise above a configured throttle threshold after a low-throttle sample.
- Brake data is a binary/on-off channel, not brake pressure. Detected points are estimates, not official driver braking points.

### Lap-time delta

Elapsed time is interpolated against distance for each lap. The displayed delta is Driver A elapsed time minus Driver B elapsed time; positive values indicate Driver A is taking longer at that distance.

## Project structure

```text
f1-telemetry-energy-analysis/
├── app.py
├── src/
│   ├── __init__.py
│   ├── analysis.py
│   ├── data_loader.py
│   └── plots.py
├── tests/
│   └── test_analysis.py
├── requirements.txt
├── .gitignore
└── README.md
```

## Known limitations and next steps

- Corner-level metrics use FastF1 circuit markers as approximate references. They are useful comparisons, not official apex points or team-grade engineering measurements; marker availability varies by circuit/session.
- Session availability depends on FastF1 and upstream data sources.
- Data loading requires internet access for the first fetch.
- The energy CSV plot uses a shared y-axis, so mixed units should be inspected carefully. Split into separate subplots before drawing conclusions from mixed measurement types.
- Potential next features: tyre compound and weather context, robust event thresholds, exportable reports, and a reproducible analysis notebook.

## Data and attribution

This project uses the FastF1 Python package and public Formula 1 timing/telemetry data. It is an independent educational portfolio project and is not affiliated with Formula 1, the FIA, or any team. Respect upstream data terms and the licences/attribution requirements of any external dataset you add.

## Licence

MIT — see `LICENSE`.

## Driver performance report

The dashboard includes a downloadable standalone HTML performance report for the selected driver/lap pair. It summarises the overall lap-time difference, sector deltas when official sector timing is present, and the largest sampled differences at FastF1 circuit corner markers. Save the HTML report and open it in a browser; use the browser's Print command to save a PDF if needed.

The narrative is descriptive rather than causal. A time delta sampled at a corner marker is not a measurement of time lost solely in that corner, and comparisons can be affected by tyre age, fuel load, traffic, weather, track evolution and setup. Missing measurements are shown as unavailable rather than invented.

The report generator is implemented in `src/report.py` and covered by automated tests.


## Instagram corner-comparison carousel

The Streamlit dashboard can generate a five-slide Instagram carousel from the currently selected session, two drivers/laps, and the available corner-marker comparison. Select a session and laps, scroll to **Instagram carousel generator**, and choose **Generate Instagram corner-comparison carousel**. Download the ZIP and upload `slide-01.png` through `slide-05.png` in order; `caption.txt` contains a matching caption, and `corner-data.csv` preserves the table used to produce the comparison.

- Images are generated locally as 1080 × 1350 PNGs (4:5 portrait).
- Lap times and corner values come from the currently loaded FastF1 session data; unavailable values are not fabricated.
- Corner markers and sampled minimum speeds are approximate references, not exact apex measurements. Time deltas at markers do not establish causal time loss.
- Interpretive text is framed as questions for further investigation, not claims about tyre, setup, traffic, or energy causes.
- Review all generated material and source/platform terms before publishing. This is an original fan analysis, not official Formula 1 content.

## Editorial newsroom and approval queue

The dashboard includes an editorial queue that scans the currently selected lap times, official sector times when available, and approximate corner-marker comparisons. It ranks up to 12 draft story opportunities and generates a caption with the selected session/lap context, supporting measurements, and a caveat.

- The priority score is a heuristic for review order, not an objective measure of sporting importance. Scores are influenced by relative differences within a story type and should not be compared as scientific metrics.
- Missing data is omitted rather than inferred. Lap-time comparisons use the two selected laps; sector comparisons use available session timing; corner references are approximate and sampled minimum speeds/time deltas do not prove a cause.
- Draft captions are editable. Approval and edited captions are saved locally in `output/editorial_state.json` and excluded from Git. The app does not connect to Instagram or publish posts automatically.
- Download the full queue or approved drafts as a ZIP containing Markdown drafts and a CSV index. Review every claim, the session context, data-source terms and platform rules before publication.

The editorial logic is implemented in `src/editorial.py` and covered by `tests/test_editorial.py`.


## Apex Telemetry public website (GitHub Pages)

The `docs/` directory contains a responsive, static, news-first website for Apex Telemetry. It can be hosted free with GitHub Pages and does not require a separate Python server. It starts with an intentionally empty newsroom rather than invented race headlines, plus an evergreen guide explaining how to read telemetry comparisons.


### Website structure

```text
docs/
├── index.html
├── posts.json
├── .nojekyll
└── assets/
    ├── app.js
    ├── favicon.svg
    └── styles.css
scripts/
└── publish_story.py
```

