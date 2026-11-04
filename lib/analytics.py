"""Analitik baca-cepat untuk layar (B.4–B.7). Hasil berat juga disimpan ke tabel predictions oleh lib/jobs.py."""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from . import db
from . import formulas as F
from .preprocess import normalize_text

TTL = 300
DEFAULT_CPM = {"comedy": 52_000, "beauty": 70_000, "lifestyle": 64_000, "culinary": 58_000, "general": 45_000, "portal": 80_000}


def today() -> date:
    return date.today()


# ====================================================================== traffic
@st.cache_data(ttl=TTL, show_spinner=False)
def traffic_daily() -> pd.DataFrame:
    d = db.df("SELECT store_id, tanggal, kunjungan, transaksi, flag FROM offline_traffic_daily")
    if d.empty:
        return pd.DataFrame(columns=["store_id", "tanggal", "kunjungan", "transaksi", "flag"])
    d["tanggal"] = pd.to_datetime(d["tanggal"])
    return d


@st.cache_data(ttl=TTL, show_spinner=False)
def campaign_items() -> pd.DataFrame:
    """Semua item yang sudah/akan tayang (disetujui) — dasar 'hari sejak campaign' & lift."""
    d = db.df("""SELECT i.id AS item_id, i.kol_id, i.store_id, i.tanggal_posting, i.harga_nego, i.deliverable,
                        s.status AS sub_status, s.jenis, s.campaign_id, c.nama AS campaign, s.no_pengajuan,
                        st.zone_id
                 FROM submission_items i JOIN submissions s ON s.id = i.submission_id
                 LEFT JOIN campaigns c ON c.id = s.campaign_id
                 JOIN stores st ON st.id = i.store_id
                 WHERE i.aktif AND i.keputusan_item = 'setuju'
                   AND s.status NOT IN ('Draft','Ditolak','Revisi','Diajukan','Review Asisten Manager','Review Manager')""")
    if not d.empty:
        d["tanggal_posting"] = pd.to_datetime(d["tanggal_posting"])
    return d


def weekly(store_ids: list[int] | None = None, exclude_event: bool = False) -> pd.DataFrame:
    t = traffic_daily()
    if store_ids is not None:
        t = t[t["store_id"].isin(store_ids)]
    if exclude_event:
        t = t[t["flag"].ne("event") | t["flag"].isna()]
    t = t.assign(minggu=t["tanggal"] - pd.to_timedelta(t["tanggal"].dt.dayofweek, unit="D"))
    return t.groupby(["store_id", "minggu"], as_index=False)["kunjungan"].sum()


@st.cache_data(ttl=TTL, show_spinner=False)
def store_baseline_table() -> pd.DataFrame:
    """Per toko: traffic 4 minggu terakhir vs forecast tanpa campaign (rata-rata tertimbang 8 minggu sebelumnya,
    pola hari sama, minggu event & campaign dikeluarkan)."""
    t = traffic_daily()
    if t.empty:
        return pd.DataFrame()
    last = t["tanggal"].max()
    items = campaign_items()
    rows = []
    for sid, g in t.groupby("store_id"):
        g = g.set_index("tanggal").sort_index()
        recent = g[g.index > last - pd.Timedelta(days=28)]
        hist = g[(g.index <= last - pd.Timedelta(days=28)) & (g.index > last - pd.Timedelta(days=28 + 56))]
        camp_days = set()
        if not items.empty:
            for d in items.loc[items["store_id"] == sid, "tanggal_posting"]:
                camp_days |= {d + pd.Timedelta(days=k) for k in range(14)}
        clean = hist[(hist["flag"].ne("event") | hist["flag"].isna()) & ~hist.index.isin(list(camp_days))]
        if len(clean) < 14:
            clean = hist
        by_dow = clean.groupby(clean.index.dayofweek)["kunjungan"].median()
        fc = sum(by_dow.get(d.dayofweek, clean["kunjungan"].median()) for d in recent.index)
        actual = recent["kunjungan"].sum()
        rows.append({"store_id": sid, "traffic_4mgg": actual, "forecast_4mgg": fc,
                     "vs_forecast": (actual / fc - 1) * 100 if fc else 0.0,
                     "harian": recent["kunjungan"].mean()})
    return pd.DataFrame(rows)


