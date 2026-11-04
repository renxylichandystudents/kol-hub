"""Layar 20 — Bukti Tayang & Status RO / Pembayaran: upload bukti tayang & update status oleh Digital Marketing & Finance."""
from datetime import datetime, time

import pandas as pd
import streamlit as st

from lib import auth, db, ui
from lib import workflow as W
from lib.rbac import can, require

user = auth.current_user()
require(user["role"], "report.view")
ui.header("Bukti Tayang & Status RO / Pembayaran", "Per KOL/Portal: bukti tayang, link, insight, status Form RO & pembayaran, dan siapa yang meng-update")
ui.flash()

scope, params = "", []
if user["role"] == "store":
    scope, params = " AND i.store_id = %s", [user.get("scope_store_id") or -1]
rows = db.df(f"""SELECT i.id AS item_id, COALESCE(c.nama, 'Tunggal ' || s.no_pengajuan) AS campaign, k.username, k.platform, st.nama AS toko,
                        i.tanggal_posting, p.link, p.tanggal_tayang, p.bukti_nama, p.insight_nama, p.telat_hari,
                        r.no_ro, r.status AS status_ro, pay.status AS status_bayar, pay.alasan_tertahan, pay.invoice_no,
                        COALESCE(u2.nama, u.nama) AS diupdate_oleh, GREATEST(p.updated_at, pay.updated_at) AS diupdate,
                        api.views AS views_api, ocr.views AS views_ocr
                 FROM submission_items i JOIN submissions s ON s.id=i.submission_id LEFT JOIN campaigns c ON c.id=s.campaign_id
                 JOIN kol_accounts k ON k.id=i.kol_id JOIN stores st ON st.id=i.store_id
                 LEFT JOIN posts p ON p.item_id=i.id LEFT JOIN ro_forms r ON r.submission_id=s.id LEFT JOIN payments pay ON pay.item_id=i.id
                 LEFT JOIN users u ON u.id=p.updated_by LEFT JOIN users u2 ON u2.id=pay.updated_by
                 LEFT JOIN LATERAL (SELECT views FROM post_metrics WHERE post_id=p.id AND sumber='api' ORDER BY diukur_pada DESC LIMIT 1) api ON TRUE
                 LEFT JOIN LATERAL (SELECT views FROM post_metrics WHERE post_id=p.id AND sumber IN ('ocr','manual') ORDER BY id DESC LIMIT 1) ocr ON TRUE
                 WHERE i.aktif AND i.keputusan_item='setuju' AND r.id IS NOT NULL{scope}
                 ORDER BY i.tanggal_posting DESC""", params)
if rows.empty:
    st.info("Belum ada baris dengan Form RO.")
    st.stop()

rows["selisih"] = [(abs(o - a) / a * 100) if pd.notna(o) and pd.notna(a) and a else None for o, a in zip(rows["views_ocr"], rows["views_api"])]
c1, c2 = st.columns([2, 1])
camp = c1.selectbox("Campaign", ["Semua"] + sorted(rows["campaign"].unique()))
only = c2.selectbox("Tampilkan", ["Semua", "Belum ada bukti", "Pembayaran tertahan", "Selisih OCR > 5%"])
v = rows if camp == "Semua" else rows[rows["campaign"] == camp]
if only == "Belum ada bukti":
    v = v[v["bukti_nama"].isna()]
elif only == "Pembayaran tertahan":
    v = v[v["status_bayar"] == "tertahan"]
elif only == "Selisih OCR > 5%":
    v = v[v["selisih"] > 5]

show = pd.DataFrame({"KOL": v["username"], "Toko": v["toko"], "Jadwal": v["tanggal_posting"], "Tayang": v["tanggal_tayang"],
                     "Bukti": v["bukti_nama"].notna().map({True: "✓", False: "—"}), "Link": v["link"],
                     "Insight": v["insight_nama"].notna().map({True: "✓", False: "—"}),
                     "Selisih OCR vs API": v["selisih"].map(lambda x: "—" if x is None or pd.isna(x) else (f"⚠ {x:.1f}%" if x > 5 else f"{x:.1f}%")),
                     "No. RO": v["no_ro"], "Status RO": v["status_ro"], "Pembayaran": v["status_bayar"], "Alasan tertahan": v["alasan_tertahan"].fillna(""),
                     "Diupdate oleh": v["diupdate_oleh"].fillna("—"), "Waktu update": v["diupdate"]})
