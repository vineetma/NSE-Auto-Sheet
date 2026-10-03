from datetime import datetime

import pytest

import nse
import sheet
import update_sheet as us
from helpers import FakeWorksheet, make_zip, udiff_csv


# --- resolve_run_date ---

@pytest.mark.parametrize("value", [None, "", "  "])
def test_run_date_blank_means_today(value):
    assert us.resolve_run_date(value).date() == datetime.now().date()


def test_run_date_parses_iso_date():
    assert us.resolve_run_date(" 2026-10-01 ") == datetime(2026, 10, 1)


def test_run_date_rejects_bad_format():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        us.resolve_run_date("01-10-2026")


# --- credentials_from_env ---

def test_credentials_parsed_from_env(monkeypatch):
    monkeypatch.setenv("GCP_CREDENTIALS", '{"client_email": "bot@example.com"}')
    assert us.credentials_from_env() == {"client_email": "bot@example.com"}


def test_credentials_missing_raises(monkeypatch):
    monkeypatch.delenv("GCP_CREDENTIALS", raising=False)
    with pytest.raises(RuntimeError, match="GCP_CREDENTIALS is not set"):
        us.credentials_from_env()


# --- main ---

def test_main_writes_everything_in_one_batch(monkeypatch):
    ws = FakeWorksheet(["old status", "NSE Code", "ABC"])
    content = make_zip(udiff_csv("ABC,EQ,INE000A01011,10,12,9,11,500"))
    monkeypatch.setattr(us, "credentials_from_env", lambda: {"fake": "key"})
    monkeypatch.setattr(sheet, "open_worksheet", lambda creds: ws)
    monkeypatch.setattr(nse, "download_bhavcopy", lambda day: content if day.day == 1 else None)
    monkeypatch.setenv("RUN_DATE", "2026-10-04")

    us.main()

    assert len(ws.batches) == 1
    data = {u["range"]: u["values"] for u in ws.batches[0][0]}
    assert data["T1"] == [["Thursday"]]
    assert data["U1"] == [["01-Oct-2026"]]
    assert data["T3"] == [[500, 10, 11, 9, 12]]
    assert data["A1"][0][0].startswith("Data Date: 01-Oct-2026 | Last Update: ")
