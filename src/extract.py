"""
Data extraction module.

Downloads historical OHLCV data and corporate actions (splits, dividends)
from Yahoo Finance via the yfinance library. Returns raw DataFrames
ready to be transformed and loaded.
"""

import time
from datetime import datetime

import pandas as pd
import yfinance as yf


def fetch_prices(tickers, start, end, batch_size=10, sleep_seconds=1.0):
    """
    Download daily OHLCV data for a list of tickers.

    Splits the request into batches to avoid rate limits and to make
    progress visible during long backfills.

    Parameters
    ----------
    tickers : list of str
        Stock symbols, e.g. ['AAPL', 'MSFT'].
    start : str
        Start date, 'YYYY-MM-DD'.
    end : str
        End date, 'YYYY-MM-DD' (exclusive).
    batch_size : int
        Number of tickers per yfinance request.
    sleep_seconds : float
        Pause between batches to be polite to Yahoo's servers.

    Returns
    -------
    pd.DataFrame
        Long-format DataFrame with columns:
            ticker, date, open, high, low, close, adj_close, volume
    """
    all_frames = []
    n_batches  = (len(tickers) + batch_size - 1) // batch_size

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        print(f"  Batch {batch_num}/{n_batches}: {batch}")

        df = yf.download(
            tickers   = batch,
            start     = start,
            end       = end,
            auto_adjust = False,
            progress  = False,
            group_by  = 'ticker',
        )

        if df.empty:
            print(f"    (no data returned for batch)")
            continue

        # yfinance returns MultiIndex columns when multiple tickers are requested.
        # Reshape to long format: one row per (ticker, date).
        if len(batch) == 1:
            ticker = batch[0]
            df_long = df.reset_index()
            df_long['ticker'] = ticker
        else:
            df_long = df.stack(level=0, future_stack=True).reset_index()
            df_long = df_long.rename(columns={'level_1': 'ticker', 'Ticker': 'ticker'})

        all_frames.append(df_long)

        if batch_num < n_batches:
            time.sleep(sleep_seconds)

    if not all_frames:
        raise RuntimeError("No data was returned from yfinance.")

    combined = pd.concat(all_frames, ignore_index=True)

    # Normalize column names
    combined.columns = [c.lower().replace(' ', '_') for c in combined.columns]
    combined = combined.rename(columns={'adj_close': 'adj_close'})

    return combined


def fetch_corporate_events(tickers, start, end):
    """
    Download split and dividend events for a list of tickers.

    Parameters
    ----------
    tickers : list of str
    start : str
    end : str

    Returns
    -------
    pd.DataFrame
        Long-format DataFrame with columns: ticker, date, event_type, amount.
    """
    rows = []
    start_dt = pd.to_datetime(start)
    end_dt   = pd.to_datetime(end)

    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            splits    = t.splits
            dividends = t.dividends
        except Exception as e:
            print(f"  ⚠ {ticker}: could not fetch actions ({e})")
            continue

        if splits is not None and len(splits) > 0:
            splits = splits.tz_localize(None) if splits.index.tz else splits
            for date, ratio in splits.items():
                if start_dt <= date < end_dt:
                    rows.append({
                        'ticker'    : ticker,
                        'date'      : date.date(),
                        'event_type': 'split',
                        'amount'    : float(ratio),
                    })

        if dividends is not None and len(dividends) > 0:
            dividends = dividends.tz_localize(None) if dividends.index.tz else dividends
            for date, amount in dividends.items():
                if start_dt <= date < end_dt:
                    rows.append({
                        'ticker'    : ticker,
                        'date'      : date.date(),
                        'event_type': 'dividend',
                        'amount'    : float(amount),
                    })

    df = pd.DataFrame(rows, columns=['ticker', 'date', 'event_type', 'amount'])
    return df


def _quick_test():
    """Sanity check: fetch a few days of data for 2 tickers."""
    print("Fetching test sample...")
    prices = fetch_prices(['AAPL', 'MSFT'],
                          start='2024-01-01',
                          end='2024-01-10',
                          batch_size=2)
    print(f"\nPrice data shape: {prices.shape}")
    print(f"Columns: {list(prices.columns)}")
    print(f"\nFirst 5 rows:")
    print(prices.head())

    print("\nFetching corporate events...")
    events = fetch_corporate_events(['AAPL'], start='2020-01-01', end='2024-01-01')
    print(f"\nEvents shape: {events.shape}")
    print(events.head())


if __name__ == "__main__":
    _quick_test()