def forecast_series(store_id: int, weeks: int = 12) -> pd.DataFrame:
    """Grafik 12 minggu: aktual vs estimasi tanpa campaign (baseline musiman, campaign & event dikeluarkan)."""
    t = traffic_daily()
    g = t[t["store_id"] == store_id].set_index("tanggal").sort_index()
    if g.empty:
        return pd.DataFrame()
    items = campaign_items()
    camp_days = set()
    posts = items.loc[items["store_id"] == store_id, "tanggal_posting"] if not items.empty else []
    for d in posts:
        camp_days |= {d + pd.Timedelta(days=k) for k in range(14)}
    est = []
    for d in g.index:
        hist = g[(g.index < d) & (g.index >= d - pd.Timedelta(days=56))]
        hist = hist[(hist.index.dayofweek == d.dayofweek) & ~hist.index.isin(list(camp_days)) &
                    (hist["flag"].ne("event") | hist["flag"].isna())]
        est.append(hist["kunjungan"].median() if len(hist) >= 2 else np.nan)
    g = g.assign(estimasi=est)
    g["minggu"] = g.index - pd.to_timedelta(g.index.dayofweek, unit="D")
    w = g.groupby("minggu").agg(aktual=("kunjungan", "sum"), estimasi=("estimasi", "sum"),
                                hari=("kunjungan", "size")).reset_index()
    w = w[w["hari"] == 7].tail(weeks)
    camp_weeks = {d - pd.Timedelta(days=d.dayofweek) for d in posts}
    w["campaign"] = w["minggu"].isin(camp_weeks)
    return w


# ====================================================================== segmentasi toko & pembanding
@st.cache_data(ttl=3600, show_spinner=False)
def store_clusters(k: int = 6) -> dict[int, int]:
    """Segmentasi toko (B.4): K-Means pada pola mingguan ternormalisasi + ukuran toko."""
    t = traffic_daily()
    if t.empty:
        return {}
    prof = t.assign(dow=t["tanggal"].dt.dayofweek).pivot_table(index="store_id", columns="dow", values="kunjungan", aggfunc="median")
    size = prof.sum(axis=1)
    X = prof.div(size, axis=0)
    X["size"] = np.log(size) / 10
    X = X.fillna(0)
    try:
        from sklearn.cluster import KMeans
        lab = KMeans(n_clusters=min(k, len(X)), n_init=10, random_state=7).fit_predict(X.values)
    except Exception:
        lab = pd.qcut(size, q=min(k, len(X)), labels=False, duplicates="drop").values
    return {int(s): int(c) for s, c in zip(X.index, lab)}


def comparators(store_id: int, start: pd.Timestamp, end: pd.Timestamp, n: int = 5) -> list[int]:
    """Toko pembanding: klaster mirip, tidak sedang ber-campaign di jendela waktu."""
    cl = store_clusters()
    items = campaign_items()
    busy = set()
    if not items.empty:
        win = items[(items["tanggal_posting"] >= start - pd.Timedelta(days=14)) & (items["tanggal_posting"] <= end)]
        busy = set(win["store_id"])
    same = [s for s, c in cl.items() if c == cl.get(store_id) and s != store_id and s not in busy]
    if len(same) < 3:
        st_df = db.df("SELECT id, zone_id FROM stores")
        z = st_df.loc[st_df["id"] == store_id, "zone_id"].iloc[0]
        same += [int(s) for s in st_df.loc[st_df["zone_id"] == z, "id"] if s != store_id and s not in busy and s not in same]
    if len(same) < 3:
        same += [s for s in cl if s != store_id and s not in busy and s not in same]
    return same[:n]


