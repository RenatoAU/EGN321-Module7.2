# Failure Timeline

Recorded execution on 2026-10-19 UTC (October 18 in America/New_York). All timestamps below are UTC. Files referenced are in `investigations/improved/`.

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
