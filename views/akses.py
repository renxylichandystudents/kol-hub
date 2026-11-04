"""Layar 25 — Akses & Role: Super User mendaftarkan akun dan memantau aktivitas."""
from datetime import date, timedelta

import streamlit as st

from lib import auth, db, ui
from lib.master import ROLES
from lib.rbac import PERMISSIONS, require

user = auth.current_user()
require(user["role"], "admin.users")
ui.header("Akses & Role", "Super User mendaftarkan akun, mengatur role & cakupan toko/zona, dan memantau aktivitas")
ui.flash()

stores, zones = ui.stores(), ui.zones()
t1, t2, t3, t4, t5 = st.tabs(["Daftarkan akun", "Pengguna", "Riwayat aktivitas", "Matriks hak akses", "Data contoh"])

with t1:
    st.caption("Role approver: **Asisten Manager** (level 1) dan **Manager** (level 2). Kata sandi sementara wajib diganti dan 2FA "
               "diaktifkan saat login pertama.")
    with st.form("new_user", clear_on_submit=False):
        c1, c2 = st.columns(2)
        nama = c1.text_input("Nama lengkap")
        email = c2.text_input("Email kantor")
        roles = st.multiselect("Role", list(ROLES), format_func=ui.role_label, help="Satu orang boleh punya lebih dari satu role; dipilih saat login.")
        c3, c4 = st.columns(2)
        zsel = c3.selectbox("Cakupan zona (opsional)", ["—"] + list(zones["nama"]))
        ssel = c4.selectbox("Cakupan toko (wajib untuk role Store)", ["—"] + list(stores["nama"]))
        ok = st.form_submit_button("Daftarkan akun", type="primary")
    if ok:
        err = None
        if not nama.strip() or "@" not in email:
            err = "Nama dan email valid wajib diisi."
        elif not roles:
            err = "Pilih minimal satu role."
        elif "store" in roles and ssel == "—":
            err = "Role Store wajib memiliki cakupan toko."
        elif db.scalar("SELECT 1 FROM users WHERE lower(email)=lower(%s)", (email.strip(),)):
            err = "Email sudah terdaftar."
        if err:
            st.error(err)
        else:
            pw = auth.temp_password()
            zid = None if zsel == "—" else int(zones[zones["nama"] == zsel]["id"].iloc[0])
            sid = None if ssel == "—" else int(stores[stores["nama"] == ssel]["id"].iloc[0])
            if sid and not zid:
                zid = int(stores[stores["id"] == sid]["zone_id"].iloc[0])
            with db.transaction() as cur:
                uid = cur.execute("""INSERT INTO users (nama, email, password_hash, must_change_password, scope_zone_id, scope_store_id, created_by)
                                     VALUES (%s,%s,%s,TRUE,%s,%s,%s) RETURNING id""",
                                  (nama.strip(), email.strip().lower(), auth.hash_password(pw), zid, sid, user["id"])).fetchone()["id"]
                for r in roles:
                    cur.execute("INSERT INTO user_roles (user_id, role) VALUES (%s,%s)", (uid, r))
            auth.log_activity(user["id"], "daftarkan_akun", "user", uid, f"Akun {email} didaftarkan ({', '.join(roles)})")
            st.success(f"Akun **{email}** terdaftar. Berikan kata sandi sementara berikut secara langsung (hanya ditampilkan sekali):")
            st.code(pw, language=None)

