"""
Stock Data Warehouse — Historical Backfill

Runs the full ETL pipeline:
    1. Read the ticker list from the companies table
    2. Extract 5 years of OHLCV data + corporate events from yfinance
    3. Clean and validate
    4. Load into Postgres with upsert semantics

Run with:  python run_backfill.py
"""

import sys
import time
from datetime import datetime, timedelta

# Make src/ importable
sys.path.insert(0, 'src')

from db import get_connection
from extract import fetch_prices, fetch_corporate_events
from transform import clean_prices, clean_events
from load import load_prices, load_events


# =============================================================================
# CONFIG
# =============================================================================

# 5 years ending today
END   = datetime.today().date().isoformat()
START = (datetime.today().date() - timedelta(days=5 * 365 + 30)).isoformat()

BATCH_SIZE = 10           # tickers per yfinance request
SLEEP      = 1.0          # seconds between batches


# =============================================================================
# 1. READ TICKERS FROM DATABASE
# =============================================================================

def get_tickers():
    """Pull the ticker list from the companies table."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ticker FROM companies ORDER BY ticker;")
            return [row[0] for row in cur.fetchall()]


# =============================================================================
# 2. SUMMARY HELPERS
# =============================================================================

def print_db_summary():
    """Print row counts for each table after the load."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM daily_prices;")
            n_prices = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM corporate_events;")
            n_events = cur.fetchone()[0]

            cur.execute("""
                SELECT MIN(date), MAX(date)
                FROM daily_prices;
            """)
            min_date, max_date = cur.fetchone()

            cur.execute("""
                SELECT ticker, COUNT(*) AS n
                FROM daily_prices
                GROUP BY ticker
                HAVING COUNT(*) < 1000
                ORDER BY n;
            """)
            thin = cur.fetchall()

    print(f"\n  Total price rows:    {n_prices:,}")
    print(f"  Total events:        {n_events:,}")
    print(f"  Date range:          {min_date} -> {max_date}")
    if thin:
        print(f"  Tickers with <1000 rows (may have incomplete history):")
        for ticker, n in thin:
            print(f"    {ticker}: {n}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 70)
    print("STOCK DATA WAREHOUSE — HISTORICAL BACKFILL")
    print("=" * 70)
    print(f"Date range: {START}  ->  {END}")

    tickers = get_tickers()
    print(f"Tickers:    {len(tickers)} (from companies table)")

    t0 = time.time()

    # -------------------------------------------------------------------------
    # PRICE DATA
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("STAGE 1: PRICE DATA")
    print("-" * 70)

    print("\n[1/3] Extracting...")
    raw_prices = fetch_prices(tickers, START, END,
                              batch_size=BATCH_SIZE,
                              sleep_seconds=SLEEP)
    print(f"  Raw rows: {len(raw_prices):,}")

    print("\n[2/3] Transforming...")
    clean = clean_prices(raw_prices)

    print("\n[3/3] Loading...")
    load_prices(clean)

    # -------------------------------------------------------------------------
    # CORPORATE EVENTS
    # -------------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("STAGE 2: CORPORATE EVENTS")
    print("-" * 70)

    print("\n[1/3] Extracting...")
    raw_events = fetch_corporate_events(tickers, START, END)
    print(f"  Raw events: {len(raw_events):,}")

    print("\n[2/3] Transforming...")
    clean_evts = clean_events(raw_events)

    print("\n[3/3] Loading...")
    load_events(clean_evts)

    # -------------------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------------------
    elapsed = time.time() - t0
    print("\n" + "=" * 70)
    print(f"DONE in {elapsed:.1f}s")
    print("=" * 70)
    print_db_summary()


if __name__ == "__main__":
    main()