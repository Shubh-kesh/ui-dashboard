"""Direct pyodbc access to the DocAI MSSQL catalog (no uidb proxy)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Sequence

import pandas as pd
import pyodbc

from .config import get_settings


class DatabaseError(RuntimeError):
    """Raised when the MSSQL connection or query fails."""


@contextmanager
def cursor() -> Iterator[pyodbc.Cursor]:
    settings = get_settings()
    conn: pyodbc.Connection | None = None
    cur: pyodbc.Cursor | None = None
    try:
        conn = pyodbc.connect(settings.connection_string(), timeout=15)
        cur = conn.cursor()
        yield cur
    except pyodbc.Error as exc:  # pragma: no cover - exercised via integration
        raise DatabaseError(str(exc)) from exc
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def fetch_all(query: str, params: Sequence[Any] = ()) -> list[dict]:
    """Run a query and return rows as a list of column-keyed dicts."""
    with cursor() as cur:
        cur.execute(query, list(params))
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def fetch_df(query: str, params: Sequence[Any] = ()) -> pd.DataFrame:
    """Run a query and return a DataFrame with upper-cased column names."""
    rows = fetch_all(query, params)
    df = pd.DataFrame(rows)
    if not df.empty:
        df.columns = [str(c).strip().upper() for c in df.columns]
    return df


def ping() -> bool:
    """True if the configured database is reachable."""
    try:
        with cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except DatabaseError:
        return False
