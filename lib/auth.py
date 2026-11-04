"""Autentikasi & activity log — Spesifikasi layar 1, 25 dan C.10.

- Kata sandi Argon2id; kunci akun 15 menit setelah 5 percobaan gagal.
- TOTP 2FA wajib; kata sandi sementara wajib diganti saat login pertama.
- Akun Super User awal dibuat dari Secrets SUPERUSER_EMAIL + SUPERUSER_INITIAL_PASSWORD (tidak ditulis di kode).
- Riwayat aktivitas tercatat di activity_log.
"""
from __future__ import annotations

import base64
import io
import os
import secrets
import string
from datetime import datetime, timedelta, timezone

import streamlit as st

from . import db

MAX_ATTEMPTS = 5
LOCK_MINUTES = 15
IDLE_MINUTES = 60


def _hasher():
    from argon2 import PasswordHasher
    return PasswordHasher()  # Argon2id, parameter default yang direkomendasikan


def hash_password(pw: str) -> str:
    return _hasher().hash(pw)


def verify_password(hash_: str, pw: str) -> bool:
    if not hash_ or not hash_.startswith("$argon2"):
        return False
    try:
        return _hasher().verify(hash_, pw)
    except Exception:
        return False


def password_problems(pw: str) -> list[str]:
    p = []
    if len(pw) < 10:
        p.append("minimal 10 karakter")
    if not any(c.isdigit() for c in pw):
        p.append("mengandung angka")
    if not any(c.isalpha() for c in pw):
        p.append("mengandung huruf")
    if pw.lower() == pw or pw.upper() == pw:
        p.append("huruf besar & kecil")
    return p


def temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(12))
        if not password_problems(pw):
            return pw


# ------------------------------------------------------------------ secrets
def _secret(name: str) -> str | None:
    try:
        v = st.secrets.get(name)
    except Exception:
        v = None
    return v or os.environ.get(name)


@st.cache_resource(show_spinner=False)
def bootstrap_superuser(_url: str) -> str:
    """Buat akun Super User awal bila belum ada (C.10). Return status singkat."""
    exists = db.scalar("SELECT COUNT(*) FROM user_roles WHERE role = 'super_user'")
    if exists:
        return "ada"
    email, pw = _secret("SUPERUSER_EMAIL"), _secret("SUPERUSER_INITIAL_PASSWORD")
    if not email or not pw:
        return "belum_dikonfigurasi"
    email = email.strip().lower()
    with db.transaction() as cur:
        u = cur.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
        if u:
            uid = u["id"]
            cur.execute("UPDATE users SET password_hash=%s, must_change_password=TRUE, is_active=TRUE WHERE id=%s",
                        (hash_password(pw), uid))
        else:
            uid = cur.execute("""INSERT INTO users (nama, email, password_hash, must_change_password)
                                 VALUES (%s, %s, %s, TRUE) RETURNING id""",
                              ("Super User", email, hash_password(pw))).fetchone()["id"]
        cur.execute("INSERT INTO user_roles (user_id, role) VALUES (%s, 'super_user') ON CONFLICT DO NOTHING", (uid,))
        cur.execute("INSERT INTO activity_log (user_id, aksi, entitas, entitas_id, label) VALUES (%s,'setup_superuser','user',%s,%s)",
                    (uid, str(uid), "Akun Super User awal dibuat oleh proses setup"))
    return "dibuat"


# ------------------------------------------------------------------ login flow
def find_user(email: str) -> dict | None:
    return db.one("""SELECT u.*, COALESCE(array_agg(r.role) FILTER (WHERE r.role IS NOT NULL), '{}') AS roles
                     FROM users u LEFT JOIN user_roles r ON r.user_id = u.id
                     WHERE lower(u.email) = lower(%s) GROUP BY u.id""", (email.strip(),))


