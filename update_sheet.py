"""Daily job: put the latest NSE trading day's top stocks by volume into the Google Sheet."""
import json
import logging
import os
import sys
from datetime import datetime

import nse
import sheet

logger = logging.getLogger("update_sheet")


def main():
    worksheet = sheet.open_worksheet(credentials_from_env())  # fails fast on a bad key, before any NSE call
    run_date = resolve_run_date(os.environ.get('RUN_DATE'))   # RUN_DATE or today
    logger.info("Run date: %s", run_date.strftime('%Y-%m-%d (%A)'))
    day = nse.find_latest_trading_day(run_date)               # skips weekends/holidays; raises FetchError
    sheet.write_day(worksheet, day)                           # headers + rows + status cell, one batch_update
    logger.info("SUCCESS: sheet updated with %s", day.label)


def credentials_from_env():
    """The service account key from GCP_CREDENTIALS, parsed from JSON."""
    creds_json = os.environ.get('GCP_CREDENTIALS')
    if not creds_json:
        raise RuntimeError("GCP_CREDENTIALS is not set")
    return json.loads(creds_json)


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
