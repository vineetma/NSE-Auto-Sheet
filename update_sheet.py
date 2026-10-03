"""Daily job: put the latest NSE trading day's top stocks by volume into the Google Sheet."""
import json
import logging
import os
import sys
from datetime import datetime, timedelta

import gspread

from config import SPREADSHEET_ID, STATUS_CELL, WORKSHEET_NAME
from nse import find_latest_trading_day
from sheet import col_letter, day_header_updates, start_col_for_date, upsert_rows

logger = logging.getLogger("update_sheet")


def main():
    worksheet = get_worksheet()

    today = resolve_run_date(os.environ.get('RUN_DATE'))
    logger.info("Run date: %s", today.strftime('%Y-%m-%d (%A)'))

    data_date, rows = find_latest_trading_day(today)
    start_col = start_col_for_date(data_date)
    logger.info("Fetched %d rows for %s; start column: %s",
                len(rows), data_date.strftime('%d-%b-%Y'), col_letter(start_col))

    ist_now = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%d-%b %H:%M')
    status_msg = f"Data Date: {data_date.strftime('%d-%b-%Y')} | Last Update: {ist_now} (IST)"
    status_update = {'range': STATUS_CELL, 'values': [[status_msg]]}
    upsert_rows(worksheet, rows, start_col, extra_updates=day_header_updates(start_col, data_date) + [status_update])
    logger.info("SUCCESS: Sheet Updated! (%s)", status_msg)


def get_worksheet():
    """Open the target worksheet with the service account key in GCP_CREDENTIALS."""
    creds_json = os.environ.get('GCP_CREDENTIALS')
    if not creds_json:
        raise RuntimeError("GCP_CREDENTIALS is not set")
    client = gspread.service_account_from_dict(json.loads(creds_json))
    return client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)


def resolve_run_date(value):
    """Parse RUN_DATE (YYYY-MM-DD); blank means today."""
    value = (value or '').strip()
    if not value:
        return datetime.now()
    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        raise ValueError(f"RUN_DATE='{value}' is not in YYYY-MM-DD format") from None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S", stream=sys.stdout)
    try:
        main()
    except Exception:
        logger.exception("FAIL: sheet not updated")
        sys.exit(1)
