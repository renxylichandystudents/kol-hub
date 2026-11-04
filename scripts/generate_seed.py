"""Bangun migrations/002_seed.sql — master 61 toko + data contoh konsisten dengan mockup.

Jalankan:  python scripts/generate_seed.py
Data contoh dapat dihapus sebelum go-live lewat layar Akses & Role (Super User).
"""
from __future__ import annotations

import json
import math
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.master import ZONES, STORES  # noqa: E402

rng = random.Random(2026)
TODAY = date(2026, 11, 4)
START = TODAY - timedelta(days=181)
OUT: list[str] = []


def q(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int,)):
        return str(v)
    if isinstance(v, float):
        return repr(round(v, 4))
    if isinstance(v, (date, datetime)):
        return f"'{v.isoformat()}'"
    if isinstance(v, (dict, list)) and not (isinstance(v, list) and v and isinstance(v[0], str) and False):
        return "'" + json.dumps(v, ensure_ascii=False).replace("'", "''") + "'::jsonb"
    return "'" + str(v).replace("'", "''") + "'"


def arr(vals, typ="text"):
    if not vals:
        return f"'{{}}'::{typ}[]"
    if typ == "text":
        return "ARRAY[" + ",".join(q(v) for v in vals) + "]::text[]"
    return "ARRAY[" + ",".join(str(v) for v in vals) + f"]::{typ}[]"


def insert(table, cols, rows, chunk=500):
    for i in range(0, len(rows), chunk):
        part = rows[i:i + chunk]
        OUT.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n" +
                   ",\n".join("(" + ", ".join(r) + ")" for r in part) + ";")


# ------------------------------------------------------------------ master
insert("zones", ["id", "nama"], [[str(i + 1), q(z)] for i, z in enumerate(ZONES)])
zone_id = {z: i + 1 for i, z in enumerate(ZONES)}
store_rows = []
for i, s in enumerate(STORES):
    s["id"] = i + 1
    s["zone_id"] = zone_id[s["zona"]]
    s["base"] = rng.randint(620, 1550)
    store_rows.append([str(s["id"]), q(s["kode"]), q(s["nama"]), str(s["zone_id"]), q(s["kota"]),
                       q(s["lat"]), q(s["lon"]), arr(s["alias"]), str(int(s["base"] * 7 * 1.06))])
insert("stores", ["id", "kode", "nama", "zone_id", "kota", "lat", "lon", "alias", "target_kunjungan_mingguan"], store_rows)
S = {s["short"]: s for s in STORES}
# angka mockup
S["Medan"]["base"] = 1030
S["Semarang"]["base"] = 830
S["Jati Makmur"]["base"] = 1100
S["Pekanbaru"]["base"] = 720
S["Garut"]["base"] = 400
S["Cibubur"]["base"] = 1150

# pengguna sistem untuk data contoh (tidak bisa login)
insert("users", ["id", "nama", "email", "password_hash", "must_change_password", "is_active"],
       [["1", q("Data Contoh (sistem)"), q("sistem@kolhub.local"), q("!disabled"), "FALSE", "FALSE"]])

insert("tax_rules", ["jenis", "keterangan", "tarif", "dasar", "tarif_tanpa_npwp", "berlaku_mulai"], [
    [q("PPh21"), q("KOL perorangan bukan pegawai: tarif Pasal 17 × 50% bruto (lapis pertama 5%)"), "0.05", "0.5", "0.06", q(date(2024, 1, 1))],
    [q("PPh23"), q("Badan usaha / portal berbadan hukum: 2% × bruto jasa"), "0.02", "1.0", "0.04", q(date(2024, 1, 1))],
])

# ------------------------------------------------------------------ KOL & portal
CITIES_BY_ZONE = {}
for s in STORES:
    CITIES_BY_ZONE.setdefault(s["zona"], [])
    if s["kota"] not in CITIES_BY_ZONE[s["zona"]]:
        CITIES_BY_ZONE[s["zona"]].append(s["kota"])

BIO = {
    "lifestyle": ["Inspirasi interior & renovasi rumah minimalis", "Home tour, DIY dekorasi rumah keluarga",
                  "Renovasi hemat ala tukang muda", "Daily vlog keluarga muda & rumah impian",
                  "Desain taman & teras rumah tropis", "Before after renovasi kamar mandi"],
    "culinary": ["Review makanan & resep dapur rumahan", "Kuliner hits dan jajan murah", "Masak simpel di dapur kecil",
                 "Foodie keliling kota, review makanan jujur"],
    "comedy": ["Sketsa komedi keluarga receh", "Konten lucu sehari-hari, parodi tukang", "Komedi bapak-bapak & prank ringan"],
    "beauty": ["Makeup & skincare harian hijab", "Beauty vlog & fashion kasual", "Review kosmetik lokal glowing"],
    "general": ["Info promo & tips belanja hemat", "Konten edukasi umum & tips harian", "Review apa saja yang lagi viral"],
}

