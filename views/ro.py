"""Layar 14 — Form Approval RO (cetak): dokumen RO siap cetak setelah disetujui."""
import pandas as pd
import streamlit as st

from lib import auth, db, docs, ui
from lib import formulas as F
from lib import workflow as W
from lib.rbac import can, require

user = auth.current_user()
require(user["role"], "ro.view")
ui.header("Form Approval RO", "Hardcopy bertanda tangan = bukti pengesahan; scan diunggah kembali & salinan digital otomatis masuk menu Finance")
ui.flash()

ros = db.df("""SELECT r.id, r.no_ro, r.status, r.kode_verifikasi, r.created_at, r.scan_nama, s.id AS sub_id, s.no_pengajuan, s.revisi_ke,
                      s.status AS sub_status, c.no_campaign, c.nama
               FROM ro_forms r JOIN submissions s ON s.id=r.submission_id LEFT JOIN campaigns c ON c.id=s.campaign_id
               ORDER BY r.created_at DESC""")
if ros.empty:
    st.info("Belum ada Form RO. Form RO dibuat otomatis setelah pengajuan disetujui Manager.")
    st.stop()
c1, c2 = st.columns([3, 1])
only_open = c2.toggle("Hanya belum ditandatangani", value=False)
view = ros[ros["status"] != "ditandatangani"] if only_open else ros
ids = view["id"].tolist() or ros["id"].tolist()
sel = st.session_state.get("sel_ro")
if not sel and st.session_state.get("sel_sub") in set(ros["sub_id"]):
    sel = int(ros[ros["sub_id"] == st.session_state["sel_sub"]]["id"].iloc[0])
pick = c1.selectbox("Form RO", ids, index=ids.index(sel) if sel in ids else 0,
                    format_func=lambda i: (lambda r: f"{r['no_ro']} · {r['no_pengajuan']} · {r['nama'] if pd.notna(r['nama']) else 'Pengajuan tunggal'} · {r['status']}")(ros.set_index('id').loc[i]))
st.session_state["sel_ro"] = pick
ro = ros.set_index("id").loc[pick].to_dict()
ro["id"] = pick

items = db.query("""SELECT k.nama AS kol_nama, k.username, k.platform, st.nama AS toko, i.deliverable, i.tanggal_posting, i.harga_nego,
                           p.pajak_jenis, p.pajak_nominal, p.invoice_no, p.status AS bayar
                    FROM submission_items i JOIN kol_accounts k ON k.id=i.kol_id JOIN stores st ON st.id=i.store_id
                    LEFT JOIN payments p ON p.item_id=i.id
                    WHERE i.submission_id=%s AND i.aktif AND i.keputusan_item='setuju' ORDER BY st.nama""", (int(ro["sub_id"]),))
approvals = db.query("""SELECT a.level, a.keputusan, a.waktu, u.nama FROM approvals a LEFT JOIN users u ON u.id=a.approver_id
                        WHERE a.submission_id=%s AND a.revisi_ke=%s ORDER BY a.level""", (int(ro["sub_id"]), int(ro["revisi_ke"])))
camp = {"no_campaign": ro["no_campaign"], "nama": ro["nama"]} if pd.notna(ro["no_campaign"]) else None
sub = {"no_pengajuan": ro["no_pengajuan"], "revisi_ke": int(ro["revisi_ke"])}

total = sum(i["harga_nego"] for i in items)
pajak = sum(i["pajak_nominal"] or 0 for i in items)
ui.kpis([{"label": "No. RO", "value": ro["no_ro"], "sub": f"ref. {ro['no_pengajuan']}" + (f" · {ro['no_campaign']}" if camp else "")},
         {"label": "Total", "value": F.rupiah(total), "sub": f"pajak {F.rupiah(pajak)} · neto {F.rupiah(total - pajak)}"},
         {"label": "Status RO", "value": ro["status"].title(), "sub": f"pengajuan: {ro['sub_status']}"},
         {"label": "Kode verifikasi", "value": ro["kode_verifikasi"], "sub": "tercetak pada dokumen"}])
st.write("")
st.dataframe(pd.DataFrame(items), hide_index=True, use_container_width=True, column_config={
    "harga_nego": st.column_config.NumberColumn("Harga", format="Rp %d"), "pajak_nominal": st.column_config.NumberColumn("Pajak", format="Rp %d")})
st.markdown("**Jejak approval:** " + (" · ".join(f"Level {a['level']} {a['keputusan']} oleh {a['nama'] or '—'} ({a['waktu']:%d/%m/%Y})"
                                                for a in approvals) or "—"))

pdf = docs.ro_pdf(ro, sub, items, approvals, camp)
b1, b2, b3 = st.columns(3)
if b1.download_button("Unduh PDF untuk dicetak", pdf, file_name=f"{ro['no_ro']}.pdf", mime="application/pdf", type="primary",
                      use_container_width=True, disabled=not can(user["role"], "ro.view")):
    if can(user["role"], "ro.manage"):
        W.mark_ro_printed(user, pick, pdf)
if ro["scan_nama"]:
    scan = db.scalar("SELECT scan_ttd FROM ro_forms WHERE id=%s", (pick,))
    b2.download_button("Unduh scan bertanda tangan", scan or b"", file_name=ro["scan_nama"], use_container_width=True)

if can(user["role"], "ro.manage") and ro["status"] != "ditandatangani":
    st.markdown("#### Unggah scan bertanda tangan")
    st.caption("Kotak tanda tangan: Dibuat · Diperiksa · Disetujui · Diterima. Setelah diunggah, pembayaran per baris diproses bila bukti tayang lengkap.")
    up = st.file_uploader("Scan RO (PDF/JPG/PNG)", type=["pdf", "jpg", "jpeg", "png"], key=f"scan_{pick}")
    if up and st.button("Simpan scan & kirim ke Finance", type="primary"):
        try:
            W.upload_signed_ro(user, pick, up.name, up.getvalue())
            st.session_state["flash_ok"] = f"Scan {ro['no_ro']} tersimpan — salinan digital masuk menu Finance."
            st.rerun()
        except W.WorkflowError as e:
            st.error(str(e))
elif ro["status"] == "ditandatangani":
    st.success("RO sudah ditandatangani dan berada di menu Finance.")
