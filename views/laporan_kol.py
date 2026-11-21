"""Laporan performa per KOL / Portal — dasar keputusan lanjutkan, evaluasi, atau stop."""
import io
from datetime import date

import pandas as pd
import streamlit as st

from lib import auth, db, ui
from lib import formulas as F
from lib import kol_report as R
from lib.rbac import require

user = auth.current_user()
require(user["role"], "kol.view")
ui.header("Laporan Performa KOL & Portal",
          "Biaya vs hasil tiap akun dari semua campaign · metrik dari API Instagram/TikTok, OCR insight, atau input manual")
ui.flash()

c = st.columns([1.3, 1.2, 1.2, 1.4, 2])
today = date.today()
start, end = ui.date_range("Periode tayang", date(today.year, 1, 1), today, key="lap_range", container=c[0])
tipe = c[1].selectbox("Jenis", ["Semua", "KOL", "Portal"])
kep = c[2].selectbox("Keputusan", ["Semua", "Lanjutkan", "Evaluasi", "Stop", "Data belum cukup"])
zona = c[3].selectbox("Zona", ["Semua"] + list(ui.zones()["nama"]))
q = c[4].text_input("Cari akun / toko")

s = R.kol_summary(start, end)
if s.empty:
    st.info("Belum ada kerja sama yang tercatat. Impor file Excel KOL & Portal terlebih dahulu.")
    st.stop()
d = s.copy()
if tipe != "Semua":
    d = d[d["tipe"] == tipe.lower()]
if kep != "Semua":
    d = d[d["keputusan"] == kep]
if zona != "Semua":
    d = d[d["zona"].str.contains(zona, regex=False)]
if q:
    d = d[d["username"].str.contains(q, case=False, regex=False) | d["toko"].str.contains(q, case=False, regex=False)]

terukur = d[d["posting_terukur"] > 0]
ui.kpis([
    {"label": "Akun", "value": F.angka(len(d), False), "sub": f"{int((d['tipe'] == 'kol').sum())} KOL · {int((d['tipe'] == 'portal').sum())} portal"},
    {"label": "Total biaya", "value": F.rupiah(d["biaya"].sum()), "sub": f"{int(d['kerja_sama'].sum())} kerja sama"},
    {"label": "Posting terukur", "value": f"{int(d['posting_terukur'].sum())}/{int(d['kerja_sama'].sum())}",
     "sub": "punya views/like dari API atau insight"},
    {"label": "CPM median", "value": F.rupiah(terukur["cpm"].median()) if terukur["cpm"].notna().any() else "—",
     "sub": "biaya per 1.000 views", "highlight": True},
    {"label": "Keputusan", "value": f"{int((d['keputusan'] == 'Lanjutkan').sum())} lanjut",
     "sub": f"{int((d['keputusan'] == 'Evaluasi').sum())} evaluasi · {int((d['keputusan'] == 'Stop').sum())} stop"},
])
if d["posting_terukur"].sum() == 0:
    st.warning("Belum ada metrik posting (views/like). Hubungkan Instagram di menu **Koneksi Instagram & TikTok** lalu sinkron, "
               "atau unggah screenshot insight di **Bukti Tayang**. Sampai saat itu keputusan berstatus *Data belum cukup*.")
st.write("")

tab_tbl, tab_det, tab_bm = st.tabs(["Ringkasan per akun", "Detail akun", "Benchmark KOL vs Portal"])

with tab_tbl:
    show = pd.DataFrame({
        "Akun": "@" + d["username"], "Jenis": d["tipe"].str.upper(), "Keputusan": d["keputusan"], "Skor": d["skor"],
        "Kerja sama": d["kerja_sama"], "Terukur": d["posting_terukur"], "Biaya": d["biaya"], "Views": d["views"],
        "CPM": d["cpm"], "ER aktual %": d["er_aktual"].round(2), "ER klaim %": d["er_klaim"].round(2),
        "Follower": d["follower_terbaru"], "Δ follower %": d["follower_growth"].round(1), "Toko": d["toko"],
        "Terakhir": d["terakhir"], "Insight": d["insight"]})
    st.dataframe(show, hide_index=True, use_container_width=True, height=520, column_config={
        "Skor": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
        "Biaya": st.column_config.NumberColumn(format="Rp %d"), "CPM": st.column_config.NumberColumn(format="Rp %d"),
        "Views": st.column_config.NumberColumn(format="%d"), "Follower": st.column_config.NumberColumn(format="%d")})
    ui.note("Skor 0–100 dibanding akun sejenis (KOL vs KOL, portal vs portal): CPM 40% (makin murah makin baik), ER aktual 25%, "
            "konsistensi views 15%, pertumbuhan follower 10%, frekuensi kerja sama 10%; komponen tanpa data tidak dihitung. "
            "Lanjutkan ≥ 65 tanpa tanda bahaya · Stop bila skor < 35 dan CPM > 1,5× median jenisnya, atau ≥ 2 tanda bahaya "
            "(ER aktual < 40% klaim, follower turun > 10%).")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        show.to_excel(xw, sheet_name="Ringkasan", index=False)
        R.post_level(start, end).drop(columns=["item_id"], errors="ignore").to_excel(xw, sheet_name="Per posting", index=False)
    st.download_button("Unduh laporan (Excel)", buf.getvalue(), file_name=f"laporan_kol_{today:%Y%m%d}.xlsx", icon=":material/download:")

