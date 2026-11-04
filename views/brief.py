"""Layar 17–18 — Creative Brief: bagian 1–5 & 6–9, pratinjau 9 slide, unduh .pptx & PDF, kirim ke KOL."""
from datetime import timedelta

import pandas as pd
import streamlit as st

from lib import auth, db, docs, ui
from lib import workflow as W
from lib.master import BRIEF_SECTIONS
from lib.rbac import require

user = auth.current_user()
require(user["role"], "brief.edit")
ui.header("Creative Brief", "9 bagian lengkap · saran dari histori · duplikasi ke banyak KOL di tanggal sama · export PowerPoint & PDF")
ui.flash()

briefs = db.df("""SELECT b.id, b.judul, b.versi, b.status, b.item_id, b.campaign_id, b.updated_at, i.tanggal_posting, k.username, st.nama AS toko
                  FROM briefs b LEFT JOIN submission_items i ON i.id=b.item_id LEFT JOIN kol_accounts k ON k.id=i.kol_id
                  LEFT JOIN stores st ON st.id=i.store_id ORDER BY b.updated_at DESC""")
items = db.df("""SELECT i.id, i.tanggal_posting, i.deliverable, k.username, k.nama AS kol, k.kategori, k.kontak, st.id AS store_id, st.nama AS toko,
                        s.campaign_id, COALESCE(c.nama, 'Tunggal') AS campaign, c.tujuan
                 FROM submission_items i JOIN submissions s ON s.id=i.submission_id LEFT JOIN campaigns c ON c.id=s.campaign_id
                 JOIN kol_accounts k ON k.id=i.kol_id JOIN stores st ON st.id=i.store_id
                 WHERE i.aktif AND s.status NOT IN ('Ditolak','Lunas','Selesai') ORDER BY i.tanggal_posting""")

mode = st.radio("Brief", ["Buka brief", "Buat brief baru"], horizontal=True, label_visibility="collapsed")
brief_id, item, secs = None, None, {}
if mode == "Buka brief":
    if briefs.empty:
        st.info("Belum ada brief — pilih 'Buat brief baru'.")
        st.stop()
    ids = briefs["id"].tolist()
    sel = st.session_state.get("sel_brief")
    brief_id = st.selectbox("Brief", ids, index=ids.index(sel) if sel in ids else 0,
                            format_func=lambda i: (lambda r: f"{r['judul']} · v{r['versi']} · {r['status']}")(briefs.set_index("id").loc[i]))
    st.session_state["sel_brief"] = brief_id
    b = briefs.set_index("id").loc[brief_id]
    judul0 = b["judul"]
    item = items[items["id"] == b["item_id"]].iloc[0] if pd.notna(b["item_id"]) and (items["id"] == b["item_id"]).any() else None
    secs = {r["urutan"]: r["isi_json"] for r in db.query("SELECT urutan, isi_json FROM brief_sections WHERE brief_id=%s", (brief_id,))}
else:
    if items.empty:
        st.info("Belum ada KOL di pengajuan aktif.")
        st.stop()
    iid = st.selectbox("Untuk KOL", items["id"], format_func=lambda i: (lambda r: f"{r['username']} → {r['toko']} · {r['campaign']} · tayang {r['tanggal_posting']}")(items.set_index("id").loc[i]))
    item = items[items["id"] == iid].iloc[0]
    judul0 = f"Brief {item['username']} — {item['campaign']}"
    # saran dari histori: brief terakhir dengan kategori KOL yang sama
    hist = db.query("""SELECT b.id FROM briefs b JOIN submission_items i ON i.id=b.item_id JOIN kol_accounts k ON k.id=i.kol_id
                       WHERE k.kategori=%s ORDER BY b.updated_at DESC LIMIT 1""", (item["kategori"],)) or db.query("SELECT id FROM briefs ORDER BY updated_at DESC LIMIT 1")
    if hist:
        secs = {r["urutan"]: r["isi_json"] for r in db.query("SELECT urutan, isi_json FROM brief_sections WHERE brief_id=%s", (hist[0]["id"],))}
        st.caption("✦ Isi awal disarankan dari brief terdahulu dengan kategori KOL serupa — sesuaikan sebelum dikirim.")
    promo = db.one("""SELECT nama FROM promo_offline_events WHERE (store_id=%s OR store_id IS NULL) AND selesai >= %s ORDER BY mulai LIMIT 1""",
                   (int(item["store_id"]), item["tanggal_posting"]))
    secs[4] = {"teks": f"{item['toko']}" + (f" — {promo['nama']}" if promo else "")}
    if pd.notna(item["tujuan"]):
        secs[1] = {"teks": item["tujuan"]}
    tp = item["tanggal_posting"]
    secs[8] = {"deliverable": f"1 {item['deliverable']}", "timeline": f"Draft {tp - timedelta(days=3):%d %b} · Revisi maks 2× · Tayang {tp:%d %b} · Laporan H+3"}

