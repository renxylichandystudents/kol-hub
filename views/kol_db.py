"""Layar 6 — Database KOL & Portal News: seluruh KOL & Portal News, kategori, dan riwayat campaign."""
from datetime import date

import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, db, docs, nlp, ui
from lib import formulas as F
from lib import workflow as W
from lib.master import KATEGORI, KATEGORI_LABEL
from lib.preprocess import dedupe_kols, normalize_username
from lib.rbac import can, require

user = auth.current_user()
require(user["role"], "kol.view")
ui.header("Database KOL & Portal News", "Kategori disarankan otomatis dari bio & caption (dapat diubah) · skor & saran harga dihitung ulang harian")
ui.flash()

kt = A.kol_table()
last_c = db.df("""SELECT DISTINCT ON (i.kol_id) i.kol_id, COALESCE(c.nama, 'Pengajuan tunggal ' || s.no_pengajuan) AS campaign_terakhir
                  FROM submission_items i JOIN submissions s ON s.id=i.submission_id LEFT JOIN campaigns c ON c.id=s.campaign_id
                  WHERE i.aktif ORDER BY i.kol_id, COALESCE(i.tanggal_posting, s.created_at::date) DESC""")
if not kt.empty and not last_c.empty:
    kt = kt.merge(last_c, left_on="id", right_on="kol_id", how="left").drop(columns=["kol_id"])
else:
    kt["campaign_terakhir"] = None

if kt.empty:
    st.info("Database masih kosong. Upload database KOL atau tambahkan satu per satu di tab bawah.")
else:
    has_hist = kt[kt["kerja_sama"] > 0]
    best = has_hist[has_hist["skor"] >= 80]
    low = has_hist[has_hist["skor"] < 50]
    ui.kpis([
        {"label": "KOL", "value": str(int((kt["tipe"] == "kol").sum())), "sub": f"{int((kt['tipe'] == 'portal').sum())} Portal News"},
        {"label": "Aktif", "value": str(int((kt["status"] == "aktif").sum())), "sub": f"{int((kt['status'] == 'diblokir').sum())} diblokir"},
        {"label": "Best performance", "value": str(len(best)), "sub": "skor ≥ 80 dengan riwayat kerja sama"},
        {"label": "Lower performance", "value": str(len(low)), "sub": "skor < 50"},
        {"label": "Harga naik tidak wajar", "value": str(int(kt["flag_harga"].sum())), "sub": "gap > 20 poin (rumus 6)", "sub_tone": "neg" if kt["flag_harga"].any() else ""},
    ])
    st.write("")

tab_list, tab_cat, tab_add, tab_up = st.tabs(["Daftar", "Komposisi & insight kategori", "Tambah akun", "Upload database"])

