"""Getting the data: find the latest trading day's NSE bhavcopy and pick its top-N stocks."""
import io
import logging
import zipfile
from datetime import timedelta

import pandas as pd
import requests

from config import (COLUMN_ALIASES, EQUITY_SERIES, FUND_ISIN_PREFIX, LOOKBACK_DAYS, NSE_HEADERS,
                    NSE_TIMEOUT, NSE_URL, OPTIONAL_COLUMNS, SHEET_COLUMNS, TOP_N)

logger = logging.getLogger(__name__)


class FetchError(RuntimeError):
    """The bhavcopy could not be downloaded or parsed (not a holiday)."""


def find_latest_trading_day(today):
    """Return (date, rows) for the latest weekday up to today that has a bhavcopy.

    rows are SHEET_COLUMNS values for the top TOP_N stocks. Holidays (no file) fall back a day,
    up to LOOKBACK_DAYS; raises FetchError if none is found or a file is unusable.
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
            raise FetchError(f"Bhavcopy for {day.strftime('%d-%b-%Y')}: {e}") from e
        if top.empty:
            raise FetchError(f"Bhavcopy for {day.strftime('%d-%b-%Y')} has no {EQUITY_SERIES} rows after filtering")
        return day, top[SHEET_COLUMNS].values.tolist()
    raise FetchError(f"No bhavcopy found in the {LOOKBACK_DAYS} days up to {today.strftime('%d-%b-%Y')}")


def download_bhavcopy(date_obj):
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
        logger.info("No bhavcopy for %s (HTTP 404: holiday or not yet published)", date_obj.strftime('%d-%b-%Y'))
        return None
    if response.status_code != 200:
        raise FetchError(f"Unexpected HTTP {response.status_code} fetching {url}")
    return response.content


def parse_bhavcopy(content):
    """Read the CSV inside the bhavcopy zip into a DataFrame with canonical column names only."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            with z.open(z.namelist()[0]) as f:
                df = pd.read_csv(f)
    except Exception as e:
        raise FetchError(f"Could not read bhavcopy zip/CSV: {e}") from e

    columns = resolve_columns(df.columns)
    return df[list(columns.values())].rename(columns={v: k for k, v in columns.items()})


def resolve_columns(columns):
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


def select_top_liquid(df, n):
    """Keep EQ-series stocks (no ETFs/funds) and return the n with the highest volume."""
    if 'series' in df.columns:
        df = df[df['series'].astype(str).str.strip() == EQUITY_SERIES]
    df = df[~df['isin'].astype(str).str.strip().str.upper().str.startswith(FUND_ISIN_PREFIX)]
    return df.sort_values(by='volume', ascending=False).head(n)