@st.cache_data(ttl=TTL, show_spinner=False)
def lift_for(store_id: int, posting: pd.Timestamp, biaya: float = 0.0, pre_days: int = 28, post_days: int = 14) -> dict:
    """(8) Lift traffic offline DiD bentuk rasio + interval bootstrap 90%; hari 'event' dikeluarkan."""
    t = traffic_daily()
    t = t[t["flag"].ne("event") | t["flag"].isna()]
    pre_s, pre_e = posting - pd.Timedelta(days=pre_days), posting - pd.Timedelta(days=1)
    post_s, post_e = posting, posting + pd.Timedelta(days=post_days - 1)
    comps = comparators(store_id, pre_s, post_e)

    def daily(ids, a, b):
        x = t[t["store_id"].isin(ids) & (t["tanggal"] >= a) & (t["tanggal"] <= b)]
        return x.groupby("tanggal")["kunjungan"].sum() / max(len(ids), 1)

    sp, so = daily([store_id], pre_s, pre_e), daily([store_id], post_s, post_e)
    cp, co = daily(comps, pre_s, pre_e), daily(comps, post_s, post_e)
    if len(sp) < 7 or len(so) < 3 or len(cp) < 7 or len(co) < 3:
        return {"ok": False, "alasan": "data traffic belum cukup"}
    # pakai rata-rata per minggu (pola hari setara) untuk bootstrap
    r = F.did_interval(list(sp.values), list(so.values), list(cp.values), list(co.values), n_boot=300)
    days = len(so)
    extra_total = r["kunjungan_tambahan"] * days
    out = {"ok": True, "pre": sp.mean() * 7, "post": so.mean() * 7, "counterfactual": r["counterfactual"] * 7,
           "kunjungan_tambahan": extra_total, "lift": r["lift"], "lift_low": r["lift_low"], "lift_high": r["lift_high"],
           "extra_low": r["extra_low"] * days, "extra_high": r["extra_high"] * days, "signifikan": r["signifikan"],
           "pembanding": comps, "pembanding_naik": (co.mean() / cp.mean() - 1) if cp.mean() else 0}
    out["keyakinan"] = "tinggi" if r["lift_low"] > 0.02 else "sedang" if r["signifikan"] else "rendah"
    out["cpiv"] = F.cpiv(biaya, extra_total) if biaya else None
    return out


@st.cache_data(ttl=TTL, show_spinner=False)
def item_lifts() -> pd.DataFrame:
    """Lift per (toko, tanggal tayang) untuk semua item yang sudah tayang ≥ 7 hari."""
    items = campaign_items()
    if items.empty:
        return pd.DataFrame()
    last = traffic_daily()["tanggal"].max()
    rows = []
    done = items[items["tanggal_posting"] <= last - pd.Timedelta(days=6)]
    groups = done.groupby(["store_id", "tanggal_posting"])
    for (sid, d), g in groups:
        r = lift_for(int(sid), d, float(g["harga_nego"].sum()))
        if r.get("ok"):
            for _, it in g.iterrows():
                rows.append({"item_id": it["item_id"], "kol_id": it["kol_id"], "store_id": sid, "zone_id": it["zone_id"],
                             "tanggal": d, "campaign": it["campaign"], "biaya_toko": g["harga_nego"].sum(),
                             "biaya": it["harga_nego"], "share": it["harga_nego"] / max(g["harga_nego"].sum(), 1), **r})
    return pd.DataFrame(rows)


# ====================================================================== KOL features & skor
def tier(follower: float) -> str:
    f = follower or 0
    return "nano" if f < 10_000 else "mikro" if f < 100_000 else "menengah" if f < 500_000 else "makro"


@st.cache_data(ttl=TTL, show_spinner=False)
def kol_base() -> pd.DataFrame:
    k = db.df("""SELECT k.*, ms.follower, ms.avg_views, ms.er AS er_snapshot, ms.audiens_kota_json,
                        ms0.avg_views AS avg_views_awal
                 FROM kol_accounts k
                 LEFT JOIN LATERAL (SELECT * FROM kol_metrics_snapshot m WHERE m.kol_id = k.id ORDER BY tanggal DESC LIMIT 1) ms ON TRUE
                 LEFT JOIN LATERAL (SELECT * FROM kol_metrics_snapshot m WHERE m.kol_id = k.id ORDER BY tanggal ASC LIMIT 1) ms0 ON TRUE
                 ORDER BY k.nama""")
    rc = db.df("""SELECT DISTINCT ON (kol_id) kol_id, deliverable, harga FROM ratecards
                  WHERE deliverable <> 'story' ORDER BY kol_id, berlaku_mulai DESC""")
    rc0 = db.df("""SELECT DISTINCT ON (kol_id) kol_id, harga AS harga_awal FROM ratecards
                   WHERE deliverable <> 'story' ORDER BY kol_id, berlaku_mulai ASC""")
    if k.empty:
        return k
    k = k.merge(rc, left_on="id", right_on="kol_id", how="left").merge(rc0, left_on="id", right_on="kol_id", how="left")
    k["audiens"] = k["audiens_kota_json"].apply(lambda x: x if isinstance(x, dict) else {})
    k["tier"] = k["follower"].map(tier)
    return k


