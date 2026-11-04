"""Unit test preprocessing (B.3), NLP (B.8) dan optimasi (B.6 no. 11, uji batasan B.10)."""
import random
from datetime import date

import numpy as np
import pandas as pd

from lib import nlp
from lib.master import STORES
from lib.optimize import Candidate, Constraints, check_constraints, solve
from lib.preprocess import (StoreMatcher, clean_traffic, dedupe_kols, flag_spam, guess_column_mapping,
                            normalize_text, normalize_username, ratecard_flags)

STORE_ROWS = [{**s, "id": i + 1} for i, s in enumerate(STORES)]


def test_store_matcher_alias_and_fuzzy():
    m = StoreMatcher(STORE_ROWS)
    assert m.match("MITRA 10 CIBUBUR")[0] == next(s["id"] for s in STORE_ROWS if s["short"] == "Cibubur")
    assert m.match("Jogja")[0] == next(s["id"] for s in STORE_ROWS if s["short"] == "Yogyakarta")
    assert m.match("Mitra10 Gading Serpng")[0] == next(s["id"] for s in STORE_ROWS if s["short"] == "Gading Serpong")
    assert m.match("Toko Antah Berantah")[0] is None
    assert m.find_in_text("stok cat di cabang kalimalang kosong terus") == \
        next(s["id"] for s in STORE_ROWS if s["short"] == "Kalimalang Baru")


def test_clean_traffic_full_pipeline():
    m = StoreMatcher(STORE_ROWS)
    days = pd.date_range("2026-08-01", periods=42, freq="D")
    rng = np.random.default_rng(1)
    vals = (1000 + 300 * (days.dayofweek >= 5) + rng.normal(0, 20, len(days))).round()
    raw = pd.DataFrame({"Nama Toko": "mitra10 cibubur", "Tgl": days.strftime("%d/%m/%Y"), "Jumlah Pengunjung": vals})
    raw.loc[10, "Jumlah Pengunjung"] = np.nan          # kosong 1 hari → imputasi
    raw.loc[20, "Jumlah Pengunjung"] = 9000             # outlier
    raw.loc[30, "Jumlah Pengunjung"] = 9500             # outlier saat event
    raw = pd.concat([raw, raw.iloc[[5]]])               # duplikat
    raw = pd.concat([raw, pd.DataFrame({"Nama Toko": ["Toko X"], "Tgl": ["01/08/2026"], "Jumlah Pengunjung": [5]})])
    mapping = guess_column_mapping(list(raw.columns))
    assert mapping["toko"] == "Nama Toko" and mapping["kunjungan"] == "Jumlah Pengunjung"
    sid = m.match("cibubur")[0]
    ev = [{"store_ids": [sid], "mulai": days[30].date(), "selesai": days[30].date()}]
    res = clean_traffic(raw, mapping, m, events=ev)
    assert res["ok"]
    log = res["log"]
    assert log["duplikat_dibuang"] == 1
    assert log["diimputasi"] == 1
    assert log["outlier_ditandai"] >= 1
    assert log["outlier_bertepatan_event"] == 1
    assert "Toko X" in log["nama_toko_tidak_dikenal"]
    d = res["data"]
    assert d.loc[d["tanggal"] == days[30], "flag"].iloc[0] == "event"
    assert len(d) == 42


