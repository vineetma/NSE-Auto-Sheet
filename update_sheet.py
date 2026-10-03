import gspread
import pandas as pd
import requests
import zipfile
import io
from datetime import datetime, timedelta
import os
import json
import logging
import sys

logger = logging.getLogger("update_sheet")

# 1. Config
# The middle value in the Google Sheet URL (not the tab). Set SPREADSHEET_ID / WORKSHEET_NAME
# in the environment to target a different sheet, e.g. a test copy.
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID') or "1mOVPxjgc1w0j2WPG_Xp4t8SKl_eb2-wHCWfdAiO145Q"
WORKSHEET_NAME = os.environ.get('WORKSHEET_NAME') or "Top 250 Stocks"

TOP_N = 250
LOOKBACK_DAYS = 5  # calendar days to search back for the latest bhavcopy

NSE_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date:%Y%m%d}_F_0000.csv.zip"
NSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}
NSE_TIMEOUT = 15  # seconds

# Canonical column name -> bhavcopy column names, UDiFF format first, then the old format.
COLUMN_ALIASES = {
    'symbol': ['TckrSymb', 'SYMBOL'],
    'series': ['SctySrs', 'SERIES'],
    'volume': ['TtlTradgVol', 'TtlTrdQty', 'TotTrdQty', 'TOTTRDQTY'],
    'open': ['OpnPric', 'OPEN'],
    'close': ['ClsPric', 'CLOSE'],
    'low': ['LwPric', 'LOW'],
    'high': ['HghPric', 'HIGH'],
}
OPTIONAL_COLUMNS = {'series'}

EQUITY_SERIES = 'EQ'
EXCLUDE_SYMBOL_KEYWORDS = ['BEES', 'ETF', 'GOLD', 'LIQUID', 'CASE', 'SILVER', 'LIQ']

# Values written per stock: column A holds the symbol, the rest go into the day's block.
SHEET_COLUMNS = ['symbol', 'volume', 'open', 'close', 'low', 'high']

def get_worksheet():
    creds_json = os.environ.get('GCP_CREDENTIALS')
    if not creds_json:
        raise RuntimeError("GCP_CREDENTIALS is not set")
    client = gspread.service_account_from_dict(json.loads(creds_json))
    return client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

# 2. NSE UDiFF Data Fetcher
class FetchError(RuntimeError):
    """The bhavcopy could not be downloaded or parsed (not a holiday)."""

def download_bhavcopy(date_obj):
    """Return the bhavcopy zip bytes for date_obj, or None if NSE has no file (holiday / not yet published).

    Raises FetchError on network errors or an unexpected HTTP status,
    so a real failure is never mistaken for a holiday.
    """
    url = NSE_URL.format(date=date_obj)
    try:
        response = requests.get(url, headers=NSE_HEADERS, timeout=NSE_TIMEOUT)
    except requests.RequestException as e:
        raise FetchError(f"Network error fetching {url}: {e}") from e

    if response.status_code == 404:
        logger.info("No bhavcopy for %s (HTTP 404: holiday or not yet published)", date_obj.strftime('%d-%b-%Y'))
        return None
    if response.status_code != 200:
        raise FetchError(f"Unexpected HTTP {response.status_code} fetching {url}")
    return response.content

def resolve_columns(columns):
    """Map each canonical name in COLUMN_ALIASES to the first alias present in columns.

    Optional columns that are absent are left out; any other missing column raises FetchError.
    """
    resolved, missing = {}, []
    for name, aliases in COLUMN_ALIASES.items():
        found = next((a for a in aliases if a in columns), None)
        if found:
            resolved[name] = found
        elif name not in OPTIONAL_COLUMNS:
            missing.append(f"{name} ({'/'.join(aliases)})")
    if missing:
        raise FetchError(f"Bhavcopy is missing columns {missing}; got {list(columns)}")
    return resolved

