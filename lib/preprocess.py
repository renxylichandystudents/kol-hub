"""Preprocessing per sumber data — Spesifikasi B.3.

Tidak ada data dipakai model sebelum lolos validasi skema, rentang nilai, duplikat,
dan kecocokan nama toko (B.1).
"""
from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

try:
    from rapidfuzz import fuzz, process  # type: ignore
except ImportError:  # fallback agar tetap jalan tanpa rapidfuzz
    fuzz = process = None


# ================================================================ nama toko
def _norm(s: str) -> str:
    s = str(s or "").lower()
    s = re.sub(r"mitra\s*10|mitra10|toko|cabang|store", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _ratio(a: str, b: str) -> float:
    if fuzz is not None:
        return float(fuzz.token_set_ratio(a, b))
    ta, tb = set(a.split()), set(b.split())
    if ta and tb and (ta <= tb or tb <= ta):
        return 100.0
    return SequenceMatcher(None, a, b).ratio() * 100


class StoreMatcher:
    """Cocokkan nama toko bebas ke 61 toko: kamus alias + fuzzy match ≥ 90."""

    def __init__(self, stores: list[dict], threshold: float = 90):
        self.threshold = threshold
        self.alias: dict[str, int] = {}
        self.names: dict[str, int] = {}
        for s in stores:
            sid = s["id"]
            self.names[_norm(s["nama"])] = sid
            for a in (s.get("alias") or []):
                self.alias[_norm(a)] = sid
            self.alias[_norm(s["kode"])] = sid

    def match(self, raw: str) -> tuple[int | None, float, str]:
        n = _norm(raw)
        if not n:
            return None, 0.0, "kosong"
        if n in self.names:
            return self.names[n], 100.0, "exact"
        if n in self.alias:
            return self.alias[n], 100.0, "alias"
        best_id, best = None, 0.0
        for name, sid in {**self.names, **self.alias}.items():
            r = _ratio(n, name)
            if r > best:
                best_id, best = sid, r
        if best >= self.threshold:
            return best_id, best, "fuzzy"
        return None, best, "tidak cocok"

    def find_in_text(self, text: str) -> int | None:
        """Gazetteer: kenali toko yang disebut dalam teks komentar."""
        t = " " + _norm(text) + " "
        hits = [(len(a), sid) for a, sid in {**self.alias, **self.names}.items() if len(a) >= 4 and f" {a} " in t]
        return max(hits)[1] if hits else None


# ================================================================ traffic offline
TRAFFIC_COLUMNS = {"toko": "Nama toko", "tanggal": "Tanggal", "kunjungan": "Kunjungan", "transaksi": "Transaksi (opsional)"}


def guess_column_mapping(columns: list[str]) -> dict[str, str | None]:
    pats = {
        "toko": r"toko|store|cabang|outlet|lokasi",
        "tanggal": r"tanggal|tgl|date|hari",
        "kunjungan": r"kunjung|visit|traffic|pengunjung|footfall",
        "transaksi": r"transaksi|trx|struk|receipt|transaction",
    }
    out = {}
    for key, p in pats.items():
        out[key] = next((c for c in columns if re.search(p, str(c), re.I)), None)
    return out


def clean_traffic(raw: pd.DataFrame, mapping: dict[str, str | None], matcher: StoreMatcher,
                  events: list[dict] | None = None, history: pd.DataFrame | None = None) -> dict:
    """Validasi & preprocessing traffic offline.

    Langkah: cocokkan toko → seragamkan tanggal → validasi rentang → buang duplikat (toko+tanggal)
    → imputasi kosong ≤ 2 hari (hari yang sama minggu lalu), > 2 hari ditandai
    → outlier robust z > 3 dari residu musiman → outlier saat event toko diberi flag 'event'.
    """
    log: dict = {"baris_awal": len(raw)}
    missing = [k for k in ("toko", "tanggal", "kunjungan") if not mapping.get(k)]
    if missing:
        return {"ok": False, "error": f"Kolom wajib belum dipetakan: {', '.join(missing)}", "log": log}

    df = pd.DataFrame({
        "toko_raw": raw[mapping["toko"]].astype(str),
        "tanggal_raw": raw[mapping["tanggal"]],
        "kunjungan": pd.to_numeric(raw[mapping["kunjungan"]], errors="coerce"),
        "transaksi": pd.to_numeric(raw[mapping["transaksi"]], errors="coerce") if mapping.get("transaksi") else np.nan,
    })

    # 1) cocokkan toko
    cache = {}
    ids, scores, methods = [], [], []
    for t in df["toko_raw"]:
        if t not in cache:
            cache[t] = matcher.match(t)
        sid, sc, m = cache[t]
        ids.append(sid); scores.append(sc); methods.append(m)
    df["store_id"], df["match_score"], df["match_method"] = ids, scores, methods
    tidak_cocok = sorted({t for t, (sid, _, _) in cache.items() if sid is None})
    log["nama_toko_distandarkan"] = sum(1 for _, (sid, _, m) in cache.items() if sid and m in ("alias", "fuzzy"))
    log["nama_toko_tidak_dikenal"] = tidak_cocok
    df = df[df["store_id"].notna()].copy()
    df["store_id"] = df["store_id"].astype(int)

    # 2) tanggal
    def parse_date(v):
        if isinstance(v, (pd.Timestamp, np.datetime64)):
            return pd.Timestamp(v).normalize()
        if isinstance(v, (int, float)) and not pd.isna(v) and 20000 < v < 80000:  # serial Excel
            return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))
        return pd.to_datetime(str(v), dayfirst=True, errors="coerce")

    df["tanggal"] = df["tanggal_raw"].map(parse_date)
    log["tanggal_tidak_valid"] = int(df["tanggal"].isna().sum())
    df = df[df["tanggal"].notna()].copy()
    df["tanggal"] = pd.to_datetime(df["tanggal"]).dt.normalize()

    # 3) rentang nilai
    invalid = df["kunjungan"].notna() & (df["kunjungan"] < 0)
    log["nilai_negatif"] = int(invalid.sum())
    df.loc[invalid, "kunjungan"] = np.nan

    # 4) duplikat
    before = len(df)
    df = df.sort_values(["store_id", "tanggal"]).drop_duplicates(["store_id", "tanggal"], keep="last")
    log["duplikat_dibuang"] = before - len(df)

    # 5) lengkapi kalender per toko + imputasi
    frames = []
    imputed, gaps_flagged = 0, 0
    for sid, g in df.groupby("store_id"):
        g = g.set_index("tanggal").reindex(pd.date_range(g["tanggal"].min(), g["tanggal"].max(), freq="D"))
        g["store_id"] = sid
        g["flag"] = None
        isna = g["kunjungan"].isna()
        run_id = (isna != isna.shift()).cumsum()
        run_len = isna.groupby(run_id).transform("sum")
        for idx in g.index[isna]:
            if run_len.loc[idx] <= 2:
                prev = idx - pd.Timedelta(days=7)
                val = g["kunjungan"].get(prev)
                if (val is None or pd.isna(val)) and history is not None:
                    h = history[(history["store_id"] == sid) & (history["tanggal"] == prev)]
                    val = h["kunjungan"].iloc[0] if len(h) else np.nan
                if val is not None and not pd.isna(val):
                    g.loc[idx, "kunjungan"] = val
                    g.loc[idx, "flag"] = "imputasi"
                    imputed += 1
            else:
                gaps_flagged += 1
        frames.append(g.reset_index().rename(columns={"index": "tanggal"}))
    df = pd.concat(frames, ignore_index=True) if frames else df.assign(flag=None)
    log["diimputasi"] = imputed
    log["kosong_lebih_2_hari_ditandai"] = gaps_flagged
    df = df[df["kunjungan"].notna()].copy()

    # 6) outlier: robust z > 3 dari residu terhadap pola mingguan
    df["dow"] = df["tanggal"].dt.dayofweek
    out_cnt, event_cnt = 0, 0
    ev = events or []
    for sid, g in df.groupby("store_id"):
        if len(g) < 14:
            continue
        seasonal = g.groupby("dow")["kunjungan"].transform("median")
        trend = g["kunjungan"].rolling(7, center=True, min_periods=3).median() / \
            seasonal.rolling(7, center=True, min_periods=3).median()
        expected = seasonal * trend.fillna(1.0)
        resid = g["kunjungan"] - expected
        med = resid.median()
        mad = (resid - med).abs().median() or 1.0
        z = (resid - med) / (1.4826 * mad)
        for idx in g.index[z.abs() > 3]:
            d = df.at[idx, "tanggal"].date()
            # events: [{store_ids: [...], mulai: date, selesai: date}] dari kalender promo offline
            is_event = any(sid in e["store_ids"] and e["mulai"] <= d <= e["selesai"] for e in ev)
            df.at[idx, "flag"] = "event" if is_event else "outlier"
            if is_event:
                event_cnt += 1
            else:
                out_cnt += 1
    log["outlier_ditandai"] = out_cnt
    log["outlier_bertepatan_event"] = event_cnt
    log["baris_siap"] = len(df)
    log["toko"] = int(df["store_id"].nunique())
    clean = df[["store_id", "tanggal", "kunjungan", "transaksi", "flag"]].copy()
    clean["kunjungan"] = clean["kunjungan"].round().astype(int)
    return {"ok": True, "data": clean, "log": log}


