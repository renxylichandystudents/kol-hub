"""Impor file Excel realisasi KOL bulanan & Portal (homeless media) → database.

Format yang dikenali (lihat juga layar "Impor Excel KOL & Portal"):
- KOL bulanan  : nama file mengandung bulan & tahun, mis. KOL_SEPT_2026.xlsx. Satu sheet, baris judul berisi kolom
                 'Toko' + kolom akun ('KOL', 'KOL/Portal', 'KOL terpilih', 'Influencer' atau 'Homeless Media'),
                 'Followers', 'ER', 'Budget', 'Type Konten', 'Campaign', link IG/TikTok ('Link …' / 'Bukti Tayang …').
- Portal       : satu sheet per promo; baris 1 = 'LIST PORTAL PROMO … - PERIODE TAYANG <tgl> <BULAN> <TAHUN>',
                 baris 2 = judul kolom. Bila ada dua kolom 'Homeless Media', kolom terakhir yang terisi = akun yang tayang.
Sel 'Toko' yang digabung (merge) diisi ke bawah. Link berisi 'cancel' = baris dibatalkan (dicatat, tidak dihitung).
Tanggal tayang dibaca dari kode link Instagram (akurat ke hari); bila tidak ada, pakai tanggal periode tayang.
Impor ulang file yang sama menggantikan campaign hasil impor sebelumnya (kunci: campaigns.impor_key).
"""
from __future__ import annotations

import calendar
import io
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timezone

BULAN = {"JANUARI": 1, "JAN": 1, "FEBRUARI": 2, "FEB": 2, "MARET": 3, "MAR": 3, "APRIL": 4, "APR": 4, "MEI": 5,
         "JUNI": 6, "JUN": 6, "JULI": 7, "JUL": 7, "AGUSTUS": 8, "AGU": 8, "AGT": 8, "AUG": 8, "SEPTEMBER": 9,
         "SEPT": 9, "SEP": 9, "OKTOBER": 10, "OKT": 10, "OCT": 10, "NOVEMBER": 11, "NOV": 11, "DESEMBER": 12,
         "DES": 12, "DEC": 12}
NAMA_BULAN = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
              "November", "Desember"]
# penulisan nama toko di file yang berbeda dari master
EXTRA_ALIAS = {"siliwangi pamulang": "Mitra10 Pamulang", "telukjambe timur": "Mitra10 Telukjambe Timur Karawang",
               "jakabaring palembang": "Mitra10 Jakabaring", "by pass bali": "Mitra10 Bypass Ngurah Rai",
               "bypass bali": "Mitra10 Bypass Ngurah Rai", "qbig tbc": "Mitra10 Q-Big"}
DELIV = {"reels": "reels", "reel": "reels", "feed carousel": "feed", "feed": "feed", "carousel": "feed",
         "story": "story", "video": "video", "tiktok": "video", "artikel": "artikel"}
NICHE = {"komedi": "comedy", "comedy": "comedy", "lifestyle": "lifestyle", "beauty": "beauty", "kuliner": "culinary",
         "culinary": "culinary", "food": "culinary"}
USER_COLS = ["KOL terpilih", "KOL/Portal", "KOL", "Influencer", "Homeless Media", "Akun"]
_ALPH = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


# ---------------------------------------------------------------- util
def _norm(s) -> str:
    s = unicodedata.normalize("NFKC", str(s)).lower().replace("mitra10", " ").replace("mitra 10", " ")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def username_norm(s: str) -> str:
    return re.sub(r"[^a-z0-9._]", "", str(s).strip().lstrip("@").lower())


def _uname(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip().lstrip("@").strip()
    if not s or s == "-" or re.fullmatch(r"[\d.,]+", s) or s.lower().startswith("http"):
        return None
    return s


def _num(v) -> float | None:
    if v is None or str(v).strip() in ("", "-"):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def _deliv(v) -> str:
    return DELIV.get(str(v or "").strip().lower(), "reels")


def _clean_url(u: str) -> str:
    u = str(u).strip()
    return re.sub(r"\?.*$", "", u) if "instagram.com" in u else u


def ig_date(url: str | None) -> date | None:
    """Tanggal unggah dari shortcode Instagram (ID media = (ms − epoch IG) << 23)."""
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]{9,12})", url or "")
    if not m:
        return None
    n = 0
    for ch in m.group(1)[:11]:
        n = n * 64 + _ALPH.index(ch)
    try:
        d = datetime.fromtimestamp(((n >> 23) + 1314220021721) / 1000, tz=timezone.utc).date()
    except (OverflowError, OSError, ValueError):
        return None
    return d if date(2015, 1, 1) <= d <= date(2100, 1, 1) else None


