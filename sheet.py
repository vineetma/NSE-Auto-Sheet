"""Writing the data: where each trading day's rows go in the Google Sheet."""
import logging
from collections.abc import Iterable
from datetime import datetime

import gspread
from gspread.utils import rowcol_to_a1

from config import (DATE_LABEL, DAY_BLOCK_WIDTH, FIRST_BLOCK_COL, KEY_COL, SPREADSHEET_ID, STATUS_CELL, TIMEZONE,
                    WORKSHEET_NAME)
from nse import TradingDay

logger = logging.getLogger(__name__)


def open_worksheet(credentials: dict) -> gspread.Worksheet:
    """Open the target worksheet with a service account key (the parsed key JSON)."""
    client = gspread.service_account_from_dict(credentials)
    return client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)


def write_day(worksheet: gspread.Worksheet, day: TradingDay) -> None:
    """Write a TradingDay's rows into its weekday block, with the block headers and status cell, in one batch."""
    start_col = start_col_for_date(day.date)
    logger.info("Fetched %d rows for %s; start column: %s", len(day.rows), day.label, col_letter(start_col))
    status = status_update(day)
    upsert_rows(worksheet, day.rows, start_col, extra_updates=day_header_updates(start_col, day.date) + [status])
    logger.info("Status: %s", status['values'][0][0])


def start_col_for_date(d: datetime) -> int:
    """Column number of d's block: Monday -> 2 (B), Tuesday -> 8 (H), ... Thursday -> 20 (T)."""
    return FIRST_BLOCK_COL + (d.isoweekday() - 1) * DAY_BLOCK_WIDTH


def col_letter(col: int) -> str:
    """Column letter for a column number, e.g. 20 -> 'T'."""
    return rowcol_to_a1(1, col)[:-1]


def day_header_updates(start_col: int, d: datetime) -> list[dict]:
    """Row-1 updates naming the day of the block at start_col, e.g. 'Thursday' and '01-Oct-2026'."""
    return [
        {'range': rowcol_to_a1(1, start_col), 'values': [[d.strftime('%A')]]},
        {'range': rowcol_to_a1(1, start_col + 1), 'values': [[d.strftime(DATE_LABEL)]]},
    ]


def status_update(day: TradingDay) -> dict:
    """STATUS_CELL update saying which trading day the sheet holds and when it was written (IST)."""
    ist_now = datetime.now(TIMEZONE).strftime('%d-%b %H:%M')
    return {'range': STATUS_CELL, 'values': [[f"Data Date: {day.label} | Last Update: {ist_now} (IST)"]]}


def upsert_rows(worksheet: gspread.Worksheet, rows: list[list], start_col: int,
                extra_updates: Iterable[dict] = ()) -> None:
    """Write rows into the block at start_col, plus extra_updates, in a single batch_update.

    rows: each row = [key, value1, value2, ...]; the key is matched against column KEY_COL
          (new keys are appended below the last row) and the values are pasted from start_col.
    extra_updates: {'range': ..., 'values': [[...]]} dicts to include, e.g. header and status cells.
    """
    # one read: existing keys from row 2 down
    existing_keys = worksheet.col_values(KEY_COL)[1:]
    key_to_row = {str(k).strip(): i + 2 for i, k in enumerate(existing_keys) if str(k).strip()}
    next_new_row = len(existing_keys) + 2

    batch_data = list(extra_updates)
    for row in rows:
        key, *values = row
        key = str(key).strip()

        if key in key_to_row:
            target_row = key_to_row[key]
        else:
            target_row = next_new_row
            key_to_row[key] = target_row
            next_new_row += 1
            # new row: write the key into the key column ourselves
            batch_data.append({'range': rowcol_to_a1(target_row, KEY_COL), 'values': [[key]]})

        batch_data.append({'range': rowcol_to_a1(target_row, start_col), 'values': [values]})

    if batch_data:
        worksheet.batch_update(batch_data, value_input_option='USER_ENTERED')
