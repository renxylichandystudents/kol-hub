"""Akun saya: ganti kata sandi & riwayat login."""
import streamlit as st

from lib import auth, db, ui

user = auth.current_user()
ui.header("Akun Saya", f"{user['nama']} · {user['email']}")

with st.form("chpw"):
    old = st.text_input("Kata sandi saat ini", type="password")
    p1 = st.text_input("Kata sandi baru", type="password")
    p2 = st.text_input("Ulangi kata sandi baru", type="password")
    ok = st.form_submit_button("Ganti kata sandi", type="primary")
if ok:
    u = db.one("SELECT password_hash FROM users WHERE id=%s", (user["id"],))
    probs = auth.password_problems(p1)
    if not auth.verify_password(u["password_hash"], old):
        st.error("Kata sandi saat ini salah.")
    elif p1 != p2:
        st.error("Kata sandi baru tidak sama.")
    elif probs:
        st.error("Kata sandi harus: " + ", ".join(probs) + ".")
    else:
        auth.set_password(user["id"], p1)
        st.success("Kata sandi diganti.")

st.markdown("#### Riwayat aktivitas saya")
st.dataframe(db.df("SELECT waktu, aksi, label, ip FROM activity_log WHERE user_id=%s ORDER BY waktu DESC LIMIT 100", (user["id"],)),
             hide_index=True, use_container_width=True,
             column_config={"waktu": st.column_config.DatetimeColumn("Waktu", format="DD MMM YYYY HH:mm")})