st.dataframe(show, hide_index=True, use_container_width=True, height=400, column_config={
    "Link": st.column_config.LinkColumn(), "Tayang": st.column_config.DatetimeColumn(format="DD MMM HH:mm"),
    "Waktu update": st.column_config.DatetimeColumn(format="DD MMM HH:mm")})
st.info("**Aturan:** pembayaran diproses bila bukti tayang, link, dan insight lengkap **dan** RO sudah ditandatangani. "
        "Angka insight dari screenshot dibaca otomatis (OCR) dan dicocokkan dengan API; selisih > 5% ditandai.")

if can(user["role"], "proof.input"):
    st.markdown("#### Upload / update bukti tayang")
    labels = (rows["username"] + " → " + rows["toko"] + " · " + rows["campaign"]).tolist()
    i = st.selectbox("KOL / Portal", range(len(rows)), format_func=lambda k: labels[k])
    r = rows.iloc[i]
    a, b = st.columns(2)
    link = a.text_input("Link posting", r["link"] or "", key=f"lk_{r['item_id']}")
    d0 = pd.to_datetime(r["tanggal_tayang"]).to_pydatetime() if pd.notna(r["tanggal_tayang"]) else datetime.combine(r["tanggal_posting"], time(19))
    d1, t1 = b.columns(2)
    tgl = d1.date_input("Tanggal tayang", d0.date(), key=f"td_{r['item_id']}")
    jam = t1.time_input("Jam", d0.time(), key=f"tt_{r['item_id']}")
    u1, u2 = st.columns(2)
    bukti = u1.file_uploader("Screenshot bukti tayang", type=["png", "jpg", "jpeg"], key=f"bk_{r['item_id']}")
    insight = u2.file_uploader("Screenshot insight", type=["png", "jpg", "jpeg"], key=f"in_{r['item_id']}")
    ocr = W.ocr_insight(insight.getvalue()) if insight else {}
    if insight:
        if ocr:
            st.success("Angka dibaca otomatis dari screenshot (OCR) — periksa & koreksi bila perlu.")
        else:
            st.warning("OCR tidak dapat membaca angka dari gambar ini — isi manual.")
    m = st.columns(5)
    vals = {k: m[j].number_input(k.title(), min_value=0, value=int(ocr.get(k, 0)), step=1, key=f"m_{k}_{r['item_id']}")
            for j, k in enumerate(["views", "likes", "komentar", "share", "save"])}
    if st.button("Simpan bukti tayang", type="primary"):
        if not link:
            st.error("Link posting wajib diisi.")
        else:
            res = W.save_proof(user, int(r["item_id"]), link, datetime.combine(tgl, jam),
                               (bukti.name, bukti.getvalue()) if bukti else None, (insight.name, insight.getvalue()) if insight else None,
                               vals, sumber="ocr" if ocr else "manual")
            msg = "Bukti tayang tersimpan."
            if res["telat_hari"]:
                msg += f" Tayang telat {res['telat_hari']} hari dari jadwal (masuk penalti skor)."
            if res["ditandai"]:
                msg += f" ⚠ Selisih views dengan API {res['selisih_api_pct']:.1f}% (> 5%) — ditandai untuk dicek."
            st.session_state["flash_ok"] = msg
            st.rerun()
    if pd.notna(r["bukti_nama"]):
        img = db.scalar("SELECT bukti FROM posts WHERE item_id=%s", (int(r["item_id"]),))
        if img and len(img) > 200:
            st.image(img, caption="Bukti tayang tersimpan", width=260)
if can(user["role"], "payment.view"):
    st.caption("Status pembayaran diperbarui Finance di menu Pembayaran & Pajak; status RO diperbarui di menu Form Approval RO.")
