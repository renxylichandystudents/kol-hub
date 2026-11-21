"""Komponen UI bersama (gaya mengikuti mockup Spesifikasi Bagian A)."""
from __future__ import annotations

import html
import re
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from . import db
from .formulas import angka, persen, rupiah  # noqa: F401  (re-export)
from .master import ROLES

CSS = """
<style>
:root{--kh-navy:#111a33;--kh-blue:#1d4ed8;--kh-orange:#f97316;--kh-line:#e5e9f2;--kh-muted:#64748b;
      --kh-green:#16a34a;--kh-red:#dc2626;--kh-amber:#d97706;--kh-soft:#eef3ff;}
section[data-testid="stSidebar"]{background:var(--kh-navy);}
section[data-testid="stSidebar"] *{color:#e6ebf5;}
section[data-testid="stSidebar"] [data-testid="stSidebarNavSeparator"]{border-color:#26314f;}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][aria-current="page"]{background:#1f2b4d;border-left:3px solid var(--kh-orange);}
section[data-testid="stSidebar"] header, section[data-testid="stSidebar"] [data-testid="stNavSectionHeader"]{color:#8ea0c6 !important;}
section[data-testid="stSidebar"] .stButton button{background:#1f2b4d;border:1px solid #33416a;color:#fff;}
section[data-testid="stSidebar"] [data-baseweb="select"] > div{background:#1f2b4d;border-color:#33416a;}
.block-container{padding-top:1.6rem;max-width:1400px;}
.kh-brand{display:flex;gap:.6rem;align-items:center;margin:.2rem 0 1rem 0}
.kh-logo{background:var(--kh-orange);color:#fff !important;font-weight:800;border-radius:10px;width:40px;height:40px;
         display:flex;align-items:center;justify-content:center;font-size:1rem}
.kh-brand b{font-size:1.15rem;color:#fff !important}.kh-brand small{display:block;color:#9fb0d3 !important}
.kh-card{background:#fff;border:1px solid var(--kh-line);border-radius:14px;padding:1rem 1.1rem;height:100%}
.kh-card.hl{background:var(--kh-soft);border-color:#c7d6fb}
.kh-kpi-l{color:var(--kh-muted);font-size:.86rem}.kh-kpi-v{font-size:1.75rem;font-weight:750;line-height:1.25;color:#0f172a}
.kh-kpi-s{color:var(--kh-muted);font-size:.8rem}
.kh-kpi-v{white-space:nowrap}
.kh-kpi-v.pos{color:var(--kh-blue)}.kh-kpi-v.neg{color:var(--kh-red)}
.kh-kpi-s.neg{color:var(--kh-red);font-weight:600}.kh-kpi-s.pos{color:var(--kh-green);font-weight:600}
.kh-badge{display:inline-block;padding:.12rem .55rem;border-radius:999px;font-size:.76rem;font-weight:600;white-space:nowrap}
.kh-b-green{background:#dcfce7;color:#166534}.kh-b-red{background:#fee2e2;color:#991b1b}.kh-b-amber{background:#fef3c7;color:#92400e}
.kh-b-blue{background:#dbeafe;color:#1e40af}.kh-b-gray{background:#eef2f7;color:#334155}.kh-b-purple{background:#ede9fe;color:#5b21b6}
.kh-strip{background:var(--kh-soft);border:1px solid #c7d6fb;border-radius:14px;padding:.7rem 1rem;margin-bottom:.8rem}
.kh-strip b{color:var(--kh-blue)}
.kh-sub{color:var(--kh-muted);margin-top:-.6rem;margin-bottom:.8rem}
.kh-note{color:var(--kh-muted);font-size:.82rem}
.kh-reason{display:inline-block;background:#f1f5f9;border-radius:6px;padding:.05rem .45rem;margin:.1rem .2rem .1rem 0;font-size:.78rem;color:#334155}
.kh-steps{display:flex;gap:.4rem;flex-wrap:wrap;margin:.2rem 0 .8rem}
.kh-step{padding:.3rem .7rem;border-radius:999px;border:1px solid var(--kh-line);font-size:.8rem;color:var(--kh-muted);background:#fff}
.kh-step.on{background:var(--kh-blue);color:#fff;border-color:var(--kh-blue)}.kh-step.done{background:#dcfce7;color:#166534;border-color:#bbf7d0}
.kh-sent{display:flex;height:14px;border-radius:7px;overflow:hidden;margin:.2rem 0 .6rem}
.kh-sent span{display:block;height:100%}
/* sembunyikan petunjuk "Press Enter to submit form" yang menutupi isi kolom kata sandi */
[data-testid="InputInstructions"]{display:none !important}
@media print{section[data-testid="stSidebar"],header,.stButton,[data-testid="stToolbar"]{display:none !important}}
</style>
"""


