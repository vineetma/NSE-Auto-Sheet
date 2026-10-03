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

The wrapper loads the key into `GCP_CREDENTIALS`, sets `RUN_DATE`, runs `update_sheet.py` with the venv Python, appends all output to `logs\run-YYYYMMDD.log`, and exits with Python's exit code.
