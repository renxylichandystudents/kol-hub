"""Akses database PostgreSQL (Supabase) — koneksi dipool & di-cache per proses Streamlit."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import streamlit as st


def database_url() -> str | None:
    url = None
    try:
        url = st.secrets.get("DATABASE_URL")
    except Exception:
        url = None
    url = url or os.environ.get("DATABASE_URL")
    if url and "sslmode=" not in url and "localhost" not in url and "127.0.0.1" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


@st.cache_resource(show_spinner=False)
def _pool(url: str):
    from psycopg2.pool import ThreadedConnectionPool
    return ThreadedConnectionPool(1, 6, url, connect_timeout=10,
                                  keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3)


@contextmanager
def conn():
    import psycopg2
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL belum di-set di Secrets.")
    pool = _pool(url)
    c = pool.getconn()
    try:
        if c.closed:
            raise psycopg2.InterfaceError("closed")
        yield c
        c.commit()
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        try:
            c.rollback()
        except Exception:
            pass
        pool.putconn(c, close=True)
        c = None
        raise
    except Exception:
        c.rollback()
        raise
    finally:
        if c is not None:
            pool.putconn(c)


def _adapt(v):
    if isinstance(v, (dict,)) or (isinstance(v, list) and v and isinstance(v[0], dict)):
        from psycopg2.extras import Json
        return Json(v, dumps=lambda o: json.dumps(o, default=str, ensure_ascii=False))
    return v


def _params(p):
    if p is None:
        return None
    if isinstance(p, dict):
        return {k: _adapt(v) for k, v in p.items()}
    return tuple(_adapt(v) for v in p)


def _retrying(fn):
    import psycopg2
    try:
        return fn()
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        return fn()  # koneksi putus → coba sekali lagi dengan koneksi baru


def query(sql: str, params=None) -> list[dict]:
    def run():
        from psycopg2.extras import RealDictCursor
        with conn() as c, c.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, _params(params))
            return [dict(r) for r in cur.fetchall()] if cur.description else []
    return [_clean_row(r) for r in _retrying(run)]


def one(sql: str, params=None) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def scalar(sql: str, params=None):
    r = one(sql, params)
    return None if r is None else next(iter(r.values()))


def df(sql: str, params=None) -> pd.DataFrame:
    rows = query(sql, params)
    return pd.DataFrame(rows)


def execute(sql: str, params=None, returning: bool = False):
    def run():
        from psycopg2.extras import RealDictCursor
        with conn() as c, c.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, _params(params))
            if returning and cur.description:
                r = cur.fetchone()
                return dict(r) if r else None
            return cur.rowcount
    return run()


@contextmanager
def transaction():
    """Gunakan untuk beberapa perintah atomik: with transaction() as cur: cur.execute(...)."""
    from psycopg2.extras import RealDictCursor
    with conn() as c, c.cursor(cursor_factory=RealDictCursor) as cur:
        yield _Cur(cur)


class _Cur:
    def __init__(self, cur):
        self.cur = cur

    def execute(self, sql, params=None):
        self.cur.execute(sql, _params(params))
        return self

    def fetchone(self):
        r = self.cur.fetchone()
        return _clean_row(dict(r)) if r else None

    def fetchall(self):
        return [_clean_row(dict(r)) for r in self.cur.fetchall()]

    def executemany(self, sql, seq):
        from psycopg2.extras import execute_batch
        execute_batch(self.cur, sql, [_params(p) for p in seq], page_size=500)
        return self

    def copy_values(self, sql, rows, page_size=1000):
        from psycopg2.extras import execute_values
        execute_values(self.cur, sql, [tuple(_adapt(v) for v in r) for r in rows], page_size=page_size)
        return self


def _clean_row(r: dict) -> dict:
    for k, v in r.items():
        if isinstance(v, Decimal):
            r[k] = float(v)
        elif isinstance(v, memoryview):
            r[k] = bytes(v)
    return r


def to_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return pd.to_datetime(v).date()