KOL_SPECS = [
    # username, nama, platform, kategori, zona utama, follower
    ("rumahminimalis.id", "Rumah Minimalis ID", "Instagram", "lifestyle", "Banten", 412_000),
    ("serpong.homes", "Serpong Homes", "Instagram", "lifestyle", "Banten", 186_000),
    ("renovkm", "Renov KM", "TikTok", "lifestyle", "Jakarta", 655_000),
    ("dapur5juta", "Dapur 5 Juta", "TikTok", "culinary", "Bekasi", 540_000),
    ("bapakbapak.diy", "Bapak Bapak DIY", "TikTok", "comedy", "Bekasi", 302_000),
    ("tukangmuda", "Tukang Muda", "TikTok", "lifestyle", "Jawa Barat", 228_000),
    ("medanrumahku", "Medan Rumahku", "Instagram", "lifestyle", "Sumatera", 98_000),
    ("kulinermedan", "Kuliner Medan", "TikTok", "culinary", "Sumatera", 265_000),
    ("palembanghits", "Palembang Hits", "Instagram", "general", "Sumatera", 143_000),
    ("lampungdaily", "Lampung Daily", "TikTok", "general", "Sumatera", 87_000),
    ("balihomedesign", "Bali Home Design", "Instagram", "lifestyle", "Bali - Lombok", 121_000),
    ("lombokfoodie", "Lombok Foodie", "TikTok", "culinary", "Bali - Lombok", 76_000),
    ("jaksel.homie", "Jaksel Homie", "Instagram", "lifestyle", "Jakarta", 210_000),
    ("komedirumahan", "Komedi Rumahan", "TikTok", "comedy", "Jakarta", 890_000),
    ("cantikhemat", "Cantik Hemat", "Instagram", "beauty", "Jakarta", 320_000),
    ("bekasiterkini.diy", "Bekasi DIY", "Instagram", "lifestyle", "Bekasi", 64_000),
    ("emakbekasi", "Emak Bekasi", "TikTok", "comedy", "Bekasi", 178_000),
    ("bintaro.family", "Bintaro Family", "Instagram", "lifestyle", "Banten", 92_000),
    ("tangerangjajan", "Tangerang Jajan", "TikTok", "culinary", "Banten", 233_000),
    ("bandung.interior", "Bandung Interior", "Instagram", "lifestyle", "Jawa Barat", 157_000),
    ("depok.mamah", "Depok Mamah", "TikTok", "lifestyle", "Jawa Barat", 134_000),
    ("bogorjajan", "Bogor Jajan", "Instagram", "culinary", "Jawa Barat", 112_000),
    ("karawang.lucu", "Karawang Lucu", "TikTok", "comedy", "Jawa Barat", 96_000),
    ("glowingbandung", "Glowing Bandung", "Instagram", "beauty", "Jawa Barat", 205_000),
    ("surabaya.rumah", "Surabaya Rumah", "Instagram", "lifestyle", "Jawa Timur", 118_000),
    ("arekmasak", "Arek Masak", "TikTok", "culinary", "Jawa Timur", 301_000),
    ("malanghomey", "Malang Homey", "Instagram", "lifestyle", "Jawa Timur", 73_000),
    ("semarangan.diy", "Semarangan DIY", "TikTok", "lifestyle", "Jawa Tengah", 81_000),
    ("jogjaomah", "Jogja Omah", "Instagram", "lifestyle", "Jawa Tengah", 166_000),
    ("solokuliner", "Solo Kuliner", "TikTok", "culinary", "Jawa Tengah", 142_000),
    ("makassar.rumah", "Makassar Rumah", "Instagram", "lifestyle", "Sulawesi", 69_000),
    ("daengkocak", "Daeng Kocak", "TikTok", "comedy", "Sulawesi", 154_000),
    ("balikpapan.home", "Balikpapan Home", "Instagram", "lifestyle", "Kalimantan", 58_000),
    ("banjar.kuliner", "Banjar Kuliner", "TikTok", "culinary", "Kalimantan", 88_000),
    ("viral.serbaserbi", "Viral Serba Serbi", "TikTok", "general", "Jakarta", 1_240_000),
    ("hematbelanja", "Hemat Belanja", "Instagram", "general", "Bekasi", 276_000),
    ("rumahkita.tv", "Rumah Kita TV", "TikTok", "lifestyle", "Banten", 498_000),
    ("ibuk.renov", "Ibuk Renov", "Instagram", "lifestyle", "Jakarta", 47_000),
    ("cat.warnawarni", "Cat Warna Warni", "TikTok", "lifestyle", "Jawa Barat", 39_000),
    ("ngakak.tukang", "Ngakak Tukang", "TikTok", "comedy", "Banten", 610_000),
    ("pekanbaru.kini", "Pekanbaru Kini", "Instagram", "general", "Sumatera", 71_000),
    ("garut.kreatif", "Garut Kreatif", "Instagram", "general", "Jawa Barat", 33_000),
]
PORTAL_SPECS = [
    ("bekasiterkini", "Bekasi Terkini", "Instagram", "Bekasi", 612_000),
    ("infotangerang", "Info Tangerang", "Instagram", "Banten", 835_000),
    ("medan.update", "Medan Update", "Instagram", "Sumatera", 455_000),
    ("jakartainfo", "Jakarta Info", "Portal News", "Jakarta", 0),
    ("depokpos", "Depok Pos", "Portal News", "Jawa Barat", 0),
    ("surabayakini", "Surabaya Kini", "Instagram", "Jawa Timur", 398_000),
    ("semarangupdate", "Semarang Update", "Instagram", "Jawa Tengah", 287_000),
    ("makassarinfo", "Makassar Info", "Instagram", "Sulawesi", 342_000),
    ("balikpapanpos", "Balikpapan Pos", "Portal News", "Kalimantan", 0),
    ("baliexpress.id", "Bali Express", "Portal News", "Bali - Lombok", 0),
    ("garutnews", "Garut News", "Instagram", "Jawa Barat", 121_000),
    ("pekanbaruterkini", "Pekanbaru Terkini", "Instagram", "Sumatera", 176_000),
]

kols = []
for un, nama, plat, kat, zona, fol in KOL_SPECS:
    kols.append({"tipe": "kol", "username": un, "nama": nama, "platform": plat, "kategori": kat, "zona": zona,
                 "follower": fol, "badan_hukum": False})
for un, nama, plat, zona, fol in PORTAL_SPECS:
    kols.append({"tipe": "portal", "username": un, "nama": nama, "platform": plat, "kategori": "general", "zona": zona,
                 "follower": fol, "badan_hukum": True})

