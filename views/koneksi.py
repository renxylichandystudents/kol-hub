"""Koneksi API Instagram (Meta) & TikTok: simpan token terenkripsi, pilih akun Mitra10, sinkron data, undang KOL TikTok."""
import pandas as pd
import streamlit as st

from lib import auth, db, ui
from lib.formulas import angka
from lib import social_api as S
from lib.rbac import require

S_fmt = lambda n: angka(n or 0, False)  # noqa: E731
user = auth.current_user()
require(user["role"], "api.manage")
ui.header("Koneksi Instagram & TikTok", "API resmi Meta & TikTok — follower KOL, metrik link tayang, dan data akun resmi Mitra10")
ui.flash()

# ---------------------------------------------------------------- ringkasan status
cfg = S.meta_cfg() if S.can_store_tokens() else None
tt_main = S.load_token("tiktok:mitra10") if S.can_store_tokens() and S.tiktok_ready() else None
n_tt_kol = len(S.token_info("tiktok:kol:") or []) if S.can_store_tokens() else 0
ui.kpis([
    {"label": "Instagram Mitra10", "value": "Terhubung" if cfg else "Belum terhubung",
     "sub": f"@{cfg['username']}" if cfg else "tempel access token Meta di tab Instagram", "sub_tone": "pos" if cfg else "neg"},
    {"label": "TikTok Mitra10", "value": "Terhubung" if tt_main else ("Siap login" if S.tiktok_ready() else "Belum disiapkan"),
     "sub": (tt_main.get("_info", {}).get("akun") or "—") if tt_main else
            ("klik login di tab TikTok" if S.tiktok_ready() else "perlu app TikTok Developer"), "sub_tone": "pos" if tt_main else "neg"},
    {"label": "KOL TikTok memberi izin", "value": S_fmt(n_tt_kol), "sub": "akun KOL yang sudah login lewat link undangan"},
])
if S.key_source() == "invalid":
    st.warning("DOC_ENCRYPTION_KEY di Secrets tidak valid — sementara token dienkripsi dengan kunci turunan dari koneksi database. "
               "Hapus atau perbaiki baris DOC_ENCRYPTION_KEY di Streamlit → Settings → Secrets.")
if not S.can_store_tokens():
    st.error("Koneksi database belum tersedia, token belum bisa disimpan.")
    st.stop()

t_ig, t_tt, t_log = st.tabs(["Instagram (Meta)", "TikTok", "Riwayat sinkron"])

