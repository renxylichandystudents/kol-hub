"""Layar 19 — Report & Hasil: laporan per toko dan zona (Tim Toko melihat tokonya sendiri)."""
import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, db, docs, ui
from lib import formulas as F
from lib.rbac import require

user = auth.current_user()
require(user["role"], "report.view")
ui.header("Report & Hasil", "Hasil per toko & zona · analisa kelebihan, kekurangan, rekomendasi")
f = ui.global_filters(user, show_period=False, key="rep")
sids = f["store_ids"]

res = db.df("""SELECT i.id AS item_id, COALESCE(c.nama, 'Tunggal ' || s.no_pengajuan) AS campaign, k.username, k.platform, k.kategori,
                      st.id AS store_id, st.nama AS toko, z.nama AS zona, i.tanggal_posting, i.harga_nego AS biaya, p.link, p.jenis_konten,
                      p.telat_hari, p.bukti_nama, p.insight_nama, m.views, m.likes, m.komentar, m.share, m.save, m.sumber
               FROM submission_items i JOIN submissions s ON s.id=i.submission_id LEFT JOIN campaigns c ON c.id=s.campaign_id
               JOIN kol_accounts k ON k.id=i.kol_id JOIN stores st ON st.id=i.store_id JOIN zones z ON z.id=st.zone_id
               JOIN posts p ON p.item_id=i.id
               LEFT JOIN LATERAL (SELECT * FROM post_metrics pm WHERE pm.post_id=p.id ORDER BY (sumber='api') DESC, diukur_pada DESC LIMIT 1) m ON TRUE
               WHERE i.aktif AND i.store_id = ANY(%s)""", (sids,))
if res.empty:
    st.info("Belum ada hasil tayang untuk toko terpilih.")
    st.stop()
camps = ["Semua campaign"] + sorted(res["campaign"].unique())
cs = st.selectbox("Campaign", camps)
if cs != camps[0]:
    res = res[res["campaign"] == cs]
lifts = A.item_lifts()
if not lifts.empty:
    lf = lifts[["item_id", "lift", "kunjungan_tambahan", "share", "keyakinan"]].rename(columns={"share": "porsi"})
    res = res.merge(lf, on="item_id", how="left")
    res["kunjungan_item"] = res["kunjungan_tambahan"] * res["porsi"]
else:
    res["lift"] = res["kunjungan_item"] = res["keyakinan"] = None
res["ER"] = [F.engagement_rate(a, b, c, d, v) for a, b, c, d, v in zip(res["likes"], res["komentar"], res["share"], res["save"], res["views"])]
res["CPM"] = [F.cpm(b, v) if v else None for b, v in zip(res["biaya"], res["views"])]

tot_b, tot_v, tot_k = res["biaya"].sum(), res["views"].sum(), res["kunjungan_item"].sum(skipna=True)
ui.kpis([{"label": "Konten tayang", "value": str(len(res)), "sub": f"{res['toko'].nunique()} toko · {res['zona'].nunique()} zona"},
         {"label": "Views", "value": F.angka(tot_v), "sub": f"CPM {F.rupiah(F.cpm(tot_b, tot_v))}"},
         {"label": "Kunjungan tambahan", "value": f"+{F.angka(tot_k)}" if tot_k else "—", "sub": "estimasi DiD dibagi per KOL"},
         {"label": "Biaya", "value": F.rupiah(tot_b), "sub": f"CPIV {F.rupiah(F.cpiv(tot_b, tot_k))}" if tot_k else ""}])

tz, tt, tc, tb = st.tabs(["Per zona", "Per toko", "Per KOL", "Bukti tayang"])
agg = dict(konten=("item_id", "count"), biaya=("biaya", "sum"), views=("views", "sum"), kunjungan=("kunjungan_item", "sum"), lift=("lift", "mean"))
cc = {"biaya": st.column_config.NumberColumn(format="Rp %d"), "views": st.column_config.NumberColumn(format="%d"),
      "kunjungan": st.column_config.NumberColumn("Kunjungan tambahan", format="%d"), "lift": st.column_config.NumberColumn("Lift rata-rata", format="%.3f")}
