from datetime import datetime

import pytest

import sheet
from config import DAY_BLOCK_WIDTH
from helpers import FakeWorksheet
from nse import TradingDay


# --- sheet layout ---

@pytest.mark.parametrize("day, letter", [
    (datetime(2026, 9, 28), "B"),   # Monday
    (datetime(2026, 9, 29), "H"),
    (datetime(2026, 9, 30), "N"),
    (datetime(2026, 10, 1), "T"),
    (datetime(2026, 10, 2), "Z"),   # Friday
])
def test_start_col_for_date(day, letter):
    assert sheet.col_letter(sheet.start_col_for_date(day)) == letter


def test_day_block_width_matches_sheet_columns():
    # 5 values after the symbol + the sheet's "Signal" column
    assert DAY_BLOCK_WIDTH == 6


def test_day_header_updates():
    assert sheet.day_header_updates(20, datetime(2026, 10, 1)) == [
        {"range": "T1", "values": [["Thursday"]]},
        {"range": "U1", "values": [["01-Oct-2026"]]},
    ]


def test_status_update():
    update = sheet.status_update(TradingDay(datetime(2026, 10, 1), []))
    assert update["range"] == "A1"
    assert update["values"][0][0].startswith("Data Date: 01-Oct-2026 | Last Update: ")
    assert update["values"][0][0].endswith(" (IST)")


# --- upsert_rows ---

def test_upsert_updates_existing_and_appends_new_rows():
    ws = FakeWorksheet(["status", "NSE Code", "AAA", "", "BBB"])
    extra = [{"range": "A1", "values": [["status msg"]]}]
    sheet.upsert_rows(ws, [["BBB", 1, 2], [" AAA ", 3, 4], ["NEW", 5, 6]], start_col=20, extra_updates=extra)

    assert len(ws.batches) == 1
    data, option = ws.batches[0]
    assert option == "USER_ENTERED"
    assert data == [
        {"range": "A1", "values": [["status msg"]]},
        {"range": "T5", "values": [[1, 2]]},     # BBB is on row 5
        {"range": "T3", "values": [[3, 4]]},     # AAA, key whitespace stripped
        {"range": "A6", "values": [["NEW"]]},    # appended after the last row
        {"range": "T6", "values": [[5, 6]]},
    ]


def test_upsert_with_no_rows_and_no_extras_writes_nothing():
    ws = FakeWorksheet(["status", "NSE Code"])
    sheet.upsert_rows(ws, [], start_col=2)
    assert ws.batches == []