# ================================================================ database KOL
LINK_RE = re.compile(r"^https?://[\w.-]+\.[a-z]{2,}(/\S*)?$", re.I)


def normalize_username(u: str) -> str:
    u = str(u or "").strip().lower()
    u = re.sub(r"^https?://(www\.)?(instagram\.com|tiktok\.com)/@?", "", u)
    return u.lstrip("@").strip("/ ").split("?")[0]


def valid_link(link: str) -> bool:
    return bool(LINK_RE.match(str(link or "").strip()))


def dedupe_kols(incoming: pd.DataFrame, existing: list[dict]) -> pd.DataFrame:
    """Tandai baris baru / digabung / ditolak: username dinormalisasi, link, kemiripan nama."""
    ex_user = {(e["platform"].lower(), e["username_norm"]): e["id"] for e in existing}
    ex_link = {str(e["link"]).rstrip("/").lower(): e["id"] for e in existing}
    ex_names = [(e["nama"].lower(), e["id"], e["platform"].lower()) for e in existing]
    rows = []
    seen = set()
    for _, r in incoming.iterrows():
        plat = str(r.get("platform", "")).strip()
        un = normalize_username(r.get("username", ""))
        link = str(r.get("link", "")).strip()
        status, alasan, match_id = "baru", "", None
        if not un or not plat:
            status, alasan = "ditolak", "username/platform kosong"
        elif not valid_link(link):
            status, alasan = "ditolak", "link tidak valid"
        elif (plat.lower(), un) in seen:
            status, alasan = "ditolak", "duplikat di dalam file"
        elif (plat.lower(), un) in ex_user:
            status, alasan, match_id = "digabung", "username sudah ada", ex_user[(plat.lower(), un)]
        elif link.rstrip("/").lower() in ex_link:
            status, alasan, match_id = "digabung", "link sudah ada", ex_link[link.rstrip("/").lower()]
        else:
            nm = str(r.get("nama", "")).lower()
            for en, eid, ep in ex_names:
                if ep == plat.lower() and nm and _ratio(nm, en) >= 95:
                    status, alasan, match_id = "digabung", f"nama mirip ({en})", eid
                    break
        seen.add((plat.lower(), un))
        rows.append({**r.to_dict(), "username_norm": un, "status_upload": status, "alasan": alasan, "match_id": match_id})
    return pd.DataFrame(rows)


