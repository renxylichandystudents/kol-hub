"""Layar 23 — Approval Request dari Toko: layar untuk Digital Marketing."""
import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, db, ui
from lib import formulas as F
from lib import workflow as W
from lib.master import KATEGORI, KATEGORI_LABEL
from lib.rbac import require

user = auth.current_user()
require(user["role"], "request.approve")
ui.header("Approval Request dari Toko", "Cek otomatis akun baru: metrik publik, kategori, harga wajar vs ratecard, duplikat, daftar blokir")
ui.flash()

reqs = db.df("""SELECT r.*, st.nama AS toko, z.nama AS zona, k.username, k.nama AS kol_nama, k.status AS kol_status, u.nama AS pengaju
                FROM store_requests r JOIN stores st ON st.id=r.store_id JOIN zones z ON z.id=st.zone_id
                LEFT JOIN kol_accounts k ON k.id=r.kol_id LEFT JOIN users u ON u.id=r.submitted_by ORDER BY r.created_at DESC""")
queue = reqs[reqs["status"].isin(["Diajukan", "Minta info"])] if not reqs.empty else reqs
ui.kpis([{"label": "Antrean", "value": str(len(queue))},
         {"label": "Akun baru", "value": str(int(queue["data_akun_baru_json"].notna().sum())) if not queue.empty else "0"},
         {"label": "Disetujui 30 hari", "value": str(int(((reqs["status"] == "Disetujui") &
                                                          (pd.to_datetime(reqs["updated_at"], utc=True) > pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=30))).sum())) if not reqs.empty else "0"}])

if queue.empty:
    st.success("Tidak ada request yang menunggu.")