with tz:
    z = res.groupby("zona").agg(**agg).reset_index()
    z["CPIV"] = [F.cpiv(b, k) for b, k in zip(z["biaya"], z["kunjungan"])]
    st.dataframe(z, hide_index=True, use_container_width=True, column_config={**cc, "CPIV": st.column_config.NumberColumn(format="Rp %d")})
with tt:
    t = res.groupby(["zona", "toko"]).agg(**agg).reset_index()
    t["CPIV"] = [F.cpiv(b, k) for b, k in zip(t["biaya"], t["kunjungan"])]
    st.dataframe(t, hide_index=True, use_container_width=True, column_config={**cc, "CPIV": st.column_config.NumberColumn(format="Rp %d")})
    st.download_button("Unduh Excel per toko", docs.to_excel(t, "per_toko"), file_name="report_per_toko.xlsx")
with tc:
    k = res[["campaign", "username", "platform", "toko", "tanggal_posting", "biaya", "views", "ER", "CPM", "lift", "keyakinan", "telat_hari"]]
    st.dataframe(k, hide_index=True, use_container_width=True, column_config={
        "biaya": st.column_config.NumberColumn(format="Rp %d"), "views": st.column_config.NumberColumn(format="%d"),
        "ER": st.column_config.NumberColumn(format="%.1f%%"), "CPM": st.column_config.NumberColumn(format="Rp %d"),
        "lift": st.column_config.NumberColumn(format="%.3f")})
with tb:
    ui.note("Bukti tayang diunggah oleh Digital Marketing; status & unggah ada di menu 'Bukti Tayang & Status RO'.")
    st.dataframe(res[["username", "toko", "tanggal_posting", "link", "bukti_nama", "insight_nama", "views", "sumber"]], hide_index=True,
                 use_container_width=True, column_config={"link": st.column_config.LinkColumn("Link posting"),
                                                          "bukti_nama": "Screenshot", "insight_nama": "Insight"})

st.markdown("#### Analisa")
kel, kek, rek = [], [], []
by_k = res.groupby("username").agg(biaya=("biaya", "sum"), views=("views", "sum"), kunj=("kunjungan_item", "sum"), lift=("lift", "mean"))
by_k["cpiv"] = [F.cpiv(b, k) for b, k in zip(by_k["biaya"], by_k["kunj"])]
v = by_k.dropna(subset=["cpiv"])
if not v.empty:
    b_ = v["cpiv"].idxmin(); w_ = v["cpiv"].idxmax()
    kel.append(f"{b_} paling efisien: {F.rupiah(v.loc[b_, 'cpiv'])} per kunjungan tambahan.")
    if len(v) > 1:
        kek.append(f"{w_} paling mahal: {F.rupiah(v.loc[w_, 'cpiv'])} per kunjungan tambahan.")
fmt = res.groupby("jenis_konten")["views"].median().sort_values(ascending=False)
if len(fmt) > 1:
    kel.append(f"Format '{fmt.index[0]}' menghasilkan median views tertinggi ({F.angka(fmt.iloc[0])}).")
    rek.append(f"Prioritaskan format '{fmt.index[0]}' pada brief berikutnya; kurangi '{fmt.index[-1]}'.")
telat = res[res["telat_hari"] > 0]
if not telat.empty:
    kek.append(f"{len(telat)} konten telat tayang ({', '.join(telat['username'].unique()[:4])}).")
    rek.append("Kirim brief ≥ H−14 dan pantau tahap Review di Timeline Produksi.")
nolift = res[(res["lift"].notna()) & (res["lift"] <= 0)]
if not nolift.empty:
    kek.append(f"Tidak ada dampak traffic di {nolift['toko'].nunique()} toko ({', '.join(nolift['toko'].str.replace('Mitra10 ', '').unique()[:4])}).")
    rek.append("Untuk toko tanpa dampak: ganti ke KOL dengan audiens lokal lebih tinggi atau tambahkan portal lokal.")
c1, c2, c3 = st.columns(3)
c1.markdown("**Kelebihan**\n" + "\n".join(f"- {x}" for x in kel or ["—"]))
c2.markdown("**Kekurangan**\n" + "\n".join(f"- {x}" for x in kek or ["—"]))
c3.markdown("**Rekomendasi**\n" + "\n".join(f"- {x}" for x in rek or ["—"]))