def ratecard_flags(history: list[dict]) -> list[dict]:
    """Riwayat ratecard per deliverable; tandai kenaikan > 20%."""
    out = []
    by_d: dict[str, list[dict]] = {}
    for h in sorted(history, key=lambda x: x["berlaku_mulai"]):
        by_d.setdefault(h["deliverable"], []).append(h)
    for d, lst in by_d.items():
        for prev, cur in zip(lst, lst[1:]):
            naik = (float(cur["harga"]) / float(prev["harga"]) - 1) * 100 if prev["harga"] else 0
            out.append({"deliverable": d, "dari": prev["harga"], "ke": cur["harga"], "naik_pct": naik,
                        "tanggal": cur["berlaku_mulai"], "flag": naik > 20})
    return out


# ================================================================ komentar
SLANG = {
    "gak": "tidak", "ga": "tidak", "nggak": "tidak", "ngga": "tidak", "enggak": "tidak", "gk": "tidak", "tdk": "tidak",
    "g": "tidak", "kagak": "tidak", "ndak": "tidak", "yg": "yang", "dgn": "dengan", "utk": "untuk", "bgt": "banget",
    "bngt": "banget", "sy": "saya", "aku": "saya", "gw": "saya", "gue": "saya", "lu": "kamu", "lo": "kamu",
    "udh": "sudah", "udah": "sudah", "sdh": "sudah", "blm": "belum", "lg": "lagi", "aja": "saja", "aj": "saja",
    "bs": "bisa", "bsa": "bisa", "brp": "berapa", "berapaan": "berapa", "hrg": "harga", "hrgnya": "harganya",
    "tp": "tapi", "tpi": "tapi", "krn": "karena", "karna": "karena", "jd": "jadi", "jdi": "jadi", "sm": "sama",
    "dmn": "di mana", "dimana": "di mana", "mna": "mana", "knp": "kenapa", "gmn": "bagaimana", "gimana": "bagaimana",
    "kak": "kakak", "min": "admin", "mimin": "admin", "bgs": "bagus", "mantul": "mantap", "mantab": "mantap",
    "ok": "oke", "okey": "oke", "thx": "terima kasih", "makasih": "terima kasih", "trims": "terima kasih",
    "pengen": "ingin", "pgn": "ingin", "mau": "ingin", "ada gk": "ada tidak", "skrg": "sekarang", "kmrn": "kemarin",
    "bbrp": "beberapa", "dah": "sudah", "bener": "benar", "emg": "memang", "emang": "memang", "kalo": "kalau",
    "klo": "kalau", "kl": "kalau", "trs": "terus", "lama bgt": "lama banget", "cs": "customer service",
}