with tab_list:
    if not kt.empty:
        c = st.columns([1.2, 1, 1, 1, 1, 2])
        tipe = c[0].selectbox("Jenis", ["Semua", "KOL", "Portal News"])
        kat = c[1].selectbox("Kategori", ["Semua"] + [KATEGORI_LABEL[k] for k in KATEGORI])
        plat = c[2].selectbox("Platform", ["Semua", "Instagram", "TikTok", "Portal News"])
        stt = c[3].selectbox("Status", ["Semua", "aktif", "diblokir"])
        lab = c[4].selectbox("Label skor", ["Semua", "Rekomendasi", "Layak", "Evaluasi", "Tidak disarankan"])
        q = c[5].text_input("Cari nama / username / kota")
        d = kt.copy()
        if tipe != "Semua":
            d = d[d["tipe"] == ("kol" if tipe == "KOL" else "portal")]
        if kat != "Semua":
            d = d[d["kategori"] == kat.lower()]
        if plat != "Semua":
            d = d[d["platform"] == plat]
        if stt != "Semua":
            d = d[d["status"] == stt]
        if lab != "Semua":
            d = d[d["label"] == lab]
        if q:
            ql = q.lower()
            d = d[d["nama"].str.lower().str.contains(ql) | d["username"].str.lower().str.contains(ql) | d["kota"].fillna("").str.lower().str.contains(ql)]
        show = pd.DataFrame({
            "Nama": d["nama"], "Akun": d["username"], "Platform": d["platform"], "Kategori": d["kategori"].map(KATEGORI_LABEL),
            "Kota": d["kota"], "Follower": d["follower"], "Avg views": d["avg_views"], "ER adj": d["er_adj"],
            "Skor": d["skor"].round(0), "Label": d["label"], "Ratecard": d["harga"], "Saran harga": d["harga_wajar"],
            "Kerja sama": d["kerja_sama"], "Campaign terakhir": d["campaign_terakhir"].fillna("—"), "Segmen": d["segmen"],
            "Status": d["status"]})
        st.dataframe(show, hide_index=True, use_container_width=True, height=460, column_config={
            "Follower": st.column_config.NumberColumn(format="%d"), "Avg views": st.column_config.NumberColumn(format="%d"),
            "ER adj": st.column_config.NumberColumn(format="%.1f%%"),
            "Skor": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
            "Ratecard": st.column_config.NumberColumn(format="Rp %d"), "Saran harga": st.column_config.NumberColumn(format="Rp %d")})
        st.download_button("Unduh Excel", docs.to_excel(show, "kol"), file_name="database_kol.xlsx")

        st.markdown("#### Aksi")
        a1, a2 = st.columns([2, 3])
        pick = a1.selectbox("Pilih akun", d["username"] + " — " + d["nama"], key="kol_pick")
        if pick:
            row = d[(d["username"] + " — " + d["nama"]) == pick].iloc[0]
            b1, b2, b3 = a2.columns(3)
            if b1.button("Buka analisa", type="primary", use_container_width=True):
                ui.go("views/kol_analisa.py", sel_kol=int(row["id"]))
            if b2.button("Bandingkan", use_container_width=True):
                lst = st.session_state.get("cmp_kols", [])
                if int(row["id"]) not in lst:
                    lst = (lst + [int(row["id"])])[-4:]
                st.session_state["cmp_kols"] = lst
                ui.go("views/bandingkan.py")
            if can(user["role"], "kol.edit"):
                with b3.popover("Ubah / blokir", use_container_width=True):
                    new_kat = st.selectbox("Kategori", KATEGORI, index=KATEGORI.index(row["kategori"]), format_func=KATEGORI_LABEL.get,
                                           help=f"Saran otomatis: {KATEGORI_LABEL.get(row['kategori_otomatis'] or 'general')}")
                    if st.button("Simpan kategori"):
                        db.execute("UPDATE kol_accounts SET kategori=%s, updated_at=NOW() WHERE id=%s", (new_kat, int(row["id"])))
                        auth.log_activity(user["id"], "ubah_kategori", "kol", int(row["id"]), f"Kategori {row['username']} → {new_kat}")
                        st.cache_data.clear(); st.rerun()
                    if row["status"] == "aktif":
                        alasan = st.text_area("Alasan blokir")
                        if st.button("Blokir akun", type="primary"):
                            try:
                                W.set_block(user, int(row["id"]), True, alasan)
                                st.rerun()
                            except W.WorkflowError as e:
                                st.error(str(e))
                    else:
                        st.caption(f"Diblokir: {row['alasan_blokir']}")
                        if st.button("Buka blokir"):
                            W.set_block(user, int(row["id"]), False)
                            st.rerun()

        b, l = st.columns(2)
        with b:
            st.markdown("#### Best performance")
            st.dataframe(has_hist.nlargest(5, "skor")[["nama", "platform", "skor", "lift_hist", "cpiv"]], hide_index=True, use_container_width=True,
                         column_config={"skor": st.column_config.NumberColumn(format="%.0f"), "lift_hist": st.column_config.NumberColumn("Lift", format="%.2f"),
                                        "cpiv": st.column_config.NumberColumn("CPIV", format="Rp %d")})
        with l:
            st.markdown("#### Lower performance")
            st.dataframe(has_hist.nsmallest(5, "skor")[["nama", "platform", "skor", "weakness"]], hide_index=True, use_container_width=True,
                         column_config={"skor": st.column_config.NumberColumn(format="%.0f"), "weakness": "Catatan"})

