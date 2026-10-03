"""Fixtures shared by the tests: bhavcopy zips, DataFrames, and fakes for requests and gspread."""
import io
import zipfile

import pandas as pd

from config import KEY_COL

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
        assert col == KEY_COL
        return list(self.col_a)

    def batch_update(self, data, value_input_option=None):
        self.batches.append((data, value_input_option))

    def update(self, *args, **kwargs):
        raise AssertionError("all writes must go through batch_update")
