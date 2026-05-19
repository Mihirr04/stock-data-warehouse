"""
Data loading module.

Inserts cleaned DataFrames into Postgres tables using bulk upsert
(ON CONFLICT DO UPDATE) so the pipeline is safely re-runnable.
"""

from io import StringIO

import pandas as pd
from psycopg2.extras import execute_values

from db import get_connection


def load_prices(df, batch_size=5000):
    """
    Insert price rows into daily_prices using bulk upsert.

    If a (ticker, date) row already exists, its values are updated.
    This makes the loader idempotent: re-running the same backfill
    will not error or duplicate.

    Parameters
    ----------
    df : pd.DataFrame
        Cleaned price data with columns:
            ticker, date, open, high, low, close, adj_close, volume
    batch_size : int
        Rows per INSERT batch.

    Returns
    -------
    int
        Number of rows inserted/updated.
    """
    if df.empty:
        print("  (no rows to load)")
        return 0

    rows = [
        (
            r.ticker,
            r.date,
            float(r.open),
            float(r.high),
            float(r.low),
            float(r.close),
            float(r.adj_close),
            int(r.volume),
        )
        for r in df.itertuples(index=False)
    ]

    sql = """
        INSERT INTO daily_prices
            (ticker, date, open, high, low, close, adj_close, volume)
        VALUES %s
        ON CONFLICT (ticker, date) DO UPDATE SET
            open      = EXCLUDED.open,
            high      = EXCLUDED.high,
            low       = EXCLUDED.low,
            close     = EXCLUDED.close,
            adj_close = EXCLUDED.adj_close,
            volume    = EXCLUDED.volume;
    """

    total = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                execute_values(cur, sql, batch, page_size=batch_size)
                total += len(batch)

    print(f"  Loaded {total:,} price rows")
    return total


def load_events(df):
    """
    Insert corporate events into corporate_events table.

    Uses a unique-key check on (ticker, date, event_type) to avoid
    duplicate inserts on re-runs.

    Parameters
    ----------
    df : pd.DataFrame
        Cleaned events with columns: ticker, date, event_type, amount.

    Returns
    -------
    int
        Number of rows inserted (existing rows are skipped).
    """
    if df.empty:
        print("  (no events to load)")
        return 0

    rows = [
        (r.ticker, r.date, r.event_type, float(r.amount))
        for r in df.itertuples(index=False)
    ]

    # corporate_events has no unique constraint we can ON CONFLICT against,
    # so we de-dupe by inserting only rows not already present.
    sql = """
        INSERT INTO corporate_events (ticker, date, event_type, amount)
        SELECT v.ticker, v.date, v.event_type, v.amount
        FROM (VALUES %s) AS v(ticker, date, event_type, amount)
        WHERE NOT EXISTS (
            SELECT 1 FROM corporate_events ce
            WHERE ce.ticker     = v.ticker
              AND ce.date       = v.date::date
              AND ce.event_type = v.event_type
        );
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows, page_size=1000)
            inserted = cur.rowcount

    print(f"  Loaded {inserted:,} new corporate events")
    return inserted


def _quick_test():
    """End-to-end smoke test: fetch -> clean -> load."""
    from extract import fetch_prices, fetch_corporate_events
    from transform import clean_prices, clean_events

    print("=== Test: load price data ===")
    raw = fetch_prices(['AAPL', 'MSFT'],
                       start='2024-01-01',
                       end='2024-01-10',
                       batch_size=2)
    clean = clean_prices(raw)
    load_prices(clean)

    print("\n=== Test: load corporate events ===")
    raw_events = fetch_corporate_events(['AAPL'], '2020-01-01', '2024-01-01')
    clean_events_df = clean_events(raw_events)
    load_events(clean_events_df)

    print("\n=== Verifying in database ===")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ticker, COUNT(*) AS n_rows
                FROM daily_prices
                WHERE ticker IN ('AAPL', 'MSFT')
                GROUP BY ticker
                ORDER BY ticker;
            """)
            for row in cur.fetchall():
                print(f"  {row[0]}: {row[1]} rows")

            cur.execute("""
                SELECT event_type, COUNT(*)
                FROM corporate_events
                WHERE ticker = 'AAPL'
                GROUP BY event_type
                ORDER BY event_type;
            """)
            for row in cur.fetchall():
                print(f"  AAPL {row[0]}s: {row[1]}")


if __name__ == "__main__":
    _quick_test()
    