kol_rows, snap_rows, rc_rows = [], [], []
for i, k in enumerate(kols, start=1):
    k["id"] = i
    cities = CITIES_BY_ZONE[k["zona"]]
    main = rng.choice(cities)
    if k["username"] in ("rumahminimalis.id", "serpong.homes", "rumahkita.tv", "bintaro.family"):
        main = "Tangerang Selatan"
    if k["username"] in ("medanrumahku", "kulinermedan", "medan.update"):
        main = "Medan"
    if k["username"] in ("semarangan.diy", "semarangupdate"):
        main = "Semarang"
    k["kota"] = main
    local = rng.uniform(0.35, 0.68)
    aud = {main: round(local, 2)}
    others = [c for c in cities if c != main] + ["Jakarta Selatan", "Bekasi", "Bandung", "Surabaya"]
    rest = 1 - local
    for c in rng.sample(others, k=min(3, len(others))):
        share = round(rest * rng.uniform(0.2, 0.5), 2)
        if c in aud:
            continue
        aud[c] = share
        rest -= share
    aud["Lainnya"] = round(max(rest, 0), 2)
    k["audiens"] = aud
    if k["platform"] == "Portal News":
        k["avg_views"] = rng.randint(18_000, 65_000)
        k["er"] = rng.uniform(0.6, 1.8)
    else:
        ratio = rng.uniform(0.18, 0.75) if k["platform"] == "TikTok" else rng.uniform(0.12, 0.45)
        k["avg_views"] = int(k["follower"] * ratio)
        base_er = {"comedy": 6.5, "beauty": 4.2, "lifestyle": 4.8, "culinary": 5.6, "general": 3.4}[k["kategori"]]
        k["er"] = max(0.8, rng.gauss(base_er, 1.3))
    if k["username"] == "rumahminimalis.id":
        k["avg_views"] = 168_000
    bio = rng.choice(BIO[k["kategori"]]) if k["tipe"] == "kol" else f"Portal berita & info seputar {k['zona']}"
    link = {"Instagram": f"https://instagram.com/{k['username']}", "TikTok": f"https://www.tiktok.com/@{k['username']}",
            "Portal News": f"https://{k['username'].replace('.', '')}.com"}[k["platform"]]
    status, alasan = "aktif", None
    if k["username"] == "garut.kreatif":
        status, alasan = "diblokir", "Bukti tayang dua kali tidak dikirim & insight tidak sesuai (selisih > 30%)"
    kol_rows.append([str(i), q(k["tipe"]), q(k["platform"]), q(k["nama"]), q("@" + k["username"]), q(k["username"]),
                     q(link), q(k["kategori"]), q(k["kategori"]), q(bio.split(",")[0].lower()), q(bio), q(main),
                     q(k["badan_hukum"]), q(rng.random() > 0.08), q(f"+62 81{rng.randint(10000000, 99999999)}"),
                     q(status), q(alasan), q("seed")])
    for m in range(6):
        d = (TODAY.replace(day=1) - timedelta(days=30 * m)).replace(day=1)
        growth = (1 - 0.025 * m)
        snap_rows.append([str(i), q(d), str(int(k["follower"] * growth)), str(int(k["avg_views"] * (1 - 0.04 * m) * rng.uniform(0.92, 1.08))),
                          q(round(k["er"] * rng.uniform(0.9, 1.1), 2)), q(aud)])
    # ratecard: harga awal mendekati CPM wajar per kategori
    cpm_target = {"comedy": 52_000, "beauty": 70_000, "lifestyle": 64_000, "culinary": 58_000, "general": 45_000}[k["kategori"]]
    if k["tipe"] == "portal":
        cpm_target = 80_000
    fair = cpm_target * k["avg_views"] / 1000
    deliv = "artikel" if k["platform"] == "Portal News" else ("reels" if k["platform"] == "Instagram" else "video")
    p0 = round(fair * rng.uniform(0.7, 1.05) / 100_000) * 100_000
    p1 = round(p0 * rng.uniform(1.0, 1.18) / 100_000) * 100_000
    if k["username"] == "rumahminimalis.id":
        p0, p1 = 5_000_000, 12_500_000
    if k["username"] in ("komedirumahan", "viral.serbaserbi"):
        p1 = round(p0 * 1.6 / 100_000) * 100_000
    k["harga"] = max(p1, 500_000)
    k["deliverable"] = deliv
    k["cpm_target"] = cpm_target
    rc_rows.append([str(i), q(deliv), str(max(p0, 500_000)), q(date(2025, 6, 1)), q("kol")])
    rc_rows.append([str(i), q(deliv), str(k["harga"]), q(date(2026, 4, 1)), q("kol")])
    if deliv != "artikel":
        rc_rows.append([str(i), q("story"), str(round(k["harga"] * 0.3 / 100_000) * 100_000 or 300_000), q(date(2026, 4, 1)), q("kol")])

insert("kol_accounts", ["id", "tipe", "platform", "nama", "username", "username_norm", "link", "kategori", "kategori_otomatis",
                        "niche", "bio", "kota_domisili", "badan_hukum", "punya_npwp", "kontak", "status", "alasan_blokir", "sumber"], kol_rows)
OUT.append("UPDATE kol_accounts SET blocked_by = 1 WHERE status = 'diblokir';")
insert("kol_metrics_snapshot", ["kol_id", "tanggal", "follower", "avg_views", "er", "audiens_kota_json"], snap_rows)
insert("ratecards", ["kol_id", "deliverable", "harga", "berlaku_mulai", "sumber"], rc_rows)
K = {k["username"]: k for k in kols}

# ------------------------------------------------------------------ promo offline
events = [
    ("Gajian Sale Juni", None, None, date(2026, 6, 25), date(2026, 6, 28)),
    ("Promo Kemerdekaan", None, None, date(2026, 8, 15), date(2026, 8, 18)),
    ("Gajian Sale September", None, None, date(2026, 9, 25), date(2026, 9, 28)),
    ("Anniversary Mitra10 Cibubur", S["Cibubur"]["id"], None, date(2026, 7, 10), date(2026, 7, 12)),
    ("Grand Re-opening Garut", S["Garut"]["id"], None, date(2026, 6, 12), date(2026, 6, 14)),
    ("Pameran Keramik Jawa Timur", None, zone_id["Jawa Timur"], date(2026, 9, 5), date(2026, 9, 8)),
    ("Promo 11.11 Renovasi Hemat", None, None, date(2026, 11, 8), date(2026, 11, 12)),
    ("Year End Sale 12.12", None, None, date(2026, 12, 10), date(2026, 12, 14)),
    ("Festival Cat Bandung", S["TAV Bandung"]["id"], None, date(2026, 11, 20), date(2026, 11, 23)),
]
insert("promo_offline_events", ["nama", "store_id", "zone_id", "mulai", "selesai"],
       [[q(n), q(sid), q(zid), q(a), q(b)] for n, sid, zid, a, b in events])


def event_stores(sid, zid):
    if sid:
        return {sid}
    if zid:
        return {s["id"] for s in STORES if s["zone_id"] == zid}
    return {s["id"] for s in STORES}


event_days = {}
for n, sid, zid, a, b in events:
    for sidx in event_stores(sid, zid):
        d = a
        while d <= b:
            event_days[(sidx, d)] = n
            d += timedelta(days=1)

# ------------------------------------------------------------------ campaign historis
camp_rows, sub_rows, item_rows, appr_rows, ro_rows, pay_rows, post_rows, met_rows = [], [], [], [], [], [], [], []
lifts = {}  # (store_id, start_date) -> lift
counters = {"camp": 0, "sub": 0, "item": 0, "ro": 0, "pay": 0, "post": 0, "inv": 0}

HIST = [
    # nama, mulai, budget, [(username, store short, lift)]
    ("Promo Gajian Juni", date(2026, 6, 20), 60_000_000, [("serpong.homes", "Gading Serpong", 0.14), ("bintaro.family", "Bintaro Jaya", 0.11),
                                                         ("dapur5juta", "Kalimalang Baru", 0.17), ("bekasiterkini", "Cibubur", 0.09),
                                                         ("medan.update", "Medan", 0.12)]),
    ("Renovasi Tengah Tahun", date(2026, 7, 14), 85_000_000, [("renovkm", "Pondok Bambu", 0.12), ("tukangmuda", "Depok", 0.10),
                                                             ("bandung.interior", "TAV Bandung", 0.13), ("jaksel.homie", "Fatmawati", 0.08),
                                                             ("infotangerang", "Q-Big", 0.10), ("arekmasak", "Kedungdoro", 0.11)]),
    ("Merdeka Belanja", date(2026, 8, 8), 70_000_000, [("komedirumahan", "Daan Mogot", 0.06), ("emakbekasi", "Jati Makmur", 0.09),
                                                      ("depok.mamah", "Cinere", 0.10), ("surabaya.rumah", "Ahmad Yani Surabaya", 0.12),
                                                      ("jogjaomah", "Yogyakarta", 0.13), ("makassar.rumah", "Tallasa City Makassar", 0.08)]),
    ("Back to Home September", date(2026, 9, 1), 78_000_000, [("rumahkita.tv", "Pamulang", 0.11), ("bogorjajan", "Iskandar Bogor", 0.07),
                                                             ("balihomedesign", "Bypass Ngurah Rai", 0.12), ("daengkocak", "Perintis Makassar", 0.05),
                                                             ("kulinermedan", "Pekanbaru", 0.06), ("hematbelanja", "Kota Harapan Indah", 0.09)]),
    ("Cat & Warna Oktober", date(2026, 10, 6), 96_000_000, [("cat.warnawarni", "Cibubur", 0.21), ("bapakbapak.diy", "Kalimalang Baru", 0.17),
                                                           ("rumahminimalis.id", "Gading Serpong", 0.15), ("ibuk.renov", "Pesanggrahan", 0.10),
                                                           ("surabayakini", "Wiyung", 0.09), ("solokuliner", "Solo Baru", 0.08),
                                                           ("banjar.kuliner", "Pal88 Banjarmasin", 0.07)]),
]
TUNGGAL = [("Request Toko: Jati Makmur", date(2026, 10, 14), ("bekasiterkini.diy", "Jati Makmur", 0.12)),
           ("Request Toko: Pekanbaru", date(2026, 8, 3), ("pekanbaruterkini", "Pekanbaru", 0.09))]