else:
    pick = st.selectbox("Request", queue["id"].tolist(), format_func=lambda i: (lambda r:
                        f"{r['no_request']} · {r['toko']} · {'akun baru' if r['data_akun_baru_json'] is not None else 'dari database'} · {r['status']}")(queue.set_index("id").loc[i]))
    r = queue.set_index("id").loc[pick]
    new = r["data_akun_baru_json"] if isinstance(r["data_akun_baru_json"], dict) else None
    st.markdown(f"**{ui.esc(r['toko'])}** ({r['zona']}) · periode {r['periode_mulai']:%d %b} – {r['periode_selesai']:%d %b %Y} · oleh {ui.esc(r['pengaju'] or '—')}  \n"
                f"Kebutuhan: {ui.esc(r['kebutuhan'])}", unsafe_allow_html=True)
    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown("#### Akun")
        if new:
            st.markdown("\n".join(f"- **{k}**: {ui.esc(v)}" for k, v in new.items() if v))
            st.markdown(f"- **ratecard**: {F.rupiah(r['ratecard'])}")
            if pd.notna(r["file_nama"]):
                st.download_button("Unduh media kit", db.scalar("SELECT file_isi FROM store_requests WHERE id=%s", (int(pick),)) or b"",
                                   file_name=r["file_nama"])
        else:
            kt = A.kol_table(store_id=int(r["store_id"]))
            k = kt[kt["id"] == r["kol_id"]]
            if not k.empty:
                k = k.iloc[0]
                st.markdown(f"**{k['username']}** · {k['platform']} · skor {k['skor']:.0f} ({k['label']}) · audiens lokal {k['audiens_lokal'] * 100:.0f}%  \n"
                            f"Ratecard {F.rupiah(k['harga'])} · harga wajar {F.rupiah(k['harga_wajar'])} · batas nego {F.rupiah(k['batas_nego'])}")
    with right:
        st.markdown("#### Cek sistem")
        cek = r["cek_sistem_json"] if isinstance(r["cek_sistem_json"], dict) else None
        if new and not cek:
            cek = W.system_check_new_account(new, r["ratecard"])
        if cek:
            ok = cek.get("lolos")
            st.markdown(ui.badge("lolos cek otomatis", "green") if ok else ui.badge("perlu perhatian", "amber"), unsafe_allow_html=True)
            st.markdown(f"- Follower: {F.angka(cek['metrik_publik']['follower'])} · estimasi views {F.angka(cek['metrik_publik']['estimasi_views'])}\n"
                        f"- Kategori disarankan: **{KATEGORI_LABEL.get(cek['kategori_saran'], cek['kategori_saran'])}** ({cek['keyakinan_kategori']:.0%})\n"
                        f"- Harga wajar {F.rupiah(cek['harga_wajar'])} vs ratecard {F.rupiah(cek['ratecard'])}"
                        + (f" ({F.persen(cek['harga_vs_wajar_pct'], 0, True)})" if cek.get("harga_vs_wajar_pct") is not None else "") +
                        f"\n- Duplikat: {'ya' if cek['duplikat'] else 'tidak'} · Daftar blokir: {'YA — ' + str(cek['alasan_blokir']) if cek['diblokir'] else 'tidak'}")
            for c in cek["catatan"]:
                if c != "lolos cek otomatis":
                    st.warning(c)
        elif r["kol_status"] == "diblokir":
            st.error("Akun ini ada di daftar blokir.")
        else:
            st.success("Akun dari database — skor & harga wajar di kiri.")

    st.markdown("#### Keputusan")
    aksi = st.radio("Aksi", ["Setujui", "Tolak", "Minta info"], horizontal=True)
    catatan = st.text_area("Catatan / alasan" + (" (wajib)" if aksi != "Setujui" else " (opsional)"))
    kat, tujuan, sub_id = None, "tunggal", None
    if aksi == "Setujui":
        c1, c2 = st.columns(2)
        if new:
            sug = (cek or {}).get("kategori_saran", "general")
            kat = c1.selectbox("Kategori", KATEGORI, index=KATEGORI.index(sug) if sug in KATEGORI else 4, format_func=KATEGORI_LABEL.get)
        tujuan_lbl = c2.radio("Diproses sebagai", ["Pengajuan tunggal", "Masuk draft campaign"], horizontal=True)
        tujuan = "tunggal" if tujuan_lbl.startswith("Pengajuan") else "draft"
        if tujuan == "draft":
            drafts = db.df("""SELECT s.id, c.no_campaign || ' — ' || c.nama AS label FROM submissions s JOIN campaigns c ON c.id=s.campaign_id
                              WHERE s.status IN ('Draft','Revisi') ORDER BY s.created_at DESC""")
            if drafts.empty:
                st.warning("Tidak ada campaign draft — akan diproses sebagai pengajuan tunggal.")
                tujuan = "tunggal"
            else:
                sub_id = st.selectbox("Campaign draft", drafts["id"], format_func=lambda i: drafts.set_index("id").loc[i, "label"])
    if st.button({"Setujui": "Setujui & tambahkan ke database" if new else "Setujui", "Tolak": "Tolak", "Minta info": "Kirim permintaan info"}[aksi],
                 type="primary"):
        try:
            res = W.review_request(user, int(pick), {"Setujui": "setujui", "Tolak": "tolak", "Minta info": "minta_info"}[aksi], catatan, kat, tujuan,
                                   int(sub_id) if sub_id else None)
            st.session_state["flash_ok"] = f"Request {r['no_request']}: {aksi.lower()}" + (f" — {res.get('masuk')}" if res.get("masuk") else "") + \
                                           (" · akun baru masuk database" if res.get("kol_baru") else "")
            st.rerun()
        except W.WorkflowError as e:
            st.error(str(e))

st.markdown("#### Riwayat request")
if not reqs.empty:
    st.dataframe(reqs[["no_request", "toko", "username", "status", "catatan", "created_at"]], hide_index=True, use_container_width=True,
                 column_config={"created_at": st.column_config.DatetimeColumn("Diajukan", format="DD MMM YYYY")})