with t2:
    users = db.df("""SELECT u.id, u.nama, u.email, COALESCE(string_agg(r.role, ', ' ORDER BY r.role), '') AS roles,
                            z.nama AS zona, s.nama AS toko, u.is_active, u.totp_enabled, u.must_change_password, u.last_login_at,
                            u.locked_until
                     FROM users u LEFT JOIN user_roles r ON r.user_id=u.id LEFT JOIN zones z ON z.id=u.scope_zone_id
                     LEFT JOIN stores s ON s.id=u.scope_store_id WHERE u.id <> 1
                     GROUP BY u.id, z.nama, s.nama ORDER BY u.nama""")
    if users.empty:
        st.info("Belum ada pengguna.")
    else:
        st.dataframe(users.drop(columns=["id"]), hide_index=True, use_container_width=True, column_config={
            "is_active": st.column_config.CheckboxColumn("Aktif"), "totp_enabled": st.column_config.CheckboxColumn("2FA"),
            "must_change_password": st.column_config.CheckboxColumn("Wajib ganti sandi"),
            "last_login_at": st.column_config.DatetimeColumn("Login terakhir", format="DD MMM YYYY HH:mm")})
        st.markdown("#### Kelola akun")
        pick = st.selectbox("Pilih akun", users["email"], key="mgr_user")
        row = users[users["email"] == pick].iloc[0]
        uid = int(row["id"])
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("Nonaktifkan" if row["is_active"] else "Aktifkan", disabled=uid == user["id"]):
            db.execute("UPDATE users SET is_active = NOT is_active WHERE id=%s", (uid,))
            auth.log_activity(user["id"], "ubah_status_akun", "user", uid, f"Status akun {pick} diubah")
            st.rerun()
        if c2.button("Reset kata sandi"):
            pw = auth.temp_password()
            db.execute("UPDATE users SET password_hash=%s, must_change_password=TRUE, failed_attempts=0, locked_until=NULL WHERE id=%s",
                       (auth.hash_password(pw), uid))
            auth.log_activity(user["id"], "reset_kata_sandi", "user", uid, f"Kata sandi {pick} direset")
            st.success("Kata sandi sementara baru (tampil sekali):")
            st.code(pw, language=None)
        if c3.button("Reset 2FA"):
            db.execute("UPDATE users SET totp_enabled=FALSE, totp_secret=NULL WHERE id=%s", (uid,))
            auth.log_activity(user["id"], "reset_2fa", "user", uid, f"2FA {pick} direset")
            st.success("2FA direset — pengguna akan diminta mengaktifkan ulang saat login.")
        if c4.button("Buka kunci"):
            db.execute("UPDATE users SET failed_attempts=0, locked_until=NULL WHERE id=%s", (uid,))
            st.success("Kunci akun dibuka.")
        cur_roles = [r for r in (row["roles"] or "").split(", ") if r]
        new_roles = st.multiselect("Role", list(ROLES), default=cur_roles, format_func=ui.role_label, key=f"roles_{uid}")
        if st.button("Simpan role") and new_roles != cur_roles:
            if uid == user["id"] and "super_user" not in new_roles:
                st.error("Anda tidak dapat mencabut role Super User dari akun sendiri.")
            elif not new_roles:
                st.error("Minimal satu role.")
            else:
                with db.transaction() as cur:
                    cur.execute("DELETE FROM user_roles WHERE user_id=%s", (uid,))
                    for r in new_roles:
                        cur.execute("INSERT INTO user_roles (user_id, role) VALUES (%s,%s)", (uid, r))
                auth.log_activity(user["id"], "ubah_role", "user", uid, f"Role {pick}: {', '.join(new_roles)}",
                                  sebelum={"roles": cur_roles}, sesudah={"roles": new_roles})
                st.rerun()

with t3:
    c1, c2, c3 = st.columns(3)
    emails = db.df("SELECT email FROM users WHERE id<>1 ORDER BY email")
    who = c1.selectbox("Pengguna", ["Semua"] + (list(emails["email"]) if not emails.empty else []))
    since = c2.date_input("Sejak", date.today() - timedelta(days=30))
    aksi = c3.text_input("Cari aksi/label")
    sql = """SELECT a.waktu, u.email, a.aksi, a.label, a.entitas, a.entitas_id, a.ip FROM activity_log a
             LEFT JOIN users u ON u.id=a.user_id WHERE a.waktu::date >= %s"""
    params = [since]
    if who != "Semua":
        sql += " AND u.email=%s"; params.append(who)
    if aksi:
        sql += " AND (a.aksi ILIKE %s OR a.label ILIKE %s)"; params += [f"%{aksi}%", f"%{aksi}%"]
    log = db.df(sql + " ORDER BY a.waktu DESC LIMIT 1000", params)
    st.dataframe(log, hide_index=True, use_container_width=True,
                 column_config={"waktu": st.column_config.DatetimeColumn("Waktu", format="DD MMM YYYY HH:mm:ss")})

with t4:
    import pandas as pd
    mat = pd.DataFrame({ui.role_label(r): ["✓" if r in roles else "" for roles in PERMISSIONS.values()] for r in ROLES},
                       index=list(PERMISSIONS))
    st.caption("Izin dicek di setiap aksi (bukan hanya menyembunyikan menu). Role Store hanya melihat data tokonya.")
    st.dataframe(mat, use_container_width=True)

with t5:
    require(user["role"], "data.reset_sample")
    st.warning("Data contoh (KOL, campaign, traffic, komentar, pembayaran) dipakai untuk mencoba semua layar. "
               "Hapus sebelum go-live. Master 61 toko/10 zona, akun pengguna, aturan pajak, dan riwayat aktivitas tetap disimpan.")
    conf = st.text_input("Ketik HAPUS DATA CONTOH untuk konfirmasi")
    if st.button("Hapus data contoh", type="primary", disabled=conf != "HAPUS DATA CONTOH"):
        with db.transaction() as cur:
            cur.execute("""TRUNCATE notifications, predictions, model_runs, data_checks, comment_nlp, social_comments, official_posts,
                           post_metrics, posts, production_tasks, brief_sections, briefs, payments, ro_forms, approvals, submission_items,
                           submissions, campaigns, store_requests, offline_traffic_daily, uploads, vendor_documents, ratecards,
                           kol_metrics_snapshot, kol_accounts, promo_offline_events RESTART IDENTITY CASCADE""")
        auth.log_activity(user["id"], "hapus_data_contoh", "sistem", None, "Data contoh dihapus")
        st.cache_data.clear()
        st.session_state["flash_ok"] = "Data contoh dihapus. Silakan upload database KOL & traffic offline yang sebenarnya."
        st.rerun()
