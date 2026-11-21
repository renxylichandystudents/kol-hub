"""Impor file traffic toko (aktual & budget) dari laporan internal Mitra10.

Format yang dikenali (otomatis per sheet):
- Harian aktual vs budget   : baris berisi blok 'ACTUAL' | 'BUDGET' | 'ACHIEVEMENT', baris berikutnya tanggal (mis. sheet apr, okt).
- Bulanan panjang           : kolom ke-3 berisi ACTUAL / BUDGET / ACH / LY / GROWTH, baris judul bulan JANUARY…DECEMBER (sheet 'mar').
                              ACTUAL & BUDGET = tahun berjalan, LY = tahun sebelumnya.
- Bulanan lebar             : baris MONTH / TYPE (Actual Traffic, Budget Traffic) / year (sheet 'jan - des', 'jan', 'feb').
- Budget harian (BUDGET_TRAFFIC): sheet per bulan (JAN…DES), baris MONTH = tanggal 1–31, YEAR (2025 / 2026), metrik
                              Budget Sales / Invoice / Traffic. Sheet MONTHLY = target bulanan (Target 2026).
Hasil: traffic harian aktual → offline_traffic_daily; budget harian → traffic_target_daily; bulanan aktual/budget → traffic_monthly.
Prioritas aktual bulanan: jumlah data harian > laporan bulanan.
"""
from __future__ import annotations

import calendar
import io
import re
from collections import defaultdict
from datetime import date, datetime

from .importer import StoreMatcher

MONTHS = {"JAN": 1, "JANUARY": 1, "JANUARI": 1, "FEB": 2, "FEBRUARY": 2, "FEBRUARI": 2, "MAR": 3, "MARCH": 3, "MARET": 3,
          "APR": 4, "APRIL": 4, "MAY": 5, "MEI": 5, "JUN": 6, "JUNE": 6, "JUNI": 6, "JUL": 7, "JULY": 7, "JULI": 7,
          "AUG": 8, "AUGUST": 8, "AGS": 8, "AGT": 8, "AGU": 8, "AGUSTUS": 8, "SEP": 9, "SEPT": 9, "SEPTEMBER": 9,
          "OCT": 10, "OKT": 10, "OCTOBER": 10, "OKTOBER": 10, "NOV": 11, "NOVEMBER": 11, "DEC": 12, "DES": 12,
          "DECEMBER": 12, "DESEMBER": 12}
EXTRA = {"pekan baru": "Mitra10 Pekanbaru", "tenth avenue": "Mitra10 TAV Bandung", "antasari": "Mitra10 Antasari Lampung",
         "rajabasa": "Mitra10 Rajabasa Lampung", "tanjung api api": "Mitra10 Tanjung Api Api Palembang",
         "telukjambe timur": "Mitra10 Telukjambe Timur Karawang", "siliwangi pamulang": "Mitra10 Pamulang",
         "pal 88 banjarmasin": "Mitra10 Pal88 Banjarmasin", "bypass ngurah": "Mitra10 Bypass Ngurah Rai"}


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _as_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}( 00:00:00)?", v.strip()):
        return date.fromisoformat(v.strip()[:10])
    return None


def _is_total(*cells) -> bool:
    return any(c is not None and re.search(r"\btotal\b", str(c), re.I) for c in cells)


def _month_of(v) -> int | None:
    if v is None:
        return None
    return MONTHS.get(re.sub(r"[^A-Z]", "", str(v).upper()))


class Matcher:
    def __init__(self, stores: list[dict]):
        self.m = StoreMatcher(stores)
        by = {s["nama"]: s["id"] for s in stores}
        from .importer import _norm
        self.extra = {_norm(k): by[v] for k, v in EXTRA.items() if v in by}
        self._norm = _norm
        self.unknown: set[str] = set()

    def __call__(self, name) -> int | None:
        if not name:
            return None
        s = str(name).strip()
        if re.search(r"\b(total|grand)\b", s, re.I):
            return None
        sid = self.m.match(s)
        if sid is None:
            n = self._norm(s)
            sid = self.extra.get(n) or next((v for k, v in self.extra.items() if k in n), None)
        if sid is None:
            self.unknown.add(s)
        return sid


