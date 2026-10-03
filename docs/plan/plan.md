# Plan: NSE-Auto-Sheet local running and restructure

Goal: run `update_sheet.py` on a schedule from the laptop (native Windows preferred, WSL as an alternative) as an equivalent of the GitHub Actions workflow in `.github/workflows/main.yml`, with the Google key kept out of the repo; and make `update_sheet.py` testable, easier to maintain, and loud on failure, without changing the sheet layout or behaviour on the happy path.

The work is grouped into stages. Each stage ends with a clear outcome that can be seen or checked, and leaves the repo working. Stages are in the suggested order; stages 1-2 involve no changes to `update_sheet.py`.

## Context: what GitHub Actions does today, and its local equivalent

| GitHub workflow | Local equivalent |
|---|---|
| `cron: '56 05 * * 1-5'` (UTC, about 11:26 IST) | Windows Task Scheduler (or cron/systemd in WSL) |
| `actions/setup-python` + `pip install ...` | `python -m venv .venv` + `requirements.txt` |
| `secrets.GCP_CREDENTIALS` | Key JSON file outside the repo, loaded into the `GCP_CREDENTIALS` env var by a wrapper script |
| `inputs.run_date` -> `RUN_DATE` | `RUN_DATE` env var, or a wrapper parameter |
| Failed job shows red | Exit code + log file (needs Stage 4 to be meaningful) |

## Overview

| Stage | Outcome | Touches `update_sheet.py` |
|---|---|---|
| 1. Local environment and credentials (Done) | Laptop can import the libraries and holds a working, gitignored key | No |
| 2. Manual local run (Done) | One command updates the sheet from the laptop and writes a log | No |
| 3. Code foundation (Done) | Module is importable without side effects and uses a supported auth library | Yes |
| 4. Loud failures (Done) | A failed run exits non-zero and is visible locally and in CI | Yes |
| 5. Unattended schedule (Done) | The laptop updates the sheet on weekdays without intervention; one clear owner of the schedule | No |
| 6. Clean internals (Done) | Small, testable functions with central config and a single sheet write | Yes |
| 7. Readable structure (Done) | Four small files; `main()` reads as the four steps of the job; tests in `tests/` | Yes (split) |
| 8. Housekeeping (Done) | Consistent, typed, IST-correct code | Yes |
| Alt. WSL | Same as Stages 2 and 5, using Linux tooling | No |

---

## User Inputs / provide configurations

* Use virtual environment setup using `python -m venv .venv` in the project root directory
* Run scripts from powershell
* in venv python versin is `Python 3.11.4`
* google secrets file is `gsheet-access-keys.json` saved in project root
* code should not break from running in github actions as well as local
* commit after every change with appropriate command following conventional commits guidance


## Stage 1: Local environment and credentials

Status: **Done** (2026-10-03, commit `371fd17`, not yet pushed). Two optional/manual items remain open below.

Outcome: `python -c "import gspread, pandas"` succeeds in the venv; the key file exists in the project root (per User Inputs) and is gitignored, `git status` does not show it, and the sheet is shared with the service account.

### Python environment and dependencies