with tab_cat:
    if not kt.empty:
        g = kt.groupby("kategori").agg(akun=("id", "count"), skor=("skor", "mean"), er=("er_adj", "mean"),
                                       cpm=("cpm_harapan", "median"), lift=("lift_hist", "mean"), kerja_sama=("kerja_sama", "sum")).reset_index()
        g["kategori"] = g["kategori"].map(KATEGORI_LABEL)
        c1, c2 = st.columns([1, 1.4])
        c1.bar_chart(g.set_index("kategori")["akun"], height=260)
        c2.dataframe(g, hide_index=True, use_container_width=True, column_config={
            "skor": st.column_config.NumberColumn("Skor rata-rata", format="%.0f"), "er": st.column_config.NumberColumn("ER adj", format="%.1f%%"),
            "cpm": st.column_config.NumberColumn("CPM median", format="Rp %d"), "lift": st.column_config.NumberColumn("Lift rata-rata", format="%.3f")})
        best_cat = g.sort_values("lift", ascending=False).dropna(subset=["lift"])
        if not best_cat.empty:
            st.info(f"Kategori dengan lift traffic offline tertinggi: **{best_cat.iloc[0]['kategori']}** "
                    f"({F.persen(best_cat.iloc[0]['lift'] * 100, tanda=True)}); CPM termurah: **{g.sort_values('cpm').iloc[0]['kategori']}**.")

with tab_add:
    if not can(user["role"], "kol.edit"):
        st.caption("Role Anda hanya dapat melihat database.")
    else:
        with st.form("add_kol"):
            c1, c2, c3 = st.columns(3)
            nama = c1.text_input("Nama akun")
            plat = c2.selectbox("Platform", ["Instagram", "TikTok", "Portal News"])
            tipe = c3.selectbox("Jenis", ["kol", "portal"], format_func={"kol": "KOL", "portal": "Portal News"}.get)
            c4, c5, c6 = st.columns(3)
            un = c4.text_input("Username (@...)")
            link = c5.text_input("Link profil / situs")
            kota = c6.text_input("Kota domisili")
            bio = st.text_area("Bio / deskripsi (dipakai untuk saran kategori)")
            c7, c8, c9, c10 = st.columns(4)
            follower = c7.number_input("Follower", min_value=0, step=1000)
            avg_views = c8.number_input("Rata-rata views", min_value=0, step=1000)
            er = c9.number_input("ER (%)", min_value=0.0, max_value=100.0, step=0.1)
            harga = c10.number_input("Ratecard (Rp)", min_value=0, step=100_000)
            c11, c12, c13 = st.columns(3)
            deliv = c11.selectbox("Deliverable", ["video", "reels", "story", "artikel"])
            badan = c12.checkbox("Badan hukum (PPh 23)", value=tipe == "portal")
            npwp = c13.checkbox("Punya NPWP", value=True)
            ok = st.form_submit_button("Simpan akun", type="primary")
        if ok:
            kat, conf = nlp.suggest_category(bio)
            norm = normalize_username(un or link)
            if not nama or not norm or not link:
                st.error("Nama, username, dan link wajib diisi.")
            elif db.scalar("SELECT 1 FROM kol_accounts WHERE lower(platform)=lower(%s) AND username_norm=%s", (plat, norm)):
                st.error("Akun sudah ada di database.")
            else:
                with db.transaction() as cur:
                    kid = cur.execute("""INSERT INTO kol_accounts (tipe, platform, nama, username, username_norm, link, kategori, kategori_otomatis,
                                         bio, kota_domisili, badan_hukum, punya_npwp, sumber) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'input')
                                         RETURNING id""", (tipe, plat, nama, "@" + norm, norm, link, kat, kat, bio, kota, badan, npwp)).fetchone()["id"]
                    cur.execute("INSERT INTO kol_metrics_snapshot (kol_id, tanggal, follower, avg_views, er, audiens_kota_json) VALUES (%s,CURRENT_DATE,%s,%s,%s,%s)",
                                (kid, follower, avg_views, er, {kota or "Lainnya": 0.5, "Lainnya": 0.5}))
                    if harga:
                        cur.execute("INSERT INTO ratecards (kol_id, deliverable, harga, berlaku_mulai) VALUES (%s,%s,%s,CURRENT_DATE)", (kid, deliv, harga))
                auth.log_activity(user["id"], "tambah_kol", "kol", kid, f"Akun {nama} ditambahkan (kategori otomatis: {kat})")
                st.cache_data.clear()
                st.session_state["flash_ok"] = f"{nama} tersimpan. Kategori disarankan: {KATEGORI_LABEL[kat]} (keyakinan {conf:.0%}) — dapat diubah."
                st.rerun()

