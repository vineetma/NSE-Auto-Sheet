from datetime import datetime

import pytest
import requests

import nse
from config import COLUMN_ALIASES
from helpers import FakeResponse, make_zip, stocks_df, udiff_csv
from nse import FetchError


# --- download_bhavcopy ---

def test_download_returns_bytes_on_200(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        return FakeResponse(200, b"zip-bytes")

    monkeypatch.setattr(nse.requests, "get", fake_get)
    assert nse.download_bhavcopy(datetime(2026, 10, 1)) == b"zip-bytes"
    assert "BhavCopy_NSE_CM_0_0_0_20261001_F_0000.csv.zip" in seen["url"]


def test_download_returns_none_on_404(monkeypatch):
    monkeypatch.setattr(nse.requests, "get", lambda url, **kw: FakeResponse(404))
    assert nse.download_bhavcopy(datetime(2026, 10, 2)) is None


def test_download_raises_on_other_status(monkeypatch):
    monkeypatch.setattr(nse.requests, "get", lambda url, **kw: FakeResponse(403))
    with pytest.raises(FetchError, match="HTTP 403"):
        nse.download_bhavcopy(datetime(2026, 10, 1))


def test_download_raises_on_network_error(monkeypatch):
    def boom(url, **kw):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(nse.requests, "get", boom)
    with pytest.raises(FetchError, match="Network error"):
        nse.download_bhavcopy(datetime(2026, 10, 1))


# --- parse_bhavcopy ---

def test_parse_udiff_renames_to_canonical_columns():
    df = nse.parse_bhavcopy(make_zip(udiff_csv("ABC,EQ,INE000A01011,10,12,9,11,500")))
    assert set(df.columns) == set(COLUMN_ALIASES)
    row = df.iloc[0]
    assert (row["symbol"], row["series"], row["volume"], row["close"]) == ("ABC", "EQ", 500, 11)


def test_parse_old_format():
    csv = "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,TOTTRDQTY,ISIN\nABC,EQ,10,12,9,11,500,INE000A01011\n"
    df = nse.parse_bhavcopy(make_zip(csv))
    assert df.iloc[0]["volume"] == 500
    assert df.iloc[0]["symbol"] == "ABC"


def test_parse_without_optional_columns():
    csv = "TckrSymb,ISIN,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol\nABC,INE000A01011,10,12,9,11,500\n"
    df = nse.parse_bhavcopy(make_zip(csv))
    assert "series" not in df.columns


def test_parse_missing_required_column_names_it():
    csv = "TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric\nABC,EQ,10,12,9,11\n"
    with pytest.raises(FetchError, match="volume"):
        nse.parse_bhavcopy(make_zip(csv))


def test_parse_corrupt_zip():
    with pytest.raises(FetchError, match="Could not read"):
        nse.parse_bhavcopy(b"<html>not a zip</html>")


# --- select_top_liquid ---

def test_select_keeps_eq_series_only():
    df = stocks_df([("AAA", "EQ", "INE1", 100), ("BBB", "BE", "INE2", 999), ("CCC", " EQ ", "INE3", 50)])
    assert nse.select_top_liquid(df, 10)["symbol"].tolist() == ["AAA", "CCC"]


def test_select_ranks_by_volume_and_limits_to_n():
    df = stocks_df([("LOW", "EQ", "INE1", 1), ("HIGH", "EQ", "INE2", 300), ("MID", "EQ", "INE3", 20)])
    assert nse.select_top_liquid(df, 2)["symbol"].tolist() == ["HIGH", "MID"]


def test_select_without_series_column():
    df = stocks_df([("AAA", "EQ", "INE1", 1), ("BBB", "BE", "INE2", 2)]).drop(columns="series")
    assert nse.select_top_liquid(df, 10)["symbol"].tolist() == ["BBB", "AAA"]


def test_select_excludes_etfs_by_isin():
    df = stocks_df([("GOLDBEES", "EQ", "INF204KB17I5", 900), ("TATSILV", "EQ", "INF277KA1984", 800),
                    ("RELIANCE", "EQ", "INE002A01018", 100)])
    assert nse.select_top_liquid(df, 10)["symbol"].tolist() == ["RELIANCE"]


def test_select_keeps_equities_with_fund_like_names():
    # The old symbol-keyword filter dropped these real companies.
    df = stocks_df([("SKYGOLD", "EQ", "INE182Z01015", 3), ("JETFREIGHT", "EQ", "INE982V01025", 2),
                    ("SILVERTUC", "EQ", "INE625X01018", 1)])
    assert nse.select_top_liquid(df, 10)["symbol"].tolist() == ["SKYGOLD", "JETFREIGHT", "SILVERTUC"]


# --- find_latest_trading_day ---

def test_latest_trading_day_skips_weekend_and_holiday(monkeypatch):
    requested = []
    content = make_zip(udiff_csv("ABC,EQ,INE000A01011,10,12,9,11,500"))

    def fake_download(day):
        requested.append(day.date().isoformat())
        return content if day.day == 1 else None  # 02-Oct is a holiday

    monkeypatch.setattr(nse, "download_bhavcopy", fake_download)
    day, rows = nse.find_latest_trading_day(datetime(2026, 10, 4))  # Sunday
    assert day == datetime(2026, 10, 1)
    assert requested == ["2026-10-02", "2026-10-01"]
    assert rows == [["ABC", 500, 10, 11, 9, 12]]  # SHEET_COLUMNS order


def test_latest_trading_day_raises_when_nothing_found(monkeypatch):
    monkeypatch.setattr(nse, "download_bhavcopy", lambda day: None)
    with pytest.raises(FetchError, match="No bhavcopy found"):
        nse.find_latest_trading_day(datetime(2026, 10, 1))


def test_latest_trading_day_adds_date_to_parse_errors(monkeypatch):
    monkeypatch.setattr(nse, "download_bhavcopy", lambda day: b"garbage")
    with pytest.raises(FetchError, match="01-Oct-2026"):
        nse.find_latest_trading_day(datetime(2026, 10, 1))


def test_latest_trading_day_raises_when_filter_leaves_nothing(monkeypatch):
    content = make_zip(udiff_csv("ABC,BE,INE000A01011,10,12,9,11,500"))
    monkeypatch.setattr(nse, "download_bhavcopy", lambda day: content)
    with pytest.raises(FetchError, match="no EQ rows"):
        nse.find_latest_trading_day(datetime(2026, 10, 1))