# ------------------------------------------------------------------ format angka (bilangan bulat + pemisah ribuan di semua tabel)
_INT_FMT = {"%d", "%.0f", "%i", "Rp %d", "Rp %.0f", "%,d", "localized"}
_SKIP_COLS = {"tahun", "year", "id", "no", "kode", "baris_ke", "dow", "jam", "slot"}


def _skip(col) -> bool:
    c = str(col).strip().lower()
    return c in _SKIP_COLS or c.endswith("_id") or c.startswith("id ")


def number_config(data, column_config: dict | None) -> tuple[dict | None, list]:
    """Semua angka tampil sebagai bilangan bulat dengan pemisah ribuan (format 'localized' → 1.234.567 di browser
    Indonesia). Persen dibulatkan tanpa desimal. Return (column_config, kolom yang datanya perlu dibulatkan)."""
    cfg = dict(column_config or {})
    to_round = []
    for k, v in list(cfg.items()):
        if not (isinstance(v, dict) and isinstance(v.get("type_config"), dict)):
            continue
        tc = v["type_config"]
        if tc.get("type") not in ("number", "progress"):
            continue
        fmt = tc.get("format")
        if tc.get("type") == "number" and (fmt in _INT_FMT or fmt is None):
            v = {**v, "type_config": {**tc, "format": "localized"}}
            if fmt and fmt.startswith("Rp") and "rp" not in str(v.get("label") or k).lower():
                v["label"] = f"{v.get('label') or k} (Rp)"
            to_round.append(k)
        elif fmt and re.fullmatch(r"%\+?\.\d+f%%", fmt):
            v = {**v, "type_config": {**tc, "format": re.sub(r"\.\d+f", ".0f", fmt)}}
        cfg[k] = v
    if isinstance(data, pd.DataFrame):
        for col in data.columns:
            if col in cfg or _skip(col):
                continue
            dt = data[col].dtype
            numeric = pd.api.types.is_numeric_dtype(dt) and not pd.api.types.is_bool_dtype(dt)
            if not numeric and dt == object:
                s = data[col].dropna()
                numeric = bool(len(s)) and s.map(lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)).all()
            if numeric:
                cfg[col] = st.column_config.NumberColumn(format="localized")
                to_round.append(col)
    return (cfg or None), to_round


def _id_num(v, fmt: str | None = None) -> str:
    """Format tampilan Indonesia: bilangan bulat bertitik ribuan; persen tanpa desimal."""
    if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if fmt and fmt.endswith("%%"):
        sign = "+" if "+" in fmt and x > 0 else ""
        return f"{sign}{round(x)}%"
    return f"{round(x):,}".replace(",", ".")


def styled(data: pd.DataFrame, column_config: dict | None):
    """Bulatkan & format semua kolom angka (titik ribuan) dan beri warna merah pada nilai minus."""
    cfg, _ = number_config(data, column_config)
    cfg = cfg or {}
    fmts, numeric = {}, []
    for col in data.columns:
        c = cfg.get(col)
        tc = c.get("type_config", {}) if isinstance(c, dict) else {}
        if isinstance(c, dict) and (tc.get("type") not in ("number", None) or c.get("hidden")):
            continue  # progress bar, link, checkbox, dsb. dibiarkan
        if c is None and not (pd.api.types.is_numeric_dtype(data[col].dtype) and not pd.api.types.is_bool_dtype(data[col].dtype)):
            continue
        if _skip(col):
            continue
        fmt = tc.get("format")
        if fmt and fmt != "localized" and not fmt.endswith("%%"):
            continue  # format khusus (mis. %.2f) dipertahankan
        numeric.append(col)
        fmts[col] = (lambda f: (lambda v: _id_num(v, f)))(fmt)
    if not numeric:
        return data, cfg
    df = data.copy()
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    sty = df.style.format(fmts, na_rep="—")

    def red(v):
        try:
            return "color:#dc2626;font-weight:600" if v is not None and not pd.isna(v) and float(v) < 0 else ""
        except (TypeError, ValueError):
            return ""
    sty = sty.map(red, subset=numeric)
    # format sudah dari Styler → hapus format angka di column_config agar tidak bentrok
    for col in numeric:
        if isinstance(cfg.get(col), dict):
            c = dict(cfg[col])
            c["type_config"] = {k: v for k, v in c.get("type_config", {}).items() if k != "format"}
            cfg[col] = c
        else:
            cfg.pop(col, None)
    return sty, cfg


def _round_cols(data, cols):
    if not isinstance(data, pd.DataFrame) or not cols:
        return data
    cols = [c for c in cols if c in data.columns]
    need = [c for c in cols if pd.api.types.is_float_dtype(data[c].dtype) or data[c].dtype == object]
    if not need:
        return data
    data = data.copy()
    for c in need:
        data[c] = pd.to_numeric(data[c], errors="coerce").round(0).astype("Int64")
    return data


