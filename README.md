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

## Failures

A missing bhavcopy (HTTP 404, i.e. a holiday or a file not yet published) falls back to the previous trading day, up to 5 days back. Anything else exits with code 1 and logs `FAIL: sheet not updated` with the cause: a network error, any other HTTP status, a corrupt zip/CSV, missing columns, no data in the 5-day window, a bad key, or a `RUN_DATE` that is not `YYYY-MM-DD`. In GitHub Actions this marks the job as failed.