@st.cache_data(ttl=TTL, show_spinner=False)
def post_history() -> pd.DataFrame:
    p = db.df("""SELECT p.id AS post_id, p.kol_id, p.item_id, p.tanggal_tayang, p.telat_hari, p.jenis_konten,
                        (p.bukti IS NULL OR p.insight IS NULL) AS bukti_kurang,
                        i.harga_nego AS biaya, i.store_id, i.tanggal_posting,
                        m.views, m.likes, m.komentar, m.share, m.save
                 FROM posts p JOIN submission_items i ON i.id = p.item_id
                 LEFT JOIN LATERAL (SELECT * FROM post_metrics pm WHERE pm.post_id = p.id
                                    ORDER BY (pm.sumber='api') DESC, diukur_pada DESC LIMIT 1) m ON TRUE""")
    if p.empty:
        return p
    p["tanggal_posting"] = pd.to_datetime(p["tanggal_posting"])
    p["umur"] = (pd.Timestamp(today()) - p["tanggal_posting"]).dt.days.clip(lower=0)
    p["er"] = p.apply(lambda r: F.engagement_rate(r["likes"], r["komentar"], r["share"], r["save"], r["views"]), axis=1)
    p["cpm"] = p.apply(lambda r: F.cpm(r["biaya"], r["views"]) if r["views"] else None, axis=1)
    return p


def _views_quantiles(k_row, posts: pd.DataFrame) -> tuple[float, float, float, int]:
    v = list(posts["views"].dropna())
    a = list(posts.loc[posts["views"].notna(), "umur"])
    prior = k_row.get("avg_views") or 0
    if len(v) >= 3:
        return (F.weighted_quantile(v, a, 0.2), F.weighted_quantile(v, a, 0.5), F.weighted_quantile(v, a, 0.8), len(v))
    # sedikit data: campur dengan rata-rata snapshot (prior) dan rentang lebar
    base = F.time_weighted_median(v, a) if v else prior
    mid = (sum(v) + prior * 2) / (len(v) + 2) if v else prior
    mid = mid if mid else base
    return mid * 0.7, mid, mid * 1.25, len(v)


def cpm_targets(kols: pd.DataFrame, posts: pd.DataFrame) -> dict:
    """CPM_target = median CPM kerja sama yang mencapai target, per kategori & tier (fallback default)."""
    if posts.empty:
        return {}
    p = posts.merge(kols[["id", "kategori", "tipe", "tier", "avg_views"]], left_on="kol_id", right_on="id")
    p = p[p["cpm"].notna()]
    p["kunci"] = np.where(p["tipe"] == "portal", "portal", p["kategori"])
    p = p[p["views"] >= 0.8 * p["avg_views"].fillna(0)]  # 'mencapai target' = views ≥ 80% ekspektasi
    out = {}
    for (kunci, t), g in p.groupby(["kunci", "tier"]):
        if len(g) >= 2:
            out[(kunci, t)] = float(g["cpm"].median())
    for kunci, g in p.groupby("kunci"):
        if len(g) >= 2:
            out[(kunci, None)] = float(g["cpm"].median())
    return out