- [x] Confirm Python 3.10+ is installed (`python --version`). Venv runs Python 3.11.4.
- [x] Create a venv in the repo root: `python -m venv .venv`. Existing `.venv` reused.
- [x] Add `requirements.txt` with `gspread`, `oauth2client`, `pandas`, `requests` (matching the workflow's install line). `oauth2client` is removed in Stage 3.
- [x] Add `.gitignore` with at least `.venv/`, `*.json` key patterns, `.env`, `logs/`, `__pycache__/`. Covers `gsheet-access-keys.json`, `*-keys.json`, `*-key.json`, `*service-account*.json`.
- [x] Install: `.venv\Scripts\pip install -r requirements.txt`. Installed gspread 6.2.1, pandas 3.0.6.
- [x] Make `main.yml` install from `requirements.txt` (optional, keeps one source of truth).
- [x] Commit: "Add requirements.txt and .gitignore" (`371fd17`).

### Google service account key

- [x] Decide where the key lives. Per User Inputs: `gsheet-access-keys.json` in the project root, excluded via `.gitignore` (deviates from the original "outside the repo" suggestion).
- [x] Obtain the key. Existing key file reused (service account `stock-updater-bot@my-example-project-476212.iam.gserviceaccount.com`).
- [x] Open the JSON, copy `client_email`, and confirm the spreadsheet is shared with that address as Editor. Read access verified by opening the "Top 250 Stocks" tab of "my-gtt-tracker" with the key; write access is confirmed by the first run in Stage 2.
- [ ] Restrict file access to your Windows user (right-click -> Properties -> Security), or in PowerShell: `icacls gsheet-access-keys.json /inheritance:r /grant:r "$env:USERNAME:(R)"`.
- [ ] Optional hygiene: delete the old key in GCP once the new one works, if you no longer need it.
- No commit (nothing in the repo changes).

Note for Stage 2: Windows defaults to cp1252 encoding; set `$env:PYTHONUTF8 = "1"` in the wrapper to avoid encoding errors.

## Stage 2: Manual local run

Outcome: running one command (or double-clicking) updates the sheet, A1 shows a fresh "Last Update" timestamp from this laptop, and a log file is written.

### First manual run

Status: **Done** (2026-10-03). Both runs exited 0 and wrote to the sheet.

- [x] In a terminal (PowerShell shown), set the env var from the file (key in project root, per User Inputs):
  `$env:PYTHONUTF8 = "1"; $env:GCP_CREDENTIALS = Get-Content .\gsheet-access-keys.json -Raw`
- [x] Run `.venv\Scripts\python update_sheet.py` with `RUN_DATE` unset, then once with a known past trading day, e.g. `$env:RUN_DATE = "2026-10-01"`.
  - Unset (today = Sat 03-Oct): skipped the weekend, 02-Oct (Gandhi Jayanti holiday) returned no file, so it fell back to Thu 01-Oct, start column `T`. "SUCCESS: Sheet Updated!", exit 0.
  - `RUN_DATE=2026-10-01`: start column `T`, "SUCCESS: Sheet Updated!", exit 0.
  - Prints a harmless `DeprecationWarning` for the `worksheet.update('A1', ...)` argument order (gspread 6); goes away in Stage 6 when the A1 write is folded into `batch_update`.
- [x] Check the sheet: the correct weekday column block is filled, header cells are right, and A1 shows the data date.
  - T1 = "Thursday", U1 = "01-Oct-2026" (Thursday block = column 20 = `T`).
  - A1 = "Data Date: 01-Oct-2026 | Last Update: 03-Oct 14:44 (IST)".
  - Row 2 is the sheet's header row ("NSE Code", "Volume", "Open Price", "Close Price", "Low", "High", "Signal"); 250 data rows have column `T` filled (e.g. MONEYVIEW, volume 655464953). Sheet has 382 symbol rows in total from earlier days.
- [x] Check NSE is reachable from the home network (the fetch prints "Fetch failed: ..." if blocked). Reachable; no "Fetch failed" lines.
- [x] Save this output as the baseline for comparing refactor stages (see Verification). Saved (gitignored, local only) in `logs/`: `baseline-unset.log`, `baseline-2026-10-01.log`, and a full-sheet snapshot `baseline-sheet-2026-10-01.json` (all values from `get_all_values()`).
- No commit. If anything fails, see Troubleshooting.

### Wrapper script

Status: **Done** (2026-10-03).

- [x] Add `scripts/run_local.ps1` that:
  - reads the key path from a variable at the top (or from `NSE_KEY_PATH`),
  - sets `GCP_CREDENTIALS` from the file,
  - accepts an optional `-RunDate` parameter and sets `RUN_DATE`,
  - runs the venv Python on `update_sheet.py`,
  - appends stdout/stderr to `logs\run-YYYYMMDD.log`,
  - returns Python's exit code as its own.
  - Written for Windows PowerShell 5.1 (the only PowerShell installed): stderr is merged without aborting, the log is UTF-8, and the caller's env vars (including `GCP_CREDENTIALS`) are restored afterwards. `-KeyPath` overrides `NSE_KEY_PATH`; `-RunDate` must be `YYYY-MM-DD`.
- [x] Run it by hand, with and without `-RunDate`; confirm the log file and the sheet.
  - Unset and `-RunDate 2026-10-01`: both "Start Column: T", "SUCCESS: Sheet Updated!", exit 0; output appended to `logs\run-20261003.log`.
  - Failure paths: missing key file -> exit 1 with an ERROR line; invalid key JSON -> Python traceback in the log, exit 1; malformed `-RunDate` -> rejected by parameter validation, exit 1.
- [x] Add a short "Running locally" section to a README (create one if absent) describing the three steps: venv, key, wrapper. Created `README.md`.
- Commit: "Add local run wrapper and README section".

## Stage 3: Code foundation

Status: **Done** (2026-10-03).

Outcome: importing `update_sheet` makes no Google calls, auth uses a supported library, and a run produces the same sheet output as the Stage 2 baseline.

- [x] Wrap setup and run logic in `get_worksheet()` and `main()`. Spreadsheet ID and tab name moved to `SPREADSHEET_ID` / `WORKSHEET_NAME` constants; `main()` calls `get_worksheet()` first so a missing/bad key still fails before any NSE fetch.
- [x] Add an `if __name__ == "__main__":` guard so importing the module has no side effects (no Google calls at import time). Verified: `import update_sheet` with `GCP_CREDENTIALS` unset succeeds.
- [x] Replace `oauth2client` (deprecated) with `gspread.service_account_from_dict`; remove `oauth2client` from `requirements.txt` (and `main.yml` if it still lists it). How the key is supplied does not change. `main.yml` already installs from `requirements.txt`; `oauth2client` was also uninstalled from the local venv to prove it is unused.
- [x] Remove unused imports (`date`), commented-out code and the stale usage block. The loop's duplicated `fetched_date_str` logic and the Hindi comment are left for Stages 6 and 7.
- Checks: `-RunDate 2026-10-01` -> column `T`, exit 0; `-RunDate 2026-10-04` (Sunday) -> skipped weekend and the 02-Oct holiday, column `T`, exit 0; `GCP_CREDENTIALS` unset -> `RuntimeError`, exit 1. Full-sheet diff against `baseline-sheet-2026-10-01.json`: 383 rows, only cell A1 differs (the "Last Update" timestamp).
- Commit: "Add main() entry point and switch to gspread auth".

## Stage 4: Loud failures

Status: **Done** (2026-10-03).

Outcome: a failed run (network error, malformed CSV, bad key) exits non-zero, shows red in GitHub Actions, writes a clear FAIL line in the local log, and shows a non-zero "Last Run Result" in Task Scheduler. Holidays still fall back to the previous trading day.

### In `update_sheet.py`

- [x] Distinguish failure modes in the NSE fetch:
  - 404 / no file (holiday): return None and try the previous day. Probed NSE: a trading day returns 200; a holiday (02-Oct), a weekend and a not-yet-published day all return 404 with an HTML page.
  - Network or parse/schema error: raise, do not fall back a day silently. Raises `FetchError` on `requests` exceptions, any status other than 200/404 (e.g. 403 when blocked), a corrupt zip/CSV, or no EQ rows left after filtering.
- [x] Exit non-zero if no trading day's data was fetched. Raises `FetchError` after the 5-day lookback (`LOOKBACK_DAYS`).
- [x] Validate required columns immediately after loading the CSV, before filtering and sorting. The error names the missing columns and lists the ones present.
- [x] Replace ad-hoc `print` with `logging` (also gives cleaner wrapper log files). Timestamped `INFO`/`ERROR` lines to stdout; the `__main__` block catches any exception, logs `FAIL: sheet not updated` with the traceback, and exits 1.
- Also: an invalid `RUN_DATE` now fails (exit 1) instead of warning and silently running for today.

### In the local wrapper

- [x] Make the wrapper log a clear OK/FAIL line with the exit code: `RESULT: OK (exit 0)` / `RESULT: FAIL (exit 1)`, before the end marker.
- [x] Optional: show a Windows toast or send yourself an email on a non-zero exit. Toast done (best effort, uses Windows PowerShell's AppUserModelID; a toast failure only logs a WARNING). `-NoToast` suppresses it. Email not done (would need SMTP credentials).

### Checks

- [x] Run with a weekend/holiday `RUN_DATE` and confirm the fallback to the previous trading day. `-RunDate 2026-10-04` (Sunday): skipped the weekend, logged the 404 for 02-Oct, wrote 01-Oct to column `T`, exit 0. `-RunDate 2026-10-01`: column `T`, exit 0. Full-sheet diff against `baseline-sheet-2026-10-01.json`: 383 rows, only A1 (timestamp) differs.
- [x] Simulate a failure (bad URL or malformed CSV) and confirm a non-zero exit code. Against a fake worksheet (no sheet writes): network error, HTTP 403, corrupt zip, missing columns, all-404 window -> each exit 1 with a specific `FetchError`. Also `RUN_DATE=2026-13-01` -> exit 1; `GCP_CREDENTIALS` unset -> exit 1. Wrapper with an invalid key JSON -> Python `FAIL` line, `RESULT: FAIL (exit 1)`, toast (confirmed on screen); missing key file -> `RESULT: FAIL (exit 1)`.
- Commit: "Fail loudly on fetch errors and add logging".

## Stage 5: Unattended schedule

Status: **Done** (2026-10-03). GitHub Actions is primary, moved to 20:00 IST. The local task is registered but disabled; `scripts/local_schedule.ps1 enable|disable|status|remove` toggles it.

Outcome: the sheet and log update on weekdays without you, a forced failure is visible in Task Scheduler, and exactly one system owns the schedule (no unintended double writes).

Do this after Stage 4; otherwise the wrapper's exit code is always 0 and a failed unattended run looks successful.

### Windows Task Scheduler

- [x] Create a task, e.g. "NSE Auto Sheet", with trigger Weekly Mon-Fri at your chosen local time (IST time, no UTC conversion; the old cron 05:56 UTC equals 11:26 IST). Created as "NSE Auto Sheet", Mon-Fri 20:00 IST (laptop timezone is India Standard Time). By 20:00 the same day's bhavcopy is normally published.
- [x] Action: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\vinee\workspace\stocks-screening\NSE-Auto-Sheet\scripts\run_local.ps1`, with "Start in" set to the repo folder. Also uses `-WindowStyle Hidden`.
- [x] Settings: "Run task as soon as possible after a scheduled start is missed"; optionally "Wake the computer to run this task"; "Run only when user is logged on" is fine (avoids storing a password). Interactive logon as the current user with limited rights; start when available; runs on battery; 30-minute time limit; a second instance is not started if one is still running. Wake is off by default (`-WakeToRun` turns it on).
- [ ] Test with "Run" in Task Scheduler, then check the log and sheet. Next day, confirm the unattended run.
  - Run on demand (Sat 03-Oct 14:58): `LastTaskResult 0`; the log shows the 404 for 02-Oct, 01-Oct written to column `T`, `RESULT: OK (exit 0)`; A1 updated to 14:59.
  - Unattended run not confirmed: the local task is disabled (GitHub is primary). Confirm the first run after enabling it, if you ever do.
- [x] Force a failure (bad key path) and confirm History / "Last Run Result" shows a non-zero result. Temporarily added `-KeyPath missing-key.json -NoToast` to the action: `LastTaskResult 1`, log shows `ERROR: Key file not found` and `RESULT: FAIL (exit 1)`. Task re-registered with the normal action afterwards.
- [x] Optionally export the task XML into `scripts/` so it can be recreated. Instead added `scripts/local_schedule.ps1` (`enable` / `disable` create or replace the task; also `status`, `remove`; options `-At HH:mm`, `-WakeToRun`). Unlike an XML export, it contains no user SID or machine-specific paths. README has a "Scheduling on the laptop" section.
- Commits: "Add Task Scheduler registration script", then "Run GitHub schedule at 20:00 IST; local schedule toggle".

### Role of the GitHub workflow

- [x] Choose one: (a) local only: remove the `schedule:` trigger from `main.yml` and keep `workflow_dispatch`; (b) GitHub primary, local as manual backup; (c) both (safe because writes are upserts, but wasteful). Chose (b) GitHub primary. The local task is disabled. Both schedules use 20:00 IST, so enabling the local one is a drop-in backup.
- [x] Apply the choice to `main.yml`. Cron changed from `56 05 * * 1-5` (11:26 IST, which wrote the previous day's data) to `30 14 * * 1-5` (20:00 IST, the same day's bhavcopy). GitHub cron can start several minutes late.

## Stage 6: Clean internals

Status: **Done** (2026-10-03), commits `7ad46ea`..`a44b4c4`, not yet pushed.

Outcome: the fetch, parse, select and write steps are small functions with unit tests; config lives in one place (so local and CI can target different sheets, e.g. a test sheet); the sheet is written in a single call. Sheet output still matches the Stage 2 baseline.

Do each part as a separate small commit.

How it was checked: `logs/stage6/capture.py` (gitignored) runs `main()` offline with a fake worksheet seeded from the baseline snapshot and a cached 01-Oct bhavcopy, and dumps every cell write. After each of the first three commits the writes were identical to the pre-Stage-6 code (253 ranges: A1, T1, U1, 250 rows). Reuse it in Stage 7 to prove the module split only moves code.

### Split the fetcher

- [x] `download_bhavcopy(date)` returns bytes or None.
- [x] `parse_bhavcopy(bytes)` returns a DataFrame with canonical column names.
- [x] `select_top_liquid(df, n)` applies the series/ETF filters and ranks by volume.
- [x] Add one column-alias map (e.g. `{"symbol": ["TckrSymb", "SYMBOL"], ...}`) with a `resolve_columns` helper; rename once so downstream code ignores old/new formats. `series` is optional, everything else is required; the error names the missing canonical columns and their aliases.
- [x] Review the keyword filter (`CASE`, `GOLD`, `LIQ`): substring matching may drop real equities. Switch to a tighter pattern or an explicit exclusion list.
  - Finding (01-Oct data): the keyword filter dropped real stocks (SKYGOLD, GOLDIAM, SHANTIGOLD, DECNGOLD, SILVERTUC, JETFREIGHT) and let ETFs without those words into the top 250 (TATSILV, METAL, BSLNIFTY, ALPHA, GROWWPOWER, MOMENTUM50).
  - Replaced it with an ISIN-prefix rule: fund/ETF units have `INF` ISINs, company shares `INE` (on 01-Oct all 349 `INF` rows in the EQ series were funds). `ISIN` is now a required column.
  - Effect on 01-Oct: six ETFs out, six stocks in (DRREDDY, ZYDUSLIFE, EPL, HMAAGRO, JTLIND, VIKRAMSOLR). It is in its own commit (`a44b4c4`), so it can be reverted alone. The six ETF rows stay in the sheet with their earlier values; nothing overwrites them any more.

### Config and orchestration

- [x] Central config section (moves to `config.py` in Stage 7): spreadsheet ID (preferably from env var), tab name, top-N (250), filter keywords, NSE URL and headers, day-block width (6). Top of `update_sheet.py`. `SPREADSHEET_ID` / `WORKSHEET_NAME` env vars override the defaults (blank = default, so CI is unaffected).
- [x] `resolve_run_date()` for `RUN_DATE` parsing.
- [x] `find_latest_trading_day(today)` returns `(date, data)`; remove duplicated `fetched_date_str` logic and the redundant `if data_to_insert:` inside the loop.
- [x] Do the sheet write once, outside the loop.

### Sheet helpers

- [x] Drop `col_num_to_letter`; use `gspread.utils.rowcol_to_a1` / `a1_to_rowcol`. `start_col_for_date` now returns a column number; `col_letter()` is only used for the log line.
- [x] Tie the day-block width constant to the data column list so they cannot drift apart. `DAY_BLOCK_WIDTH = len(SHEET_COLUMNS[1:]) + 1` (the values plus the sheet's "Signal" column).
- [x] Fold header, data and status-cell writes into a single `batch_update` (remove the separate `worksheet.update('A1', ...)`). The gspread `DeprecationWarning` is gone.

### Tests

- [x] Add unit tests for `parse_bhavcopy`, `select_top_liquid`, `start_col_for_date` and `upsert_rows` using fixtures and a fake worksheet. `tests/test_update_sheet.py` has 33 tests, also covering `download_bhavcopy`, `resolve_run_date`, `find_latest_trading_day` and `main()` (one batch, no other writes). pytest is in `requirements-dev.txt`, and `pytest.ini` sets the import path. Run: `.venv\Scripts\python -m pytest`. Tests run locally only; GitHub Actions does not run them (decided 2026-10-03).

### Checks

- Live run via the wrapper with `-RunDate 2026-10-04` (Sunday): 404 for 02-Oct, 01-Oct written to column `T`, `RESULT: OK (exit 0)`, no warnings.
- Full-sheet diff against `baseline-sheet-2026-10-01.json`: 383 rows. Besides A1, only the six newly included stocks changed (their Thursday block, plus the sheet's own Signal/Weekly formula cells). New snapshot: `logs/stage6/sheet-after-stage6.json`.

## Stage 7: Readable structure

Status: **Done** (2026-10-03), commits `673b29c`, `572fb71`, `678b2a8`, not yet pushed. The GitHub `workflow_dispatch` check is still open until the commits are pushed.

Outcome: someone new can read `update_sheet.py` top to bottom in a minute and know what the job does, then open just one other file to see how a step works. The project has four source files plus tests. GitHub Actions, `run_local.ps1`, the Task Scheduler action and the README still run `python update_sheet.py` with no changes. Cell writes are identical to Stage 6.

Starting point (after Stage 6): `update_sheet.py` is 227 lines with four numbered sections (`# 1. Config`, `# 2. NSE UDiFF Data Fetcher`, `# 3. Sheet Writer`, `# 4. Execution Logic`); the functions are already small and covered by 33 tests in `tests/test_update_sheet.py`. So this stage mostly moves code along those section boundaries, then tidies `main()`.

### Target layout (flat modules, no package)

Four files are the smallest useful split. Each file has one reason to change. A package (`nse_auto_sheet/`) or more files would add imports and ceremony and not make anything easier to read.

| File | Responsibility | Contains (current names; new ones in bold) | Approx. size |
|---|---|---|---|
| `update_sheet.py` | Entry point: read env vars, run the steps, log, set the exit code | `main()`, `resolve_run_date()`, **`credentials_from_env()`** (the env part of `get_worksheet`), logging setup, `__main__` guard | ~45 lines |
| `config.py` | Every tunable value, in one place, with a comment each | `SPREADSHEET_ID` / `WORKSHEET_NAME` (env overrides), `TOP_N`, `LOOKBACK_DAYS`, `NSE_URL`, `NSE_HEADERS`, `NSE_TIMEOUT`, `COLUMN_ALIASES`, `OPTIONAL_COLUMNS`, `EQUITY_SERIES`, `FUND_ISIN_PREFIX`, sheet layout (`SHEET_COLUMNS`, `KEY_COL`, `FIRST_BLOCK_COL`, `DAY_BLOCK_WIDTH`, `STATUS_CELL`) | ~50 lines |
| `nse.py` | Getting the data: "which trading day, and what are its top-N rows" | `FetchError`, **`TradingDay`**, `download_bhavcopy`, `resolve_columns`, `parse_bhavcopy`, `select_top_liquid`, `find_latest_trading_day` | ~100 lines |
| `sheet.py` | Writing the data: "where it goes in the sheet" | **`open_worksheet(credentials)`** (the gspread part of `get_worksheet`), `start_col_for_date`, `col_letter`, `day_header_updates`, **`status_update`**, `upsert_rows`, **`write_day`** | ~75 lines |
| `tests/test_nse.py`, `tests/test_sheet.py`, `tests/test_update_sheet.py` | The existing 33 tests, split to match; `test_update_sheet.py` keeps the `resolve_run_date` and `main()` tests | shared helpers (`make_zip`, `udiff_csv`, `FakeWorksheet`, ...) move to `tests/conftest.py` or a small `tests/helpers.py` | |

Dependency direction: `update_sheet` imports `config`, `nse` and `sheet`. `nse` imports only `config`; `sheet` imports `config` and the `TradingDay` type from `nse`. Only `update_sheet.py` (`GCP_CREDENTIALS`, `RUN_DATE`) and `config.py` (`SPREADSHEET_ID`, `WORKSHEET_NAME`) read environment variables, so `nse` and `sheet` can be tested without env setup.

### Commit 1: move code only

- [x] Create `config.py`, `nse.py`, `sheet.py` from the four numbered sections, with no renames or logic changes. `update_sheet.py` keeps `main()`, `resolve_run_date()` and the `__main__` block.
- [x] Each module gets its own `logging.getLogger(__name__)`. Keep the `update_sheet` logger name for the entry point so log lines look the same.
- [x] Split the tests and update monkeypatch targets to the new module (e.g. `nse.requests.get` instead of `update_sheet.requests.get`). `pytest.ini` (`pythonpath = .`) already makes the flat imports work.
- Check: `pytest` passes; `logs/stage6/capture.py` (pointed at the new modules) shows the same 253 cell writes as after Stage 6.
- Done: shared test helpers went to `tests/helpers.py` (plain imports, not fixtures). `get_worksheet()` stayed in `update_sheet.py` until commit 2. `logs/stage7/capture.py` handles both commits' entry points; output identical to `logs/stage7/ref.json` (= `logs/stage6/p5.json`) after each commit.
- Commit: "Split update_sheet.py into config, nse and sheet modules".

### Commit 2: readable core, `main()` as the job description

- [x] `main()` should be about five lines, one per step, with no date formatting or update dicts. Target shape:

  ```python
  def main() -> None:
      worksheet = sheet.open_worksheet(credentials_from_env())  # fails fast on a bad key, before any NSE call
      run_date = resolve_run_date(os.environ.get("RUN_DATE"))   # RUN_DATE or today
      day = nse.find_latest_trading_day(run_date)               # skips weekends/holidays; raises FetchError
      sheet.write_day(worksheet, day)                           # headers + rows + A1 status, one batch_update
      logger.info("SUCCESS: sheet updated with %s", day.label)
  ```

- [x] Add `TradingDay` (a small `dataclass`: `date`, `rows`, and a `label` property such as "01-Oct-2026") and have `find_latest_trading_day` return it instead of the `(date, rows)` tuple, so the `%d-%b-%Y` formatting lives in one place.
- [x] Add `sheet.write_day(worksheet, day)`: start column, header updates, status update, then `upsert_rows` (one `batch_update`). The status-message and "Fetched N rows; start column" log lines move here from `main()`.
- [x] Split `get_worksheet()` into `credentials_from_env()` (in `update_sheet.py`) and `sheet.open_worksheet(credentials)`.
- Check: `pytest` passes (update the `main()` test for the new return type); capture output unchanged.
- Done: also added `config.DATE_LABEL` (`%d-%b-%Y`) used by `nse` and `sheet`, and tests for `credentials_from_env` and `status_update` (36 tests). `main()` keeps a "Run date" log line, so it is six lines. `write_day` logs "Status: ..." and `main()` ends with "SUCCESS: sheet updated with 01-Oct-2026". `sheet.py` does not import `TradingDay` yet; it comes with the type hints in Stage 8.
- Commit: "Simplify main() with TradingDay and write_day".

### Readability rules (apply in both commits)

- [x] Each module starts with a one- or two-line docstring saying what it is for. Public functions without a docstring today (`get_worksheet`, `col_letter`, `day_header_updates`) get a one-liner.
- [x] Each function works at one level of detail: orchestration functions call helpers; helpers do not call back up.
- [x] Names say what the thing is (e.g. `rows`, `day`, `TOP_N`); no magic numbers or strings outside `config.py`.
- [x] Remove the numbered section comments (`# 1. Config` ... `# 4. Execution Logic`); the file boundaries replace them. Keep comments that explain why (why 404 means a holiday, why the ISIN prefix identifies ETFs); drop ones that restate the code.
- [x] Put public functions first in each module, in call order, with private helpers (`_name`) below them.

### Commit 3: docs

- [x] Add a short "How it works" section to the README: the four files in one line each, and the `main()` steps.
- [x] ~~Add `pytest` to `requirements-dev.txt`~~: already done in Stage 6. Tests stay local only (no `pytest` step in `main.yml`), per the Stage 6 decision.
- Commit: "Add README How it works section".

### Checks

- The full Verification list below.
- `python -c "import update_sheet, nse, sheet, config"` with no env vars set succeeds and makes no network calls.
- `python update_sheet.py` from the repo root works locally (wrapper, `-RunDate 2026-10-01`) and in one `workflow_dispatch` run on GitHub (the script's folder is on `sys.path`, so flat imports resolve).
- Full-sheet diff against `logs/stage6/sheet-after-stage6.json` shows only A1.

Results (2026-10-03): 36 tests pass; imports with no env vars succeed; capture identical (253 ranges, Sunday 04-Oct falls back to 01-Oct); wrapper run `-RunDate 2026-10-01` gives `RESULT: OK (exit 0)`; `-RunDate 2026-02-30` gives `RESULT: FAIL (exit 1)`; live-sheet diff (`logs/stage7/snapshot.py`, saved as `logs/stage7/sheet-after-stage7.json`) changes only A1. Open: the GitHub `workflow_dispatch` run, after pushing.

## Stage 8: Housekeeping

Outcome: the status timestamp is correct IST regardless of the laptop's timezone, and the code is consistent and typed.

- [x] Replace `datetime.utcnow()` (deprecated since Python 3.12) with `datetime.now(ZoneInfo("Asia/Kolkata"))` in `sheet.status_update`. Consider the same for "today" in `resolve_run_date`, so a run from a laptop in another timezone picks the IST date. Done: `config.TIMEZONE` is used by both; `resolve_run_date` returns a naive datetime holding the IST date, like a parsed `RUN_DATE`. `tzdata` (needed by `zoneinfo` on Windows) is already installed as a pandas dependency.
- [x] ~~Translate the Hindi comment to English~~: no longer present (removed during Stages 3-6).
- [x] Add basic type hints to the public functions in `nse.py`, `sheet.py` and `update_sheet.py`. Python 3.10 syntax (`bytes | None`, `list[dict]`), matching the GitHub workflow.

Results (2026-10-03): 38 tests pass (new: status time and blank `RUN_DATE` at 01-Oct 20:00 UTC give 02-Oct 01:30 IST); imports with no env vars succeed; wrapper run `-RunDate 2026-10-01` gives `RESULT: OK (exit 0)` with status `Last Update: 03-Oct 15:21 (IST)`; live-sheet diff against a snapshot taken just before (`logs/stage8/`) changes only A1.

## Alternative: WSL instead of native Windows

Only if you prefer Linux tooling. Replaces the Windows parts of Stages 2 and 5. Outcome: a WSL run succeeds and Windows Task Scheduler triggers it.

- [ ] Create the venv inside the WSL filesystem (not `/mnt/c`, which is slower) and install requirements.
- [ ] Add `scripts/run_local.sh` equivalent to the PowerShell wrapper: `export GCP_CREDENTIALS="$(cat ~/secrets/nse-sheet-key.json)"` then run Python; log to `logs/`.
- [ ] Do not rely on `cron` inside WSL alone: WSL shuts down when idle. Trigger from Windows Task Scheduler with `wsl.exe -e /home/<user>/.../run_local.sh`, or enable systemd in `/etc/wsl.conf` and use a systemd timer plus Windows keeping WSL alive.
- [ ] Keep the key in the WSL home with `chmod 600`.

---

## Verification (applies to every code stage)

- Run with `RUN_DATE` set to a known trading day and compare the sheet output against the latest baseline (same rows, same columns, same header cells): `baseline-sheet-2026-10-01.json` up to Stage 5, `logs/stage6/sheet-after-stage6.json` from Stage 6 on (the ISIN filter changed six rows).
- Run with a weekend/holiday `RUN_DATE` to confirm the fallback to the previous trading day.
- Simulate a failure (bad URL or malformed CSV) and confirm a non-zero exit code (from Stage 4 on).
- Run the unit tests (from Stage 6 on).
- Import every module with no env vars set and confirm there are no side effects (from Stage 7 on).

## Troubleshooting

- `RuntimeError: GCP_CREDENTIALS is not set`: the env var is not set in that shell or task; check the wrapper.
- `APIError 403 / PERMISSION_DENIED`: the sheet is not shared with the service account's `client_email`, or the Sheets/Drive API is not enabled in the GCP project.
- `Fetch failed` for every date: NSE blocked the request or the network is down; try a browser to `nsearchives.nseindia.com`, then retry later.
- Task ran but nothing happened: check "Start in" directory, the log file, and that the task uses the venv Python path, not a system one.
- Laptop asleep at run time: confirm the "run as soon as possible after a missed start" setting.
- Key leaked into git: rotate it in GCP immediately, then remove it from history.

## Security

- The key never goes in the repo, a `.env` committed to git, or chat/logs. Do not print `GCP_CREDENTIALS` in the wrapper.
- Use a service account scoped to just this sheet (shared as Editor on that sheet only).
