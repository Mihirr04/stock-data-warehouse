"""
Database connection module.

Centralizes all Postgres connection logic. Reads credentials from .env
and exposes both a low-level psycopg2 connection and a SQLAlchemy engine.
"""

import os
from contextlib import contextmanager

import psycopg2
from dotenv import load_dotenv
from sqlalchemy import create_engine

# Load .env into environment variables once, at import time
load_dotenv()

DB_HOST     = os.getenv('DB_HOST', 'localhost')
DB_PORT     = os.getenv('DB_PORT', '5432')
DB_NAME     = os.getenv('DB_NAME', 'stock_warehouse')
DB_USER     = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD')

if not DB_PASSWORD:
    raise RuntimeError(
        "DB_PASSWORD not found in environment. "
        "Make sure .env exists and contains DB_PASSWORD."
    )


def get_engine():
    """
    Returns a SQLAlchemy engine for the Postgres database.

    Use this for pandas integration (df.to_sql, pd.read_sql) and any
    high-level ORM-style work.

    URL-encodes the password so special characters (@, :, /, etc.)
    don't break the connection string.
    """
    from urllib.parse import quote_plus
    safe_password = quote_plus(DB_PASSWORD)
    url = f"postgresql+psycopg2://{DB_USER}:{safe_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url)

@contextmanager
def get_connection():
    """
    Context manager yielding a raw psycopg2 connection.

    Use this for direct SQL execution, transactions, and operations
    that need fine-grained control. Automatically commits on success,
    rolls back on error, and always closes the connection.

    Example:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM companies")
                print(cur.fetchone())
    """
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_connection():
    """Quick sanity check that the database is reachable."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM companies;")
            company_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM sectors;")
            sector_count = cur.fetchone()[0]

    print(f"✓ Connected to Postgres")
    print(f"  Version: {version.split(',')[0]}")
    print(f"  Companies in DB: {company_count}")
    print(f"  Sectors in DB:   {sector_count}")


if __name__ == "__main__":
    test_connection()