@st.cache_data(ttl=TTL, show_spinner=False)
def kol_table(store_id: int | None = None, zone_id: int | None = None) -> pd.DataFrame:
    """Fitur, skor (rumus 7), saran harga (5), deteksi kenaikan harga (6) — opsional dihitung ulang untuk toko/zona."""
    k = kol_base()
    if k.empty:
        return k
    posts = post_history()
    lifts = item_lifts()
    stores = db.df("SELECT s.id, s.kota, s.zone_id FROM stores s")
    zone_cities = stores.groupby("zone_id")["kota"].apply(set).to_dict()
    target_city, target_zone_cities = None, set()
    if store_id:
        row = stores[stores["id"] == store_id].iloc[0]
        target_city, target_zone_cities = row["kota"], zone_cities.get(row["zone_id"], set())
        zone_id = zone_id or int(row["zone_id"])
    elif zone_id:
        target_zone_cities = zone_cities.get(zone_id, set())
    targets = cpm_targets(k, posts)

    rows = []
    for _, r in k.iterrows():
        kp = posts[posts["kol_id"] == r["id"]] if not posts.empty else pd.DataFrame(columns=["views", "umur", "er", "cpm", "telat_hari", "bukti_kurang"])
        q20, q50, q80, n = _views_quantiles(r, kp)
        er_list = list(kp["er"].dropna()) if not kp.empty else []
        er_kol = float(np.mean(er_list)) if er_list else float(r["er_snapshot"] or 0)
        n_er = len(er_list) if er_list else 1
        kunci = "portal" if r["tipe"] == "portal" else r["kategori"]
        cpm_t = targets.get((kunci, r["tier"])) or targets.get((kunci, None)) or DEFAULT_CPM.get(kunci, 55_000)
        harga = float(r["harga"] or 0)
        exp_cpm = F.cpm(harga, q50) if q50 else None
        price = F.suggest_price(cpm_t, q50 or 0, q80 or 0)
        aud = r["audiens"] or {}
        if target_city:
            lokal = aud.get(target_city, 0) + 0.5 * sum(v for c, v in aud.items() if c in target_zone_cities and c != target_city)
        elif target_zone_cities:
            lokal = sum(v for c, v in aud.items() if c in target_zone_cities)
        else:
            lokal = max([v for c, v in aud.items() if c != "Lainnya"] or [0])
        kl = lifts[lifts["kol_id"] == r["id"]] if not lifts.empty else pd.DataFrame()
        if not kl.empty and store_id and (kl["store_id"] == store_id).any():
            kl_scope = kl[kl["store_id"] == store_id]
        elif not kl.empty and zone_id and (kl["zone_id"] == zone_id).any():
            kl_scope = kl[kl["zone_id"] == zone_id]
        else:
            kl_scope = kl
        lift_hist = float(kl_scope["lift"].mean()) if not kl_scope.empty else None
        extra_hist = float((kl_scope["kunjungan_tambahan"] * kl_scope["share"]).mean()) if not kl_scope.empty else None
        cpiv = F.cpiv(float(kl_scope["biaya"].sum()), float((kl_scope["kunjungan_tambahan"] * kl_scope["share"]).sum())) if not kl_scope.empty else None
        gap = F.price_increase_gap(float(r["harga_awal"] or harga or 1), harga or 1, float(r["avg_views_awal"] or q50 or 1), float(r["avg_views"] or q50 or 1))
        last_used = kp["tanggal_posting"].max() if not kp.empty else None
        rows.append({
            "id": r["id"], "nama": r["nama"], "username": r["username"], "tipe": r["tipe"], "platform": r["platform"],
            "kategori": r["kategori"], "kategori_otomatis": r["kategori_otomatis"], "kota": r["kota_domisili"], "status": r["status"],
            "alasan_blokir": r["alasan_blokir"], "follower": r["follower"], "avg_views": r["avg_views"], "tier": r["tier"],
            "er_kol": er_kol, "n_post": n, "views_q20": q20, "views_q50": q50, "views_q80": q80,
            "konsistensi": F.consistency(list(kp["views"].dropna())) if len(kp) >= 2 else None,
            "harga": harga, "deliverable": r["deliverable"], "cpm_target": cpm_t, "cpm_harapan": exp_cpm,
            "efisiensi": (cpm_t / exp_cpm) if exp_cpm else None,
            "harga_wajar": price.wajar, "batas_nego": price.batas_atas,
            "audiens_lokal": lokal, "audiens": aud, "lift_hist": lift_hist, "extra_hist": extra_hist, "cpiv": cpiv,
            "telat": int((kp["telat_hari"] > 0).sum()) if not kp.empty else 0,
            "bukti_kurang": int(kp["bukti_kurang"].sum()) if not kp.empty and "bukti_kurang" in kp else 0,
            "kerja_sama": int(len(kp)), "terakhir": last_used,
            "gap_harga": gap["gap"], "flag_harga": gap["flag"], "naik_ratecard": gap["delta_ratecard"], "naik_views": gap["delta_views"],
            "bio": r["bio"], "niche": r["niche"], "link": r["link"], "badan_hukum": r["badan_hukum"], "punya_npwp": r["punya_npwp"],
            "kontak": r["kontak"],
        })
    d = pd.DataFrame(rows)
    # ER_adj (rumus 2) terhadap rata-rata kategori
    cat_er = d.groupby("kategori")["er_kol"].mean().to_dict()
    d["er_adj"] = [F.er_adjusted(max(n, 1), e, cat_er.get(c, e)) for n, e, c in zip(d["n_post"], d["er_kol"], d["kategori"])]
    # persentil komponen dalam kategori-tier (fallback kategori, lalu semua)
    comp_E, comp_K, comp_C, comp_R, comp_D = [], [], [], [], []
    for _, r in d.iterrows():
        grp = d[(d["kategori"] == r["kategori"]) & (d["tier"] == r["tier"])]
        if len(grp) < 4:
            grp = d[d["kategori"] == r["kategori"]]
        if len(grp) < 4:
            grp = d
        comp_E.append(F.percentile_rank(r["er_adj"], list(grp["er_adj"])))
        comp_K.append(F.percentile_rank(r["konsistensi"], list(d["konsistensi"].dropna())) if r["konsistensi"] is not None and not pd.isna(r["konsistensi"]) else 50.0)
        comp_C.append(F.percentile_rank(r["efisiensi"], list(d["efisiensi"].dropna())) if r["efisiensi"] else 50.0)
        comp_R.append(F.percentile_rank(r["audiens_lokal"], list(d["audiens_lokal"])))
        comp_D.append(F.percentile_rank(r["lift_hist"], list(d["lift_hist"].dropna())) if r["lift_hist"] is not None and not pd.isna(r["lift_hist"]) else None)
    d["E"], d["K"], d["C"], d["R"], d["D"] = comp_E, comp_K, comp_C, comp_R, comp_D
    scores, labels, kontrib, penal = [], [], [], []
    for _, r in d.iterrows():
        s = F.kol_score(r["E"], r["K"], r["C"], r["R"], None if r["D"] is None or pd.isna(r["D"]) else r["D"],
                        telat=r["telat"], bukti_tidak_lengkap=min(r["bukti_kurang"], 2))
        scores.append(s["skor"]); labels.append(s["label"]); kontrib.append(s["kontribusi"]); penal.append(s["penalti"])
    d["skor"], d["label"], d["kontribusi"], d["penalti"] = scores, labels, kontrib, penal
    d["data_terbatas"] = d["n_post"] < 3
    d["strength"] = d.apply(_strengths, axis=1)
    d["weakness"] = d.apply(_weaknesses, axis=1)
    d["segmen"] = segment_kols(d)
    return d.sort_values("skor", ascending=False).reset_index(drop=True)


