"""Every tunable value for the job: target sheet, NSE download, stock filter and sheet layout."""
import os
from zoneinfo import ZoneInfo

# The middle value in the Google Sheet URL (not the tab). Set SPREADSHEET_ID / WORKSHEET_NAME
# in the environment to target a different sheet, e.g. a test copy.
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID') or "1mOVPxjgc1w0j2WPG_Xp4t8SKl_eb2-wHCWfdAiO145Q"
WORKSHEET_NAME = os.environ.get('WORKSHEET_NAME') or "Top 250 Stocks"

TOP_N = 250
LOOKBACK_DAYS = 5  # calendar days to search back for the latest bhavcopy

NSE_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date:%Y%m%d}_F_0000.csv.zip"
NSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}
NSE_TIMEOUT = 15  # seconds

# Canonical column name -> bhavcopy column names, UDiFF format first, then the old format.
COLUMN_ALIASES = {
    'symbol': ['TckrSymb', 'SYMBOL'],
    'series': ['SctySrs', 'SERIES'],
    'isin': ['ISIN'],
    'volume': ['TtlTradgVol', 'TtlTrdQty', 'TotTrdQty', 'TOTTRDQTY'],
    'open': ['OpnPric', 'OPEN'],
    'close': ['ClsPric', 'CLOSE'],
    'low': ['LwPric', 'LOW'],
    'high': ['HghPric', 'HIGH'],
}
OPTIONAL_COLUMNS = {'series'}

EQUITY_SERIES = 'EQ'
# ETFs and other fund units trade in the EQ series too; their ISINs start with INF
# (company shares use INE), which is more reliable than matching words in the symbol.
FUND_ISIN_PREFIX = 'INF'

# Sheet layout. Row 1 holds the status cell and each day's name/date, row 2 the column headers.
# Column A holds the symbol (SHEET_COLUMNS[0]); each weekday has a block, Monday's starting at
# column B, holding the remaining SHEET_COLUMNS followed by the sheet's own "Signal" column.
SHEET_COLUMNS = ['symbol', 'volume', 'open', 'close', 'low', 'high']
KEY_COL = 1                                  # A
FIRST_BLOCK_COL = 2                          # B
DAY_BLOCK_WIDTH = len(SHEET_COLUMNS[1:]) + 1  # values + "Signal" = 6
STATUS_CELL = 'A1'
TIMEZONE = ZoneInfo('Asia/Kolkata')  # NSE's: "today" and the status timestamp are IST on any machine
DATE_LABEL = '%d-%b-%Y'  # how a trading day is shown in the sheet and logs, e.g. 01-Oct-2026