def _wrap(fn, editor: bool = False):
    def inner(data=None, *args, **kwargs):
        try:
            if editor or not isinstance(data, pd.DataFrame):
                cfg, rnd = number_config(data, kwargs.get("column_config"))
                kwargs["column_config"] = cfg
            else:
                data, cfg = styled(data, kwargs.get("column_config"))
                kwargs["column_config"] = cfg or None
        except Exception:  # noqa: BLE001 — format gagal tidak boleh menghentikan layar
            pass
        if not editor:
            kwargs.setdefault("placeholder", "—")  # sel kosong tampil "—", bukan "None"
        return fn(data, *args, **kwargs)
    inner._kh_wrapped = True
    inner.__wrapped__ = fn
    return inner


def _original(fn):
    while getattr(fn, "_kh_wrapped", False) and hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def date_range(label: str, default_start: date, default_end: date, key: str, max_value: date | None = None,
               container=None) -> tuple[date, date]:
    """Pemilih periode berbentuk kalender (klik tanggal mulai lalu tanggal selesai)."""
    box = container or st
    v = box.date_input(label, value=(default_start, default_end), max_value=max_value, format="DD/MM/YYYY", key=key)
    if isinstance(v, (tuple, list)):
        if len(v) == 2:
            return v[0], v[1]
        if len(v) == 1:
            return v[0], v[0]
        return default_start, default_end
    return v, v


def setup():
    st.markdown(CSS, unsafe_allow_html=True)
    # pasang ulang setiap run (bukan hanya sekali) agar versi terbaru selalu dipakai setelah deploy tanpa restart
    st.dataframe = _wrap(_original(st.dataframe))
    st.data_editor = _wrap(_original(st.data_editor), editor=True)


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def header(title: str, subtitle: str | None = None):
    st.markdown(f"## {esc(title)}")
    if subtitle:
        st.markdown(f"<div class='kh-sub'>{esc(subtitle)}</div>", unsafe_allow_html=True)


_NEG = re.compile(r"(?<![\w.,])(-\s?(?:Rp\s?)?\d[\d.,]*\s?%?)")


def red_neg(text: str) -> str:
    """Escape teks lalu warnai merah setiap angka minus (mis. -4%, -1.234)."""
    return _NEG.sub(r"<span style='color:#dc2626;font-weight:600'>\1</span>", esc(text))


def kpis(items: list[dict]):
    cols = st.columns(len(items))
    for c, it in zip(cols, items):
        val = str(it["value"])
        tone = it.get("tone", "") or ("neg" if val.strip().startswith(("-", "−")) else "")
        size = "" if len(val) <= 11 else " style='font-size:1.25rem'" if len(val) <= 17 else " style='font-size:1.05rem'"
        c.markdown(
            f"<div class='kh-card {'hl' if it.get('highlight') else ''}'><div class='kh-kpi-l'>{esc(it['label'])}</div>"
            f"<div class='kh-kpi-v {tone}'{size}>{esc(val)}</div>"
            f"<div class='kh-kpi-s {it.get('sub_tone', '')}'>{red_neg(it.get('sub', ''))}</div></div>",
            unsafe_allow_html=True)


def badge(text: str, tone: str = "gray") -> str:
    return f"<span class='kh-badge kh-b-{tone}'>{esc(text)}</span>"


def score_tone(s: float | None) -> str:
    if s is None:
        return "gray"
    return "green" if s >= 80 else "blue" if s >= 65 else "amber" if s >= 50 else "red"


STATUS_TONE = {
    "Draft": "gray", "Diajukan": "blue", "Review Asisten Manager": "blue", "Review Manager": "purple", "Disetujui": "green",
    "Form RO dibuat": "green", "RO ditandatangani": "green", "Di Finance": "amber", "Dibayar sebagian": "amber",
    "Lunas": "green", "Selesai": "green", "Ditolak": "red", "Revisi": "amber",
    "tertahan": "red", "siap": "blue", "diproses": "amber", "lunas": "green",
    "Minta info": "amber", "aktif": "green", "diblokir": "red",
}


def status_badge(s: str) -> str:
    return badge(s, STATUS_TONE.get(s, "gray"))


def steps(labels: list[str], current: int):
    html_ = "".join(f"<span class='kh-step {'done' if i < current else 'on' if i == current else ''}'>{i + 1}. {esc(l)}</span>"
                    for i, l in enumerate(labels))
    st.markdown(f"<div class='kh-steps'>{html_}</div>", unsafe_allow_html=True)


def reasons(items: list[str]) -> str:
    return "".join(f"<span class='kh-reason'>{esc(r)}</span>" for r in items)