def next_no(key, prefix, width=3):
    counters[key] += 1
    return counters[key], f"{prefix}-2026-{counters[key]:0{width}d}"


def add_item(sub_id, k, store, post_date, harga, skor, status_final="setuju", pred=None):
    counters["item"] += 1
    iid = counters["item"]
    item_rows.append([str(iid), str(sub_id), str(k["id"]), str(store["id"]), q(k["deliverable"]), q(post_date),
                      str(k["harga"]), str(harga), q(skor), q(pred or {}), "TRUE", q(status_final)])
    return iid


def add_post(iid, k, post_date, telat=0, with_proof=True, views_factor=1.0):
    counters["post"] += 1
    pid = counters["post"]
    views = int(k["avg_views"] * rng.uniform(0.75, 1.3) * views_factor)
    er = k["er"] / 100 * rng.uniform(0.85, 1.15)
    inter = views * er
    likes = int(inter * 0.78); kom = int(inter * 0.09); share = int(inter * 0.08); save = int(inter * 0.05)
    jenis = rng.choice(["tutorial", "review", "before-after", "promo"])
    post_rows.append([str(pid), str(iid), str(k["id"]), q(f"{'https://www.tiktok.com/@' if k['platform'] == 'TikTok' else 'https://instagram.com/p/'}{k['username']}-{pid}"),
                      q(k["platform"]), q(datetime.combine(post_date, datetime.min.time()) + timedelta(hours=rng.choice([11, 12, 18, 19, 20]))),
                      q(jenis), q(rng.randint(25, 90)), q("bukti.png" if with_proof else None), q("insight.png" if with_proof else None), str(telat)])
    if with_proof:
        met_rows.append([str(pid), str(views), str(likes), str(kom), str(share), str(save), q("api"), q(post_date + timedelta(days=7))])
        met_rows.append([str(pid), str(int(views * rng.choice([1.0, 1.0, 1.02, 0.93]))), str(likes), str(kom), str(share), str(save), q("ocr"), q(post_date + timedelta(days=7))])
    return pid, views


def score_guess(k):
    return round(min(97, 45 + k["er"] * 4 + math.log10(max(k["avg_views"], 1000)) * 3 + rng.uniform(-6, 6)), 1)


def add_payment(ro_id, iid, k, nominal, status, created):
    counters["pay"] += 1
    counters["inv"] += 1
    if k["badan_hukum"]:
        jenis, pajak = "PPh23", round(nominal * 0.02)
    else:
        jenis, pajak = "PPh21", round(nominal * 0.05 * 0.5)
    alasan = "Bukti tayang / insight belum lengkap" if status == "tertahan" else None
    paid = q(datetime.combine(created + timedelta(days=rng.randint(10, 25)), datetime.min.time())) if status == "lunas" else "NULL"
    pay_rows.append([str(ro_id), str(iid), q(f"INV/KOL/2026/{counters['inv']:04d}"), str(nominal), q(jenis), str(pajak), q(status),
                     q(alasan), paid, q(datetime.combine(created, datetime.min.time()))])


def approvals_for(sub_id, start, rev=0):
    appr_rows.append([str(sub_id), str(rev), "1", "1", q("setuju"), q("Sesuai budget & kebutuhan toko"), q(datetime.combine(start - timedelta(days=9), datetime.min.time()))])
    appr_rows.append([str(sub_id), str(rev), "2", "1", q("setuju"), q(None), q(datetime.combine(start - timedelta(days=8), datetime.min.time()))])


for nama, mulai, budget, items in HIST:
    cid, cno = next_no("camp", "CMP")
    stores_in = [S[s]["id"] for _, s, _ in items]
    zones_in = sorted({S[s]["zone_id"] for _, s, _ in items})
    is_last = nama.startswith("Cat & Warna")
    camp_status = "Di Finance" if is_last else "Selesai"
    camp_rows.append([str(cid), q(cno), q(nama), q("Mendorong kunjungan toko lewat konten KOL & portal lokal"), q(mulai),
                      q(mulai + timedelta(days=21)), str(budget), q("grup"), str(len(items)), arr(zones_in, "int"), arr(stores_in, "int"),
                      q(camp_status), "1", q(datetime.combine(mulai - timedelta(days=14), datetime.min.time()))])
    sid_, sno = next_no("sub", "PGJ")
    sub_status = "Di Finance" if is_last else "Lunas"
    sub_rows.append([str(sid_), q(sno), str(cid), q("grup"), "0", q(sub_status), "1", q(datetime.combine(mulai - timedelta(days=10), datetime.min.time())), "NULL"])
    approvals_for(sid_, mulai)
    rid, rno = next_no("ro", "RO")
    ro_rows.append([str(rid), q(rno), str(sid_), q("ditandatangani"), q(f"V{rng.randint(100000, 999999)}"), q(datetime.combine(mulai - timedelta(days=7), datetime.min.time()))])
    for j, (un, st, lift) in enumerate(items):
        k = K[un]
        store = S[st]
        post = mulai + timedelta(days=2 + j * 2)
        harga = max(500_000, int(round(k["harga"] * rng.uniform(0.85, 1.0) / 100_000) * 100_000))
        iid = add_item(sid_, k, store, post, harga, score_guess(k))
        if un == "cat.warnawarni":
            cibubur_oct = {"sub": sid_, "ro": rid, "harga_kol": harga, "created": mulai - timedelta(days=7)}
        telat = 1 if (un in ("daengkocak", "komedirumahan")) else 0
        proof = not (is_last and j >= 4)
        add_post(iid, k, post, telat=telat, with_proof=proof)
        lifts[(store["id"], post)] = lift
        if is_last:
            status = "siap" if proof else "tertahan"
            if j == 0:
                status = "diproses"
        else:
            status = "lunas"
            if nama == "Back to Home September" and j >= 2:
                status = "siap"
        add_payment(rid, iid, k, harga, status, mulai - timedelta(days=7))

