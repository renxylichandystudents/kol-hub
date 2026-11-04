"""Layar 9 — Campaign & Pengajuan (lembar campaign): daftar campaign & nomor pengajuan/RO dengan status."""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from lib import auth, db, ui
from lib import formulas as F
from lib import workflow as W
from lib.rbac import can, require

user = auth.current_user()
require(user["role"], "campaign.view")
ui.header("Campaign & Pengajuan", "Lembar campaign: campaign dibuat dulu, lalu KOL dipilih, direkap, dan diajukan sebagai 1 file")
ui.flash()

sheet = db.df("""
    SELECT s.id AS sub_id, c.id AS campaign_id, COALESCE(c.no_campaign, '—') AS no_campaign,
           COALESCE(c.nama, 'Tunggal: ' || MAX(k.nama) || ' → ' || MAX(st.nama)) AS nama,
           s.jenis, COUNT(i.id) FILTER (WHERE i.aktif) AS jumlah_kol,
           COALESCE(SUM(i.harga_nego) FILTER (WHERE i.aktif), 0) AS total, c.budget,
           s.no_pengajuan, s.revisi_ke, r.no_ro, COALESCE(s.status, c.status) AS status, c.periode_mulai, s.created_at
    FROM submissions s LEFT JOIN campaigns c ON c.id = s.campaign_id
    LEFT JOIN submission_items i ON i.submission_id = s.id
    LEFT JOIN kol_accounts k ON k.id = i.kol_id LEFT JOIN stores st ON st.id = i.store_id
    LEFT JOIN ro_forms r ON r.submission_id = s.id
    GROUP BY s.id, c.id, r.no_ro ORDER BY s.created_at DESC""")

tab_sheet, tab_new = st.tabs(["Lembar campaign", "Buat campaign baru"])

with tab_sheet:
    if sheet.empty:
        st.info("Belum ada campaign.")
    else:
        c1, c2, c3 = st.columns([1, 1, 2])
        jf = c1.selectbox("Jenis", ["Semua", "grup", "tunggal"])
        sf = c2.selectbox("Status", ["Semua", "Perlu tindakan saya", "Draft", "Menunggu approval", "Ditolak/Revisi", "Disetujui & RO", "Di Finance", "Selesai"])
        q = c3.text_input("Cari no. / nama campaign / no. pengajuan / RO")
        d = sheet.copy()
        if jf != "Semua":
            d = d[d["jenis"] == jf]
        groups = {"Draft": ["Draft"], "Menunggu approval": ["Review Asisten Manager", "Review Manager"], "Ditolak/Revisi": ["Ditolak", "Revisi"],
                  "Disetujui & RO": ["Disetujui", "Form RO dibuat", "RO ditandatangani"], "Di Finance": ["Di Finance", "Dibayar sebagian"],
                  "Selesai": ["Lunas", "Selesai"]}
        if sf == "Perlu tindakan saya":
            mine = {"ecommerce": ["Draft", "Ditolak", "Revisi", "Form RO dibuat"], "super_user": ["Draft", "Ditolak", "Revisi", "Form RO dibuat"],
                    "asst_manager": ["Review Asisten Manager"], "manager": ["Review Manager"], "finance": ["Di Finance"]}.get(user["role"], [])
            d = d[d["status"].isin(mine)]
        elif sf != "Semua":
            d = d[d["status"].isin(groups[sf])]
        if q:
            ql = q.lower()
            d = d[d.apply(lambda r: ql in " ".join(str(x) for x in [r["no_campaign"], r["nama"], r["no_pengajuan"], r["no_ro"]]).lower(), axis=1)]
        show = pd.DataFrame({"No. campaign": d["no_campaign"], "Nama": d["nama"], "Jenis": d["jenis"].str.title(), "Jumlah KOL": d["jumlah_kol"],
                             "Total": d["total"], "Budget": d["budget"],
                             "No. pengajuan": d["no_pengajuan"] + d["revisi_ke"].map(lambda r: f" (rev {r})" if r else ""),
                             "No. RO": d["no_ro"].fillna("—"), "Status": d["status"]})
        st.dataframe(show, hide_index=True, use_container_width=True, height=380, column_config={
            "Total": st.column_config.NumberColumn(format="Rp %d"), "Budget": st.column_config.NumberColumn(format="Rp %d")})
        st.markdown("#### Buka")
        opts = (d["no_pengajuan"] + " · " + d["nama"] + " · " + d["status"]).tolist()
        if opts:
            o1, o2 = st.columns([3, 1.3])
            pick = o1.selectbox("Pengajuan", opts, label_visibility="collapsed")
            row = d.iloc[opts.index(pick)]
            sid, status = int(row["sub_id"]), row["status"]
            if status in ("Review Asisten Manager", "Review Manager") and (
                    can(user["role"], "submission.approve.level1") or can(user["role"], "submission.approve.level2")):
                if o2.button("Buka review", type="primary", use_container_width=True):
                    ui.go("views/approval.py", sel_sub=sid)
            elif status in ("Form RO dibuat", "RO ditandatangani", "Di Finance", "Dibayar sebagian", "Lunas", "Disetujui") and can(user["role"], "ro.view"):
                if o2.button("Buka Form RO", type="primary", use_container_width=True):
                    ui.go("views/ro.py", sel_sub=sid)
            elif can(user["role"], "campaign.edit"):
                if o2.button("Buka draft pengajuan", type="primary", use_container_width=True):
                    ui.go("views/draft.py", sel_sub=sid)
            ui.note("Pengajuan tunggal tampil sebagai satu baris dan dibuka langsung tanpa halaman campaign.")

