"""KOL Hub — Aplikasi Digital Marketing Mitra10 (Spesifikasi Final v1.0).

Prototipe Streamlit + PostgreSQL (Supabase). Menu menyesuaikan role pengguna.
"""
import streamlit as st

st.set_page_config(page_title="KOL Hub — Mitra10", page_icon="🎯", layout="wide", initial_sidebar_state="expanded")

from lib import auth, db, migrate, ui  # noqa: E402
from lib.rbac import can  # noqa: E402

ui.setup()

url = db.database_url()
if not url:
    st.error("DATABASE_URL belum di-set. Tambahkan di Streamlit Cloud → Settings → Secrets.")
    st.code('DATABASE_URL = "postgresql://postgres.<project>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres"', language="toml")
    st.stop()

try:
    migrate.ensure_schema(url)
    su_status = auth.bootstrap_superuser(url)
except Exception as e:  # koneksi/migrasi gagal → tampilkan jelas, jangan blank
    st.error(f"Tidak dapat menyiapkan database: {e}")
    st.stop()
st.session_state["_su_status"] = su_status

P = "views/"
PAGES = [
    # (file, judul, ikon, izin, bagian)
    ("dashboard.py", "Dashboard", ":material/dashboard:", "dashboard.view", "Utama"),
    ("social.py", "Social Media Listening", ":material/headphones:", "social.view", "Utama"),
    ("performa.py", "Performa Toko & Zona", ":material/location_on:", "stores.view", "Utama"),
    ("upload_traffic.py", "Upload Traffic Offline", ":material/upload:", "traffic.upload", "Utama"),
    ("impor_traffic.py", "Impor Traffic & Budget", ":material/table_view:", "traffic.upload", "Utama"),
    ("kol_db.py", "Database KOL & Portal", ":material/group:", "kol.view", "KOL & Toko"),
    ("kol_analisa.py", "Analisa & Scoring KOL", ":material/insights:", "kol.view", "KOL & Toko"),
    ("bandingkan.py", "Bandingkan KOL", ":material/compare_arrows:", "kol.view", "KOL & Toko"),
    ("mapping.py", "Mapping Toko, Zona & KOL", ":material/map:", "kol.view", "KOL & Toko"),
    ("laporan_kol.py", "Laporan Performa KOL & Portal", ":material/leaderboard:", "kol.view", "KOL & Toko"),
    ("impor.py", "Impor Excel KOL & Portal", ":material/upload_file:", "data.import", "KOL & Toko"),
    ("koneksi.py", "Koneksi Instagram & TikTok", ":material/link:", "api.manage", "KOL & Toko"),
    ("campaign.py", "Campaign & Pengajuan", ":material/list_alt:", "campaign.view", "Campaign"),
    ("seleksi.py", "Seleksi & Review KOL", ":material/checklist:", "campaign.edit", "Campaign"),
    ("draft.py", "Draft Pengajuan", ":material/edit_note:", "campaign.edit", "Campaign"),
    ("approval.py", "Review & Approval", ":material/rule:", "approve", "Campaign"),
    ("ro.py", "Form Approval RO", ":material/print:", "ro.view", "Campaign"),
    ("kalender.py", "Kalender Event", ":material/calendar_month:", "calendar.view", "Kalender & Brief"),
    ("timeline.py", "Timeline Produksi", ":material/view_timeline:", "calendar.view", "Kalender & Brief"),
    ("brief.py", "Creative Brief", ":material/draw:", "brief.edit", "Kalender & Brief"),
    ("report.py", "Report & Hasil", ":material/summarize:", "report.view", "Report & Pembayaran"),
    ("bukti.py", "Bukti Tayang & Status RO", ":material/photo_library:", "report.view", "Report & Pembayaran"),
    ("pembayaran.py", "Pembayaran & Pajak", ":material/payments:", "payment.view", "Report & Pembayaran"),
    ("request_toko.py", "Request KOL / Portal", ":material/storefront:", "request.create", "Request Toko"),
    ("request_approval.py", "Approval Request Toko", ":material/inbox:", "request.approve", "Request Toko"),
    ("model.py", "Model & Testing", ":material/science:", "ml.view", "Sistem"),
    ("akses.py", "Akses & Role", ":material/admin_panel_settings:", "admin.users", "Sistem"),
    ("akun.py", "Akun Saya", ":material/person:", "dashboard.view", "Sistem"),
]