# Cibubur Oktober: total biaya Rp 22,3 jt (contoh B.6 no. 8) → tambahkan portal ke item Cibubur
k = K["bekasiterkini"]
portal_price = 22_300_000 - cibubur_oct["harga_kol"]
iid = add_item(cibubur_oct["sub"], k, S["Cibubur"], date(2026, 10, 9), portal_price, score_guess(k))
add_post(iid, k, date(2026, 10, 9), with_proof=True)
add_payment(cibubur_oct["ro"], iid, k, portal_price, "siap", cibubur_oct["created"])

for nama, mulai, (un, st, lift) in TUNGGAL:
    sid_, sno = next_no("sub", "PGJ")
    sub_rows.append([str(sid_), q(sno), "NULL", q("tunggal"), "0", q("Lunas" if mulai.month < 10 else "Di Finance"), "1",
                     q(datetime.combine(mulai - timedelta(days=8), datetime.min.time())), "NULL"])
    approvals_for(sid_, mulai)
    rid, rno = next_no("ro", "RO")
    ro_rows.append([str(rid), q(rno), str(sid_), q("ditandatangani"), q(f"V{rng.randint(100000, 999999)}"), q(datetime.combine(mulai - timedelta(days=6), datetime.min.time()))])
    k = K[un]
    store = S[st]
    iid = add_item(sid_, k, store, mulai, k["harga"], score_guess(k))
    add_post(iid, k, mulai, with_proof=True)
    lifts[(store["id"], mulai)] = lift
    add_payment(rid, iid, k, k["harga"], "lunas" if mulai.month < 10 else "siap", mulai - timedelta(days=6))

# pembayaran lama tertunda > 30 hari: ubah sebagian 'siap' dari September
# (sudah di-set pada loop) — tambahkan juga baris tertahan agar total tertunda realistis

# ------------------------------------------------------------------ campaign berjalan
# (a) Draft Promo 11.11 — 7 dari 9 KOL terisi
cid, cno = next_no("camp", "CMP")
draft_cid = cid
draft_stores = ["Medan", "Semarang", "Jati Makmur", "Pekanbaru", "Gading Serpong", "Kalimalang Baru", "Fatmawati"]
camp_rows.append([str(cid), q(cno), q("Promo 11.11 — Renovasi Hemat"), q("Traffic toko saat promo 11.11, fokus toko dengan skor butuh tinggi"),
                  q(date(2026, 11, 8)), q(date(2026, 11, 22)), "120000000", q("grup"), "9",
                  arr(sorted({S[s]["zone_id"] for s in draft_stores}), "int"), arr([S[s]["id"] for s in draft_stores], "int"),
                  q("Draft"), "1", q(datetime(2026, 10, 28, 9, 0))])
sid_, sno = next_no("sub", "PGJ")
sub_rows.append([str(sid_), q(sno), str(cid), q("grup"), "0", q("Draft"), "NULL", "NULL", "NULL"])
for (un, st) in [("medan.update", "Medan"), ("medanrumahku", "Medan"), ("semarangupdate", "Semarang"),
                 ("emakbekasi", "Jati Makmur"), ("pekanbaruterkini", "Pekanbaru"), ("serpong.homes", "Gading Serpong"),
                 ("dapur5juta", "Kalimalang Baru")]:
    k = K[un]
    add_item(sid_, k, S[st], date(2026, 11, 9 + rng.randint(0, 4)), k["harga"], score_guess(k), status_final=None)
    item_rows[-1][-1] = "NULL"

# (b) Diajukan, menunggu Asisten Manager
cid, cno = next_no("camp", "CMP")
camp_rows.append([str(cid), q(cno), q("Renovasi Akhir Tahun"), q("Awareness renovasi sebelum libur akhir tahun"),
                  q(date(2026, 11, 25)), q(date(2026, 12, 15)), "90000000", q("grup"), "5",
                  arr([zone_id["Jawa Barat"], zone_id["Jawa Timur"]], "int"), arr([S["Depok"]["id"], S["Kebon Sari Malang"]["id"], S["Cibinong"]["id"]], "int"),
                  q("Diajukan"), "1", q(datetime(2026, 10, 30, 10, 0))])
sid_, sno = next_no("sub", "PGJ")
sub_rows.append([str(sid_), q(sno), str(cid), q("grup"), "0", q("Review Asisten Manager"), "1", q(datetime(2026, 11, 2, 15, 30)), "NULL"])
for (un, st) in [("tukangmuda", "Depok"), ("depok.mamah", "Cibinong"), ("malanghomey", "Kebon Sari Malang"), ("arekmasak", "Kebon Sari Malang"),
                 ("depokpos", "Depok")]:
    k = K[un]
    add_item(sid_, k, S[st], date(2026, 11, 26 + rng.randint(0, 5)), int(k["harga"] * 0.95), score_guess(k), status_final=None)
    item_rows[-1][-1] = "NULL"

# (c) Ditolak Manager → perlu revisi
cid, cno = next_no("camp", "CMP")
camp_rows.append([str(cid), q(cno), q("Dapur Impian Sulawesi"), q("Kitchen set & keramik dapur zona Sulawesi"),
                  q(date(2026, 11, 15)), q(date(2026, 11, 30)), "40000000", q("grup"), "3",
                  arr([zone_id["Sulawesi"]], "int"), arr([S["Pengayoman Makassar"]["id"], S["Kendari"]["id"]], "int"),
                  q("Ditolak"), "1", q(datetime(2026, 10, 20, 10, 0))])
sid_, sno = next_no("sub", "PGJ")
rej_sub = sid_
sub_rows.append([str(sid_), q(sno), str(cid), q("grup"), "0", q("Ditolak"), "1", q(datetime(2026, 10, 24, 11, 0)), "NULL"])
appr_rows.append([str(sid_), "0", "1", "1", q("setuju"), q(None), q(datetime(2026, 10, 25, 9, 0))])
appr_rows.append([str(sid_), "0", "2", "1", q("tolak"), q("Daeng Kocak telat tayang di campaign September; ganti dengan akun lifestyle"), q(datetime(2026, 10, 26, 14, 0))])
for (un, st, kep, cat) in [("makassar.rumah", "Pengayoman Makassar", "setuju", None),
                           ("daengkocak", "Pengayoman Makassar", "tolak", "Riwayat telat tayang; audiens tidak relevan untuk kitchen set"),
                           ("makassarinfo", "Kendari", "setuju", None)]:
    k = K[un]
    add_item(sid_, k, S[st], date(2026, 11, 16), k["harga"], score_guess(k), status_final=kep)
    item_rows[-1].append(q(cat))