def _strengths(r) -> list[str]:
    s = []
    if r["E"] >= 70: s.append(f"ER tinggi ({F.persen(r['er_adj'])}) dibanding kategori")
    if r["K"] >= 70: s.append("views konsisten antar posting")
    if r["C"] >= 70: s.append("biaya per 1.000 views efisien")
    if r["R"] >= 70: s.append(f"audiens lokal kuat ({r['audiens_lokal'] * 100:.0f}%)")
    if r["D"] is not None and not pd.isna(r["D"]) and r["D"] >= 70: s.append(f"lift historis {F.persen((r['lift_hist'] or 0) * 100, tanda=True)}")
    return s or ["belum ada keunggulan menonjol"]


def _weaknesses(r) -> list[str]:
    w = []
    if r["E"] <= 35: w.append("ER di bawah rata-rata kategori")
    if r["K"] <= 35: w.append("views naik-turun (tidak stabil)")
    if r["C"] <= 35: w.append("harga mahal untuk views yang didapat")
    if r["R"] <= 35: w.append("audiens lokal rendah")
    if r["flag_harga"]: w.append(f"harga naik lebih cepat dari hasil (gap {r['gap_harga']:.0f} poin)")
    if r["telat"]: w.append(f"telat tayang {r['telat']}×")
    if r["data_terbatas"]: w.append("data terbatas (< 3 kerja sama)")
    return w or ["tidak ada catatan"]


def segment_kols(d: pd.DataFrame) -> list[str]:
    """Segmentasi KOL (B.4): HDBSCAN pada ER, views, konsistensi, efisiensi, audiens lokal; label dari karakter klaster."""
    feats = d[["er_adj", "avg_views", "K", "C", "R"]].copy()
    feats["avg_views"] = np.log1p(feats["avg_views"].fillna(0))
    feats = feats.fillna(feats.median())
    X = ((feats - feats.mean()) / feats.std(ddof=0).replace(0, 1)).values
    labels = None
    try:
        from sklearn.cluster import HDBSCAN
        labels = HDBSCAN(min_cluster_size=4).fit_predict(X)
    except Exception:
        labels = None
    names = []
    for i, r in d.iterrows():
        if r["R"] >= 60 and r["C"] >= 55:
            n = "lokal efisien"
        elif r["avg_views"] and r["avg_views"] > d["avg_views"].median() and r["K"] < 45:
            n = "viral tidak stabil"
        elif r["C"] < 45 and r["K"] >= 55:
            n = "mahal stabil"
        else:
            n = "berkembang"
        if labels is not None and labels[i] == -1:
            n += " · unik"
        names.append(n)
    return names