# ---------------------------------------------------------------- Instagram
with t_ig:
    if cfg:
        info = (S.load_token("meta") or {}).get("_info", {})
        st.success(f"Terhubung ke **@{cfg['username']}** (IG user {cfg['ig_user_id']}) · token berlaku: {info.get('expires_at', '—')}")
        n_kol = db.scalar("SELECT COUNT(*) FROM kol_accounts WHERE lower(platform)='instagram' AND status='aktif'")
        stat = db.df("""SELECT COALESCE(api_status,'belum dicek') AS status, COUNT(*) AS akun FROM kol_accounts
                        WHERE lower(platform)='instagram' AND status='aktif' GROUP BY 1 ORDER BY 2 DESC""")
        c1, c2, c3 = st.columns(3)
        c1.metric("Akun KOL/portal IG", S_fmt(n_kol))
        c2.metric("Bisa dibaca API (Business/Creator)", S_fmt(int(stat.loc[stat["status"] == "ok", "akun"].sum()) if not stat.empty else 0))
        c3.metric("Posting tayang ber-metrik API", S_fmt(db.scalar("SELECT COUNT(DISTINCT post_id) FROM post_metrics WHERE sumber='api'")))
        st.dataframe(stat, hide_index=True)
        b1, b2, b3 = st.columns(3)
        batch = b3.number_input("Akun per sinkron", 10, 400, 60, step=10,
                                help="Business Discovery dibatasi Meta per jam; sisa akun dilanjutkan pada sinkron berikutnya.")
        if b1.button("Sinkron akun resmi Mitra10", icon=":material/sync:"):
            with st.spinner("Membaca posting, insight & komentar akun resmi…"):
                try:
                    r = S.sync_official_instagram()
                    st.session_state["flash_ok"] = f"Instagram resmi: {r.get('media', 0)} posting, {r.get('komentar_baru', 0)} komentar baru."
                except Exception as e:  # noqa: BLE001
                    st.session_state["flash_err"] = f"Gagal: {e}"
            st.cache_data.clear()
            st.rerun()
        if b2.button("Sinkron follower & metrik KOL", type="primary", icon=":material/group:"):
            with st.spinner(f"Membaca {batch} akun KOL/portal via Business Discovery…"):
                try:
                    r = S.sync_kol_instagram(int(batch))
                    msg = (f"KOL: {r.get('akun_dicek', 0)} akun dicek, {r.get('akun_ok', 0)} terbaca, {r.get('akun_bukan_bisnis', 0)} akun pribadi, "
                           f"{r.get('posting_cocok', 0)} link tayang terisi metrik.")
                    if r.get("berhenti_rate_limit"):
                        msg += " Batas rate Meta tercapai — lanjutkan ±1 jam lagi."
                    st.session_state["flash_ok"] = msg
                except Exception as e:  # noqa: BLE001
                    st.session_state["flash_err"] = f"Gagal: {e}"
            st.cache_data.clear()
            st.rerun()
        with st.expander("Ganti / putuskan koneksi"):
            if st.button("Putuskan koneksi Instagram"):
                S.delete_token("meta")
                auth.log_activity(user["id"], "putus_meta", "api", None, "Koneksi Meta diputus")
                st.rerun()
    st.markdown("#### " + ("Ganti token" if cfg else "Hubungkan akun Instagram Mitra10"))
    st.caption("Token dari Meta for Developers (Graph API Explorer / System User di Business Manager) dengan izin: "
               "instagram_basic, instagram_manage_insights, instagram_manage_comments, pages_show_list, pages_read_engagement, "
               "business_management. Token System User tidak kedaluwarsa; token user biasa ditukar otomatis ke token 60 hari.")
    tok = st.text_input("Access token", type="password", key="meta_tok")
    if tok:
        try:
            accts = S.meta_discover_accounts(tok)
        except Exception as e:  # noqa: BLE001
            st.error(f"Token tidak bisa dipakai: {e}")
            accts = []
        if accts:
            opt = st.selectbox("Akun Instagram Business", accts,
                               format_func=lambda a: f"@{a['username']} · Page {a['page']} · {a['followers'] or 0:,} follower".replace(",", "."))
            if st.button("Simpan koneksi", type="primary"):
                final = tok
                app_id, app_secret = S.secret("META_APP_ID"), S.secret("META_APP_SECRET")
                if app_id and app_secret:  # tukar ke token jangka panjang bila memungkinkan
                    try:
                        final = S.graph_get("oauth/access_token", tok, {"grant_type": "fb_exchange_token", "client_id": app_id,
                                                                        "client_secret": app_secret, "fb_exchange_token": tok})["access_token"]
                    except Exception:  # noqa: BLE001
                        final = tok
                dbg = S.meta_token_debug(final)
                S.save_token("meta", {"access_token": final}, {"ig_user_id": opt["ig_user_id"], "username": opt["username"],
                                                               "page": opt["page"], "expires_at": dbg.get("expires_at"),
                                                               "scopes": dbg.get("scopes")}, user["id"])
                auth.log_activity(user["id"], "hubung_meta", "api", None, f"Instagram @{opt['username']} terhubung")
                st.session_state.pop("meta_tok", None)
                st.session_state["flash_ok"] = f"Instagram @{opt['username']} terhubung. Klik sinkron untuk menarik data."
                st.rerun()
        elif tok and not accts:
            st.warning("Token valid tetapi tidak ada Facebook Page yang terhubung ke akun Instagram Business. "
                       "Pastikan IG Mitra10 = akun Business/Creator dan sudah ditautkan ke Facebook Page, lalu beri izin Page itu saat membuat token.")

