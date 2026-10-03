"""Getting the data: find the latest trading day's NSE bhavcopy and pick its top-N stocks."""
import io
import logging
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd
import requests

from config import (COLUMN_ALIASES, DATE_LABEL, EQUITY_SERIES, FUND_ISIN_PREFIX, LOOKBACK_DAYS, NSE_HEADERS,
                    NSE_TIMEOUT, NSE_URL, OPTIONAL_COLUMNS, SHEET_COLUMNS, TOP_N)

logger = logging.getLogger(__name__)


class FetchError(RuntimeError):
    """The bhavcopy could not be downloaded or parsed (not a holiday)."""


@dataclass
class TradingDay:
    """A trading day and its top stocks, each row in SHEET_COLUMNS order."""
    date: datetime
    rows: list[list]

    @property
    def label(self) -> str:
        return self.date.strftime(DATE_LABEL)


def find_latest_trading_day(today: datetime) -> TradingDay:
    """Return the latest weekday up to today that has a bhavcopy, with its top TOP_N stocks.

    Holidays (no file) fall back a day, up to LOOKBACK_DAYS;
    raises FetchError if none is found or a file is unusable.
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
            raise FetchError(f"Bhavcopy for {day.strftime(DATE_LABEL)}: {e}") from e
        if top.empty:
            raise FetchError(f"Bhavcopy for {day.strftime(DATE_LABEL)} has no {EQUITY_SERIES} rows after filtering")
        return TradingDay(day, top[SHEET_COLUMNS].values.tolist())
    raise FetchError(f"No bhavcopy found in the {LOOKBACK_DAYS} days up to {today.strftime(DATE_LABEL)}")


def download_bhavcopy(date_obj: datetime) -> bytes | None:
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
        logger.info("No bhavcopy for %s (HTTP 404: holiday or not yet published)", date_obj.strftime(DATE_LABEL))
        return None
    if response.status_code != 200:
        raise FetchError(f"Unexpected HTTP {response.status_code} fetching {url}")
    return response.content


def parse_bhavcopy(content: bytes) -> pd.DataFrame:
    """Read the CSV inside the bhavcopy zip into a DataFrame with canonical column names only."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            with z.open(z.namelist()[0]) as f:
                df = pd.read_csv(f)
    except Exception as e:
        raise FetchError(f"Could not read bhavcopy zip/CSV: {e}") from e

    columns = resolve_columns(df.columns)
    return df[list(columns.values())].rename(columns={v: k for k, v in columns.items()})


def resolve_columns(columns: Iterable[str]) -> dict[str, str]:
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


def select_top_liquid(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Keep EQ-series stocks (no ETFs/funds) and return the n with the highest volume."""
    if 'series' in df.columns:
        df = df[df['series'].astype(str).str.strip() == EQUITY_SERIES]
    df = df[~df['isin'].astype(str).str.strip().str.upper().str.startswith(FUND_ISIN_PREFIX)]
    return df.sort_values(by='volume', ascending=False).head(n)
