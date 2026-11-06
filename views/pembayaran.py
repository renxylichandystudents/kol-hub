"""Layar 21 — Pembayaran & Pajak: role Finance; pengajuan disetujui masuk otomatis."""
import os
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from lib import auth, db, docs, ui
from lib import formulas as F
from lib import workflow as W
from lib.rbac import can, require

user = auth.current_user()
require(user["role"], "payment.view")
manage = can(user["role"], "payment.manage")
ui.header("Pembayaran & Pajak", "Pengajuan yang disetujui masuk otomatis · pembayaran tertahan bila bukti tayang/dokumen belum lengkap")
ui.flash()

pay = db.df("""SELECT p.id, p.invoice_no, p.nominal, p.pajak_jenis, p.pajak_nominal, p.status, p.alasan_tertahan, p.created_at, p.paid_at,
                      r.id AS ro_id, r.no_ro, r.status AS status_ro, s.no_pengajuan, s.jenis, COALESCE(c.no_campaign, '—') AS no_campaign,
                      COALESCE(c.nama, 'Tunggal') AS campaign, k.id AS kol_id, k.nama AS vendor, k.username, k.badan_hukum,
                      st.nama AS toko, z.nama AS zona, (po.bukti IS NOT NULL) AS ada_bukti, (po.insight IS NOT NULL) AS ada_insight, po.link,
                      (SELECT COUNT(*) FROM vendor_documents d WHERE d.kol_id=k.id AND d.terverifikasi) AS dok_ok
               FROM payments p JOIN ro_forms r ON r.id=p.ro_id JOIN submissions s ON s.id=r.submission_id
               LEFT JOIN campaigns c ON c.id=s.campaign_id JOIN submission_items i ON i.id=p.item_id
               JOIN kol_accounts k ON k.id=i.kol_id JOIN stores st ON st.id=i.store_id JOIN zones z ON z.id=st.zone_id
               LEFT JOIN posts po ON po.item_id=p.item_id
               ORDER BY p.created_at DESC""")
if pay.empty:
    st.info("Belum ada pembayaran. Baris pembayaran dibuat otomatis saat pengajuan disetujui Manager.")
    st.stop()
pay["created_at"] = pd.to_datetime(pay["created_at"], utc=True)
pay["umur"] = (pd.Timestamp.now(tz="UTC") - pay["created_at"]).dt.days
pay["neto"] = pay["nominal"] - pay["pajak_nominal"]

new = pay[pay["created_at"] >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)].drop_duplicates("ro_id")
if not new.empty:
    st.markdown("#### ✦ Masuk otomatis dari approval (7 hari terakhir)")
    for r in new.itertuples():
        st.markdown(f"- **{r.no_ro}** · {r.no_pengajuan} · {ui.esc(r.campaign)} · status RO {ui.status_badge(r.status_ro)}", unsafe_allow_html=True)

with st.expander("Filter", expanded=False):
    f1, f2, f3, f4, f5 = st.columns(5)
    d_from = f1.date_input("Dari tanggal", date.today() - timedelta(days=180))
    d_to = f2.date_input("Sampai", date.today())
    q = f3.text_input("No. pengajuan / invoice / RO")
    zf = f4.selectbox("Zona", ["Semua"] + list(ui.zones()["nama"]))
    rf = f5.selectbox("Status RO", ["Semua", "dibuat", "dicetak", "ditandatangani"])
    g1, g2 = st.columns(2)
    tf = g1.selectbox("Pajak", ["Semua", "PPh21", "PPh23"])
    sf = g2.multiselect("Status bayar", ["tertahan", "siap", "diproses", "lunas"], default=["tertahan", "siap", "diproses", "lunas"])
v = pay[(pay["created_at"].dt.date >= d_from) & (pay["created_at"].dt.date <= d_to) & pay["status"].isin(sf)]
if q:
    ql = q.lower()
    v = v[v[["no_pengajuan", "invoice_no", "no_ro", "no_campaign"]].astype(str).apply(lambda r: ql in " ".join(r).lower(), axis=1)]
if zf != "Semua":
    v = v[v["zona"] == zf]
if rf != "Semua":
    v = v[v["status_ro"] == rf]
if tf != "Semua":
    v = v[v["pajak_jenis"] == tf]

unpaid = v[v["status"] != "lunas"]
ui.kpis([{"label": "Belum dibayar", "value": F.rupiah(unpaid["nominal"].sum()), "sub": f"{len(unpaid)} baris"},
         {"label": "> 30 hari", "value": str(int((unpaid["umur"] > 30).sum())), "sub": F.rupiah(unpaid[unpaid["umur"] > 30]["nominal"].sum()),
          "sub_tone": "neg" if (unpaid["umur"] > 30).any() else ""},
         {"label": "Tertahan", "value": str(int((v["status"] == "tertahan").sum())), "sub": "bukti tayang / RO belum lengkap"},
         {"label": "Pajak dipotong", "value": F.rupiah(v["pajak_nominal"].sum()), "sub": f"PPh21 {F.rupiah(v[v['pajak_jenis'] == 'PPh21']['pajak_nominal'].sum())}"},
         {"label": "Lunas", "value": F.rupiah(v[v["status"] == "lunas"]["nominal"].sum())}])