# (d) Disetujui, Form RO dibuat menunggu tanda tangan
cid, cno = next_no("camp", "CMP")
camp_rows.append([str(cid), q(cno), q("Kamar Mandi Bersih November"), q("Sanitary & keramik kamar mandi Jabodetabek"),
                  q(date(2026, 11, 10)), q(date(2026, 11, 24)), "55000000", q("grup"), "3",
                  arr([zone_id["Jakarta"], zone_id["Banten"]], "int"), arr([S["Pondok Bambu"]["id"], S["Bintaro Jaya"]["id"]], "int"),
                  q("Form RO dibuat"), "1", q(datetime(2026, 10, 18, 10, 0))])
sid_, sno = next_no("sub", "PGJ")
ro_pending_sub = sid_
sub_rows.append([str(sid_), q(sno), str(cid), q("grup"), "0", q("Form RO dibuat"), "1", q(datetime(2026, 10, 22, 9, 0)), "NULL"])
approvals_for(sid_, date(2026, 11, 1))
rid, rno = next_no("ro", "RO")
ro_rows.append([str(rid), q(rno), str(sid_), q("dicetak"), q(f"V{rng.randint(100000, 999999)}"), q(datetime(2026, 10, 25, 9, 0))])
running_items = []
for (un, st, d) in [("renovkm", "Pondok Bambu", date(2026, 11, 11)), ("bintaro.family", "Bintaro Jaya", date(2026, 11, 13)),
                    ("ngakak.tukang", "Bintaro Jaya", date(2026, 11, 13))]:
    k = K[un]
    iid = add_item(sid_, k, S[st], d, int(k["harga"] * 0.9), score_guess(k))
    running_items.append((iid, k, d))

# fix kolom catatan_item untuk semua baris item
cols_item = ["id", "submission_id", "kol_id", "store_id", "deliverable", "tanggal_posting", "ratecard", "harga_nego",
             "skor_saat_itu", "prediksi_json", "dicentang", "keputusan_item", "catatan_item"]
for r in item_rows:
    if len(r) == 12:
        r.append("NULL")

insert("campaigns", ["id", "no_campaign", "nama", "tujuan", "periode_mulai", "periode_selesai", "budget", "jenis", "slot",
                     "target_zone_ids", "target_store_ids", "status", "created_by", "created_at"], camp_rows)
insert("submissions", ["id", "no_pengajuan", "campaign_id", "jenis", "revisi_ke", "status", "submitted_by", "submitted_at", "store_request_id"], sub_rows)
insert("submission_items", cols_item, item_rows)
insert("approvals", ["submission_id", "revisi_ke", "level", "approver_id", "keputusan", "catatan", "waktu"], appr_rows)
insert("ro_forms", ["id", "no_ro", "submission_id", "status", "kode_verifikasi", "created_at"], ro_rows)
insert("payments", ["ro_id", "item_id", "invoice_no", "nominal", "pajak_jenis", "pajak_nominal", "status", "alasan_tertahan", "paid_at", "created_at"], pay_rows)
insert("posts", ["id", "item_id", "kol_id", "link", "platform", "tanggal_tayang", "jenis_konten", "durasi_detik", "bukti_nama", "insight_nama", "telat_hari"], post_rows)
OUT.append("UPDATE posts SET bukti = convert_to('bukti-tayang-contoh', 'UTF8') WHERE bukti_nama IS NOT NULL;")
OUT.append("UPDATE posts SET insight = convert_to('insight-contoh', 'UTF8') WHERE insight_nama IS NOT NULL;")
OUT.append("UPDATE ro_forms SET scan_ttd = convert_to('scan-ro-contoh', 'UTF8'), scan_nama = 'scan_ro.pdf' WHERE status = 'ditandatangani';")
insert("post_metrics", ["post_id", "views", "likes", "komentar", "share", "save", "sumber", "diukur_pada"], met_rows)

# timeline produksi untuk campaign berjalan (d) + item Oktober yang belum lapor
STAGES = ["pitching", "brief", "take", "review", "posting", "lapor"]
pt_rows = []
for iid, k, d in running_items:
    t0 = d - timedelta(days=16)
    for n, tahap in enumerate(STAGES):
        start = t0 + timedelta(days=[0, 3, 7, 10, 16, 19][n])
        end = start + timedelta(days=[2, 3, 2, 4, 0, 2][n])
        status = "selesai" if end < TODAY else ("berjalan" if start <= TODAY else "belum")
        if k["username"] == "ngakak.tukang" and tahap == "take":
            status = "berjalan"  # terlambat
            end = TODAY - timedelta(days=2)
        pt_rows.append([str(iid), q(tahap), str(n + 1), q(start), q(end), q(status), "0"])
insert("production_tasks", ["item_id", "tahap", "urutan", "mulai", "selesai", "status", "revisi"], pt_rows)

# brief untuk item renovkm (9 bagian lengkap)
brief_item = running_items[0][0]
OUT.append(f"INSERT INTO briefs (id, item_id, campaign_id, judul, versi, status, updated_by) VALUES "
           f"(1, {brief_item}, {counters['camp']}, 'Brief @renovkm — Kamar Mandi Bersih November', 2, 'draft', 1);")
sections = [
    {"teks": "Mendorong kunjungan ke Mitra10 Pondok Bambu selama periode promo sanitary 10–24 Nov; target +900–1.500 kunjungan tambahan."},
    {"teks": "Renovasi kamar mandi tidak harus mahal: semua kebutuhan ada di Mitra10 Pondok Bambu, bisa dipasang sekalian."},
    {"teks": "Keluarga muda 25–40 tahun di Jakarta Timur & Bekasi barat yang sedang/akan renovasi rumah."},
    {"teks": "Mitra10 Pondok Bambu — promo kloset duduk & keramik 30x30 diskon hingga 25%, cicilan 0%."},
    {"scene": [{"no": 1, "durasi": "0–3 dtk", "visual": "Kamar mandi lama, keramik retak", "audio": "Hook: 'Kamar mandi begini masih dipakai?'"},
               {"no": 2, "durasi": "3–15 dtk", "visual": "Belanja di Mitra10 Pondok Bambu, pilih keramik & kloset", "audio": "Sebut promo & harga"},
               {"no": 3, "durasi": "15–35 dtk", "visual": "Proses pasang (timelapse)", "audio": "Tips memilih keramik anti licin"},
               {"no": 4, "durasi": "35–45 dtk", "visual": "Before–after", "audio": "CTA datang ke toko, sebut lokasi"}]},
    {"wajib": "Sebut 'Mitra10 Pondok Bambu', tampilkan papan promo, tag @mitra10official", "dilarang": "Menyebut merek kompetitor, klaim harga termurah tanpa syarat"},
    {"caption": "Renov kamar mandi 3 hari, budget aman! Semua belanja di @mitra10official Pondok Bambu 🔨", "hashtag": "#Mitra10 #RenovasiHemat #KamarMandiBersih"},
    {"deliverable": "1 video TikTok 30–45 dtk + 2 story", "timeline": "Draft 7 Nov · Revisi maks 2× · Tayang 11 Nov 19.00 · Laporan H+3"},
    {"referensi": "Konten 'TT · Renov KM' (612 rb views, Okt) — format tutorial < 45 dtk unggul 2,4×"},
]
for n, (judul, isi) in enumerate(zip(["Objective", "Pesan utama", "Target audiens", "Toko & promo", "Storyboard per scene",
                                      "Wajib & dilarang", "Caption & hashtag", "Deliverable & timeline", "Referensi"], sections), start=1):
    OUT.append(f"INSERT INTO brief_sections (brief_id, urutan, judul, isi_json) VALUES (1, {n}, {q(judul)}, {q(isi)});")

