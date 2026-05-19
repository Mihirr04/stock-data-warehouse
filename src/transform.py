"""
Data transformation module.

Cleans and validates raw price data and corporate events before loading
into the database. Filters bad rows, normalizes types, and reports
data quality issues.
"""

import pandas as pd


def clean_prices(df):
    """
    Clean raw price data from yfinance.

    Steps:
        1. Drop rows missing the close price (the only NOT NULL column)
        2. Fill NaN open/high/low with close (rare; happens on illiquid days)
        3. Validate high >= low, close > 0, volume >= 0
        4. Drop duplicate (ticker, date) pairs
        5. Convert date column to date type (no time component)

    Parameters
    ----------
    df : pd.DataFrame
        Raw output from extract.fetch_prices.

    Returns
    -------
    pd.DataFrame
        Cleaned, validated DataFrame ready to insert.
    """
    initial_rows = len(df)
    issues = []

    # Make sure expected columns exist
    expected = {'date', 'ticker', 'open', 'high', 'low', 'close', 'adj_close', 'volume'}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # 1. Drop rows with no close price
    n_before = len(df)
    df = df.dropna(subset=['close']).copy()
    dropped_no_close = n_before - len(df)
    if dropped_no_close > 0:
        issues.append(f"  Dropped {dropped_no_close} rows missing close")

    # 2. Fill missing open/high/low with close
    df['open']  = df['open'].fillna(df['close'])
    df['high']  = df['high'].fillna(df['close'])
    df['low']   = df['low'].fillna(df['close'])
    df['adj_close'] = df['adj_close'].fillna(df['close'])

    # Volume can be 0 (holidays in some markets), but never null
    df['volume'] = df['volume'].fillna(0).astype('int64')

    # 3. Validate constraints
    bad_high_low = (df['high'] < df['low']).sum()
    if bad_high_low > 0:
        issues.append(f"  Dropping {bad_high_low} rows where high < low")
        df = df[df['high'] >= df['low']]

    bad_close = (df['close'] <= 0).sum()
    if bad_close > 0:
        issues.append(f"  Dropping {bad_close} rows where close <= 0")
        df = df[df['close'] > 0]

    bad_volume = (df['volume'] < 0).sum()
    if bad_volume > 0:
        issues.append(f"  Dropping {bad_volume} rows where volume < 0")
        df = df[df['volume'] >= 0]

    # 4. Drop duplicates on (ticker, date)
    n_before = len(df)
    df = df.drop_duplicates(subset=['ticker', 'date'], keep='last')
    dropped_dupes = n_before - len(df)
    if dropped_dupes > 0:
        issues.append(f"  Dropped {dropped_dupes} duplicate (ticker, date) rows")

    # 5. Convert date to pure date (no time component)
    df['date'] = pd.to_datetime(df['date']).dt.date

    # Reorder columns to match database table
    df = df[['ticker', 'date', 'open', 'high', 'low', 'close', 'adj_close', 'volume']]
    df = df.reset_index(drop=True)

    # Report
    final_rows = len(df)
    print(f"Cleaned prices: {initial_rows} -> {final_rows} rows")
    for issue in issues:
        print(issue)

    return df


def clean_events(df):
    """
    Clean corporate events data.

    Parameters
    ----------
    df : pd.DataFrame
        Raw output from extract.fetch_corporate_events.

    Returns
    -------
    pd.DataFrame
        Cleaned events DataFrame.
    """
    if df.empty:
        return df

    initial_rows = len(df)

    # Drop rows missing any critical field
    df = df.dropna(subset=['ticker', 'date', 'event_type', 'amount']).copy()

    # Validate event_type values
    valid_types = {'split', 'dividend'}
    df = df[df['event_type'].isin(valid_types)]

    # Drop non-positive amounts
    df = df[df['amount'] > 0]

    # Drop duplicates on (ticker, date, event_type)
    df = df.drop_duplicates(subset=['ticker', 'date', 'event_type'], keep='last')

    # Ensure date is pure date
    df['date'] = pd.to_datetime(df['date']).dt.date

    df = df.reset_index(drop=True)

    print(f"Cleaned events: {initial_rows} -> {len(df)} rows")
    return df


def _quick_test():
    """Sanity check using a small sample from extract."""
    from extract import fetch_prices, fetch_corporate_events

    print("=== Testing clean_prices ===")
    raw = fetch_prices(['AAPL', 'MSFT'],
                       start='2024-01-01',
                       end='2024-01-10',
                       batch_size=2)
    cleaned = clean_prices(raw)
    print(f"\nFirst 3 rows:\n{cleaned.head(3)}")
    print(f"\nDtypes:\n{cleaned.dtypes}")

    print("\n=== Testing clean_events ===")
    raw_events = fetch_corporate_events(['AAPL'], '2020-01-01', '2024-01-01')
    cleaned_events = clean_events(raw_events)
    print(f"\nFirst 3 rows:\n{cleaned_events.head(3)}")


if __name__ == "__main__":
    _quick_test()