with tab_new:
    if not can(user["role"], "campaign.edit"):
        st.caption("Hanya E-commerce / Super User yang membuat campaign.")
    else:
        pre = st.session_state.pop("new_campaign_prefill", None) or st.session_state.get("_prefill_keep")
        if pre:
            st.session_state["_prefill_keep"] = pre
            st.info(f"{len(pre.get('kols', []))} KOL dari halaman Mapping akan dimasukkan ke draft setelah campaign dibuat.")
        stores, zones = ui.stores(), ui.zones()
        with st.form("new_campaign"):
            nama = st.text_input("Nama campaign", placeholder="mis. Promo 12.12 — Year End Sale")
            c1, c2, c3 = st.columns(3)
            mulai = c1.date_input("Periode mulai", (pre or {}).get("tanggal") or date.today() + timedelta(days=14))
            selesai = c2.date_input("Periode selesai", mulai + timedelta(days=14))
            budget = c3.number_input("Budget (Rp)", min_value=0, step=1_000_000, value=60_000_000)
            tujuan = st.text_area("Tujuan", placeholder="mis. Menaikkan traffic toko selama promo; target +X kunjungan")
            c4, c5, c6 = st.columns(3)
            jenis = c4.radio("Jenis", ["grup", "tunggal"], horizontal=True, format_func=str.title)
            slot = c5.number_input("Slot KOL", min_value=1, max_value=50, value=max(len((pre or {}).get("kols", [])), 5))
            zsel = c6.multiselect("Zona", list(zones["nama"]),
                                  default=sorted({stores.set_index("id").loc[s, "zona"] for s in (pre or {}).get("store_ids", [])}))
            pool = stores[stores["zona"].isin(zsel)] if zsel else stores
            ssel = st.multiselect("Toko", list(pool["nama"]), default=[stores.set_index("id").loc[s, "nama"] for s in (pre or {}).get("store_ids", [])])
            ok = st.form_submit_button("Buat campaign", type="primary")
        if ok:
            try:
                zid = [int(zones[zones["nama"] == z]["id"].iloc[0]) for z in zsel]
                sids = [int(stores[stores["nama"] == s]["id"].iloc[0]) for s in ssel]
                res = W.create_campaign(user, nama, tujuan, mulai, selesai, budget, jenis, int(slot), zid, sids)
                if pre and pre.get("kols"):
                    for k in pre["kols"]:
                        W.add_item(user, res["submission_id"], int(k), pre["store_ids"][0], None, pre.get("tanggal"))
                    st.session_state.pop("_prefill_keep", None)
                    ui.go("views/draft.py", sel_sub=res["submission_id"], flash_ok=f"Campaign {res['no']} dibuat & KOL dimasukkan ke draft.")
                st.session_state.pop("_prefill_keep", None)
                ui.go("views/seleksi.py", sel_campaign=res["campaign_id"], flash_ok=f"Campaign {res['no']} dibuat — sekarang pilih KOL.")
            except W.WorkflowError as e:
                st.error(str(e))