class StoreMatcher:
    def __init__(self, stores: list[dict]):
        self.keys: list[tuple[str, int]] = []
        by_name = {s["nama"]: s["id"] for s in stores}
        for s in stores:
            self.keys.append((_norm(s["nama"]), s["id"]))
            for a in s.get("alias") or []:
                self.keys.append((_norm(a), s["id"]))
        for k, nama in EXTRA_ALIAS.items():
            if nama in by_name:
                self.keys.append((_norm(k), by_name[nama]))
        self.keys = [k for k in self.keys if k[0]]
        self.by_len = sorted(self.keys, key=lambda t: -len(t[0]))

    def match(self, name: str | None) -> int | None:
        n = _norm(name or "")
        if not n:
            return None
        for k, sid in self.keys:
            if n == k:
                return sid
        hits = {sid for k, sid in self.by_len if re.search(rf"\b{re.escape(k)}\b", n)}
        if len(hits) == 1:
            return hits.pop()
        # beberapa toko cocok (mis. 'Makassar' → 3 toko) → ambil kunci terpanjang hanya bila jelas lebih spesifik
        for k, sid in self.by_len:
            if re.search(rf"\b{re.escape(k)}\b", n) and len(k.split()) >= 2:
                return sid
        return None


# ---------------------------------------------------------------- parsing
def _bulan_tahun(filename: str) -> tuple[int | None, int | None]:
    up = re.sub(r"[^A-Z0-9]+", " ", filename.upper())
    m = None
    for tok in up.split():
        if tok in BULAN:
            m = BULAN[tok]
    y = re.search(r"\b(20\d\d)\b", up)
    return m, int(y.group(1)) if y else None


def parse_kol(ws, filename: str, matcher: StoreMatcher) -> tuple[list[dict], list[str]]:
    rows, issues = [], []
    bulan, tahun = _bulan_tahun(filename)
    if not bulan or not tahun:
        return [], [f"{filename}: bulan/tahun tidak terbaca dari nama file (contoh: KOL_SEPT_2026.xlsx)."]
    data = list(ws.iter_rows(values_only=True))
    hi = next((i for i, r in enumerate(data[:10]) if r and "toko" in [str(x).strip().lower() for x in r if x]), None)
    if hi is None:
        return [], [f"{filename}: kolom 'Toko' tidak ditemukan."]
    hdr = [str(h).strip() if h else "" for h in data[hi]]
    col = {}
    for i, h in enumerate(hdr):
        if h and h not in col:
            col[h] = i
    lower = {h.lower(): i for h, i in col.items()}
    ti = lower["toko"]
    ui_ = None
    for c in USER_COLS:
        if c in col:
            vals = [r[col[c]] for r in data[hi + 1:] if len(r) > col[c] and r[col[c]] is not None]
            if vals and sum(isinstance(v, str) for v in vals) > len(vals) / 2:
                ui_ = col[c]
                break
    if ui_ is None:
        return [], [f"{filename}: kolom nama akun KOL tidak ditemukan."]
    fi = lower.get("followers")
    if fi is None and "Influencer" in col and col["Influencer"] != ui_:
        fi = col["Influencer"]
    link_cols = [i for i, h in enumerate(hdr) if h.lower().startswith(("link", "bukti"))]
    key = f"KOL-{tahun}-{bulan:02d}"
    toko = None
    for ri, r in enumerate(data[hi + 1:], start=hi + 2):
        r = list(r) + [None] * (len(hdr) - len(r))
        if r[ti]:
            toko = str(r[ti]).strip()
        u = _uname(r[ui_])
        if not u or not toko:
            continue
        links = [str(r[i]).strip() for i in link_cols if r[i] not in (None, "", "-")]
        cancel = any(l.lower() == "cancel" for l in links)
        urls = [l for l in links if l.lower().startswith("http")]
        ig = [_clean_url(l) for l in urls if "instagram.com" in l]
        other = [l for l in urls if "instagram.com" not in l]
        budget = _num(r[lower["budget"]]) if "budget" in lower else None
        if budget is None and not urls:
            issues.append(f"{filename} baris {ri}: {u} ({toko}) tanpa budget & tanpa link — dilewati.")
            continue
        er = _num(r[lower["er"]]) if "er" in lower else None
        tgl = next((d for d in map(ig_date, ig) if d), None)
        rows.append({
            "key": key, "tipe": "kol", "file": filename, "baris": ri, "toko": toko, "store_id": matcher.match(toko),
            "username": u, "followers": _num(r[fi]) if fi is not None else None,
            "er": round(er * 100, 2) if er is not None and er < 1 else er,
            "avg_views": _num(r[lower["avg views"]]) if "avg views" in lower else None,
            "niche": str(r[lower["niche"]]).strip() if "niche" in lower and r[lower["niche"]] else None,
            "deliverable": _deliv(r[lower["type konten"]]) if "type konten" in lower else "reels",
            "label": str(r[lower["campaign"]]).strip() if "campaign" in lower and r[lower["campaign"]] else "Store Endorse",
            "budget": budget, "cancel": cancel, "ig": ig, "other": other, "tanggal": tgl,
            "camp_nama": f"KOL Store Endorse — {NAMA_BULAN[bulan]} {tahun}",
            "camp_mulai": date(tahun, bulan, 1), "camp_selesai": date(tahun, bulan, calendar.monthrange(tahun, bulan)[1]),
            "snapshot": date(tahun, bulan, 1),
        })
        if budget is None:
            issues.append(f"{filename} baris {ri}: {u} ({toko}) budget kosong — dicatat Rp 0.")
    return rows, issues