# ------------------------------------------------------------------ traffic offline
tr_rows = []
days = [START + timedelta(days=i) for i in range((TODAY - START).days)]  # sampai kemarin
for s in STORES:
    base = s["base"]
    trend_slope = rng.uniform(-0.00015, 0.0002)
    if s["short"] in ("Medan", "Semarang", "Jati Makmur", "Pekanbaru"):
        trend_slope = 0
    for i, d in enumerate(days):
        dow = d.weekday()
        season = 1.0 + (0.32 if dow == 5 else 0.42 if dow == 6 else -0.06 if dow in (1, 2) else 0)
        payday = 1.08 if d.day >= 25 or d.day <= 2 else 1.0
        v = base * season * payday * (1 + trend_slope * i)
        # penurunan 4 minggu terakhir untuk toko yang 'butuh KOL' (angka mockup)
        drop = {"Medan": 0.098, "Semarang": 0.062, "Jati Makmur": 0.04, "Pekanbaru": 0.031}.get(s["short"], 0)
        if drop and (TODAY - d).days <= 28:
            v *= (1 - drop)
        # dampak campaign: naik selama 14 hari sejak tayang (meluruh)
        for (sid, pd_), lift in lifts.items():
            if sid == s["id"] and 0 <= (d - pd_).days < 14:
                v *= 1 + lift * (1 - (d - pd_).days / 20)
        flag = None
        if (s["id"], d) in event_days:
            v *= 1.45
            flag = "event"
        v *= rng.gauss(1, 0.045)
        tr_rows.append([str(s["id"]), q(d), str(int(v)), str(int(v * rng.uniform(0.33, 0.41))), q(flag), "1"])
OUT.append("INSERT INTO uploads (id, jenis, nama_file, ringkasan_validasi_json, uploaded_by, uploaded_at) VALUES "
           f"(1, 'traffic', 'traffic_harian_mei-nov_2026.xlsx', {q({'baris_awal': len(tr_rows), 'baris_siap': len(tr_rows), 'toko': 61, 'catatan': 'data contoh'})}, 1, {q(datetime(2026, 11, 4, 7, 0))});")
insert("offline_traffic_daily", ["store_id", "tanggal", "kunjungan", "transaksi", "flag", "upload_id"], tr_rows, chunk=1000)

# ------------------------------------------------------------------ konten akun resmi
op_rows = []
for i in range(84):
    plat = "TikTok" if i % 2 else "Instagram"
    d = TODAY - timedelta(days=rng.randint(1, 180))
    jenis = rng.choice(["tutorial", "tutorial", "promo", "review", "behind the scene", "before-after"])
    dur = rng.randint(15, 44) if jenis == "tutorial" and rng.random() < 0.7 else rng.randint(30, 120)
    mult = 2.4 if (jenis == "tutorial" and dur < 45) else 1.0
    views = int(rng.uniform(40_000, 160_000) * mult * (1.6 if plat == "TikTok" else 1.0))
    er = rng.uniform(0.04, 0.08)
    inter = views * er
    judul = rng.choice(["Cat 11 warna", "Renov KM", "Dapur 5 juta", "Tips pilih keramik", "Lampu hemat energi",
                        "Kloset duduk vs jongkok", "Teras minimalis", "Promo gajian", "Pipa bocor? Ini caranya",
                        "Kitchen set modular", "Cat anti bocor", "Wallpaper kamar anak"])
    op_rows.append([q(plat), q(judul), q(jenis), str(dur), q(datetime.combine(d, datetime.min.time()) + timedelta(hours=rng.choice([9, 12, 17, 19, 20, 21]))),
                    str(views), str(int(inter * 0.8)), str(int(inter * 0.05)), str(int(inter * 0.1)), str(int(inter * 0.05))])
op_rows += [
    [q("TikTok"), q("Renov KM"), q("tutorial"), "41", q(datetime(2026, 10, 12, 19)), "612000", "41000", "1284", "3920", "2100"],
    [q("Instagram"), q("Cat 11 warna"), q("tutorial"), "38", q(datetime(2026, 10, 5, 12)), "298000", "18000", "642", "1105", "900"],
    [q("TikTok"), q("Dapur 5 juta"), q("before-after"), "52", q(datetime(2026, 10, 20, 20)), "254000", "16000", "910", "870", "640"],
]
insert("official_posts", ["platform", "judul", "jenis_konten", "durasi_detik", "tanggal", "views", "likes", "komentar", "share", "save"], op_rows)

# ------------------------------------------------------------------ topik & komentar
TOPICS = [
    ("Stok cat kosong", ["stok", "kosong", "habis", "cat"], "isu"),
    ("Antrean kasir panjang", ["kasir", "antre", "antri", "lama"], "isu"),
    ("Pengiriman terlambat", ["kirim", "pengiriman", "telat", "kurir", "ongkir"], "isu"),
    ("Pelayanan kurang ramah", ["jutek", "cuek", "pelayanan", "karyawan", "pegawai"], "isu"),
    ("Tanya harga & promo", ["berapa", "harga", "promo", "diskon", "cicilan"], "kebutuhan"),
    ("Jasa pasang / instalasi", ["pasang", "dipasang", "tukang", "jasa", "instalasi"], "kebutuhan"),
    ("Cabang & lokasi terdekat", ["cabang", "alamat", "lokasi", "buka"], "kebutuhan"),
    ("Ide renovasi kamar mandi", ["kamar mandi", "kloset", "keramik", "sanitary"], "peluang"),
    ("Inspirasi dapur & kitchen set", ["dapur", "kitchen set", "kompor", "wastafel"], "peluang"),
    ("Konten tutorial DIY", ["tutorial", "cara", "diy", "tips"], "peluang"),
    ("Warna cat favorit", ["warna", "sage", "putih", "abu"], "peluang"),
]
insert("topics", ["id", "label", "kata_kunci", "jenis"], [[str(i + 1), q(l), arr(k), q(j)] for i, (l, k, j) in enumerate(TOPICS)])