def attempt_login(email: str, pw: str) -> tuple[dict | None, str | None]:
    u = find_user(email)
    now = datetime.now(timezone.utc)
    if not u or not u["is_active"]:
        return None, "Email atau kata sandi salah."
    if u["locked_until"] and u["locked_until"] > now:
        menit = int((u["locked_until"] - now).total_seconds() // 60) + 1
        return None, f"Akun dikunci sementara karena percobaan gagal berulang. Coba lagi dalam {menit} menit."
    if not verify_password(u["password_hash"], pw):
        n = u["failed_attempts"] + 1
        lock = now + timedelta(minutes=LOCK_MINUTES) if n >= MAX_ATTEMPTS else None
        db.execute("UPDATE users SET failed_attempts=%s, locked_until=%s WHERE id=%s",
                   (0 if lock else n, lock, u["id"]))
        log_activity(u["id"], "login_gagal", "user", u["id"], "Percobaan login gagal")
        if lock:
            return None, f"Terlalu banyak percobaan gagal. Akun dikunci {LOCK_MINUTES} menit."
        return None, f"Email atau kata sandi salah. Sisa percobaan: {MAX_ATTEMPTS - n}."
    if not u["roles"]:
        return None, "Akun belum memiliki role. Hubungi Super User."
    return u, None


def finish_login(u: dict, role: str, metode: str = "password"):
    db.execute("UPDATE users SET failed_attempts=0, locked_until=NULL, last_login_at=NOW() WHERE id=%s", (u["id"],))
    st.session_state["user"] = {
        "id": u["id"], "nama": u["nama"], "email": u["email"], "role": role, "roles": list(u["roles"]),
        "scope_store_id": u["scope_store_id"], "scope_zone_id": u["scope_zone_id"],
    }
    st.session_state["last_seen"] = datetime.now(timezone.utc)
    st.session_state.pop("login_stage", None)
    st.session_state.pop("pending_user", None)
    log_activity(u["id"], "login", "user", u["id"], f"Login sebagai {role} ({metode})")


def set_password(uid: int, pw: str):
    db.execute("UPDATE users SET password_hash=%s, must_change_password=FALSE WHERE id=%s", (hash_password(pw), uid))
    log_activity(uid, "ganti_kata_sandi", "user", uid, "Kata sandi diganti")


def new_totp_secret() -> str:
    import pyotp
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    import pyotp
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="KOL Hub Mitra10")


def verify_totp(secret: str, code: str) -> bool:
    import pyotp
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)


def qr_png(data: str) -> bytes | None:
    try:
        import qrcode
        img = qrcode.make(data)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def enable_totp(uid: int, secret: str):
    db.execute("UPDATE users SET totp_secret=%s, totp_enabled=TRUE WHERE id=%s", (secret, uid))
    log_activity(uid, "aktifkan_2fa", "user", uid, "Verifikasi 2 langkah diaktifkan")


def current_user() -> dict | None:
    u = st.session_state.get("user")
    if not u:
        return None
    last = st.session_state.get("last_seen")
    now = datetime.now(timezone.utc)
    if last and now - last > timedelta(minutes=IDLE_MINUTES):
        logout(reason="Sesi berakhir karena tidak aktif.")
        return None
    st.session_state["last_seen"] = now
    return u


def logout(reason: str | None = None):
    u = st.session_state.get("user")
    if u:
        log_activity(u["id"], "logout", "user", u["id"], "Logout")
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    if reason:
        st.session_state["flash"] = reason


# ------------------------------------------------------------------ SSO Google Workspace (opsional)
def sso_configured() -> bool:
    try:
        return hasattr(st, "login") and "auth" in st.secrets
    except Exception:
        return False


def sso_user_email() -> str | None:
    try:
        if getattr(st.user, "is_logged_in", False):
            return st.user.get("email")
    except Exception:
        pass
    return None


# ------------------------------------------------------------------ activity log
def log_activity(user_id, aksi: str, entitas: str | None = None, entitas_id=None, label: str | None = None,
                 sebelum=None, sesudah=None):
    try:
        ip = None
        try:
            ip = st.context.headers.get("X-Forwarded-For", "").split(",")[0] or None
        except Exception:
            pass
        db.execute("""INSERT INTO activity_log (user_id, aksi, entitas, entitas_id, label, sebelum_json, sesudah_json, ip)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                   (user_id, aksi, entitas, None if entitas_id is None else str(entitas_id), label, sebelum, sesudah, ip))
    except Exception:
        pass  # pencatatan tidak boleh menggagalkan aksi utama


def b64(png: bytes) -> str:
    return base64.b64encode(png).decode()
