"""Layar 8 — Mapping Toko, Zona & KOL: traffic offline, dampak campaign, dan KOL yang disarankan per toko."""
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, db, ui
from lib import formulas as F
from lib import workflow as W
from lib.rbac import can, require

user = auth.current_user()
require(user["role"], "kol.view")
ui.header("Mapping Toko, Zona & KOL", "Traffic offline & historisnya, dampak campaign, dan KOL yang disarankan per toko")
ui.flash()

stores = ui.stores()
needs = A.store_needs()
c1, c2 = st.columns([1, 2])
zsel = c1.selectbox("Zona", ["Semua"] + list(ui.zones()["nama"]), key="mp_zone")
pool = stores if zsel == "Semua" else stores[stores["zona"] == zsel]
default = st.session_state.get("sel_store")
names = list(pool["nama"])
idx = names.index(stores.set_index("id").loc[default, "nama"]) if default in set(pool["id"]) else 0
ssel = c2.selectbox("Toko", names, index=idx, key="mp_store")
store_id = int(pool[pool["nama"] == ssel]["id"].iloc[0])
st.session_state["sel_store"] = store_id
srow = stores[stores["id"] == store_id].iloc[0]
nrow = needs[needs["store_id"] == store_id]

m1, m2 = st.columns([1, 1.6], gap="medium")
with m1:
    mp = pool.merge(needs[["store_id", "skor"]], left_on="id", right_on="store_id", how="left")
    mp["color"] = mp["skor"].map(lambda s: "#dc2626" if s >= 80 else "#f59e0b" if s >= 60 else "#16a34a")
    mp.loc[mp["id"] == store_id, "color"] = "#1d4ed8"
    mp["size"] = 2500 + (mp["skor"].fillna(50) * 60)
    st.map(mp, latitude="lat", longitude="lon", color="color", size="size", height=300)
    ui.note("Warna: merah skor butuh ≥ 80, kuning ≥ 60, hijau < 60, biru = toko terpilih.")
with m2:
    if not nrow.empty:
        n = nrow.iloc[0]
        ui.kpis([
            {"label": "Traffic 4 minggu", "value": F.angka(n["traffic_4mgg"]), "sub": f"{F.persen(n['vs_forecast'], tanda=True)} vs forecast"},
            {"label": "Skor butuh KOL", "value": f"{n['skor']:.0f}", "sub": n["saran"], "highlight": True},
            {"label": "Campaign terakhir", "value": "Belum pernah" if n["hari_sejak"] >= 365 else f"{int(n['hari_sejak'])} hari",
             "sub": f"respons historis {F.persen(n['responsivitas'] * 100, tanda=True)}"},
        ])
        st.markdown(ui.reasons(n["alasan"]), unsafe_allow_html=True)
    st.markdown("#### Traffic offline 12 minggu: aktual vs estimasi tanpa campaign")
    fs = A.forecast_series(store_id, 12)
    if not fs.empty:
        long = fs.melt(id_vars=["minggu", "campaign"], value_vars=["aktual", "estimasi"], var_name="seri", value_name="kunjungan")
        lines = alt.Chart(long).mark_line(point=True).encode(
            x=alt.X("minggu:T", title=None), y=alt.Y("kunjungan:Q", title="Kunjungan/minggu", scale=alt.Scale(zero=False)),
            color=alt.Color("seri:N", scale=alt.Scale(domain=["aktual", "estimasi"], range=["#1d4ed8", "#94a3b8"]), title=None),
            strokeDash=alt.condition(alt.datum.seri == "estimasi", alt.value([5, 4]), alt.value([0])))
        marks = alt.Chart(fs[fs["campaign"]]).mark_rule(color="#f97316", strokeWidth=2).encode(x="minggu:T")
        st.altair_chart((marks + lines).properties(height=250), use_container_width=True)
        ui.note("Garis oranye = minggu campaign. Estimasi = median musiman 8 minggu sebelumnya (hari campaign & event dikeluarkan).")

st.markdown("#### Analisa dampak campaign terhadap traffic offline")
lifts = A.item_lifts()
sl = lifts[lifts["store_id"] == store_id].drop_duplicates("tanggal") if not lifts.empty else pd.DataFrame()
if sl.empty:
    st.caption("Belum ada campaign yang tayang ≥ 7 hari di toko ini.")