def test_kol_dedupe_and_ratecard():
    existing = [{"id": 1, "platform": "Instagram", "username_norm": "rumahminimalis.id",
                 "link": "https://instagram.com/rumahminimalis.id", "nama": "Rumah Minimalis"}]
    inc = pd.DataFrame([
        {"platform": "Instagram", "username": "@RumahMinimalis.id", "link": "https://instagram.com/rumahminimalis.id", "nama": "RM"},
        {"platform": "TikTok", "username": "dapur5juta", "link": "https://tiktok.com/@dapur5juta", "nama": "Dapur 5 Juta"},
        {"platform": "TikTok", "username": "dapur5juta", "link": "https://tiktok.com/@dapur5juta", "nama": "Dapur 5 Juta"},
        {"platform": "TikTok", "username": "x", "link": "bukan-link", "nama": "X"},
    ])
    out = dedupe_kols(inc, existing)
    assert list(out["status_upload"]) == ["digabung", "baru", "ditolak", "ditolak"]
    assert normalize_username("https://www.tiktok.com/@Abc.Def?lang=id") == "abc.def"
    fl = ratecard_flags([{"deliverable": "video", "harga": 5e6, "berlaku_mulai": date(2025, 1, 1)},
                         {"deliverable": "video", "harga": 12.5e6, "berlaku_mulai": date(2026, 1, 1)}])
    assert fl[0]["flag"] and round(fl[0]["naik_pct"]) == 150


def test_comment_cleaning_and_spam():
    assert normalize_text("Gak ada stok cat nya kak 😡😡") == "tidak ada stok cat nya kakak emo_neg emo_neg"
    df = pd.DataFrame({"teks": ["cek bio utk promo slot gacor", "bagus", "mantap"] + ["follow aku ya"] * 5})
    s = flag_spam(df)
    assert s.iloc[0] and not s.iloc[1] and s.iloc[3]


def test_sentiment_cascade_and_aspects():
    assert nlp.sentiment_cascade("Pelayanan di Cibubur ramah banget, mantap 👍🔥")["sentimen"] == "positif"
    neg = nlp.sentiment_cascade("kecewa, stok cat kosong terus, pegawai jutek")
    assert neg["sentimen"] == "negatif"
    assert nlp.sentiment_cascade("tidak bagus")["sentimen"] == "negatif"
    assert set(nlp.aspects("stok cat kosong, kasir antre lama")) >= {"stok", "produk", "kasir"}
    assert nlp.intent("kak berapa harga kloset duduk?") == "bertanya harga"
    assert nlp.intent("bisa dipasang sekalian tidak?") == "butuh jasa"
    topics = [{"id": 1, "kata_kunci": ["stok", "kosong", "habis"]}, {"id": 2, "kata_kunci": ["kasir", "antre"]}]
    assert nlp.assign_topic("stok cat kosong", topics) == 1
    kw = nlp.keywords(["stok cat kosong", "stok cat kosong lagi", "kasir antre"])
    assert kw[0][0].startswith("stok")


def test_category_suggestion():
    assert nlp.suggest_category("Review makanan & resep dapur rumahan")[0] == "culinary"
    assert nlp.suggest_category("Inspirasi interior rumah minimalis & renovasi")[0] == "lifestyle"
    assert nlp.suggest_category("akun random")[0] == "general"


def _cands():
    rng = random.Random(3)
    out = []
    for i in range(18):
        out.append(Candidate(key=f"{i}:{i % 6}", kol_id=i, store_id=i % 6, zone="AB"[i % 2],
                             harga=rng.randint(3, 15) * 1e6, expected_visits=rng.randint(300, 1500),
                             skor=rng.randint(40, 95), diblokir=(i == 4)))
    return out


def test_optimizer_respects_constraints():
    cands = _cands()
    cons = Constraints(budget=50e6, jumlah_kol=5, wajib_toko=[0, 1], zona_min=0.1, zona_maks=0.9)
    r = solve(cands, cons)
    assert r["status"] == "optimal"
    assert r["cek"]["semua"], r["cek"]
    assert all(not c.diblokir and c.skor >= 50 for c in r["terpilih"])


def test_optimizer_infeasible():
    cons = Constraints(budget=1e6, jumlah_kol=5)
    r = solve(_cands(), cons)
    assert r["status"] == "tidak layak"


def test_check_constraints_detects_violation():
    c = _cands()[:3]
    res = check_constraints(c, Constraints(budget=1, jumlah_kol=3))
    assert not res["budget"] and not res["semua"]