# ---------------------------------------------------------------- detektor & parser per sheet
def _daily_blocks(rows):
    """Sheet harian: cari baris penanda ACTUAL/BUDGET lalu baris tanggal."""
    for i, r in enumerate(rows[:6]):
        marks = {str(v).strip().upper(): j for j, v in enumerate(r) if isinstance(v, str)}
        if "ACTUAL" in marks and "BUDGET" in marks:
            hdr = rows[i + 1]
            if sum(_as_date(v) is not None for v in hdr) >= 5:
                return i + 1, marks["ACTUAL"], marks["BUDGET"], marks.get("ACHIEVEMENT", len(hdr))
    return None


def parse_daily(rows, match, out):
    b = _daily_blocks(rows)
    if not b:
        return False
    hi, a0, b0, c0 = b
    hdr = rows[hi]
    for r in rows[hi + 1:]:
        sid = match(r[0])
        if not sid:
            continue
        for j in range(a0, len(hdr)):
            d = _as_date(hdr[j])
            if d is None or j >= len(r):
                continue
            v = _num(r[j])
            if v is None:
                continue
            if a0 <= j < b0:
                out["daily_actual"][(sid, d)] = v
            elif b0 <= j < c0:
                out["daily_budget"].setdefault((sid, d), {})["traffic"] = v
    return True


def parse_monthly_long(rows, match, out, tahun: int):
    hi = next((i for i, r in enumerate(rows[:6]) if r and str(r[0] or "").strip().upper() == "MONTH"
               and sum(_month_of(v) is not None for v in r) >= 6), None)
    if hi is None or not any(str(r[2] or "").strip().upper() == "ACTUAL" for r in rows[hi:hi + 8] if len(r) > 2):
        return False
    mcols = {j: _month_of(v) for j, v in enumerate(rows[hi]) if _month_of(v)}
    sid = None
    for r in rows[hi + 1:]:
        if _is_total(r[0] if r else None, r[1] if len(r) > 1 else None):
            sid = None
            continue
        if len(r) > 1 and r[1]:
            sid = match(r[1])
        kind = str(r[2] or "").strip().upper() if len(r) > 2 else ""
        if not sid or kind not in ("ACTUAL", "BUDGET", "LY"):
            continue
        y = tahun - 1 if kind == "LY" else tahun
        for j, m in mcols.items():
            v = _num(r[j]) if j < len(r) else None
            if v is None or (kind == "ACTUAL" and v == 0):
                continue
            key = (sid, date(y, m, 1))
            if kind == "BUDGET":
                out["monthly"].setdefault(key, {})["budget"] = v
            else:
                out["monthly"].setdefault(key, {}).setdefault("aktual", v)
    return True


def parse_monthly_wide(rows, match, out):
    if len(rows) < 5 or str(rows[1][0] or "").strip().upper() != "TYPE":
        return False
    month, year = {}, {}
    cm = cy = None
    for j in range(len(rows[0])):
        m = _month_of(rows[0][j])
        if rows[0][j] is not None:
            cm = m
        yv = rows[2][j] if j < len(rows[2]) else None
        if yv is not None and re.fullmatch(r"\d{4}", str(yv).strip().split(".")[0]):
            cy = int(str(yv).strip().split(".")[0])
        elif rows[0][j] is not None:
            cy = None
        month[j], year[j] = cm, cy
    n = 0
    for r in rows[4:]:
        sid = match(r[1] if len(r) > 1 else None)
        if not sid:
            continue
        for j in range(2, min(len(r), len(rows[1]))):
            t = str(rows[1][j] or "").strip().lower()
            if not month.get(j) or not year.get(j):
                continue
            kind = "aktual" if t in ("actual traffic", "traffic") else "budget" if t == "budget traffic" else None
            v = _num(r[j])
            if kind and v:
                out["monthly"].setdefault((sid, date(year[j], month[j], 1)), {}).setdefault(kind, v)
                n += 1
    return n > 0


