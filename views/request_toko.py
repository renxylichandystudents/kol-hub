"""Layar 22 — Request KOL / Portal (Toko): layar untuk role Store."""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, db, ui
from lib import formulas as F
from lib import workflow as W
from lib.rbac import Forbidden, require

user = auth.current_user()
require(user["role"], "request.create")
ui.header("Request KOL / Portal News", "Ajukan kebutuhan KOL untuk toko: pilih dari database yang disarankan, atau kirim akun yang belum ada")
ui.flash()

stores = ui.stores()
if user["role"] == "store":
    store_id = user.get("scope_store_id")
    if not store_id:
        st.error("Akun Store belum memiliki cakupan toko. Hubungi Super User.")
        st.stop()
    st.markdown(f"Toko: **{stores.set_index('id').loc[store_id, 'nama']}**")
else:
    store_id = int(stores[stores["nama"] == st.selectbox("Toko", list(stores["nama"]))]["id"].iloc[0])

sumber = st.radio("Akun", ["Pilih dari database (disarankan untuk toko ini)", "Akun belum ada di database"], horizontal=True)
with st.form("req"):
    kebutuhan = st.text_area("Kebutuhan", placeholder="mis. traffic akhir pekan turun; butuh KOL lokal untuk promo cat")
    c1, c2 = st.columns(2)
    mulai = c1.date_input("Periode mulai", date.today() + timedelta(days=14))
    selesai = c2.date_input("Periode selesai", date.today() + timedelta(days=28))
    rec = A.recommend_for_store(store_id, k=8, seed=store_id)
    kol_id, new_acc, rc, file = None, None, None, None
    if sumber.startswith("Pilih"):
        if rec.empty:
            st.caption("Belum ada saran untuk toko ini.")
        else:
            kol_id = st.selectbox("KOL / Portal disarankan", rec["id"].tolist(), format_func=lambda k: (lambda r:
                                  f"{r['username']} · {r['platform']} · skor {r['skor']:.0f} · audiens lokal {r['audiens_lokal'] * 100:.0f}% · "
                                  f"prediksi +{F.angka(r['prediksi_low'])}–{F.angka(r['prediksi_high'])} kunjungan")(rec.set_index("id").loc[k]))
            rc = float(rec.set_index("id").loc[kol_id, "harga"]) if kol_id else None
    else:
        a1, a2, a3 = st.columns(3)
        nama = a1.text_input("Nama akun")
        plat = a2.selectbox("Platform", ["Instagram", "TikTok", "Portal News"])
        un = a3.text_input("Username")
        b1, b2, b3 = st.columns(3)
        link = b1.text_input("Link")
        fol = b2.number_input("Follower", min_value=0, step=1000)
        rc = b3.number_input("Ratecard (Rp)", min_value=0, step=100_000)
        bio = st.text_input("Deskripsi akun / bio")
        k1, k2 = st.columns(2)
        kontak = k1.text_input("Kontak")
        kota = k2.text_input("Kota domisili", stores.set_index("id").loc[store_id, "kota"])
        mk = st.file_uploader("File media kit / ratecard", type=["pdf", "png", "jpg", "jpeg"])
        new_acc = {"nama": nama, "platform": plat, "username": un, "link": link, "follower": fol, "kontak": kontak, "bio": bio, "kota": kota}
        file = (mk.name, mk.getvalue()) if mk else None
    ok = st.form_submit_button("Kirim request", type="primary")
if ok:
    if not kebutuhan.strip():
        st.error("Kebutuhan wajib diisi.")
    elif new_acc is not None and not (new_acc["nama"] and new_acc["username"] and new_acc["link"]):
        st.error("Nama, username, dan link akun baru wajib diisi.")
    elif new_acc is None and not kol_id:
        st.error("Pilih akun.")
    else:
        try:
            no = W.create_request(user, store_id, kebutuhan, mulai, selesai, kol_id, new_acc, rc, file)
            st.session_state["flash_ok"] = f"Request {no} terkirim ke Digital Marketing."
            st.rerun()
        except (Forbidden, W.WorkflowError) as e:
            st.error(str(e))

st.markdown("#### Status request")
mine = db.df("""SELECT r.no_request, r.created_at, r.kebutuhan, COALESCE(k.username, r.data_akun_baru_json->>'username') AS akun,
                       CASE WHEN r.kol_id IS NULL OR r.data_akun_baru_json IS NOT NULL THEN 'akun baru' ELSE 'dari database' END AS jenis,
                       r.ratecard, r.status, r.catatan
                FROM store_requests r LEFT JOIN kol_accounts k ON k.id=r.kol_id WHERE r.store_id=%s ORDER BY r.created_at DESC""", (store_id,))
if mine.empty:
    st.caption("Belum ada request.")
else:
    st.dataframe(mine, hide_index=True, use_container_width=True, column_config={
        "created_at": st.column_config.DatetimeColumn("Diajukan", format="DD MMM YYYY"), "ratecard": st.column_config.NumberColumn(format="Rp %d"),
        "status": "Status", "catatan": "Catatan Digital Marketing"})
    ui.note("Status: Diajukan → direview Digital Marketing → Disetujui (diproses sebagai pengajuan tunggal / masuk draft campaign) · Ditolak (dengan alasan) · Minta info.")