with tab_up:
    if not can(user["role"], "kol.edit"):
        st.caption("Role Anda hanya dapat melihat database.")
    else:
        st.download_button("Template Excel database KOL", docs.kol_template(), file_name="template_database_kol.xlsx")
        f = st.file_uploader("Upload database (Excel/CSV)", type=["xlsx", "xls", "csv"], key="kol_up")
        if f:
            raw = pd.read_csv(f) if f.name.lower().endswith(".csv") else pd.read_excel(f)
            raw.columns = [str(c).strip().lower() for c in raw.columns]
            existing = db.query("SELECT id, platform, username_norm, link, nama FROM kol_accounts")
            res = dedupe_kols(raw, existing)
            res["kategori_saran"] = [nlp.suggest_category(str(b or ""))[0] if not str(k or "").strip() else str(k).lower()
                                     for b, k in zip(res.get("bio", [""] * len(res)), res.get("kategori", [""] * len(res)))]
            cnt = res["status_upload"].value_counts()
            ui.kpis([{"label": "Baru", "value": str(cnt.get("baru", 0))}, {"label": "Digabung", "value": str(cnt.get("digabung", 0)),
                      "sub": "akun sudah ada → data diperbarui"}, {"label": "Ditolak", "value": str(cnt.get("ditolak", 0))}])
            st.dataframe(res[[c for c in ["nama", "platform", "username", "link", "kategori_saran", "status_upload", "alasan"] if c in res]],
                         hide_index=True, use_container_width=True)
            if st.button("Proses upload", type="primary"):
                n_new = n_merge = 0
                with db.transaction() as cur:
                    up = cur.execute("INSERT INTO uploads (jenis, nama_file, ringkasan_validasi_json, uploaded_by) VALUES ('kol_db',%s,%s,%s) RETURNING id",
                                     (f.name, {k: int(v) for k, v in cnt.items()}, user["id"])).fetchone()["id"]
                    for _, r in res.iterrows():
                        if r["status_upload"] == "ditolak":
                            continue
                        kat = r["kategori_saran"] if r["kategori_saran"] in KATEGORI else "general"
                        if r["status_upload"] == "baru":
                            kid = cur.execute("""INSERT INTO kol_accounts (tipe, platform, nama, username, username_norm, link, kategori, kategori_otomatis,
                                                 bio, kota_domisili, kontak, badan_hukum, punya_npwp, sumber)
                                                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'upload') RETURNING id""",
                                              (str(r.get("tipe") or "kol").lower(), r["platform"], r.get("nama") or r["username_norm"], "@" + r["username_norm"],
                                               r["username_norm"], r["link"], kat, kat, r.get("bio"), r.get("kota_domisili"), r.get("kontak"),
                                               bool(r.get("badan_hukum") or False), bool(r.get("punya_npwp") if pd.notna(r.get("punya_npwp")) else True))).fetchone()["id"]
                            n_new += 1
                        else:
                            kid = int(r["match_id"])
                            n_merge += 1
                        if pd.notna(r.get("follower")) or pd.notna(r.get("avg_views")):
                            cur.execute("""INSERT INTO kol_metrics_snapshot (kol_id, tanggal, follower, avg_views, er) VALUES (%s,CURRENT_DATE,%s,%s,%s)
                                           ON CONFLICT (kol_id, tanggal) DO UPDATE SET follower=EXCLUDED.follower, avg_views=EXCLUDED.avg_views, er=EXCLUDED.er""",
                                        (kid, int(r["follower"]) if pd.notna(r.get("follower")) else None,
                                         int(r["avg_views"]) if pd.notna(r.get("avg_views")) else None,
                                         float(r["er"]) if pd.notna(r.get("er")) else None))
                        if pd.notna(r.get("harga")) and float(r["harga"]) > 0:
                            cur.execute("INSERT INTO ratecards (kol_id, deliverable, harga, berlaku_mulai, sumber) VALUES (%s,%s,%s,CURRENT_DATE,'kol')",
                                        (kid, r.get("deliverable") or "video", float(r["harga"])))
                auth.log_activity(user["id"], "upload_database_kol", "upload", up, f"Upload database KOL: {n_new} baru, {n_merge} digabung")
                st.cache_data.clear()
                st.session_state["flash_ok"] = f"Upload selesai: {n_new} baru, {n_merge} digabung, {cnt.get('ditolak', 0)} ditolak."
                st.rerun()
