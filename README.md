# NSE-Auto-Sheet

Fetches the NSE bhavcopy, picks the top 250 stocks by volume, and writes them into the weekday column block of a Google Sheet. Runs on a schedule in GitHub Actions (`.github/workflows/main.yml`) and can also be run locally.

## Running locally

From PowerShell in the repo root:

1. **Python environment**

   ```powershell
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```

2. **Google key.** Save the service account key JSON as `gsheet-access-keys.json` in the repo root (it is gitignored), or anywhere else and point `NSE_KEY_PATH` (or `-KeyPath`) at it. The spreadsheet must be shared as Editor with the key's `client_email`.

3. **Run the wrapper**

   ```powershell
   .\scripts\run_local.ps1                      # today (falls back to the last trading day)
   .\scripts\run_local.ps1 -RunDate 2026-10-01  # a specific date (YYYY-MM-DD)
   ```

   If script execution is blocked, use `powershell -ExecutionPolicy Bypass -File .\scripts\run_local.ps1`.

The wrapper loads the key into `GCP_CREDENTIALS`, sets `RUN_DATE`, runs `update_sheet.py` with the venv Python, appends all output to `logs\run-YYYYMMDD.log`, and exits with Python's exit code. Each run ends with a `RESULT: OK` or `RESULT: FAIL (exit N)` line, and a failed run also shows a Windows toast (pass `-NoToast` to suppress it).

## Scheduling on the laptop

GitHub Actions is the primary schedule (weekdays at 20:00 IST, 14:30 UTC). An optional local backup in Windows Task Scheduler ("NSE Auto Sheet") runs at the same time. It is disabled by default:

```powershell
.\scripts\local_schedule.ps1                 # status
.\scripts\local_schedule.ps1 enable          # Mon-Fri at 20:00 local time
.\scripts\local_schedule.ps1 enable -At 18:30 -WakeToRun
.\scripts\local_schedule.ps1 disable         # keep the task, but don't run it on a schedule
.\scripts\local_schedule.ps1 remove
```

The task runs `run_local.ps1` as you, only while you are logged on (so no password is stored). If the laptop is off or asleep at the scheduled time, the run starts as soon as possible afterwards. Running both schedules is safe because each write overwrites that day's column block. Check "Last Run Result" in Task Scheduler (0 = OK, 1 = failed) and the `logs\` folder.

## Failures

A missing bhavcopy (HTTP 404, i.e. a holiday or a file not yet published) falls back to the previous trading day, up to 5 days back. Anything else exits with code 1 and logs `FAIL: sheet not updated` with the cause: a network error, any other HTTP status, a corrupt zip/CSV, missing columns, no data in the 5-day window, a bad key, or a `RUN_DATE` that is not `YYYY-MM-DD`. In GitHub Actions this marks the job as failed.

## Tests

Unit tests use fixtures and a fake worksheet, so they make no network or Google calls:

```powershell
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

Set `SPREADSHEET_ID` and/or `WORKSHEET_NAME` to point a real run at a different sheet, e.g. a test copy.