judul = st.text_input("Judul brief", judul0)
meta = f"{item['kol']} · {item['toko']} · tayang {item['tanggal_posting']:%d %b %Y}" if item is not None else ""
t1, t2 = st.tabs(["Creative Brief (1/2) · bagian 1–5", "Creative Brief (2/2) · bagian 6–9 & pratinjau"])
new = {}
with t1:
    for n in range(1, 5):
        new[n] = {"teks": st.text_area(f"{n}. {BRIEF_SECTIONS[n - 1]}", secs.get(n, {}).get("teks", ""), height=90, key=f"s{n}_{brief_id}")}
    st.markdown(f"**5. {BRIEF_SECTIONS[4]}**")
    sc = pd.DataFrame(secs.get(5, {}).get("scene") or [{"no": 1, "durasi": "0–3 dtk", "visual": "", "audio": ""}])
    sc = st.data_editor(sc, num_rows="dynamic", use_container_width=True, key=f"sc_{brief_id}",
                        column_config={"no": st.column_config.NumberColumn("Scene", width="small")})
    new[5] = {"scene": sc.fillna("").to_dict("records")}
with t2:
    a, b = st.columns(2)
    new[6] = {"wajib": a.text_area("6. Wajib", secs.get(6, {}).get("wajib", ""), key=f"w_{brief_id}"),
              "dilarang": b.text_area("6. Dilarang", secs.get(6, {}).get("dilarang", ""), key=f"d_{brief_id}")}
    new[7] = {"caption": st.text_area("7. Caption", secs.get(7, {}).get("caption", ""), key=f"cap_{brief_id}"),
              "hashtag": st.text_input("7. Hashtag", secs.get(7, {}).get("hashtag", "#Mitra10"), key=f"tag_{brief_id}")}
    c, d = st.columns(2)
    new[8] = {"deliverable": c.text_input("8. Deliverable", secs.get(8, {}).get("deliverable", ""), key=f"del_{brief_id}"),
              "timeline": d.text_input("8. Timeline", secs.get(8, {}).get("timeline", ""), key=f"tl_{brief_id}")}
    best = db.one("SELECT platform, judul, views, jenis_konten, durasi_detik FROM official_posts ORDER BY views DESC LIMIT 1")
    ref_default = secs.get(9, {}).get("referensi") or (f"Konten '{best['judul']}' ({best['views']:,} views, {best['jenis_konten']}, {best['durasi_detik']} dtk)".replace(",", ".") if best else "")
    new[9] = {"referensi": st.text_area("9. Referensi", ref_default, key=f"ref_{brief_id}")}

    st.markdown("#### Pratinjau 9 slide")
    for row in range(3):
        cols = st.columns(3)
        for col, n in zip(cols, range(row * 3 + 1, row * 3 + 4)):
            body = "<br>".join(ui.esc(x) for x in docs._sec_text(n, new.get(n, {})) if x) or "—"
            col.markdown(f"<div class='kh-card' style='min-height:150px'><div style='background:#111a33;color:#fff;margin:-1rem -1.1rem .6rem;"
                         f"padding:.4rem .8rem;border-radius:14px 14px 0 0;font-weight:700'>{n}. {BRIEF_SECTIONS[n - 1]}</div>"
                         f"<div style='font-size:.8rem'>{body[:420]}</div></div>", unsafe_allow_html=True)

s1, s2, s3, s4 = st.columns(4)
if s1.button("Simpan", type="primary", use_container_width=True):
    bid = W.save_brief(user, brief_id, int(item["id"]) if item is not None else None,
                       int(item["campaign_id"]) if item is not None and pd.notna(item["campaign_id"]) else None, judul, new)
    ui.go("views/brief.py", sel_brief=bid, flash_ok="Brief disimpan (versi baru).")
s2.download_button("Unduh .pptx", docs.brief_pptx(judul, meta, new), file_name=f"{judul}.pptx", use_container_width=True,
                   mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
s3.download_button("Unduh PDF", docs.brief_pdf(judul, meta, new), file_name=f"{judul}.pdf", mime="application/pdf", use_container_width=True)
if brief_id and s4.button("Tandai terkirim ke KOL", use_container_width=True):
    db.execute("UPDATE briefs SET status='terkirim', updated_at=NOW() WHERE id=%s", (brief_id,))
    if item is not None:
        db.execute("UPDATE production_tasks SET status='selesai' WHERE item_id=%s AND tahap IN ('pitching','brief')", (int(item["id"]),))
    auth.log_activity(user["id"], "kirim_brief", "brief", brief_id, f"Brief '{judul}' dikirim ke KOL")
    st.rerun()
if item is not None and pd.notna(item["kontak"]):
    st.caption(f"Kontak KOL: {item['kontak']} — kirim file .pptx/PDF lewat kanal resmi tim.")

if brief_id and item is not None:
    with st.expander("Duplikasi brief ke KOL lain di tanggal tayang sama"):
        same = items[(items["tanggal_posting"] == item["tanggal_posting"]) & (items["id"] != item["id"])]
        if same.empty:
            st.caption("Tidak ada KOL lain dengan tanggal tayang yang sama.")
        else:
            targets = st.multiselect("KOL", same["id"], format_func=lambda i: (lambda r: f"{r['username']} → {r['toko']}")(same.set_index("id").loc[i]))
            if st.button("Duplikasi", disabled=not targets):
                W.duplicate_brief(user, brief_id, [int(t) for t in targets])
                st.session_state["flash_ok"] = f"Brief diduplikasi ke {len(targets)} KOL."
                st.rerun()