# ---------------------------------------------------------------- TikTok
with t_tt:
    if not S.tiktok_ready():
        st.info("TikTok belum disiapkan. Langkah sekali saja:")
        st.markdown(
            "1. Buka **developers.tiktok.com** → buat App → tambahkan produk **Login Kit** dan **Display API**.\n"
            "2. Aktifkan scope `user.info.basic`, `user.info.profile`, `user.info.stats`, `video.list`.\n"
            f"3. Daftarkan Redirect URI: `{S.secret('APP_URL') or 'https://kol-app-b5spr735acpivshmftdig3.streamlit.app/'}`\n"
            "4. Ajukan review app ke TikTok (±beberapa hari).\n"
            "5. Setelah disetujui, isi di Streamlit → Settings → Secrets: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `APP_URL`.")
    else:
        main = tt_main
        if main:
            i = main.get("_info", {})
            st.success(f"TikTok Mitra10 terhubung: **{i.get('akun', '—')}** · {S_fmt(i.get('follower'))} follower")
            if st.button("Sinkron video TikTok Mitra10", icon=":material/sync:"):
                try:
                    r = S.sync_official_tiktok()
                    st.session_state["flash_ok"] = f"TikTok resmi: {r.get('video', 0)} video diperbarui."
                except Exception as e:  # noqa: BLE001
                    st.session_state["flash_err"] = f"Gagal: {e}"
                st.cache_data.clear()
                st.rerun()
        else:
            if st.button("Buat link login TikTok Mitra10", type="primary"):
                st.session_state["tt_main_url"] = S.tiktok_auth_url(S.new_oauth_state("tiktok:mitra10", user["id"]))
            if st.session_state.get("tt_main_url"):
                st.link_button("Login TikTok Mitra10 & beri izin", st.session_state["tt_main_url"])

        st.markdown("#### Undang KOL TikTok")
        st.caption("Metrik video TikTok milik KOL hanya bisa dibaca bila KOL memberi izin. Kirim link ini ke KOL; setelah mereka login & "
                   "menyetujui, video & follower mereka tersinkron otomatis tiap hari. Link berlaku 14 hari.")
        kols = db.df("SELECT id, username, tipe FROM kol_accounts WHERE status='aktif' ORDER BY username")
        if not kols.empty:
            pick = st.selectbox("KOL / portal", kols["id"], format_func=lambda x: kols.set_index("id").loc[x, "username"])
            if st.button("Buat link undangan"):
                st.code(S.tiktok_auth_url(S.new_oauth_state(f"tiktok:kol:{int(pick)}", user["id"])), language=None)
        conn = S.token_info("tiktok:kol:")
        if conn:
            st.dataframe(pd.DataFrame([{"KOL id": c["nama"].rsplit(":", 1)[1], "Akun TikTok": c["info_json"].get("akun"),
                                        "Follower": c["info_json"].get("follower"), "Terhubung": c["updated_at"]} for c in conn]),
                         hide_index=True, use_container_width=True)
            if st.button("Sinkron video KOL TikTok"):
                r = S.sync_kol_tiktok()
                st.session_state["flash_ok"] = f"TikTok KOL: {r['kol']} akun, {r['video']} video, {r['cocok']} cocok dengan baris campaign."
                st.cache_data.clear()
                st.rerun()

with t_log:
    log = db.df("""SELECT jenis AS "Jenis", mulai AS "Mulai", selesai AS "Selesai", ringkasan_json::text AS "Ringkasan"
                   FROM social_sync_log ORDER BY id DESC LIMIT 100""")
    st.dataframe(log, hide_index=True, use_container_width=True)