# ====================================================================== kebutuhan toko (rumus 9)
@st.cache_data(ttl=TTL, show_spinner=False)
def store_needs() -> pd.DataFrame:
    base = store_baseline_table()
    if base.empty:
        return base
    stores = db.df("SELECT s.id, s.nama, s.kota, s.zone_id, z.nama AS zona, s.target_kunjungan_mingguan FROM stores s JOIN zones z ON z.id=s.zone_id")
    items = campaign_items()
    lifts = item_lifts()
    last = traffic_daily()["tanggal"].max()
    rows = []
    for _, s in stores.iterrows():
        b = base[base["store_id"] == s["id"]]
        if b.empty:
            continue
        b = b.iloc[0]
        its = items[(items["store_id"] == s["id"]) & (items["tanggal_posting"] <= last)] if not items.empty else pd.DataFrame()
        hari = (last - its["tanggal_posting"].max()).days if not its.empty else 999
        c30 = int((its["tanggal_posting"] > last - pd.Timedelta(days=30)).sum()) if not its.empty else 0
        sl = lifts[lifts["store_id"] == s["id"]] if not lifts.empty else pd.DataFrame()
        zl = lifts[lifts["zone_id"] == s["zone_id"]] if not lifts.empty else pd.DataFrame()
        resp = float(sl["lift"].mean()) if not sl.empty else (float(zl["lift"].mean()) * 0.8 if not zl.empty else 0.05)
        weekly_actual = b["traffic_4mgg"] / 4
        target = s["target_kunjungan_mingguan"] or weekly_actual
        rows.append({"store_id": s["id"], "toko": s["nama"], "zona": s["zona"], "zone_id": s["zone_id"], "kota": s["kota"],
                     "traffic_4mgg": b["traffic_4mgg"], "vs_forecast": b["vs_forecast"], "penurunan_pct": -b["vs_forecast"],
                     "hari_sejak": hari, "responsivitas": resp, "selisih_target": (target - weekly_actual) / target * 100 if target else 0,
                     "campaign_30hr": c30})
    scored = pd.DataFrame(F.store_need_scores(rows))
    if scored.empty:
        return scored

    def saran(r):
        if r["skor"] >= 85: return "2 KOL + portal"
        if r["skor"] >= 75: return "KOL lokal (2–4)"
        if r["skor"] >= 65: return "1 KOL + portal"
        if r["skor"] >= 55: return "Portal lokal"
        return "Belum perlu"
    scored["saran"] = scored.apply(saran, axis=1)
    return scored.sort_values("skor", ascending=False).reset_index(drop=True)


# ====================================================================== rekomendasi KOL × toko (rumus 10)
@st.cache_data(ttl=TTL, show_spinner=False)
def store_need_text(store_id: int) -> str:
    rows = db.query("""SELECT n.teks_bersih, t.label FROM comment_nlp n LEFT JOIN topics t ON t.id=n.topic_id
                       WHERE n.store_id=%s AND NOT n.is_spam ORDER BY n.comment_id DESC LIMIT 200""", (store_id,))
    return " ".join((r["teks_bersih"] or "") + " " + (r["label"] or "") for r in rows)


def _similarity(a: str, b: str) -> float:
    ta, tb = set(normalize_text(a).split()), set(normalize_text(b).split())
    if not ta or not tb:
        return 0.5
    return min(1.0, 0.3 + len(ta & tb) / math.sqrt(len(ta) * len(tb)))


