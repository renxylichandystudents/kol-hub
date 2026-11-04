"""Migrasi skema otomatis: file migrations/NNN_*.sql dijalankan sekali, berurutan, atomik."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from . import db

MIG_DIR = Path(__file__).resolve().parents[1] / "migrations"


@st.cache_resource(show_spinner="Menyiapkan database (sekali saja)…")
def ensure_schema(url: str) -> dict:
    """Jalankan migrasi yang belum diterapkan. Di-cache per proses agar hanya sekali."""
    applied_now = []
    with db.conn() as c, c.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(424242)")
        try:
            cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                             versi VARCHAR(100) PRIMARY KEY, diterapkan TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
            cur.execute("ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY")
            c.commit()
            cur.execute("SELECT versi FROM schema_migrations")
            done = {r[0] for r in cur.fetchall()}
            for f in sorted(MIG_DIR.glob("*.sql")):
                if f.name in done:
                    continue
                cur.execute(f.read_text(encoding="utf-8"))
                cur.execute("INSERT INTO schema_migrations (versi) VALUES (%s)", (f.name,))
                c.commit()
                applied_now.append(f.name)
        except Exception:
            c.rollback()
            raise
        finally:
            cur.execute("SELECT pg_advisory_unlock(424242)")
            c.commit()
    return {"diterapkan": applied_now}
