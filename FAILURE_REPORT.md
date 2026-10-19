# Failure Report: Paused Replay Source

Renato Jacinto · EGN 321 · Module 7 · Assignment 7.2

Evidence scope: This report documents actual automated execution in the assistant's Linux environment, using my previously packaged Module 7.1 project and its unchanged Module 6 CSV. It does not claim execution on my Windows computer or a live physical sensor. The narrative and code were prepared with AI assistance, disclosed in AI_LOG.md. The failure is a deliberately paused CSV replay using the existing local demo control. No replacement dataset was invented.

## 1. System Before Failure

My system validates temperature input, stores replay history in SQLite, evaluates alerts, and serves a Flask dashboard through Waitress. The original archive is stored separately from replay deliveries. Before the improved experiment, health was HEALTHY, the latest accepted temperature was 22.14 °C (reading ID 3), and the dashboard and status API both returned HTTP 200. SQLite integrity_check returned `ok`; the archive contained 8,780 rows across its sensors, and the replay table contained three rows. Both the temperature alert and the input alert were NORMAL. Evidence: `investigations/improved/01_normal.json` and the matching saved dashboard HTML.

The experiment used a 0.5-second replay interval, so delivery age greater than 1.5 seconds is stale and age greater than 5 seconds produces FAILED. Normal default delivery is 2 seconds, with thresholds of 6 and 20 seconds. Original CSV timestamps remain classroom history, not present-day measurement times.

## 2. Failure Introduced

At 2026-10-19 03:12:16.546627 UTC (October 18, 11:12:16 PM EDT), the harness atomically replaced the investigation runtime's `control.json` with `{"pause": true}`. The existing `--demo` control makes tick skip new deliveries while the worker, SQLite, and web server continue running. This simulates an unavailable replay source without modifying the CSV or stopping health evaluation.

Expected: reading IDs stop advancing, stale input becomes unavailable, health becomes DEGRADED and eventually FAILED. Actual: replay count remained three; current became null, data_status became STALE, and health followed those transitions. HTTP remained 200. The intervention is recorded separately in `actions.jsonl`; application logs alone cannot prove why the source stopped.

## 3. First Observable Symptom

The first observable symptom is that the last delivered reading stopped advancing. This is distinct from the known injected root cause, the pause control. The first explicit application warning was HEALTH_CHANGED from HEALTHY to DEGRADED at 03:12:17.977481 UTC with reason NO_DELIVERY and latest_reading_id 3. Downstream effects were STALE_DATA, unavailable current temperature, and FAILED at 03:12:21.482767 UTC. FAILED here describes unusable input, not a crashed Flask server or failed database. Warning time is detection time, not the exact time the source became unavailable.

## 4. Log Evidence

Primary files are `investigations/improved/application.jsonl` (application observations) and `actions.jsonl` (injection, diagnosis, and recovery actions). They show accepted readings 1–3, a delivery gap, health degradation, input alert activation, prolonged failure, accepted reading 4, health recovery, and alert clearance. The first three stored rows and the source CSV were preserved. A separate baseline run in `investigations/baseline/` documents the logging weakness before the improvement.

Representative actual events:

```text
03:12:17.977481+00:00 HEALTH_CHANGED WARNING Health HEALTHY -> DEGRADED reason=NO_DELIVERY latest_reading_id=3
03:12:17.977934+00:00 INPUT_ALERT_CHANGED WARNING NORMAL -> STALE_DATA
03:12:21.482767+00:00 HEALTH_CHANGED ERROR Health DEGRADED -> FAILED reason=NO_DELIVERY
03:12:21.985437+00:00 READING_PROCESSED INFO Replay sample_number=4 value=22.09
03:12:21.985787+00:00 HEALTH_CHANGED INFO Health FAILED -> HEALTHY
03:12:21.985837+00:00 INPUT_ALERT_CHANGED INFO STALE_DATA -> NORMAL
```

## 5. Timeline of Events

All times in this evidence table are UTC. `FAILURE_TIMELINE.md` and `FAILURE_TIMELINE.csv` contain the full recorded sequence.