def parse_portal_sheet(ws, filename: str, matcher: StoreMatcher) -> tuple[list[dict], list[str]]:
    rows, issues = [], []
    data = list(ws.iter_rows(values_only=True))
    title = str(data[0][0] or "").strip()
    m = re.search(r"PERIODE TAYANG\s+(\d{1,2})(?:\s*-\s*\d{1,2})?\s+([A-Z]+)\s+(\d{4})", title.upper())
    if not m or m.group(2) not in BULAN:
        return [], [f"{filename} sheet '{ws.title}': tanggal 'PERIODE TAYANG' tidak terbaca dari judul."]
    tayang = date(int(m.group(3)), BULAN[m.group(2)], int(m.group(1)))
    nama = re.sub(r"^LIST PORTAL PROMO\s+", "", title.split(" - ")[0], flags=re.I).strip().title()
    nama = re.sub(r"\bLns\b", "LNS", nama)
    hdr = [str(h).strip() if h else "" for h in data[1]]
    lower = {}
    for i, h in enumerate(hdr):
        if h and h.lower() not in lower:
            lower[h.lower()] = i
    if "toko" not in lower:
        return [], [f"{filename} sheet '{ws.title}': kolom 'Toko' tidak ditemukan di baris 2."]
    hm = [i for i, h in enumerate(hdr) if h.lower() == "homeless media"]
    ti, li = lower["toko"], lower.get("link")
    key = f"PRT-{tayang.isoformat()}-{re.sub(r'[^a-z0-9]+', '-', nama.lower()).strip('-')}"[:60]
    toko = None
    for ri, r in enumerate(data[2:], start=3):
        r = list(r) + [None] * (len(hdr) - len(r))
        if r[ti]:
            toko = str(r[ti]).strip()
        bud = _num(r[lower["budget"]]) if "budget" in lower else None
        users = [_uname(r[i]) for i in hm]
        u = next((x for x in reversed(users) if x), None)
        if not u or not toko or bud is None:
            continue
        link = str(r[li]).strip() if li is not None and r[li] else ""
        cancel = link.lower() == "cancel"
        ig = [_clean_url(link)] if "instagram.com" in link else []
        other = [link] if link.lower().startswith("http") and not ig else []
        rows.append({
            "key": key, "tipe": "portal", "file": f"{filename} · {ws.title}", "baris": ri, "toko": toko,
            "store_id": matcher.match(toko), "username": u, "followers": None, "er": None, "avg_views": None,
            "niche": None, "deliverable": _deliv(r[lower["type konten"]]) if "type konten" in lower else "reels",
            "label": "Portal Promo", "budget": bud, "cancel": cancel, "ig": ig, "other": other,
            "tanggal": None if cancel else (next((d for d in map(ig_date, ig) if d), None) or tayang),
            "camp_nama": f"Portal — {nama} · tayang {tayang:%d/%m}", "camp_mulai": tayang, "camp_selesai": tayang, "snapshot": None,
            "backup": [x for x in users[:-1] if x and x != u],
            "hook": str(r[lower["hook cover"]]).strip() if "hook cover" in lower and r[lower["hook cover"]] else None,
        })
    if not rows:
        issues.append(f"{filename} sheet '{ws.title}': tidak ada baris berisi akun & budget.")
    return rows, issues