def parse_bhavcopy(content):
    """Read the CSV inside the bhavcopy zip into a DataFrame with canonical column names only."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            with z.open(z.namelist()[0]) as f:
                df = pd.read_csv(f)
    except Exception as e:
        raise FetchError(f"Could not read bhavcopy zip/CSV: {e}") from e

    columns = resolve_columns(df.columns)
    return df[list(columns.values())].rename(columns={v: k for k, v in columns.items()})

def select_top_liquid(df, n):
    """Keep EQ-series stocks (no ETFs/funds) and return the n with the highest volume."""
    if 'series' in df.columns:
        df = df[df['series'].astype(str).str.strip() == EQUITY_SERIES]
    filter_keywords = '|'.join(EXCLUDE_SYMBOL_KEYWORDS)
    df = df[~df['symbol'].astype(str).str.contains(filter_keywords, case=False, na=False)]
    return df.sort_values(by='volume', ascending=False).head(n)

def resolve_run_date(value):
    """Parse RUN_DATE (YYYY-MM-DD); blank means today."""
    value = (value or '').strip()
    if not value:
        return datetime.now()
    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        raise ValueError(f"RUN_DATE='{value}' is not in YYYY-MM-DD format") from None

def find_latest_trading_day(today):
    """Return (date, rows) for the latest weekday up to today that has a bhavcopy.

    rows are SHEET_COLUMNS values for the top TOP_N stocks. Holidays (no file) fall back a day,
    up to LOOKBACK_DAYS; raises FetchError if none is found or a file is unusable.
    """
    for i in range(LOOKBACK_DAYS):
        day = today - timedelta(days=i)
        if day.weekday() >= 5:
            continue
        content = download_bhavcopy(day)
        if content is None:
            continue
        try:
            top = select_top_liquid(parse_bhavcopy(content), TOP_N)
        except FetchError as e:
            raise FetchError(f"Bhavcopy for {day.strftime('%d-%b-%Y')}: {e}") from e
        if top.empty:
            raise FetchError(f"Bhavcopy for {day.strftime('%d-%b-%Y')} has no {EQUITY_SERIES} rows after filtering")
        return day, top[SHEET_COLUMNS].values.tolist()
    raise FetchError(f"No bhavcopy found in the {LOOKBACK_DAYS} days up to {today.strftime('%d-%b-%Y')}")

def col_num_to_letter(n):
    """1 -> A, 2 -> B, ... 27 -> AA, etc."""
    letters = ''
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
    
def start_col_for_date(d):
    """Monday=1 ... Sunday=7, matching your (wkday-1)*6+2 formula."""
    weekday = d.isoweekday()  # Mon=1, ..., Sun=7
    col_idx = (weekday - 1) * 6 + 2
    return col_num_to_letter(col_idx)

def day_header_updates(start_col, d):
    col_idx = gspread.utils.a1_to_rowcol(f"{start_col}1")[1]
    next_col = col_num_to_letter(col_idx + 1)
    return [
        {'range': f"{start_col}1", 'values': [[d.strftime('%A')]]},        # e.g. "Wednesday"
        {'range': f"{next_col}1", 'values': [[d.strftime('%d-%b-%Y')]]},   # e.g. "30-Sep-2026"
    ]
    
def upsert_rows(worksheet, data_to_insert, key_col='A', start_col='B', extra_updates=None):
    """
    data_to_insert: list of rows, each row = [key, value1, value2, ...]
                    (key = the symbol/date/whatever goes in key_col;
                     value1, value2, ... are what gets pasted starting at start_col)
    key_col:   column holding the match key (default 'A')
    start_col: column where the non-key values start being pasted (default 'B')
    extra_updates: optional list of {'range': ..., 'values': [[...]]} dicts
                   to fold into the same batch_update call (e.g. header row cells).
    """
    key_col_idx = gspread.utils.a1_to_rowcol(f"{key_col}1")[1]

    # one read: existing keys from row 2 down
    existing_keys = worksheet.col_values(key_col_idx)[1:]
    key_to_row = {str(k).strip(): i + 2 for i, k in enumerate(existing_keys) if str(k).strip()}
    next_new_row = len(existing_keys) + 2

    batch_data = list(extra_updates) if extra_updates else []
    for row in data_to_insert:
        key, *values = row
        key = str(key).strip()

        if key in key_to_row:
            target_row = key_to_row[key]
        else:
            target_row = next_new_row
            key_to_row[key] = target_row
            next_new_row += 1
            # new row — write the key into column A ourselves
            batch_data.append({'range': f"{key_col}{target_row}", 'values': [[key]]})

        batch_data.append({'range': f"{start_col}{target_row}", 'values': [values]})

    if batch_data:
        worksheet.batch_update(batch_data, value_input_option='USER_ENTERED')


# 3. Execution Logic
def main():
    worksheet = get_worksheet()

    today = resolve_run_date(os.environ.get('RUN_DATE'))
    logger.info("Run date: %s", today.strftime('%Y-%m-%d (%A)'))

    data_date, rows = find_latest_trading_day(today)
    start_col = start_col_for_date(data_date)
    logger.info("Fetched %d rows for %s; start column: %s",
                len(rows), data_date.strftime('%d-%b-%Y'), start_col)

    # 4. Update Sheet
    header_updates = day_header_updates(start_col, data_date)
    upsert_rows(worksheet, rows, key_col='A', start_col=start_col, extra_updates=header_updates)

    ist_now = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%d-%b %H:%M')
    status_msg = f"Data Date: {data_date.strftime('%d-%b-%Y')} | Last Update: {ist_now} (IST)"
    worksheet.update('A1', [[status_msg]])
    logger.info("SUCCESS: Sheet Updated! (%s)", status_msg)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S", stream=sys.stdout)
    try:
        main()
    except Exception:
        logger.exception("FAIL: sheet not updated")
        sys.exit(1)