| Time (UTC) | Component | Event | Evidence | Interpretation |
|---|---|---|---|---|
| 2026-10-19T03:12:15.465996+00:00 | Health | HEALTH_CHANGED | application.jsonl | Observed health transition: None -> HEALTHY |
| 2026-10-19T03:12:15.466064+00:00 | Health | INPUT_ALERT_CHANGED | application.jsonl | Input alert is now NORMAL |
| 2026-10-19T03:12:16.546377+00:00 | Investigator | CAPTURE_01_NORMAL | actions.jsonl | Investigation observation or verification |
| 2026-10-19T03:12:16.546627+00:00 | Investigator | SOURCE_PAUSED | actions.jsonl | Controlled root cause: delivery paused |
| 2026-10-19T03:12:17.977481+00:00 | Health | HEALTH_CHANGED | application.jsonl | Observed health transition: HEALTHY -> DEGRADED |
| 2026-10-19T03:12:17.977872+00:00 | Health | MISSING_OR_STALE_DATA | application.jsonl | Investigation observation or verification |
| 2026-10-19T03:12:17.977934+00:00 | Health | INPUT_ALERT_CHANGED | application.jsonl | Input alert is now STALE_DATA |
| 2026-10-19T03:12:18.024136+00:00 | Investigator | CAPTURE_02_STALE | actions.jsonl | Investigation observation or verification |
| 2026-10-19T03:12:21.482767+00:00 | Health | HEALTH_CHANGED | application.jsonl | Observed health transition: DEGRADED -> FAILED |
| 2026-10-19T03:12:21.482908+00:00 | Health | MISSING_OR_STALE_DATA | application.jsonl | Investigation observation or verification |
| 2026-10-19T03:12:21.529493+00:00 | Investigator | CAPTURE_03_FAILED | actions.jsonl | Investigation observation or verification |
| 2026-10-19T03:12:21.529746+00:00 | Investigator | DATABASE_WRITE_PROBE_OK | actions.jsonl | SQLite accepted a write transaction; alternative cause rejected |
| 2026-10-19T03:12:21.529794+00:00 | Investigator | HYPOTHESIS_SELECTED | actions.jsonl | Investigation observation or verification |
| 2026-10-19T03:12:21.529966+00:00 | Investigator | SOURCE_RESUMED | actions.jsonl | Remove the pause without restarting or deleting history |
| 2026-10-19T03:12:21.985787+00:00 | Health | HEALTH_CHANGED | application.jsonl | Observed health transition: FAILED -> HEALTHY |
| 2026-10-19T03:12:21.985837+00:00 | Health | INPUT_ALERT_CHANGED | application.jsonl | Input alert is now NORMAL |
| 2026-10-19T03:12:22.015844+00:00 | Investigator | CAPTURE_04_RECOVERED | actions.jsonl | Investigation observation or verification |
| 2026-10-19T03:12:22.016049+00:00 | Investigator | VERIFICATION_PASSED | actions.jsonl | Investigation observation or verification |

## 6. Possible Cause 1

Hypothesis: the replay source is paused or otherwise not delivering records.

Supporting evidence: the latest reading ID remains 3 while HTTP requests and database reads succeed. Health logs show increasing delivery age and NO_DELIVERY. The investigator's action log records the pause.

Missing evidence: baseline application logs contain no source heartbeat or independent source-process status; without the action log, intentional pause and unexpected source loss would look alike.

Deterministic test: `test_cause1_paused_replay_and_recovery` pauses the source, fixes the clock beyond the stale and failed thresholds, and asserts unchanged reading ID, STALE_DATA, DEGRADED, then FAILED. Resuming delivery must add the next reading and clear the input alert. The real HTTP experiment independently repeats the sequence with actual elapsed time. Result: confirmed as the injected cause.

## 7. Possible Cause 2

Hypothesis: SQLite locking or a write-path problem prevents new readings from being committed, making deliveries appear stale.

Supporting evidence: a frozen committed reading ID is compatible with unsuccessful writes, so a frozen dashboard value alone cannot rule this out.

Missing evidence: the incident contains no OperationalError, locked-database exception, HTTP error, or failed integrity check. Those absences alone do not prove storage is healthy.

