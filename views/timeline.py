"""Layar 16 — Timeline Produksi Konten: Pitching → Brief → Take konten → Review → Posting → Pelaporan."""
from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from lib import auth, db, ui
from lib.master import PROD_STAGES
from lib.rbac import can, require

user = auth.current_user()
require(user["role"], "calendar.view")
ui.header("Timeline Produksi Konten", "Gantt per KOL · tahap terlambat ditandai · aturan otomatis & notifikasi")
ui.flash()

scope, params = "", []
if user["role"] == "store":
    scope, params = " AND i.store_id = %s", [user.get("scope_store_id") or -1]
t = db.df(f"""SELECT t.id, t.item_id, t.tahap, t.urutan, t.mulai, t.selesai, t.status, t.revisi, k.username, st.nama AS toko,
                     COALESCE(c.nama, 'Tunggal ' || s.no_pengajuan) AS campaign, i.tanggal_posting, p.tanggal_tayang
              FROM production_tasks t JOIN submission_items i ON i.id=t.item_id JOIN submissions s ON s.id=i.submission_id
              LEFT JOIN campaigns c ON c.id=s.campaign_id JOIN kol_accounts k ON k.id=i.kol_id JOIN stores st ON st.id=i.store_id
              LEFT JOIN posts p ON p.item_id=i.id
              WHERE i.aktif{scope} ORDER BY i.tanggal_posting, k.username, t.urutan""", params)
if t.empty:
    st.info("Belum ada timeline. Timeline dibuat otomatis saat Form RO dibuat (mundur dari tanggal tayang).")
    st.stop()

today = date.today()
t["terlambat"] = (t["status"] != "selesai") & (pd.to_datetime(t["selesai"]).dt.date < today)
camps = ["Semua"] + sorted(t["campaign"].unique())
csel = st.selectbox("Campaign", camps)
v = t if csel == "Semua" else t[t["campaign"] == csel]
v = v.assign(baris=v["username"] + " · " + v["toko"].str.replace("Mitra10 ", ""),
             label=v["tahap"].map(dict(PROD_STAGES)),
             warna=v.apply(lambda r: "terlambat" if r["terlambat"] else r["status"], axis=1),
             selesai_plot=pd.to_datetime(v["selesai"]) + pd.Timedelta(days=1))
late = v[v["terlambat"]]
ui.kpis([{"label": "Item diproduksi", "value": str(v["item_id"].nunique())},
         {"label": "Tahap terlambat", "value": str(len(late)), "sub_tone": "neg" if len(late) else "", "sub": "perlu tindakan" if len(late) else "aman"},
         {"label": "Tayang 7 hari ke depan", "value": str(v[(pd.to_datetime(v["tanggal_posting"]).dt.date >= today) &
                                                         (pd.to_datetime(v["tanggal_posting"]).dt.date <= today + timedelta(days=7))]["item_id"].nunique())},
         {"label": "Menunggu laporan", "value": str(v[(v["tahap"] == "lapor") & (v["status"] != "selesai")]["item_id"].nunique())}])

chart = alt.Chart(v).mark_bar(cornerRadius=3, height=14).encode(
    x=alt.X("mulai:T", title=None), x2="selesai_plot:T", y=alt.Y("baris:N", title=None, sort=None),
    color=alt.Color("warna:N", title=None, scale=alt.Scale(domain=["selesai", "berjalan", "belum", "terlambat"],
                                                           range=["#16a34a", "#1d4ed8", "#cbd5e1", "#dc2626"])),
    tooltip=["username", "toko", "label", "mulai", "selesai", "status", "revisi"])
text = alt.Chart(v).mark_text(align="left", dx=3, fontSize=9, color="#0f172a").encode(x="mulai:T", y=alt.Y("baris:N", sort=None), text="label")
rule = alt.Chart(pd.DataFrame({"hari_ini": [pd.Timestamp(today)]})).mark_rule(color="#f97316", strokeWidth=2).encode(x="hari_ini:T")
st.altair_chart((chart + text + rule).properties(height=max(220, 26 * v["baris"].nunique())), use_container_width=True)

c1, c2 = st.columns(2, gap="medium")
with c1:
    st.markdown("#### Aturan otomatis")
    st.markdown("""- Brief dikirim ≥ H−14 sebelum tayang
- Draft konten masuk ≥ H−3; revisi draft **maks 2×**
- Bukti tayang & insight wajib diunggah **H+3**
- Tahap lewat tenggat → ditandai merah & notifikasi ke E-commerce
- Pembayaran tertahan sampai bukti tayang, link, insight lengkap & RO ditandatangani""")
with c2:
    st.markdown("#### Notifikasi")
    alerts = [f"⛔ {r.username} — {r.label} terlambat sejak {r.selesai:%d %b} ({r.toko})" for r in late.itertuples()]
    rev = v[(v["tahap"] == "review") & (v["revisi"] >= 2) & (v["status"] != "selesai")]
    alerts += [f"⚠️ {r.username} — revisi sudah {r.revisi}× (batas 2)" for r in rev.itertuples()]
    noproof = v[(v["tahap"] == "posting") & pd.notna(v["tanggal_posting"]) & v["tanggal_tayang"].isna() &
                (pd.to_datetime(v["tanggal_posting"]).dt.date + timedelta(days=3) < today)]
    alerts += [f"📎 {r.username} — bukti tayang belum diunggah (H+3 lewat)" for r in noproof.itertuples()]
    st.markdown("\n".join(f"- {a}" for a in alerts) if alerts else "Tidak ada peringatan.")

if can(user["role"], "calendar.edit"):
    st.markdown("#### Perbarui tahap")
    items = (v[["item_id", "baris"]].drop_duplicates())
    a1, a2, a3, a4 = st.columns([2, 1.2, 1, 1])
    it = a1.selectbox("KOL", items["item_id"], format_func=lambda i: items.set_index("item_id").loc[i, "baris"])
    tahap = a2.selectbox("Tahap", [k for k, _ in PROD_STAGES], format_func=dict(PROD_STAGES).get)
    cur = v[(v["item_id"] == it) & (v["tahap"] == tahap)]
    status = a3.selectbox("Status", ["belum", "berjalan", "selesai"], index=["belum", "berjalan", "selesai"].index(cur["status"].iloc[0]) if len(cur) else 0)
    revisi = a4.number_input("Revisi", 0, 5, int(cur["revisi"].iloc[0]) if len(cur) else 0, disabled=tahap != "review")
    if st.button("Simpan", type="primary"):
        if tahap == "review" and revisi > 2:
            st.error("Revisi draft maksimal 2× sesuai aturan.")
        else:
            db.execute("UPDATE production_tasks SET status=%s, revisi=%s WHERE item_id=%s AND tahap=%s", (status, revisi, int(it), tahap))
            auth.log_activity(user["id"], "update_timeline", "item", int(it), f"{dict(PROD_STAGES)[tahap]} → {status}")
            st.rerun()
