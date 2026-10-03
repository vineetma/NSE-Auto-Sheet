import gspread
import pandas as pd
import requests
import zipfile
import io
from datetime import datetime, timedelta
import os
import json

# 1. Sheet Setup
# The middle value in the Google Sheet URL (not the tab).
SPREADSHEET_ID = "1mOVPxjgc1w0j2WPG_Xp4t8SKl_eb2-wHCWfdAiO145Q"
WORKSHEET_NAME = "Top 250 Stocks"

def get_worksheet():
    creds_json = os.environ.get('GCP_CREDENTIALS')
    if not creds_json:
        raise RuntimeError("GCP_CREDENTIALS is not set")
    client = gspread.service_account_from_dict(json.loads(creds_json))
    return client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

# 2. NSE UDiFF Data Fetcher
def fetch_bhavcopy_for_date(date_obj):
    date_str = date_obj.strftime("%Y%m%d")
    url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                csv_filename = z.namelist()[0]
                with z.open(csv_filename) as f:
                    df = pd.read_csv(f)
                    
                    sym_col = 'TckrSymb' if 'TckrSymb' in df.columns else 'SYMBOL'
                    close_col = 'ClsPric' if 'ClsPric' in df.columns else 'CLOSE'
                    open_col = 'OpnPric' if 'OpnPric' in df.columns else 'OPEN'
                    low_col = 'LwPric' if 'LwPric' in df.columns else 'LOW'
                    high_col = 'HghPric' if 'HghPric' in df.columns else 'HIGH'
                    series_col = 'SctySrs' if 'SctySrs' in df.columns else 'SERIES'
                    
                    vol_col = 'TtlTradgVol'
                    for c in ['TtlTradgVol', 'TtlTrdQty', 'TotTrdQty', 'TOTTRDQTY']:
                        if c in df.columns:
                            vol_col = c
                            break
                    
                    # सिर्फ EQ सीरीज और ETFs (LIQUID/BEES) को बाहर करना
                    if series_col in df.columns:
                        df = df[df[series_col].astype(str).str.strip() == 'EQ']
                    filter_keywords = 'BEES|ETF|GOLD|LIQUID|CASE|SILVER|LIQ'
                    df = df[~df[sym_col].astype(str).str.contains(filter_keywords, case=False, na=False)]
                    
                    df_top = df.sort_values(by=vol_col, ascending=False).head(250)
                    required = [sym_col, vol_col, open_col, close_col, low_col, high_col]
                    missing = [c for c in required if c is None or c not in df.columns]
                    if missing:
                        raise ValueError(f"Missing columns: {missing}")
                    return df_top[required].values.tolist()
        return None
    except Exception as e:
        print(f"Fetch failed: {e}")
        return None

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

    run_date_str = os.environ.get('RUN_DATE', '').strip()
    if run_date_str:
        try:
            today = datetime.strptime(run_date_str, '%Y-%m-%d')
        except ValueError:
            print(f"WARNING: RUN_DATE='{run_date_str}' is not in YYYY-MM-DD format, falling back to today.")
            today = datetime.now()
    else:
        today = datetime.now()
    data_to_insert = None
    fetched_date_str = ""

    for i in range(5):
        test_date = today - timedelta(days=i)
        if test_date.weekday() >= 5: continue

        data_to_insert = fetch_bhavcopy_for_date(test_date)
        if not data_to_insert:
            continue
        start_col = start_col_for_date(test_date)
        print("Start Column: ", start_col)
        header_updates = day_header_updates(start_col, test_date)
        upsert_rows(worksheet, data_to_insert, key_col='A', start_col=start_col, extra_updates=header_updates)
        fetched_date_str = test_date.strftime('%d-%b-%Y')
        if data_to_insert:
            fetched_date_str = test_date.strftime('%d-%b-%Y')
            break

    # 4. Update Sheet
    if data_to_insert:
        ist_now = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%d-%b %H:%M')
        status_msg = f"Data Date: {fetched_date_str} | Last Update: {ist_now} (IST)"
        worksheet.update('A1', [[status_msg]])
        print("SUCCESS: Sheet Updated!")


if __name__ == "__main__":
    main()