def recommend_for_store(store_id: int, k: int = 8, seed: int | None = None) -> pd.DataFrame:
    kt = kol_table(store_id=store_id)
    if kt.empty:
        return kt
    kt = kt[(kt["status"] == "aktif") & (kt["skor"] >= 50)].copy()
    need_text = store_need_text(store_id) or "renovasi rumah promo cat keramik dapur kamar mandi"
    base = store_baseline_table()
    b = base[base["store_id"] == store_id]
    weekly_base = float(b["traffic_4mgg"].iloc[0] / 4) if not b.empty else 7000.0
    cat_lift = kt.groupby("kategori")["lift_hist"].mean().to_dict()
    rng = random.Random(seed if seed is not None else store_id * 31 + date.today().toordinal())
    out = []
    for _, r in kt.iterrows():
        sim = _similarity(f"{r['bio']} {r['niche']} {r['kategori']}", need_text)
        rk = F.rank_kol_store(min(1.0, r["audiens_lokal"]), r["skor"], r["lift_hist"], sim, rng=rng)
        lift_exp = r["lift_hist"] if r["lift_hist"] is not None and not pd.isna(r["lift_hist"]) else (cat_lift.get(r["kategori"]) or 0.08)
        lift_exp = 0.5 * lift_exp + 0.5 * lift_exp * min(1.0, r["audiens_lokal"] / 0.4)
        extra = weekly_base * 2 * lift_exp
        lo, hi = extra * (0.6 if not r["data_terbatas"] else 0.4), extra * (1.25 if not r["data_terbatas"] else 1.6)
        alasan = []
        if r["audiens_lokal"] >= 0.3:
            alasan.append(f"audiens lokal {r['audiens_lokal'] * 100:.0f}%")
        if r["lift_hist"] is not None and not pd.isna(r["lift_hist"]):
            alasan.append(f"lift historis {F.persen(r['lift_hist'] * 100, tanda=True)}")
        if sim > 0.55:
            alasan.append("cocok dengan kebutuhan dari social listening")
        if rk["thompson"]:
            alasan.append("KOL baru — dieksplorasi (Thompson sampling)")
        alasan.append(f"skor {r['skor']:.0f}")
        out.append({**r.to_dict(), "rank": rk["rank"], "thompson": rk["thompson"], "kemiripan": sim,
                    "prediksi_kunjungan": extra, "prediksi_low": lo, "prediksi_high": hi, "alasan": alasan[:3]})
    cand = sorted(out, key=lambda x: -x["rank"])
    chosen = F.mmr_diversify(cand, max_overlap=0.60, k=k)
    return pd.DataFrame(chosen)


# ====================================================================== konten & sosial
@st.cache_data(ttl=TTL, show_spinner=False)
def comments_nlp(start: date, end: date, platform: str | None = None, store_ids: tuple | None = None) -> pd.DataFrame:
    sql = """SELECT c.id, c.platform, c.waktu, c.teks_anonim, n.is_spam, n.teks_bersih, n.sentimen, n.skor, n.metode,
                    n.aspek, n.niat, n.topic_id, n.store_id, t.label AS topik, t.jenis AS jenis_topik
             FROM social_comments c JOIN comment_nlp n ON n.comment_id = c.id
             LEFT JOIN topics t ON t.id = n.topic_id
             WHERE c.waktu::date BETWEEN %s AND %s"""
    params = [start, end]
    if platform:
        sql += " AND c.platform = %s"
        params.append(platform)
    d = db.df(sql, params)
    if not d.empty:
        d["waktu"] = pd.to_datetime(d["waktu"], utc=True).dt.tz_convert("Asia/Jakarta")
        if store_ids:
            d = d[d["store_id"].isin(store_ids) | d["store_id"].isna()]
    return d


def sentiment_summary(d: pd.DataFrame) -> dict:
    x = d[~d["is_spam"]] if not d.empty else d
    n = len(x)
    if n == 0:
        return {"n": 0, "pos": 0, "neu": 0, "neg": 0, "net": 0.0}
    pos = int((x["sentimen"] == "positif").sum()); neg = int((x["sentimen"] == "negatif").sum())
    return {"n": n, "pos": pos / n * 100, "neg": neg / n * 100, "neu": (n - pos - neg) / n * 100,
            "net": F.net_sentiment(pos, neg, n)}


def topic_spikes(d: pd.DataFrame) -> pd.DataFrame:
    """Lonjakan isu: robust z-score volume harian per topik & platform vs median 28 hari."""
    x = d[(~d["is_spam"]) & d["topik"].notna()].copy() if not d.empty else d
    if x.empty:
        return pd.DataFrame()
    x["hari"] = x["waktu"].dt.date
    out = []
    last_day = x["hari"].max()
    for (plat, top, jenis), g in x.groupby(["platform", "topik", "jenis_topik"]):
        daily = g.groupby("hari").size()
        idx = pd.date_range(last_day - timedelta(days=30), last_day, freq="D").date
        daily = daily.reindex(idx, fill_value=0)
        recent = daily.iloc[-3:].mean()
        z = F.robust_spike_z(recent, list(daily.iloc[:-3].values))
        neg = (g["sentimen"] == "negatif").mean() * 100
        stores = g["store_id"].dropna().astype(int).value_counts().head(3).index.tolist()
        out.append({"platform": plat, "topik": top, "jenis": jenis, "volume_30hr": int(daily.sum()), "rata_3hr": recent,
                    "z": z, "lonjakan": z > 3, "negatif_pct": neg, "toko": stores})
    return pd.DataFrame(out).sort_values(["lonjakan", "z"], ascending=False)