EMOJI_SENT = {
    "😍": " emo_pos ", "🥰": " emo_pos ", "❤": " emo_pos ", "👍": " emo_pos ", "🔥": " emo_pos ", "😊": " emo_pos ",
    "🙏": " emo_pos ", "👏": " emo_pos ", "💯": " emo_pos ", "😁": " emo_pos ", "😂": " emo_lucu ", "🤣": " emo_lucu ",
    "😡": " emo_neg ", "😠": " emo_neg ", "👎": " emo_neg ", "😤": " emo_neg ", "😭": " emo_neg ", "😞": " emo_neg ",
    "🙄": " emo_neg ", "💔": " emo_neg ",
}

SPAM_PATTERNS = re.compile(
    r"(?:https?://|www\.|wa\.me|bit\.ly|slot|gacor|judi|dm for promo|follow balik|cek bio|pinjol|giveaway pulsa|"
    r"jual followers|link di bio)", re.I)

EN_WORDS = {"the", "and", "is", "are", "you", "this", "what", "where", "price", "how", "very", "good", "nice"}


def anonymize(username: str) -> str:
    return "u_" + hashlib.sha256(str(username).encode()).hexdigest()[:10]


def normalize_text(text: str) -> str:
    t = str(text or "")
    for e, tok in EMOJI_SENT.items():
        t = t.replace(e, tok)
    t = t.lower()
    t = re.sub(r"@\w+", " ", t)
    t = re.sub(r"(.)\1{2,}", r"\1\1", t)  # "bagusss" → "baguss"
    t = re.sub(r"[^\w\s]", " ", t)
    words = t.split()
    t = " ".join(SLANG.get(w, w) for w in words)
    return re.sub(r"\s+", " ", t).strip()


def detect_language(text: str) -> str:
    w = set(normalize_text(text).split())
    return "en" if len(w & EN_WORDS) >= 2 else "id"


def flag_spam(df: pd.DataFrame) -> pd.Series:
    """Spam/bot: link/kata kunci promosi, duplikat massal (≥ 5 teks identik), teks kosong."""
    text = df["teks"].astype(str)
    norm = text.str.lower().str.replace(r"\s+", " ", regex=True).str.strip()
    dup = norm.map(norm.value_counts()) >= 5
    return text.str.contains(SPAM_PATTERNS) | dup | (norm.str.len() < 2)