def parse_files(files: list[tuple[str, bytes]], stores: list[dict]) -> tuple[list[dict], list[str]]:
    """files = [(nama_file, isi_bytes)]. Return (baris, catatan)."""
    import openpyxl
    matcher = StoreMatcher(stores)
    rows, issues = [], []
    for name, content in files:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=False)
        except Exception as e:  # noqa: BLE001
            issues.append(f"{name}: tidak bisa dibuka sebagai Excel ({e}).")
            continue
        portal = [ws for ws in wb.worksheets if str(ws.cell(1, 1).value or "").strip().upper().startswith("LIST PORTAL")]
        if portal:
            for ws in portal:
                r, i = parse_portal_sheet(ws, name, matcher)
                rows += r
                issues += i
        else:
            r, i = parse_kol(wb.active, name, matcher)
            rows += r
            issues += i
    return rows, issues


def summarize(rows: list[dict]) -> list[dict]:
    out = defaultdict(lambda: {"baris": 0, "cancel": 0, "budget": 0.0, "tanpa_link": 0, "toko_belum_cocok": 0})
    for r in rows:
        s = out[r["key"]]
        s.update({"campaign": r["camp_nama"], "jenis": "KOL" if r["tipe"] == "kol" else "Portal", "mulai": r["camp_mulai"]})
        s["baris"] += 1
        s["cancel"] += int(r["cancel"])
        s["budget"] += 0 if r["cancel"] else (r["budget"] or 0)
        s["tanpa_link"] += int(not r["cancel"] and not r["ig"] and not r["other"])
        s["toko_belum_cocok"] += int(not r["store_id"])
    return sorted(({"key": k, **v} for k, v in out.items()), key=lambda x: (x["mulai"], x["key"]))


# ---------------------------------------------------------------- simpan
def _next_no(cur, table: str, col: str, prefix: str) -> str:
    r = cur.execute(f"SELECT {col} AS no FROM {table} WHERE {col} LIKE %s ORDER BY {col} DESC LIMIT 1",
                    (f"{prefix}-%",)).fetchone()
    n = int(r["no"].rsplit("-", 1)[1]) + 1 if r else 1
    return f"{prefix}-{n:03d}"


def _values(cur, sql: str, rows: list[tuple], fetch: bool = False):
    """execute_values dalam satu round-trip (penting: server app & database bisa berjauhan)."""
    from psycopg2.extras import execute_values
    if not rows:
        return []
    out = execute_values(cur.cur, sql, rows, page_size=1000, fetch=fetch)
    return [dict(r) for r in out] if fetch else []