with tab_det:
    pick = st.selectbox("Akun", d["kol_id"], format_func=lambda x: "@" + d.set_index("kol_id").loc[x, "username"])
    if pick is not None:
        r = d.set_index("kol_id").loc[pick]
        tone = {"Lanjutkan": "green", "Evaluasi": "amber", "Stop": "red"}.get(r["keputusan"], "gray")
        st.markdown(f"### @{ui.esc(r['username'])} {ui.badge(r['keputusan'], tone)}", unsafe_allow_html=True)
        st.markdown(ui.esc(r["insight"]))
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Biaya total", F.rupiah(r["biaya"]))
        k2.metric("Views total", F.angka(r["views"]) if pd.notna(r["views"]) else "—")
        k3.metric("CPM", F.rupiah(r["cpm"]) if pd.notna(r["cpm"]) else "—")
        k4.metric("Follower terbaru", F.angka(r["follower_terbaru"]) if pd.notna(r["follower_terbaru"]) else "—",
                  f"{round(r['follower_growth']):+d}%" if pd.notna(r["follower_growth"]) else None)
        ft = R.follower_trend()
        ft = ft[ft["kol_id"] == pick].dropna(subset=["follower"])
        if len(ft) >= 2:
            st.markdown("**Tren follower**")
            st.line_chart(ft.set_index("tanggal")["follower"], height=200)
        p = R.post_level(start, end)
        p = p[p["kol_id"] == pick].sort_values("tanggal", ascending=False)
        st.markdown("**Riwayat posting**")
        st.dataframe(pd.DataFrame({"Tanggal": p["tanggal"], "Campaign": p["campaign"], "Toko": p["toko"], "Konten": p["deliverable"],
                                   "Biaya": p["biaya"], "Views": p["views_total"], "Like": p["likes"], "Komentar": p["komentar"],
                                   "Share": p["share"], "ER %": p["er_post"].round(2), "CPM": p["cpm"], "Sumber": p["sumber"], "Link": p["link"]}),
                     hide_index=True, use_container_width=True, column_config={
                         "Biaya": st.column_config.NumberColumn(format="Rp %d"), "CPM": st.column_config.NumberColumn(format="Rp %d"),
                         "Link": st.column_config.LinkColumn()})

with tab_bm:
    bm = R.benchmark(s)
    st.dataframe(bm.rename(columns={"tipe": "Jenis", "akun": "Akun", "biaya": "Biaya", "views": "Views", "cpm_median": "CPM median",
                                    "er_median": "ER median %"}), hide_index=True, use_container_width=True,
                 column_config={"Biaya": st.column_config.NumberColumn(format="Rp %d"), "CPM median": st.column_config.NumberColumn(format="Rp %d")})
    zt = R.post_level(start, end)
    if not zt.empty:
        z = zt.groupby(["zona", "tipe"]).agg(biaya=("biaya", "sum"), posting=("item_id", "size"), views=("views_total", "sum")).reset_index()
        z["CPM"] = z["biaya"] / z["views"].where(z["views"] > 0) * 1000
        st.markdown("**Per zona**")
        st.dataframe(z.rename(columns={"zona": "Zona", "tipe": "Jenis", "biaya": "Biaya", "posting": "Posting", "views": "Views"}),
                     hide_index=True, use_container_width=True,
                     column_config={"Biaya": st.column_config.NumberColumn(format="Rp %d"), "CPM": st.column_config.NumberColumn(format="Rp %d")})
