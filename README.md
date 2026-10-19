# Sensor Watch — Failure Investigation (Assignment 7.2)

Renato Jacinto · EGN 321

This continues the supplied Module 7.1 monitor, its Module 6 CSV archive, temperature validation, SQLite history, alerts, Flask dashboard, and supervisor. The investigated failure is paused replay delivery. It adds evidence-rich health logging and a visible input alert.

## Read the submission

Start with `FAILURE_REPORT.md`. The thirteen required sections and evidence table are complete. `FAILURE_TIMELINE.md` and `.csv` contain the event sequence. `investigations/baseline/` contains the original investigation, and `investigations/improved/` contains the improved repeat. Each has actual application logs, injection/action logs, normal/stale/failed/recovered JSON, saved HTTP HTML output, process output, verification JSON, and a SQLite backup. Output is provided instead of screenshots, as permitted by the assignment. `TEST_RESULTS.txt` records the seven passing tests. `AI_LOG.md` discloses the assistance and execution environment.

## Install and run on Windows

Extract the ZIP and open a terminal inside this project folder:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe supervisor.py
```

Open http://127.0.0.1:5000/ and http://127.0.0.1:5000/history. Stop with Ctrl+C. The default supervisor creates a separate `runtime/` database; it does not use the packaged investigation database. Default delivery interval is 2 seconds. Stale is greater than 6 seconds; FAILED is greater than 20 seconds. Temperature alert triggers after three accepted readings >=30 °C and clears at <=28.5 °C. Stale input is hidden rather than presented as current. Runtime state persists for restart recovery. The CSV is historical replay, not live hardware data.

## Run verification tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

The original four tests remain. Three new tests cover paused-source diagnosis and recovery, an isolated database-lock comparison, and temperature alert activation/clearance. The lock test uses a temporary database and does not change the main experiment.

## Repeat the real HTTP investigation

```powershell
.venv\Scripts\python.exe investigate_failure.py
```

On Linux use `python3` or your virtual environment's Python. The harness starts the app on localhost port 5058 with an isolated runtime and 0.5-second delivery. Port 5058 must be free. It waits for healthy operation, atomically sets a pause, captures stale and failed output, probes SQLite with a rolled-back write, records its hypothesis, resumes delivery, verifies recovery and history preservation, and stops its test process. No browser installation is required. A new timestamped folder under `investigations/` preserves each run; existing folders cannot be overwritten. For an explicit unique folder use `--label my_local_run`.

`--demo` enables the existing local control file. The main incident changes only `pause`; it does not override CSV temperatures. Its mode/provenance still say SYNTHETIC_TEST because that is the inherited fault-control mode. The normal supervisor run ignores demo controls. Do not run the inherited `capture_evidence.py` unless you intentionally want the older Module 7.1 multi-fault demonstration; `investigate_failure.py` is the Assignment 7.2 procedure.

## What changed

Health logs now include severity, component, previous/new health, reason, input age, thresholds, reading ID, and database path. Reading events include sample number; worker errors include exception type. The API/dashboard expose a separate input alert with activation and clearance events. See `IMPROVEMENT.diff`, `baseline_source/`, and report sections 10–12. Existing validation, archive separation, and temperature hysteresis are retained.

## Source and evidence limits

The original `data/module6_sample_sensor_history.csv` is unchanged; SHA-256 is recorded in each verification.json. The archive contains 8,780 rows across sensors. Source timestamps have no specified timezone; experiment logs use UTC. October 19 at 03:12 UTC is October 18 at 11:12 PM EDT. Packaged evidence was collected in the assistant Linux environment. It is not a claim of Windows, hardware, boot, disk-failure, or production verification. The report explains remaining limitations.