def sentiment_bar(pos: float, neu: float, neg: float):
    st.markdown(f"<div class='kh-sent'><span style='width:{pos}%;background:#16a34a'></span>"
                f"<span style='width:{neu}%;background:#cbd5e1'></span><span style='width:{neg}%;background:#ea580c'></span></div>",
                unsafe_allow_html=True)


def note(text: str):
    st.markdown(f"<div class='kh-note'>{esc(text)}</div>", unsafe_allow_html=True)


def card(md: str, highlight: bool = False):
    st.markdown(f"<div class='kh-card {'hl' if highlight else ''}'>{md}</div>", unsafe_allow_html=True)


# ------------------------------------------------------------------ master cache
@st.cache_data(ttl=600, show_spinner=False)
def stores() -> pd.DataFrame:
    return db.df("""SELECT s.id, s.kode, s.nama, replace(s.nama,'Mitra10 ','') AS short, s.kota, s.lat, s.lon,
                           s.alias, s.zone_id, z.nama AS zona, s.target_kunjungan_mingguan
                    FROM stores s JOIN zones z ON z.id = s.zone_id ORDER BY z.id, s.nama""")


@st.cache_data(ttl=600, show_spinner=False)
def zones() -> pd.DataFrame:
    return db.df("SELECT id, nama FROM zones ORDER BY id")


def store_name(sid) -> str:
    s = stores()
    r = s[s["id"] == sid]
    return r["nama"].iloc[0] if len(r) else "—"


# ------------------------------------------------------------------ filter global
def global_filters(user: dict, show_period: bool = True, key: str = "g") -> dict:
    """Pilihan toko (61) & zona yang memfilter layar; role Store terkunci di tokonya."""
    s = stores()
    z = zones()
    cols = st.columns([2.2, 1.6, 1.6] if show_period else [2.2, 1.6])
    if user["role"] == "store":
        sid = user.get("scope_store_id")
        row = s[s["id"] == sid]
        cols[0].selectbox("Toko", [row["nama"].iloc[0] if len(row) else "—"], disabled=True, key=f"{key}_st_locked")
        cols[1].selectbox("Zona", [row["zona"].iloc[0] if len(row) else "—"], disabled=True, key=f"{key}_zn_locked")
        store_ids = [sid] if sid else []
        zone_id = int(row["zone_id"].iloc[0]) if len(row) else None
    else:
        zone_opts = ["Semua"] + list(z["nama"])
        zsel = cols[1].selectbox("Zona", zone_opts, key="f_zone")
        pool = s if zsel == "Semua" else s[s["zona"] == zsel]
        store_opts = [f"Semua ({len(pool)})"] + list(pool["nama"])
        cur = st.session_state.get("f_store")
        if cur not in store_opts:
            st.session_state["f_store"] = store_opts[0]
        ssel = cols[0].selectbox("Toko", store_opts, key="f_store")
        if ssel.startswith("Semua"):
            store_ids = list(pool["id"])
        else:
            store_ids = list(pool[pool["nama"] == ssel]["id"])
        zone_id = None if zsel == "Semua" else int(z[z["nama"] == zsel]["id"].iloc[0])
    out = {"store_ids": [int(x) for x in store_ids], "zone_id": zone_id,
           "single_store": len(store_ids) == 1, "all": len(store_ids) == len(s)}
    if show_period:
        today = date.today()
        start, end = date_range("Periode", today - timedelta(days=30), today, key=f"{key}_periode", container=cols[2])
        out.update({"start": start, "end": end, "period_label": f"{start:%d/%m/%Y} – {end:%d/%m/%Y}"})
    return out


# ------------------------------------------------------------------ navigasi & notifikasi
def go(page: str, **state):
    for k, v in state.items():
        st.session_state[k] = v
    st.switch_page(page)


def notify(pesan: str, role: str | None = None, user_id: int | None = None, link: str | None = None):
    try:
        db.execute("INSERT INTO notifications (user_id, role, pesan, link) VALUES (%s,%s,%s,%s)", (user_id, role, pesan, link))
    except Exception:
        pass


def unread_notifications(user: dict) -> list[dict]:
    return db.query("""SELECT id, pesan, link, waktu FROM notifications
                       WHERE dibaca = FALSE AND (user_id = %s OR (user_id IS NULL AND role = %s))
                       ORDER BY waktu DESC LIMIT 20""", (user["id"], user["role"]))


def role_label(r: str) -> str:
    return ROLES.get(r, r)


def flash():
    msg = st.session_state.pop("flash_ok", None)
    if msg:
        st.success(msg)
    msg = st.session_state.pop("flash_err", None)
    if msg:
        st.error(msg)


def data_limited(text: str = "data terbatas") -> str:
    return badge(text, "amber")