# Callback OAuth TikTok (KOL atau akun Mitra10 memberi izin) — bisa datang tanpa sesi login
qp = st.query_params
if qp.get("code") and qp.get("state"):
    from lib import social_api as S
    try:
        st.success(S.handle_tiktok_callback(qp["code"], qp["state"]))
    except Exception as e:  # noqa: BLE001
        st.error(f"Gagal menghubungkan akun TikTok: {e}")
    st.query_params.clear()
    st.stop()
if qp.get("error") and qp.get("state"):
    st.warning(f"Izin TikTok tidak diberikan ({qp.get('error_description') or qp.get('error')}).")
    st.query_params.clear()
    st.stop()

user = auth.current_user()

if not user:
    login = st.Page(P + "login.py", title="Masuk", icon=":material/login:", default=True)
    st.navigation([login], position="hidden").run()
    st.stop()


def allowed(perm: str) -> bool:
    if perm == "approve":
        return can(user["role"], "submission.approve.level1") or can(user["role"], "submission.approve.level2")
    return can(user["role"], perm)


sections: dict[str, list] = {}
for i, (f, title, icon, perm, sec) in enumerate(PAGES):
    if allowed(perm):
        sections.setdefault(sec, []).append(st.Page(P + f, title=title, icon=icon, default=(f == "dashboard.py")))

with st.sidebar:
    st.markdown("<div class='kh-brand'><div class='kh-logo'>KH</div><div><b>KOL Hub</b>"
                "<small>Digital Marketing · Mitra10</small></div></div>", unsafe_allow_html=True)

nav = st.navigation(sections)

with st.sidebar:
    st.divider()
    st.markdown(f"**{ui.esc(user['nama'])}**  \nRole aktif: **{ui.role_label(user['role'])}**")
    if len(user["roles"]) > 1:
        new_role = st.selectbox("Ganti role", user["roles"], index=user["roles"].index(user["role"]),
                                format_func=ui.role_label, key="role_switch")
        if new_role != user["role"]:
            user["role"] = new_role
            auth.log_activity(user["id"], "ganti_role", "user", user["id"], f"Ganti role ke {new_role}")
            st.rerun()
    notes = ui.unread_notifications(user)
    with st.popover(f"Notifikasi · {len(notes)}", use_container_width=True):
        if not notes:
            st.caption("Tidak ada notifikasi baru.")
        for n in notes:
            st.markdown(f"- {ui.esc(n['pesan'])}  \n  <span class='kh-note'>{n['waktu']:%d %b %H.%M}</span>", unsafe_allow_html=True)
        if notes and st.button("Tandai sudah dibaca", key="notif_read"):
            db.execute("UPDATE notifications SET dibaca=TRUE WHERE id = ANY(%s)", ([n["id"] for n in notes],))
            st.rerun()
    if st.button("Keluar", use_container_width=True, icon=":material/logout:"):
        auth.logout()
        st.rerun()
    st.caption("61 toko · 10 zona · data 2026")

from lib import jobs  # noqa: E402

try:
    jobs.ensure_fresh()
except Exception as e:
    st.warning(f"Job analitik terjadwal gagal dijalankan: {e}. Layar memakai hasil terakhir yang tersedia.")

if not st.session_state.get("_social_checked"):
    st.session_state["_social_checked"] = True
    try:
        from lib import social_api as S
        if db.scalar("SELECT COUNT(*) FROM api_tokens"):
            def _sync():
                if any(S.run_daily().values()):
                    st.cache_data.clear()
            jobs._run_bg(_sync, "sosial")
    except Exception as e:  # noqa: BLE001
        st.warning(f"Sinkron Instagram/TikTok gagal: {e}")

nav.run()