COLS = {"invoice_no": "Invoice", "vendor": "Vendor", "toko": "Toko", "nominal": st.column_config.NumberColumn("Bruto", format="Rp %d"),
        "pajak_jenis": "Pajak", "pajak_nominal": st.column_config.NumberColumn("Potongan", format="Rp %d"),
        "neto": st.column_config.NumberColumn("Neto", format="Rp %d"), "bukti": "Bukti tayang", "dokumen": "Dokumen", "status": "Status",
        "alasan_tertahan": "Alasan tertahan", "umur": st.column_config.NumberColumn("Umur (hari)", format="%d")}


def vendor_table(d: pd.DataFrame):
    x = d.assign(bukti=[("✓" if b and i and l else "kurang") for b, i, l in zip(d["ada_bukti"], d["ada_insight"], d["link"])],
                 dokumen=d["dok_ok"].map(lambda n: f"{n} terverifikasi" if n else "belum ada"))
    st.dataframe(x[list(COLS)], hide_index=True, use_container_width=True, column_config=COLS)


tg, tt, tr, tx, tv = st.tabs(["Grup per campaign", "Tunggal", "Rekap toko & zona", "Aturan pajak", "Brankas dokumen vendor"])
with tg:
    g = v[v["jenis"] == "grup"]
    camp = g.groupby(["no_campaign", "campaign", "no_pengajuan", "no_ro", "status_ro"]).agg(
        baris=("id", "count"), total=("nominal", "sum"), dibayar=("nominal", lambda s: s[g.loc[s.index, "status"] == "lunas"].sum())).reset_index()
    camp["sisa"] = camp["total"] - camp["dibayar"]
    st.dataframe(camp, hide_index=True, use_container_width=True, column_config={
        "total": st.column_config.NumberColumn(format="Rp %d"), "dibayar": st.column_config.NumberColumn(format="Rp %d"),
        "sisa": st.column_config.NumberColumn("Sisa belum dibayar", format="Rp %d")})
    for r in camp.itertuples():
        with st.expander(f"{r.no_campaign} · {r.campaign} · {r.no_ro} — sisa {F.rupiah(r.sisa)}"):
            vendor_table(g[g["no_ro"] == r.no_ro])
with tt:
    t = v[v["jenis"] == "tunggal"]
    if t.empty:
        st.caption("Tidak ada pengajuan tunggal.")
    else:
        vendor_table(t)
with tr:
    a, b = st.columns(2)
    for col, key in ((a, "zona"), (b, "toko")):
        rk = v.groupby(key).agg(total=("nominal", "sum"), lunas=("nominal", lambda s: s[v.loc[s.index, "status"] == "lunas"].sum()),
                                pajak=("pajak_nominal", "sum")).reset_index()
        rk["belum"] = rk["total"] - rk["lunas"]
        col.dataframe(rk, hide_index=True, use_container_width=True, column_config={c: st.column_config.NumberColumn(format="Rp %d") for c in ["total", "lunas", "pajak", "belum"]})
    st.download_button("Unduh rekap (Excel)", docs.to_excel(v.drop(columns=["created_at"]).assign(dibuat=v["created_at"].dt.tz_localize(None)), "pembayaran"),
                       file_name="rekap_pembayaran.xlsx")
with tx:
    rules = db.df("SELECT jenis, keterangan, tarif, dasar, tarif_tanpa_npwp, berlaku_mulai FROM tax_rules ORDER BY jenis, berlaku_mulai DESC")
    st.dataframe(rules, hide_index=True, use_container_width=True)
    ui.note("PPh 21 KOL perorangan = tarif Pasal 17 × 50% bruto; PPh 23 badan usaha = 2% × bruto (lebih tinggi tanpa NPWP). "
            "Disimpan sebagai tabel aturan dengan tanggal berlaku — wajib divalidasi tim Tax (C.13).")
    if manage:
        with st.form("tax"):
            c1, c2, c3, c4, c5 = st.columns(5)
            j = c1.selectbox("Jenis", ["PPh21", "PPh23"])
            tarif = c2.number_input("Tarif", 0.0, 1.0, 0.05, 0.005, format="%.3f")
            dasar = c3.number_input("Dasar (× bruto)", 0.0, 1.0, 0.5 if j == "PPh21" else 1.0, 0.05)
            tn = c4.number_input("Tarif tanpa NPWP", 0.0, 1.0, 0.06, 0.005, format="%.3f")
            mulai = c5.date_input("Berlaku mulai", date.today())
            ket = st.text_input("Keterangan / dasar hukum")
            if st.form_submit_button("Tambah versi aturan"):
                db.execute("INSERT INTO tax_rules (jenis, keterangan, tarif, dasar, tarif_tanpa_npwp, berlaku_mulai) VALUES (%s,%s,%s,%s,%s,%s)",
                           (j, ket, tarif, dasar, tn, mulai))
                auth.log_activity(user["id"], "aturan_pajak", "tax_rule", None, f"Aturan {j} {tarif} berlaku {mulai}")
                st.rerun()
