"""Laporan performa per KOL / Portal untuk keputusan lanjut-evaluasi-stop.

Sumber: baris pengajuan yang disetujui (biaya, toko, campaign), link tayang + metrik (API / OCR / manual),
riwayat follower & ER (snapshot Excel dan API), video TikTok KOL yang memberi izin.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from . import db

MIN_POST = 1


@st.cache_data(ttl=300, show_spinner=False)
def post_level(start=None, end=None) -> pd.DataFrame:
    """Satu baris per posting tayang (item setuju) + metrik terbaru."""
    d = db.df("""SELECT i.id AS item_id, i.kol_id, k.username_norm AS username, k.nama, k.tipe, k.kategori, k.api_status, i.store_id, st.nama AS toko,
                        z.nama AS zona, c.id AS campaign_id, c.nama AS campaign, i.deliverable, i.harga_nego AS biaya,
                        COALESCE(p.tanggal_tayang::date, i.tanggal_posting) AS tanggal, p.link,
                        m.views, m.likes, m.komentar, m.share, m.save, m.sumber, m.diukur_pada,
                        tt.views AS tt_views, tt.likes AS tt_likes, tt.komentar AS tt_komentar, tt.share AS tt_share,
                        fs.follower AS follower_saat_itu
                 FROM submission_items i
                 JOIN submissions s ON s.id=i.submission_id
                 LEFT JOIN campaigns c ON c.id=s.campaign_id
                 JOIN kol_accounts k ON k.id=i.kol_id
                 JOIN stores st ON st.id=i.store_id JOIN zones z ON z.id=st.zone_id
                 LEFT JOIN posts p ON p.item_id=i.id
                 LEFT JOIN LATERAL (SELECT views, likes, komentar, share, save, sumber, diukur_pada FROM post_metrics pm
                                    WHERE pm.post_id=p.id ORDER BY diukur_pada DESC, (sumber='api') DESC LIMIT 1) m ON TRUE
                 LEFT JOIN LATERAL (SELECT SUM(views) AS views, SUM(likes) AS likes, SUM(komentar) AS komentar, SUM(share) AS share
                                    FROM kol_tiktok_videos v WHERE v.item_id=i.id) tt ON TRUE
                 LEFT JOIN LATERAL (SELECT follower FROM kol_metrics_snapshot ms WHERE ms.kol_id=i.kol_id AND ms.follower IS NOT NULL
                                    ORDER BY abs(ms.tanggal - COALESCE(i.tanggal_posting, CURRENT_DATE)) LIMIT 1) fs ON TRUE
                 WHERE i.aktif AND i.keputusan_item='setuju'
                   AND s.status NOT IN ('Draft','Ditolak','Revisi','Diajukan','Review Asisten Manager','Review Manager')
                   AND (%s::date IS NULL OR COALESCE(p.tanggal_tayang::date, i.tanggal_posting) >= %s::date)
                   AND (%s::date IS NULL OR COALESCE(p.tanggal_tayang::date, i.tanggal_posting) <= %s::date)""",
              (start, start, end, end))
    if d.empty:
        return d
    for c in ["views", "likes", "komentar", "share", "save", "tt_views", "tt_likes", "tt_komentar", "tt_share", "biaya", "follower_saat_itu"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["views_total"] = d[["views", "tt_views"]].sum(axis=1, min_count=1)
    d["interaksi"] = d[["likes", "komentar", "share", "save", "tt_likes", "tt_komentar", "tt_share"]].sum(axis=1, min_count=1)
    d["terukur"] = d["views_total"].notna() | d["interaksi"].notna()
    d["er_post"] = np.where(d["follower_saat_itu"] > 0, (d[["likes", "komentar"]].sum(axis=1, min_count=1)) / d["follower_saat_itu"] * 100, np.nan)
    d["cpm"] = np.where(d["views_total"] > 0, d["biaya"] / d["views_total"] * 1000, np.nan)
    d["cpe"] = np.where(d["interaksi"] > 0, d["biaya"] / d["interaksi"], np.nan)
    return d


@st.cache_data(ttl=300, show_spinner=False)
def follower_trend() -> pd.DataFrame:
    return db.df("""SELECT kol_id, tanggal, follower, er, avg_views FROM kol_metrics_snapshot
                    WHERE follower IS NOT NULL OR er IS NOT NULL ORDER BY kol_id, tanggal""")


def _pct_rank(s: pd.Series, lower_better: bool = False) -> pd.Series:
    r = s.rank(pct=True)
    return (1 - r + 1 / max(s.notna().sum(), 1)) if lower_better else r


def kol_summary(start=None, end=None) -> pd.DataFrame:
    p = post_level(start, end)
    if p.empty:
        return pd.DataFrame()
    g = p.groupby("kol_id")
    s = pd.DataFrame({
        "username": g["username"].first(), "tipe": g["tipe"].first(), "kategori": g["kategori"].first(), "api_status": g["api_status"].first(),
        "kerja_sama": g.size(), "posting_terukur": g["terukur"].sum(), "biaya": g["biaya"].sum(),
        "toko": g["toko"].agg(lambda x: ", ".join(sorted(set(x)))[:200]), "n_toko": g["store_id"].nunique(),
        "zona": g["zona"].agg(lambda x: ", ".join(sorted(set(x)))), "terakhir": g["tanggal"].max(),
        "views": g["views_total"].sum(min_count=1), "interaksi": g["interaksi"].sum(min_count=1),
        "views_median": g["views_total"].median(), "er_aktual": g["er_post"].median(),
        "views_cv": g["views_total"].agg(lambda x: x.std() / x.mean() if x.notna().sum() >= 2 and x.mean() else np.nan),
    }).reset_index()
    biaya_terukur = p[p["views_total"] > 0].groupby("kol_id")["biaya"].sum()
    views_terukur = p[p["views_total"] > 0].groupby("kol_id")["views_total"].sum()
    s["cpm"] = s["kol_id"].map(biaya_terukur / views_terukur * 1000)
    inter_b = p[p["interaksi"] > 0].groupby("kol_id")["biaya"].sum() / p[p["interaksi"] > 0].groupby("kol_id")["interaksi"].sum()
    s["cpe"] = s["kol_id"].map(inter_b)
    # follower: awal vs terbaru; ER klaim (Excel) vs aktual
    ft = follower_trend()
    if not ft.empty:
        f = ft.dropna(subset=["follower"]).groupby("kol_id")
        s["follower_awal"] = s["kol_id"].map(f["follower"].first())
        s["follower_terbaru"] = s["kol_id"].map(f["follower"].last())
        s["follower_tgl"] = s["kol_id"].map(f["tanggal"].last())
        s["er_klaim"] = s["kol_id"].map(ft.dropna(subset=["er"]).groupby("kol_id")["er"].median())
    else:
        s[["follower_awal", "follower_terbaru", "follower_tgl", "er_klaim"]] = np.nan
    s["follower_growth"] = np.where(s["follower_awal"] > 0, (s["follower_terbaru"] / s["follower_awal"] - 1) * 100, np.nan)
    return _decide(s)


def _decide(s: pd.DataFrame) -> pd.DataFrame:
    s = s.copy()
    s["skor"] = np.nan
    s["cpm_vs_median"] = np.nan
    for tipe, idx in s.groupby("tipe").groups.items():
        x = s.loc[idx]
        comp = pd.DataFrame({
            "cpm": _pct_rank(x["cpm"], lower_better=True) * 40,
            "er": _pct_rank(x["er_aktual"]) * 25,
            "konsisten": _pct_rank(x["views_cv"], lower_better=True) * 15,
            "growth": _pct_rank(x["follower_growth"]) * 10,
            "repeat": _pct_rank(x["kerja_sama"]) * 10,
        }, index=x.index)
        w = pd.Series({"cpm": 40, "er": 25, "konsisten": 15, "growth": 10, "repeat": 10})
        avail = comp.notna().mul(w, axis=1).sum(axis=1)
        sk = (comp.sum(axis=1, min_count=1) / avail.replace(0, np.nan) * 100).round(0)
        s.loc[idx, "skor"] = sk.where(x["posting_terukur"] >= MIN_POST)
        s.loc[idx, "cpm_vs_median"] = x["cpm"] / x["cpm"].median() if x["cpm"].notna().any() else np.nan

    def flags(r):
        f = []
        if pd.notna(r["er_klaim"]) and pd.notna(r["er_aktual"]) and r["er_klaim"] > 0 and r["er_aktual"] < 0.4 * r["er_klaim"]:
            f.append("ER aktual jauh di bawah klaim")
        if pd.notna(r["follower_growth"]) and r["follower_growth"] < -10:
            f.append("follower turun > 10%")
        if pd.notna(r["views_cv"]) and r["views_cv"] > 1.2:
            f.append("views tidak konsisten")
        if r["api_status"] == "bukan_bisnis":
            f.append("akun pribadi — metrik via screenshot insight")
        return f

    s["catatan"] = s.apply(flags, axis=1)

    def keputusan(r):
        if r["posting_terukur"] < MIN_POST or pd.isna(r["skor"]):
            return "Data belum cukup"
        serious = [x for x in r["catatan"] if x.startswith(("ER aktual", "follower turun"))]
        if r["skor"] >= 65 and not serious:
            return "Lanjutkan"
        mahal = pd.notna(r.get("cpm_vs_median")) and r["cpm_vs_median"] > 1.5
        if (r["skor"] < 35 and mahal) or len(serious) >= 2:
            return "Stop"
        return "Evaluasi"

    s["keputusan"] = s.apply(keputusan, axis=1)
    s["insight"] = s.apply(_insight, axis=1)
    order = {"Lanjutkan": 0, "Evaluasi": 1, "Stop": 2, "Data belum cukup": 3}
    return s.assign(_o=s["keputusan"].map(order)).sort_values(["_o", "skor"], ascending=[True, False]).drop(columns="_o").reset_index(drop=True)


def _fmt(n):
    if pd.isna(n):
        return "—"
    return f"{round(float(n)):,}".replace(",", ".")


def _pct(x):
    return "<1%" if 0 < x < 1 else f"{round(x)}%"


def _insight(r) -> str:
    parts = []
    if r["posting_terukur"]:
        parts.append(f"{int(r['posting_terukur'])}/{int(r['kerja_sama'])} posting terukur, median {_fmt(r['views_median'])} views")
        if pd.notna(r["cpm"]):
            parts.append(f"CPM Rp {_fmt(r['cpm'])}")
        if pd.notna(r["er_aktual"]):
            k = f" (klaim {_pct(r['er_klaim'])})" if pd.notna(r["er_klaim"]) else ""
            parts.append(f"ER aktual {_pct(r['er_aktual'])}{k}")
    else:
        parts.append(f"{int(r['kerja_sama'])} kerja sama, belum ada metrik posting")
    if pd.notna(r["follower_terbaru"]):
        g = f", {round(r['follower_growth']):+d}% sejak data awal" if pd.notna(r["follower_growth"]) else ""
        parts.append(f"follower {_fmt(r['follower_terbaru'])}{g}")
    if r["catatan"]:
        parts.append("⚠ " + "; ".join(r["catatan"]))
    return " · ".join(parts)


def benchmark(s: pd.DataFrame) -> pd.DataFrame:
    if s.empty:
        return s
    return s.groupby("tipe").agg(akun=("kol_id", "size"), biaya=("biaya", "sum"), views=("views", "sum"),
                                 cpm_median=("cpm", "median"), er_median=("er_aktual", "median")).reset_index()
