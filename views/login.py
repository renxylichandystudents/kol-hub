"""Layar 1 — Login & Pilih Role. Akun hanya didaftarkan oleh Super User."""
import streamlit as st

from lib import auth, ui

st.markdown("<style>section[data-testid='stSidebar']{display:none}</style>", unsafe_allow_html=True)

left, right = st.columns([1.05, 1], gap="large")
with left:
    st.markdown(
        "<div style='background:#111a33;border-radius:18px;padding:2.2rem 2rem;color:#e6ebf5;min-height:440px'>"
        "<div class='kh-brand'><div class='kh-logo'>KH</div><div><b>KOL Hub</b><small>Digital Marketing · Mitra10</small></div></div>"
        "<h3 style='color:#fff;margin-top:1.2rem'>Kelola KOL & Portal News dari hulu ke hilir</h3>"
        "<p style='color:#b9c5e0'>Baca kebutuhan toko & percakapan media sosial, pilih KOL berbasis data, ajukan & setujui campaign, "
        "cetak Form RO, pantau tayang, ukur dampak ke traffic toko, hingga pembayaran.</p>"
        "<p style='color:#8ea0c6;font-size:.85rem;margin-top:2rem'>61 toko · 10 zona · Instagram & TikTok Mitra10 Official</p></div>",
        unsafe_allow_html=True)

with right:
    msg = st.session_state.pop("flash", None)
    if msg:
        st.info(msg)
    stage = st.session_state.get("login_stage", "cred")
    pending = st.session_state.get("pending_user")

    if st.session_state.get("_su_status") == "belum_dikonfigurasi":
        st.warning("Belum ada akun Super User. Tambahkan **SUPERUSER_EMAIL** dan **SUPERUSER_INITIAL_PASSWORD** di Secrets "
                   "Streamlit Cloud, lalu reboot app. Kata sandi awal wajib diganti dan 2FA diaktifkan saat login pertama.")

    if stage == "cred" or not pending:
        st.markdown("### Masuk")
        st.caption("Gunakan email kantor. Akun didaftarkan oleh Super User.")
        with st.form("login"):
            email = st.text_input("Email kantor", placeholder="nama@mitra10.co.id")
            pw = st.text_input("Kata sandi", type="password")
            ok = st.form_submit_button("Masuk", type="primary", use_container_width=True)
        if ok:
            u, err = auth.attempt_login(email, pw)
            if err:
                st.error(err)
            else:
                u = {k: v for k, v in u.items() if k not in ("password_hash", "totp_secret")}
                st.session_state["pending_user"] = u
                st.session_state["login_stage"] = "change_pw" if u["must_change_password"] else (
                    "totp" if u["totp_enabled"] else "enroll")
                st.rerun()
        if auth.sso_configured():
            sso_email = auth.sso_user_email()
            if sso_email:
                u = auth.find_user(sso_email)
                if u and u["is_active"] and u["roles"]:
                    st.session_state["pending_user"] = u
                    st.session_state["login_stage"] = "role"
                    st.session_state["sso"] = True
                    st.rerun()
                else:
                    st.error(f"{sso_email} belum didaftarkan oleh Super User.")
            st.button("Masuk dengan Google Workspace", on_click=st.login, use_container_width=True, icon=":material/account_circle:")

    elif stage == "change_pw":
        st.markdown("### Ganti kata sandi sementara")
        st.caption("Wajib saat login pertama. Minimal 10 karakter, huruf besar & kecil, dan angka.")
        with st.form("chpw"):
            p1 = st.text_input("Kata sandi baru", type="password")
            p2 = st.text_input("Ulangi kata sandi baru", type="password")
            ok = st.form_submit_button("Simpan", type="primary", use_container_width=True)
        if ok:
            probs = auth.password_problems(p1)
            if p1 != p2:
                st.error("Kata sandi tidak sama.")
            elif probs:
                st.error("Kata sandi harus: " + ", ".join(probs) + ".")
            else:
                auth.set_password(pending["id"], p1)
                st.session_state["login_stage"] = "totp" if pending["totp_enabled"] else "enroll"
                st.rerun()

    elif stage == "enroll":
        st.markdown("### Aktifkan verifikasi 2 langkah")
        st.caption("Pindai kode QR dengan Google Authenticator / Microsoft Authenticator, lalu masukkan 6 digit kode.")
        if "totp_secret_new" not in st.session_state:
            st.session_state["totp_secret_new"] = auth.new_totp_secret()
        secret = st.session_state["totp_secret_new"]
        uri = auth.totp_uri(secret, pending["email"])
        png = auth.qr_png(uri)
        if png:
            st.image(png, width=190)
        st.code(secret, language=None)
        with st.form("enroll"):
            code = st.text_input("Kode 6 digit", max_chars=6)
            ok = st.form_submit_button("Verifikasi & aktifkan", type="primary", use_container_width=True)
        if ok:
            if auth.verify_totp(secret, code):
                auth.enable_totp(pending["id"], secret)
                st.session_state.pop("totp_secret_new", None)
                st.session_state["login_stage"] = "role"
                st.rerun()
            else:
                st.error("Kode tidak cocok. Pastikan jam di ponsel akurat lalu coba lagi.")

    elif stage == "totp":
        st.markdown("### Verifikasi 2 langkah")
        with st.form("totp"):
            code = st.text_input("Kode dari aplikasi authenticator", max_chars=6)
            ok = st.form_submit_button("Verifikasi", type="primary", use_container_width=True)
        if ok:
            fresh = auth.find_user(pending["email"])
            if auth.verify_totp(fresh["totp_secret"], code):
                st.session_state["login_stage"] = "role"
                st.rerun()
            else:
                auth.log_activity(pending["id"], "2fa_gagal", "user", pending["id"], "Kode 2FA salah")
                st.error("Kode salah.")

    if st.session_state.get("login_stage") == "role" and pending:
        roles = list(pending["roles"])
        if len(roles) == 1:
            auth.finish_login(pending, roles[0], "sso" if st.session_state.get("sso") else "password+2fa")
            st.rerun()
        st.markdown("### Pilih role")
        st.caption("Menu menyesuaikan role yang dipilih.")
        r = st.radio("Masuk sebagai", roles, format_func=ui.role_label)
        if st.button("Lanjut", type="primary", use_container_width=True):
            auth.finish_login(pending, r, "sso" if st.session_state.get("sso") else "password+2fa")
            st.rerun()

    if stage != "cred" and pending and st.button("Batal", key="cancel_login"):
        for k in ("pending_user", "login_stage", "totp_secret_new", "sso"):
            st.session_state.pop(k, None)
        st.rerun()