TPL = {
    "pos": ["Pelayanan di {toko} ramah banget, mantap 👍", "Kontennya inspiratif, jadi pengen renov dapur 😍",
            "Terima kasih admin, barang sudah sampai dengan aman 🙏", "Belanja di {toko} lengkap, harganya juga oke",
            "Tutorialnya jelas, langsung praktek di rumah 🔥", "Kloset duduknya bagus, pemasangan cepat", "Suka banget warna sage nya 🥰",
            "Promo gajian kemarin worth it parah", "Mitra10 {toko} parkirnya luas, nyaman"],
    "neg": ["Stok cat di {toko} kosong terus, kecewa 😡", "Kasir {toko} antre lama banget", "Pengiriman telat 3 hari, ga ada kabar",
            "Pegawai di {toko} jutek, ditanya malah cuek", "Barang datang rusak, komplain belum dibalas", "Mahal ya dibanding toko sebelah",
            "Gak ada stok keramik 60x60 di {toko}", "cat yang di video habis di semua cabang 😤"],
    "neu": ["Kak berapa harga kloset duduk yang di video?", "Bisa dipasang sekalian gak kak?", "Cabang terdekat dari {kota} di mana ya?",
            "Ada cicilan 0% gak min?", "Jam buka {toko} sampai jam berapa?", "Kitchen set modular ready di {toko}?",
            "Warna abu yang dipakai namanya apa kak?", "ada jasa tukang juga kah?"],
    "spam": ["Cek bio buat promo slot gacor!!!", "follow balik ya kak", "Jual followers murah wa.me/628123", "pinjol cair cepat cek bio"],
}
cm_rows = []
start_c = TODAY - timedelta(days=90)
for i in range(3200):
    plat = "TikTok" if rng.random() < 0.55 else "Instagram"
    d = start_c + timedelta(days=rng.randint(0, 89), hours=rng.randint(7, 23), minutes=rng.randint(0, 59))
    r = rng.random()
    p_pos = 0.58 if plat == "Instagram" else 0.51
    p_neg = 0.10 if plat == "Instagram" else 0.14
    kind = "pos" if r < p_pos else "neg" if r < p_pos + p_neg else "neu" if r < 0.96 else "spam"
    st = rng.choice(STORES)
    text = rng.choice(TPL[kind]).format(toko=st["short"], kota=st["kota"])
    if rng.random() < 0.25:
        text = text.replace("tidak", "gak").replace("banget", "bgt")
    cm_rows.append([q(plat), q(f"{plat[:2].upper()}-{rng.randint(1, 84)}"), q(f"u_{rng.getrandbits(40):010x}"), q(text), q(d)])
# lonjakan isu "stok cat kosong" di TikTok 3 hari terakhir
for i in range(140):
    st = rng.choice([S["Kalimalang Baru"], S["Cibubur"], S["Jati Makmur"], S["Pondok Bambu"]])
    d = datetime.combine(TODAY - timedelta(days=rng.randint(0, 2)), datetime.min.time()) + timedelta(hours=rng.randint(7, 23))
    text = rng.choice(["Stok cat di {toko} kosong terus, kecewa 😡", "cat yang di video habis di semua cabang 😤",
                       "Gak ada stok cat putih di {toko}", "Stok cat kosong lagi di {toko}?"]).format(toko=st["short"])
    cm_rows.append([q("TikTok"), q("TT-85"), q(f"u_{rng.getrandbits(40):010x}"), q(text), q(d)])
for i in range(12):  # bot: teks identik massal
    cm_rows.append([q("Instagram"), q("IG-3"), q(f"u_{rng.getrandbits(40):010x}"), q("Promo spesial cek bio sekarang juga"), q(datetime(2026, 10, 30, 10, i))])
insert("social_comments", ["platform", "post_ref", "author_hash", "teks_anonim", "waktu"], cm_rows, chunk=800)

# ------------------------------------------------------------------ request toko
req_rows = [
    [q("REQ-2026-001"), str(S["Semarang"]["id"]), str(K["semarangan.diy"]["id"]), "NULL", q("Butuh KOL lifestyle untuk menaikkan traffic akhir pekan"),
     q(date(2026, 11, 14)), q(date(2026, 11, 28)), str(K["semarangan.diy"]["harga"]), q("Diajukan"), q(None), q(datetime(2026, 11, 3, 10))],
    [q("REQ-2026-002"), str(S["Medan"]["id"]), "NULL",
     q({"nama": "Medan Kuliner Hits", "platform": "TikTok", "username": "@medankulinerhits", "link": "https://www.tiktok.com/@medankulinerhits",
        "follower": 184000, "kategori": "culinary", "kontak": "+62 812 6000 1234", "kota": "Medan",
        "bio": "Review kuliner & jajanan hits kota Medan"}),
     q("Portal/KOL lokal Medan untuk promo 11.11, traffic turun"), q(date(2026, 11, 8)), q(date(2026, 11, 20)), "6500000", q("Diajukan"), q(None), q(datetime(2026, 11, 2, 14))],
    [q("REQ-2026-003"), str(S["Jati Makmur"]["id"]), str(K["bekasiterkini.diy"]["id"]), "NULL", q("Request KOL DIY untuk promo cat"),
     q(date(2026, 10, 12)), q(date(2026, 10, 20)), str(K["bekasiterkini.diy"]["harga"]), q("Disetujui"), q("Diproses sebagai pengajuan tunggal PGJ-2026-006"), q(datetime(2026, 10, 1, 9))],
    [q("REQ-2026-004"), str(S["Garut"]["id"]), str(K["garut.kreatif"]["id"]), "NULL", q("KOL lokal Garut"),
     q(date(2026, 10, 1)), q(date(2026, 10, 10)), "1500000", q("Ditolak"), q("Akun dalam daftar blokir; gunakan portal Garut News"), q(datetime(2026, 9, 20, 9))],
]
insert("store_requests", ["no_request", "store_id", "kol_id", "data_akun_baru_json", "kebutuhan", "periode_mulai", "periode_selesai",
                          "ratecard", "status", "catatan", "created_at"], req_rows)

# ------------------------------------------------------------------ sequence
for t in ["zones", "stores", "users", "kol_accounts", "campaigns", "submissions", "submission_items", "ro_forms", "posts",
          "topics", "briefs", "uploads"]:
    OUT.append(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), (SELECT MAX(id) FROM {t}));")

header = ("-- Data awal: 61 toko / 10 zona (data Mitra10) + data contoh (angka & akun adalah contoh)\n"
          f"-- dihasilkan oleh scripts/generate_seed.py — tanggal acuan {TODAY.isoformat()}\n")
(ROOT / "migrations" / "002_seed.sql").write_text(header + "\n".join(OUT) + "\n", encoding="utf-8")
print("rows:", {"kol": len(kol_rows), "traffic": len(tr_rows), "komentar": len(cm_rows), "item": len(item_rows), "pay": len(pay_rows)})
