import io
import zipfile
from datetime import datetime

import pandas as pd
import pytest
import requests

import update_sheet as us
from update_sheet import FetchError

UDIFF_HEADER = "TckrSymb,SctySrs,ISIN,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol"


def make_zip(csv_text, name="bhavcopy.csv"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, csv_text)
    return buf.getvalue()


def udiff_csv(*rows):
    return "\n".join([UDIFF_HEADER, *rows]) + "\n"


def stocks_df(rows):
    """rows: (symbol, series, isin, volume); prices are fixed."""
    return pd.DataFrame(
        [{"symbol": s, "series": sr, "isin": i, "volume": v, "open": 10.0, "close": 11.0, "low": 9.0, "high": 12.0}
         for s, sr, i, v in rows])


class FakeResponse:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


class FakeWorksheet:
    def __init__(self, col_a):
        self.col_a = col_a
        self.batches = []

    def col_values(self, col):
        assert col == us.KEY_COL
        return list(self.col_a)

    def batch_update(self, data, value_input_option=None):
        self.batches.append((data, value_input_option))

    def update(self, *args, **kwargs):
        raise AssertionError("all writes must go through batch_update")


# --- download_bhavcopy ---

def test_download_returns_bytes_on_200(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        return FakeResponse(200, b"zip-bytes")

    monkeypatch.setattr(us.requests, "get", fake_get)
    assert us.download_bhavcopy(datetime(2026, 10, 1)) == b"zip-bytes"
    assert "BhavCopy_NSE_CM_0_0_0_20261001_F_0000.csv.zip" in seen["url"]


def test_download_returns_none_on_404(monkeypatch):
    monkeypatch.setattr(us.requests, "get", lambda url, **kw: FakeResponse(404))
    assert us.download_bhavcopy(datetime(2026, 10, 2)) is None


def test_download_raises_on_other_status(monkeypatch):
    monkeypatch.setattr(us.requests, "get", lambda url, **kw: FakeResponse(403))
    with pytest.raises(FetchError, match="HTTP 403"):
        us.download_bhavcopy(datetime(2026, 10, 1))


def test_download_raises_on_network_error(monkeypatch):
    def boom(url, **kw):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(us.requests, "get", boom)
    with pytest.raises(FetchError, match="Network error"):
        us.download_bhavcopy(datetime(2026, 10, 1))


# --- parse_bhavcopy ---

def test_parse_udiff_renames_to_canonical_columns():
    df = us.parse_bhavcopy(make_zip(udiff_csv("ABC,EQ,INE000A01011,10,12,9,11,500")))
    assert set(df.columns) == set(us.COLUMN_ALIASES)
    row = df.iloc[0]
    assert (row["symbol"], row["series"], row["volume"], row["close"]) == ("ABC", "EQ", 500, 11)


def test_parse_old_format():
    csv = "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,TOTTRDQTY,ISIN\nABC,EQ,10,12,9,11,500,INE000A01011\n"
    df = us.parse_bhavcopy(make_zip(csv))
    assert df.iloc[0]["volume"] == 500
    assert df.iloc[0]["symbol"] == "ABC"


def test_parse_without_optional_columns():
    csv = "TckrSymb,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol\nABC,10,12,9,11,500\n"
    df = us.parse_bhavcopy(make_zip(csv))
    assert "series" not in df.columns


def test_parse_missing_required_column_names_it():
    csv = "TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric\nABC,EQ,10,12,9,11\n"
    with pytest.raises(FetchError, match="volume"):
        us.parse_bhavcopy(make_zip(csv))


def test_parse_corrupt_zip():
    with pytest.raises(FetchError, match="Could not read"):
        us.parse_bhavcopy(b"<html>not a zip</html>")


# --- select_top_liquid ---

def test_select_keeps_eq_series_only():
    df = stocks_df([("AAA", "EQ", "INE1", 100), ("BBB", "BE", "INE2", 999), ("CCC", " EQ ", "INE3", 50)])
    assert us.select_top_liquid(df, 10)["symbol"].tolist() == ["AAA", "CCC"]


def test_select_ranks_by_volume_and_limits_to_n():
    df = stocks_df([("LOW", "EQ", "INE1", 1), ("HIGH", "EQ", "INE2", 300), ("MID", "EQ", "INE3", 20)])
    assert us.select_top_liquid(df, 2)["symbol"].tolist() == ["HIGH", "MID"]


def test_select_without_series_column():
    df = stocks_df([("AAA", "EQ", "INE1", 1), ("BBB", "BE", "INE2", 2)]).drop(columns="series")
    assert us.select_top_liquid(df, 10)["symbol"].tolist() == ["BBB", "AAA"]


def test_select_excludes_etfs():
    df = stocks_df([("GOLDBEES", "EQ", "INF204KB17I5", 900), ("NIFTYBEES", "EQ", "INF204KB14I2", 800),
                    ("RELIANCE", "EQ", "INE002A01018", 100)])
    assert us.select_top_liquid(df, 10)["symbol"].tolist() == ["RELIANCE"]


# --- resolve_run_date ---

@pytest.mark.parametrize("value", [None, "", "  "])
def test_run_date_blank_means_today(value):
    assert us.resolve_run_date(value).date() == datetime.now().date()


def test_run_date_parses_iso_date():
    assert us.resolve_run_date(" 2026-10-01 ") == datetime(2026, 10, 1)


def test_run_date_rejects_bad_format():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        us.resolve_run_date("01-10-2026")


# --- find_latest_trading_day ---

def test_latest_trading_day_skips_weekend_and_holiday(monkeypatch):
    requested = []
    content = make_zip(udiff_csv("ABC,EQ,INE000A01011,10,12,9,11,500"))

    def fake_download(day):
        requested.append(day.date().isoformat())
        return content if day.day == 1 else None  # 02-Oct is a holiday

    monkeypatch.setattr(us, "download_bhavcopy", fake_download)
    day, rows = us.find_latest_trading_day(datetime(2026, 10, 4))  # Sunday
    assert day == datetime(2026, 10, 1)
    assert requested == ["2026-10-02", "2026-10-01"]
    assert rows == [["ABC", 500, 10, 11, 9, 12]]  # SHEET_COLUMNS order


def test_latest_trading_day_raises_when_nothing_found(monkeypatch):
    monkeypatch.setattr(us, "download_bhavcopy", lambda day: None)
    with pytest.raises(FetchError, match="No bhavcopy found"):
        us.find_latest_trading_day(datetime(2026, 10, 1))


def test_latest_trading_day_adds_date_to_parse_errors(monkeypatch):
    monkeypatch.setattr(us, "download_bhavcopy", lambda day: b"garbage")
    with pytest.raises(FetchError, match="01-Oct-2026"):
        us.find_latest_trading_day(datetime(2026, 10, 1))


def test_latest_trading_day_raises_when_filter_leaves_nothing(monkeypatch):
    content = make_zip(udiff_csv("ABC,BE,INE000A01011,10,12,9,11,500"))
    monkeypatch.setattr(us, "download_bhavcopy", lambda day: content)
    with pytest.raises(FetchError, match="no EQ rows"):
        us.find_latest_trading_day(datetime(2026, 10, 1))


# --- sheet layout ---

@pytest.mark.parametrize("day, letter", [
    (datetime(2026, 9, 28), "B"),   # Monday
    (datetime(2026, 9, 29), "H"),
    (datetime(2026, 9, 30), "N"),
    (datetime(2026, 10, 1), "T"),
    (datetime(2026, 10, 2), "Z"),   # Friday
])
def test_start_col_for_date(day, letter):
    assert us.col_letter(us.start_col_for_date(day)) == letter


def test_day_block_width_matches_sheet_columns():
    # 5 values after the symbol + the sheet's "Signal" column
    assert us.DAY_BLOCK_WIDTH == 6


def test_day_header_updates():
    assert us.day_header_updates(20, datetime(2026, 10, 1)) == [
        {"range": "T1", "values": [["Thursday"]]},
        {"range": "U1", "values": [["01-Oct-2026"]]},
    ]


# --- upsert_rows ---

def test_upsert_updates_existing_and_appends_new_rows():
    ws = FakeWorksheet(["status", "NSE Code", "AAA", "", "BBB"])
    extra = [{"range": "A1", "values": [["status msg"]]}]
    us.upsert_rows(ws, [["BBB", 1, 2], [" AAA ", 3, 4], ["NEW", 5, 6]], start_col=20, extra_updates=extra)

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
    us.upsert_rows(ws, [], start_col=2)
    assert ws.batches == []


# --- main ---

def test_main_writes_everything_in_one_batch(monkeypatch):
    ws = FakeWorksheet(["old status", "NSE Code", "ABC"])
    content = make_zip(udiff_csv("ABC,EQ,INE000A01011,10,12,9,11,500"))
    monkeypatch.setattr(us, "get_worksheet", lambda: ws)
    monkeypatch.setattr(us, "download_bhavcopy", lambda day: content if day.day == 1 else None)
    monkeypatch.setenv("RUN_DATE", "2026-10-04")

    us.main()

    assert len(ws.batches) == 1
    data = {u["range"]: u["values"] for u in ws.batches[0][0]}
    assert data["T1"] == [["Thursday"]]
    assert data["U1"] == [["01-Oct-2026"]]
    assert data["T3"] == [[500, 10, 11, 9, 12]]
    assert data["A1"][0][0].startswith("Data Date: 01-Oct-2026 | Last Update: ")