with tv:
    if not can(user["role"], "vendor_docs.view"):
        st.caption("Dokumen KTP/NPWP & rekening hanya dapat dibuka Finance dan Super User.")
    else:
        key = None
        try:
            key = st.secrets.get("DOC_ENCRYPTION_KEY")
        except Exception:
            key = os.environ.get("DOC_ENCRYPTION_KEY")
        vendors = v.drop_duplicates("kol_id")[["kol_id", "vendor", "username"]]
        vk = st.selectbox("Vendor", vendors["kol_id"], format_func=lambda k: (lambda r: f"{r['vendor']} ({r['username']})")(vendors.set_index("kol_id").loc[k]))
        docs_ = db.df("SELECT id, jenis, nama_file, terverifikasi, uploaded_at FROM vendor_documents WHERE kol_id=%s ORDER BY uploaded_at DESC", (int(vk),))
        st.dataframe(docs_, hide_index=True, use_container_width=True)
        if not key:
            st.warning("Brankas dokumen belum aktif: tambahkan **DOC_ENCRYPTION_KEY** (kunci Fernet) di Secrets. Dokumen hanya disimpan terenkripsi.")
        else:
            from cryptography.fernet import Fernet
            fernet = Fernet(key.encode() if isinstance(key, str) else key)
            c1, c2 = st.columns(2)
            jenis = c1.selectbox("Jenis dokumen", ["KTP", "NPWP", "rekening", "lainnya"])
            up = c2.file_uploader("Unggah (terenkripsi)", type=["pdf", "jpg", "jpeg", "png"], key=f"vd_{vk}")
            if up and st.button("Simpan dokumen"):
                db.execute("INSERT INTO vendor_documents (kol_id, jenis, nama_file, isi_terenkripsi, uploaded_by) VALUES (%s,%s,%s,%s,%s)",
                           (int(vk), jenis, up.name, fernet.encrypt(up.getvalue()), user["id"]))
                auth.log_activity(user["id"], "unggah_dokumen_vendor", "kol", int(vk), f"Dokumen {jenis} diunggah")
                st.rerun()
            if not docs_.empty:
                did = st.selectbox("Buka dokumen", docs_["id"], format_func=lambda i: (lambda r: f"{r['jenis']} · {r['nama_file']}")(docs_.set_index("id").loc[i]))
                d1, d2 = st.columns(2)
                blob = db.scalar("SELECT isi_terenkripsi FROM vendor_documents WHERE id=%s", (int(did),))
                try:
                    plain = fernet.decrypt(blob) if blob else b""
                except Exception:
                    plain = b""
                if d1.download_button("Unduh (akses tercatat)", plain, file_name=docs_.set_index("id").loc[did, "nama_file"]):
                    auth.log_activity(user["id"], "akses_dokumen_vendor", "vendor_document", int(did), "Dokumen vendor dibuka")
                if d2.button("Tandai terverifikasi"):
                    db.execute("UPDATE vendor_documents SET terverifikasi=TRUE WHERE id=%s", (int(did),))
                    st.rerun()

if manage:
    st.markdown("#### Update status pembayaran")
    act = v[v["status"] != "lunas"]
    if act.empty:
        st.caption("Semua baris sudah lunas.")
    else:
        lab = (act["invoice_no"].fillna("—") + " · " + act["vendor"] + " · " + act["nominal"].map(F.rupiah) + " · " + act["status"]).tolist()
        i = st.selectbox("Baris", range(len(act)), format_func=lambda k: lab[k])
        r = act.iloc[i]
        nxt = {"tertahan": ["siap"], "siap": ["diproses", "lunas"], "diproses": ["lunas"]}.get(r["status"], [])
        c1, c2, c3 = st.columns([1, 1.4, 1])
        to = c1.selectbox("Ubah ke", nxt or ["—"])
        inv = c2.text_input("No. invoice", r["invoice_no"] or "")
        if r["status"] == "tertahan":
            st.caption(f"Tertahan: {r['alasan_tertahan']}. Status berubah otomatis menjadi 'siap' setelah syarat lengkap.")
        if c3.button("Simpan", type="primary", disabled=not nxt or r["status"] == "tertahan"):
            try:
                W.update_payment(user, int(r["id"]), to, inv or None)
                st.session_state["flash_ok"] = f"Pembayaran {inv} → {to}."
                st.rerun()
            except W.WorkflowError as e:
                st.error(str(e))