else:
    names_by_id = stores.set_index("id")["short"]
    show = pd.DataFrame({
        "Campaign": sl["campaign"].fillna("Tunggal"), "Tayang": sl["tanggal"].dt.date,
        "Kunjungan tambahan": sl["kunjungan_tambahan"].round(),
        "Rentang 90%": [f"{F.angka(a)} – {F.angka(b)}" for a, b in zip(sl["extra_low"], sl["extra_high"])],
        "Lift": sl["lift"] * 100, "Keyakinan": sl["keyakinan"], "Biaya": sl["biaya_toko"], "CPIV": sl["cpiv"],
        "Toko pembanding": sl["pembanding"].map(lambda ids: ", ".join(names_by_id.get(i, str(i)) for i in ids))})
    st.dataframe(show, hide_index=True, use_container_width=True, column_config={
        "Kunjungan tambahan": st.column_config.NumberColumn(format="%d"), "Lift": st.column_config.NumberColumn(format="%+.1f%%"),
        "Biaya": st.column_config.NumberColumn(format="Rp %d"), "CPIV": st.column_config.NumberColumn(format="Rp %d")})
    r0 = sl.iloc[-1]
    st.markdown(f"Contoh perhitungan ({r0['campaign']}): pre {F.angka(r0['pre'])}/minggu, pembanding naik "
                f"{F.persen(r0['pembanding_naik'] * 100, tanda=True)} → counterfactual {F.angka(r0['counterfactual'])}; aktual "
                f"{F.angka(r0['post'])} → lift {F.persen(r0['lift'] * 100, tanda=True)}.")

with st.expander("Traffic offline historis (seluruh data)"):
    w = A.weekly([store_id])
    if not w.empty:
        st.area_chart(w.set_index("minggu")["kunjungan"], height=220)

st.markdown("#### KOL / Portal News yang disarankan")
rec = A.recommend_for_store(store_id, k=8)
if rec.empty:
    st.info("Belum ada KOL yang memenuhi syarat (aktif & skor ≥ 50).")
    st.stop()
rec_show = pd.DataFrame({
    "Pilih": False, "KOL": rec["username"], "Platform": rec["platform"], "Kategori": rec["kategori"],
    "Audiens lokal": rec["audiens_lokal"] * 100, "Skor": rec["skor"].round(0),
    "Prediksi kunjungan": [f"+{F.angka(a)} – {F.angka(b)}" for a, b in zip(rec["prediksi_low"], rec["prediksi_high"])],
    "Saran harga": rec["harga_wajar"], "Ratecard": rec["harga"], "Alasan": rec["alasan"].map(" · ".join), "id": rec["id"]})
edited = st.data_editor(rec_show, hide_index=True, use_container_width=True, disabled=[c for c in rec_show.columns if c != "Pilih"],
                        column_config={"id": None, "Audiens lokal": st.column_config.NumberColumn(format="%.0f%%"),
                                       "Skor": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
                                       "Saran harga": st.column_config.NumberColumn(format="Rp %d"),
                                       "Ratecard": st.column_config.NumberColumn(format="Rp %d")}, key=f"rec_{store_id}")
ui.note("Rank = 0,35·audiens lokal + 0,25·skor + 0,25·lift historis toko/zona + 0,15·kemiripan konten dengan kebutuhan dari social "
        "listening; KOL baru dieksplorasi dengan Thompson sampling; MMR mencegah audiens tumpang tindih > 60%.")

if can(user["role"], "campaign.edit"):
    picked = edited[edited["Pilih"]]
    st.markdown("#### Ajukan")
    drafts = db.df("""SELECT s.id AS sub_id, c.id, c.no_campaign, c.nama, c.jenis FROM campaigns c
                      JOIN submissions s ON s.campaign_id=c.id WHERE s.status IN ('Draft','Revisi') ORDER BY c.created_at DESC""")
    a1, a2, a3 = st.columns([1.2, 2, 1])
    jenis = a1.radio("Jenis", ["Grup", "Tunggal"], horizontal=True)
    tgl = a3.date_input("Rencana tayang", date.today() + timedelta(days=14))
    if jenis == "Grup":
        opts = ["+ Buat campaign baru"] + (drafts["no_campaign"] + " — " + drafts["nama"]).tolist()
        target = a2.selectbox("Masukkan ke campaign draft", opts)
    if st.button(f"Ajukan {len(picked)} KOL", type="primary", disabled=picked.empty):
        try:
            if jenis == "Tunggal":
                for _, p in picked.iterrows():
                    r = rec[rec["id"] == p["id"]].iloc[0]
                    W.create_single_submission(user, int(p["id"]), store_id, float(r["harga_wajar"] if r["harga"] > r["batas_nego"] else r["harga"]), tgl)
                st.session_state["flash_ok"] = f"{len(picked)} pengajuan tunggal dibuat sebagai draft — buka menu Campaign & Pengajuan."
                st.rerun()
            elif target.startswith("+"):
                ui.go("views/campaign.py", new_campaign_prefill={"store_ids": [store_id], "kols": picked["id"].astype(int).tolist(), "tanggal": tgl})
            else:
                sub_id = int(drafts.iloc[opts.index(target) - 1]["sub_id"])
                for _, p in picked.iterrows():
                    W.add_item(user, sub_id, int(p["id"]), store_id, None, tgl)
                ui.go("views/draft.py", sel_sub=sub_id, flash_ok=f"{len(picked)} KOL masuk ke draft {target}.")
        except W.WorkflowError as e:
            st.error(str(e))