def load(rows: list[dict], user_id: int, store_zone: dict[int, int]) -> dict:
    """Simpan ke database dalam satu transaksi. Baris tanpa store_id harus sudah dipetakan sebelumnya."""
    from . import db
    if any(not r["store_id"] for r in rows):
        raise ValueError("Masih ada toko yang belum dipetakan ke master.")
    for r in rows:
        r["norm"] = username_norm(r["username"])
    camps = defaultdict(list)
    for r in rows:
        camps[r["key"]].append(r)
    stat = defaultdict(int)
    with db.transaction() as cur:
        # ---- akun (cari yang sudah ada sekaligus, sisanya insert batch)
        norms = sorted({r["norm"] for r in rows})
        portal = {r["norm"] for r in rows if r["tipe"] == "portal"}
        niche = {}
        for r in sorted(rows, key=lambda r: r["tanggal"] or r["camp_mulai"]):
            if r.get("niche"):
                niche[r["norm"]] = r["niche"]
        ex = cur.execute("""SELECT id, tipe, username_norm FROM kol_accounts
                            WHERE lower(platform)='instagram' AND username_norm = ANY(%s)""", (norms,)).fetchall()
        kid = {e["username_norm"]: e["id"] for e in ex}
        up = [e["id"] for e in ex if e["username_norm"] in portal and e["tipe"] != "portal"]
        if up:
            cur.execute("UPDATE kol_accounts SET tipe='portal', updated_at=NOW() WHERE id = ANY(%s)", (up,))
        new = []
        for n in norms:
            if n not in kid:
                kat = NICHE.get((niche.get(n) or "").lower(), "general")
                new.append(("portal" if n in portal else "kol", "Instagram", n, "@" + n, n, f"https://www.instagram.com/{n}/",
                            kat, kat, niche.get(n), "impor_excel"))
        for r in _values(cur, """INSERT INTO kol_accounts (tipe, platform, nama, username, username_norm, link, kategori,
                                 kategori_otomatis, niche, sumber) VALUES %s RETURNING id, username_norm""", new, fetch=True):
            kid[r["username_norm"]] = r["id"]
        stat["akun_baru"] = len(new)
        # ---- metrik snapshot (follower/ER/avg views per bulan)
        snap = {}
        for r in rows:
            if r["snapshot"] and (r["followers"] or r["er"] or r["avg_views"]):
                snap.setdefault((kid[r["norm"]], r["snapshot"]), (r["followers"], r["avg_views"], r["er"]))
        _values(cur, """INSERT INTO kol_metrics_snapshot (kol_id, tanggal, follower, avg_views, er) VALUES %s
                        ON CONFLICT (kol_id, tanggal) DO UPDATE SET follower=COALESCE(EXCLUDED.follower, kol_metrics_snapshot.follower),
                        avg_views=COALESCE(EXCLUDED.avg_views, kol_metrics_snapshot.avg_views),
                        er=COALESCE(EXCLUDED.er, kol_metrics_snapshot.er)""",
                [(k, d, *v) for (k, d), v in snap.items()])
        # ---- campaign (impor ulang = ganti)
        keys = sorted(camps, key=lambda k: (camps[k][0]["camp_mulai"], k))
        olds = cur.execute("SELECT id FROM campaigns WHERE impor_key = ANY(%s)", (keys,)).fetchall()
        if olds:
            cur.execute("DELETE FROM campaigns WHERE id = ANY(%s)", ([o["id"] for o in olds],))
            stat["campaign_diganti"] = len(olds)
        posts = []
        for key in keys:
            rs = camps[key]
            r0 = rs[0]
            ok = [r for r in rs if not r["cancel"]]
            dates = [r["tanggal"] for r in rs if r["tanggal"]]
            mulai = r0["camp_mulai"]
            selesai = max([r0["camp_selesai"]] + dates)
            sids = sorted({r["store_id"] for r in rs})
            zids = sorted({store_zone[s] for s in sids if s in store_zone})
            status = "Selesai" if all(r["ig"] or r["other"] for r in ok) else "Disetujui"
            labels = sorted({r["label"] for r in rs})
            tujuan = (f"Endorse KOL per toko ({', '.join(labels)})" if r0["tipe"] == "kol"
                      else f"Promo lewat portal / homeless media — tayang {mulai:%d/%m/%Y}") + f" · impor {r0['file'].split(' · ')[0]}"
            y = mulai.year
            cno = _next_no(cur, "campaigns", "no_campaign", f"CMP-{y}")
            cid = cur.execute("""INSERT INTO campaigns (no_campaign, nama, tujuan, periode_mulai, periode_selesai, budget, jenis, slot,
                                                        target_zone_ids, target_store_ids, status, created_by, created_at, impor_key)
                                 VALUES (%s,%s,%s,%s,%s,%s,'grup',%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                              (cno, r0["camp_nama"], tujuan, mulai, selesai, sum(r["budget"] or 0 for r in ok), len(ok), zids, sids,
                               status, user_id, datetime.combine(mulai, datetime.min.time()), key)).fetchone()["id"]
            sno = _next_no(cur, "submissions", "no_pengajuan", f"PGJ-{y}")
            sid = cur.execute("""INSERT INTO submissions (no_pengajuan, campaign_id, jenis, status, submitted_by, submitted_at, created_at)
                                 VALUES (%s,%s,'grup',%s,%s,%s,%s) RETURNING id""",
                              (sno, cid, status, user_id, mulai, mulai)).fetchone()["id"]
            stat["campaign"] += 1
            vals = []
            for r in rs:
                harga = r["budget"] or 0
                cat = []
                if r["cancel"]:
                    cat.append("Cancel (sesuai file Excel)")
                if r["budget"] is None:
                    cat.append("Budget kosong di file Excel")
                if len(r["ig"]) > 1:
                    cat.append("IG lain: " + " , ".join(r["ig"][1:]))
                if r["other"] and r["ig"]:
                    cat.append("TikTok/lain: " + " , ".join(r["other"]))
                elif len(r["other"]) > 1:
                    cat.append("Link lain: " + " , ".join(r["other"][1:]))
                if r.get("backup"):
                    cat.append("Akun alternatif di file: " + ", ".join(r["backup"]))
                if r.get("hook"):
                    cat.append("Hook cover: " + r["hook"].replace("\n", " "))
                vals.append((sid, kid[r["norm"]], r["store_id"], r["deliverable"], r["tanggal"], harga, harga, not r["cancel"],
                             "tolak" if r["cancel"] else "setuju", " | ".join(cat) or None))
            ids = _values(cur, """INSERT INTO submission_items (submission_id, kol_id, store_id, deliverable, tanggal_posting, ratecard,
                                  harga_nego, dicentang, keputusan_item, catatan_item) VALUES %s RETURNING id""", vals, fetch=True)
            for r, it in zip(rs, ids):
                stat["baris"] += 1
                stat["cancel"] += int(r["cancel"])
                link = (r["ig"] or r["other"] or [None])[0]
                if link and not r["cancel"]:
                    plat = "Instagram" if "instagram.com" in link else "TikTok" if "tiktok" in link else "Lainnya"
                    jenis = {"reels": "Reels", "feed": "Feed Carousel"}.get(r["deliverable"], r["deliverable"])
                    posts.append((it["id"], kid[r["norm"]], link, plat,
                                  datetime.combine(r["tanggal"], datetime.min.time()).replace(hour=12) if r["tanggal"] else None,
                                  jenis, user_id))
        _values(cur, "INSERT INTO posts (item_id, kol_id, link, platform, tanggal_tayang, jenis_konten, updated_by) VALUES %s", posts)
        stat["link_tayang"] = len(posts)
        # ---- ratecard: catat bila harga per akun & deliverable berubah
        hist = defaultdict(list)
        for r in rows:
            if r["budget"] and not r["cancel"]:
                hist[(kid[r["norm"]], r["deliverable"])].append((r["tanggal"] or r["camp_mulai"], float(r["budget"])))
        have = defaultdict(list)
        for e in cur.execute("SELECT kol_id, deliverable, harga, berlaku_mulai FROM ratecards WHERE kol_id = ANY(%s)",
                             (sorted({k for k, _ in hist}),)).fetchall():
            have[(e["kol_id"], e["deliverable"])].append((e["berlaku_mulai"], float(e["harga"])))
        rc = []
        for (k, d), h in hist.items():
            known = set(have[(k, d)])
            first = min(x[0] for x in h)
            prev = [x for x in sorted(have[(k, d)]) if x[0] < first]
            last = prev[-1][1] if prev else None
            for tgl, harga in sorted(h):
                if harga != last:
                    if (tgl, harga) not in known:
                        rc.append((k, d, harga, tgl, "nego"))
                        known.add((tgl, harga))
                    last = harga
        _values(cur, "INSERT INTO ratecards (kol_id, deliverable, harga, berlaku_mulai, sumber) VALUES %s", rc)
        stat["ratecard"] = len(rc)
    return dict(stat)