def parse_budget_daily(rows, match, out, sheet: str):
    m = _month_of(sheet)
    if not m or len(rows) < 4 or str(rows[0][0] or "").strip().upper() != "MONTH" or str(rows[1][0] or "").strip().upper() != "YEAR":
        return False
    days, years = {}, {}
    cd = cy = None
    for j in range(len(rows[0])):
        v = rows[0][j]
        if v is not None:
            cd = int(_num(v)) if _num(v) is not None else None
        y = rows[1][j] if j < len(rows[1]) else None
        if y is not None:
            mt = re.search(r"(\d{4})", str(y))
            cy = int(mt.group(1)) if mt else None
        days[j], years[j] = cd, cy
    metric = {j: str(v or "").strip().lower() for j, v in enumerate(rows[2])}
    got = False
    for r in rows[3:]:
        sid = match(r[1] if len(r) > 1 else None)
        if not sid:
            continue
        for j in range(2, len(r)):
            d, y, mt = days.get(j), years.get(j), metric.get(j, "")
            if not d or not y:
                continue
            if d > calendar.monthrange(y, m)[1]:
                continue
            key = {"traffic": "traffic", "invoice": "invoice", "budget sales": "sales"}.get(mt)
            v = _num(r[j])
            if key and v is not None:
                out["daily_budget"].setdefault((sid, date(y, m, d)), {})[key] = v
                got = True
    return got


def parse_budget_monthly(rows, match, out):
    if len(rows) < 4 or str(rows[1][0] or "").strip().upper() != "YEAR" or not any("target" in str(v).lower() for v in rows[1] if v):
        return False
    month, tgt = {}, {}
    cm = None
    ty = None
    for j in range(len(rows[0])):
        if rows[0][j] is not None:
            cm = _month_of(rows[0][j])
        y = rows[1][j] if j < len(rows[1]) else None
        if y is not None:
            mt = re.search(r"target\s*(\d{4})", str(y), re.I)
            ty = int(mt.group(1)) if mt else None
        month[j], tgt[j] = cm, ty
    for r in rows[3:]:
        sid = match(r[1] if len(r) > 1 else None)
        if not sid:
            continue
        for j in range(2, len(r)):
            if month.get(j) and tgt.get(j) and str(rows[2][j] or "").strip().lower() == "traffic":
                v = _num(r[j])
                if v:
                    out["monthly"].setdefault((sid, date(tgt[j], month[j], 1)), {}).setdefault("budget", v)
    return True


def parse_files(files: list[tuple[str, bytes]], stores: list[dict], tahun: int | None = None) -> tuple[dict, list[str]]:
    import openpyxl
    match = Matcher(stores)
    out = {"daily_actual": {}, "daily_budget": {}, "monthly": {}}
    notes = []
    books = []
    for name, content in files:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        except Exception as e:  # noqa: BLE001
            notes.append(f"{name}: tidak bisa dibuka ({e}).")
            continue
        books.append((name, [(ws.title, [tuple(r) for r in ws.iter_rows(values_only=True)]) for ws in wb.worksheets]))
    # tahun berjalan: dari tanggal di sheet harian bila ada
    if tahun is None:
        ys = [_as_date(v).year for _, sheets in books for _, rows in sheets for r in rows[:4] for v in r if _as_date(v)]
        tahun = max(set(ys), key=ys.count) if ys else date.today().year
    for name, sheets in books:
        used = []
        # bulanan lebar: pakai sheet dengan bulan terbanyak per pasangan tahun (sheet kumulatif jan–des menimpa sebagian)
        for title, rows in sheets:
            ok = (parse_daily(rows, match, out) or parse_monthly_long(rows, match, out, tahun) or parse_budget_daily(rows, match, out, title)
                  or parse_budget_monthly(rows, match, out) or parse_monthly_wide(rows, match, out))
            if ok:
                used.append(title)
        skipped = [t for t, _ in sheets if t not in used]
        notes.append(f"{name}: dibaca {len(used)} sheet" + (f"; dilewati: {', '.join(skipped)}" if skipped else ""))
    if match.unknown:
        notes.append("Nama toko tidak dikenali (dilewati): " + ", ".join(sorted(match.unknown)[:30]))
    # aktual bulanan dari data harian (lebih akurat) menggantikan laporan bulanan
    agg = defaultdict(float)
    cnt = defaultdict(int)
    for (sid, d), v in out["daily_actual"].items():
        agg[(sid, d.replace(day=1))] += v
        cnt[(sid, d.replace(day=1))] += 1
    for k, v in agg.items():
        if cnt[k] >= calendar.monthrange(k[1].year, k[1].month)[1] - 1:
            out["monthly"].setdefault(k, {})["aktual"] = v
    out["tahun"] = tahun
    return out, notes


