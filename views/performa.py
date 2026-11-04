"""Layar 4 — Performa Toko & Zona: online vs offline per zona dan toko."""
import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, db, docs, ui
from lib import formulas as F
from lib.rbac import require

user = auth.current_user()
require(user["role"], "stores.view")
ui.header("Performa Toko & Zona", "Traffic offline (upload harian / POS) dibandingkan dampak konten online")
f = ui.global_filters(user, show_period=False)
sids = f["store_ids"]

stores = ui.stores()
needs = A.store_needs()
lifts = A.item_lifts()
views = db.df("""SELECT i.store_id, SUM(m.views) AS views FROM posts p JOIN submission_items i ON i.id=p.item_id
                 JOIN LATERAL (SELECT views FROM post_metrics pm WHERE pm.post_id=p.id ORDER BY (sumber='api') DESC LIMIT 1) m ON TRUE
                 WHERE p.tanggal_tayang >= NOW() - INTERVAL '90 days' GROUP BY i.store_id""")

# per toko
last_lift = (lifts.sort_values("tanggal").drop_duplicates("store_id", keep="last") if not lifts.empty else pd.DataFrame(
    columns=["store_id", "lift", "kunjungan_tambahan", "biaya_toko", "cpiv", "keyakinan", "campaign", "tanggal", "lift_low", "lift_high"]))
tbl = needs.merge(last_lift[["store_id", "lift", "lift_low", "lift_high", "kunjungan_tambahan", "biaya_toko", "cpiv", "keyakinan", "campaign", "tanggal"]],
                  on="store_id", how="left").merge(views, on="store_id", how="left")
tbl = tbl[tbl["store_id"].isin(sids)]


def kesimpulan(r):
    if pd.isna(r["lift"]):
        return "Belum ada campaign terukur"
    if r["lift_low"] > 0:
        return f"Dampak positif nyata ({F.persen(r['lift'] * 100, tanda=True)})"
    if r["lift_high"] < 0:
        return "Tidak berdampak / negatif"
    return "Dampak belum meyakinkan (interval melewati 0)"


def rekom(r):
    if pd.isna(r["lift"]):
        return "Uji 1 KOL lokal + portal" if r["skor"] >= 60 else "Pantau"
    if r["lift_low"] > 0 and (r["cpiv"] or 1e9) < 5000:
        return "Ulangi format & KOL yang sama"
    if r["lift_low"] > 0:
        return "Lanjutkan, negosiasi harga"
    return "Ganti KOL / format konten"


tbl["kesimpulan"] = tbl.apply(kesimpulan, axis=1)
tbl["rekomendasi"] = tbl.apply(rekom, axis=1)

# kartu zona
zt = tbl.groupby("zona").agg(traffic=("traffic_4mgg", "sum"), toko=("store_id", "count"),
                              views=("views", "sum"), lift=("lift", "mean")).reset_index()
base = A.store_baseline_table().merge(stores[["id", "zona"]], left_on="store_id", right_on="id")
base = base[base["store_id"].isin(sids)]
zfc = base.groupby("zona").agg(a=("traffic_4mgg", "sum"), f=("forecast_4mgg", "sum")).reset_index()
zt = zt.merge(zfc, on="zona", how="left")
order = [z for z in ui.zones()["nama"] if z in set(zt["zona"])]
zt = zt.set_index("zona").loc[order].reset_index()
st.markdown("#### Per zona")
for i in range(0, len(zt), 5):
    cols = st.columns(5)
    for c, (_, r) in zip(cols, zt.iloc[i:i + 5].iterrows()):
        vs = (r["a"] / r["f"] - 1) * 100 if r["f"] else 0
        c.markdown(
            f"<div class='kh-card'><div class='kh-kpi-l'>{ui.esc(r['zona'])} · {int(r['toko'])} toko</div>"
            f"<div class='kh-kpi-v' style='font-size:1.3rem'>{F.angka(r['traffic'])}</div>"
            f"<div class='kh-kpi-s'>traffic offline 4 mgg · {F.persen(vs, tanda=True)} vs forecast</div>"
            f"<div class='kh-kpi-s'>views KOL 90 hr {F.angka(r['views'] or 0)} · lift {F.persen((r['lift'] or 0) * 100, tanda=True) if pd.notna(r['lift']) else '—'}</div></div>",
            unsafe_allow_html=True)
    st.write("")

st.markdown("#### Traffic mingguan per zona")
w = A.weekly(sids)
w = w.merge(stores[["id", "zona"]], left_on="store_id", right_on="id")
w = w[w["minggu"] >= w["minggu"].max() - pd.Timedelta(weeks=12)]
st.line_chart(w.groupby(["minggu", "zona"])["kunjungan"].sum().unstack(), height=260)

st.markdown("#### Per toko")
show = pd.DataFrame({
    "Toko": tbl["toko"], "Zona": tbl["zona"], "Traffic 4 mgg": tbl["traffic_4mgg"], "vs forecast": tbl["vs_forecast"],
    "Campaign terakhir": tbl["campaign"].fillna("—"), "Lift": tbl["lift"] * 100, "Kunjungan tambahan": tbl["kunjungan_tambahan"],
    "Biaya per kunjungan tambahan": tbl["cpiv"], "Keyakinan": tbl["keyakinan"].fillna("—"), "Kesimpulan": tbl["kesimpulan"],
    "Rekomendasi": tbl["rekomendasi"]})
st.dataframe(show, hide_index=True, use_container_width=True, height=440, column_config={
    "Traffic 4 mgg": st.column_config.NumberColumn(format="%d"),
    "vs forecast": st.column_config.NumberColumn(format="%+.1f%%"),
    "Lift": st.column_config.NumberColumn(format="%+.1f%%"),
    "Kunjungan tambahan": st.column_config.NumberColumn(format="%d"),
    "Biaya per kunjungan tambahan": st.column_config.NumberColumn("CPIV (Rp)", format="Rp %d")})
ui.note("Lift = DiD bentuk rasio terhadap toko pembanding dari klaster serupa yang tidak ber-campaign; hari bertanda 'event' "
        "dikeluarkan; keyakinan dari bootstrap 90% (rumus B.6 no. 8).")
st.download_button("Unduh Excel", data=docs.to_excel(show, "performa_toko"),
                   file_name="performa_toko.xlsx")