Deterministic test: `test_cause2_database_lock_confirm_then_reject` obtains an exclusive lock on an isolated test database, asserts that tick raises a locked OperationalError, releases it, and verifies successful delivery. During the actual paused-source incident, BEGIN IMMEDIATE and a no-op UPDATE succeeded and were rolled back; dashboard queries succeeded and integrity_check returned ok. These discriminate the observed incident from a database lock. Result: rejected for this incident. The isolated lock test is a diagnostic comparison, not a second failure introduced into the main investigation.

## 8. Recovery Procedure

I documented the investigation sequence through the automated harness: observe the stale/failed states, examine logs, probe database availability, and record the selected hypothesis before resuming the source. At 03:12:21.529966 UTC it set `control.json` to `{"pause": false}`. The existing worker then consumed the next CSV row. No database was deleted, history was not reimported, the app was not restarted, and no old readings were overwritten. Both baseline and improved investigation folders are retained. The harness stops its test server only after recovery verification is complete.

## 9. Verification of Recovery

`04_recovered.json` records accepted temperature 22.09 °C at reading ID 4, HEALTHY, input alert NORMAL, and temperature alert NORMAL. The dashboard and API returned 200, integrity_check returned ok, and the archive still contained 8,780 rows. The harness compared the complete original replay-row prefix against the recovered database and verified the CSV SHA-256 stayed unchanged. `verification.json` records PASS and replay counts of 3 before/while failed and 4 after recovery. `verified_monitor.db` is a preserved SQLite backup.

Seven pytest tests passed, including the original four tests and three investigation tests. The extra alert test verifies that three high readings activate the existing temperature alert and a low reading clears it. Synthetic high/low values are isolated test fixtures, not the main incident dataset. Failed and recovered JSON plus saved dashboard HTML satisfy the requested output evidence; the HTML files are saved HTTP responses, not browser screenshots.

## 10. What the Logs Told Me

The baseline logs showed accepted readings, health-state changes, a missing/stale event, and the later resumed reading. The improved logs identify the affected component, previous and new health, severity, delivery age, valid-input age, active thresholds, latest reading ID, database path, input alert activation, and clearance. These records distinguish input failure from complete application unavailability when combined with HTTP and database output.

## 11. What the Logs Did Not Tell Me

The baseline logs did not state whether degradation resulted from stale deliveries, invalid data, or a temperature threshold. They omitted the age, previous health, component, and input-alert lifecycle. Even the improved application logs cannot independently identify who paused the source, prove that a physical sensor was disconnected, or diagnose unavailable storage when logging itself cannot write. The separate investigator action log provides the injected root cause. A source heartbeat or source-status event would make future diagnosis easier.

## 12. Improvement Made

After the baseline run, I used the investigation findings to improve `app.py`, `logging_config.py`, and the dashboard template. Health transition events now include previous_health, reason, age_seconds, valid_age_seconds, thresholds, component, latest_reading_id, and database_path. JSON events include severity. Worker exceptions include exception_type and database_path. Reading events include sample_number and reading_id. A separate `input_alert` exposes STALE_DATA or NO_VALID_INPUT and logs transitions without repeatedly logging an unchanged alert. The temperature alert retains its original hysteresis behavior. The dashboard displays the input alert.

`baseline_source/` preserves the original changed Python files, and `IMPROVEMENT.diff` shows the actual code changes. The improved HTTP investigation and all seven tests passed after the change. The baseline run precedes the implementation; the repeated improved run demonstrates the resulting behavior.

## 13. Remaining Limitations

The pause mechanism is a classroom fault injection, not a hardware unplug test. This experiment uses accelerated replay of the same existing dataset; its source dates are historical and timezone-unspecified. Demo mode retains the original SYNTHETIC_TEST label even though this incident overrides no sensor values. It was executed in the assistant environment, not on my computer. SQLite integrity_check does not establish correctness of every historical value or all storage failure modes. Rounded age_seconds may display 1.50 while the internal comparison is already greater than 1.5. Worker polling and HTTP polling produce small detection delays. The app still relies on its supervisor for worker crash recovery, and this incident does not prove recovery from power loss, persistent disk failure, or corrupted databases. The web app has no authentication and binds to localhost.

My own GitHub repository URL must be added to GITHUB_LINK.txt after uploading these files. The instructor assignment link is not my submission repository.