def summary(out: dict) -> dict:
    da = out["daily_actual"]
    db_ = out["daily_budget"]
    mo = out["monthly"]
    rng = lambda ks: (min(ks), max(ks)) if ks else (None, None)  # noqa: E731
    return {"harian_aktual": len(da), "harian_aktual_rentang": rng([d for _, d in da]),
            "harian_budget": len(db_), "harian_budget_rentang": rng([d for _, d in db_]),
            "bulanan": len(mo), "bulanan_rentang": rng([d for _, d in mo]),
            "toko": len({s for s, _ in list(da) + list(db_) + list(mo)})}


def load(out: dict, user_id: int, file_names: str, stores: list[dict]) -> dict:
    import pandas as pd

    from . import db
    from .preprocess import StoreMatcher as PM
    from .preprocess import clean_traffic
    res = {}
    with db.transaction() as cur:
        up = cur.execute("INSERT INTO uploads (jenis, nama_file, ringkasan_validasi_json, uploaded_by) VALUES ('traffic',%s,%s,%s) RETURNING id",
                         (file_names[:200], '{"sumber": "impor laporan traffic & budget"}', user_id)).fetchone()["id"]
        if out["daily_actual"]:
            names = {s["id"]: s["nama"] for s in stores}
            raw = pd.DataFrame([{"toko": names[s], "tanggal": d, "kunjungan": v} for (s, d), v in out["daily_actual"].items()])
            ev = db.query("SELECT mulai, selesai, store_id, zone_id FROM promo_offline_events")
            all_ids = [s["id"] for s in stores]
            events = [{"mulai": e["mulai"], "selesai": e["selesai"],
                       "store_ids": [e["store_id"]] if e["store_id"] else
                       ([s["id"] for s in stores if s["zone_id"] == e["zone_id"]] if e["zone_id"] else all_ids)} for e in ev]
            c = clean_traffic(raw, {"toko": "toko", "tanggal": "tanggal", "kunjungan": "kunjungan", "transaksi": None}, PM(stores), events=events)
            if not c["ok"]:
                raise ValueError(c["error"])
            data = c["data"]
            rows = [(int(r.store_id), r.tanggal.date(), int(r.kunjungan), None, r.flag if isinstance(r.flag, str) else None, up)
                    for r in data.itertuples()]
            cur.copy_values("""INSERT INTO offline_traffic_daily (store_id, tanggal, kunjungan, transaksi, flag, upload_id) VALUES %s
                               ON CONFLICT (store_id, tanggal) DO UPDATE SET kunjungan=EXCLUDED.kunjungan, flag=EXCLUDED.flag,
                               upload_id=EXCLUDED.upload_id""", rows)
            res["harian_aktual"] = len(rows)
            res["log"] = {k: v for k, v in c["log"].items() if isinstance(v, (int, float, str))}
        if out["daily_budget"]:
            rows = [(s, d, v.get("traffic"), v.get("invoice"), v.get("sales")) for (s, d), v in out["daily_budget"].items()]
            cur.copy_values("""INSERT INTO traffic_target_daily (store_id, tanggal, traffic, invoice, sales) VALUES %s
                               ON CONFLICT (store_id, tanggal) DO UPDATE SET traffic=COALESCE(EXCLUDED.traffic, traffic_target_daily.traffic),
                               invoice=COALESCE(EXCLUDED.invoice, traffic_target_daily.invoice),
                               sales=COALESCE(EXCLUDED.sales, traffic_target_daily.sales)""", rows)
            res["harian_budget"] = len(rows)
        if out["monthly"]:
            rows = [(s, b, round(v["aktual"]) if v.get("aktual") is not None else None, v.get("budget")) for (s, b), v in out["monthly"].items()]
            cur.copy_values("""INSERT INTO traffic_monthly (store_id, bulan, aktual, budget) VALUES %s
                               ON CONFLICT (store_id, bulan) DO UPDATE SET aktual=COALESCE(EXCLUDED.aktual, traffic_monthly.aktual),
                               budget=COALESCE(EXCLUDED.budget, traffic_monthly.budget), updated_at=NOW()""", rows)
            res["bulanan"] = len(rows)
        cur.execute("UPDATE uploads SET ringkasan_validasi_json=%s WHERE id=%s",
                    (__import__("json").dumps({"baris_siap": res.get("harian_aktual", 0), "toko": len({s for s, _ in out['daily_actual']}),
                                               **res}, default=str), up))
    return res
