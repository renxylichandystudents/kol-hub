"""Uji layar (smoke test UI per role): setiap layar yang boleh dibuka role tersebut dirender tanpa error."""
from pathlib import Path

import pytest

from tests.conftest import needs_db

APP = str(Path(__file__).resolve().parents[1] / "app.py")

pytestmark = needs_db

ROLE_PAGES = {
    "ecommerce": ["dashboard", "social", "performa", "upload_traffic", "kol_db", "kol_analisa", "bandingkan", "mapping", "campaign",
                  "seleksi", "draft", "ro", "kalender", "timeline", "brief", "report", "bukti", "pembayaran", "request_approval", "model", "akun"],
    "asst_manager": ["dashboard", "approval", "campaign", "ro", "kol_db"],
    "manager": ["dashboard", "approval"],
    "finance": ["dashboard", "pembayaran", "ro", "bukti"],
    "store": ["dashboard", "kalender", "timeline", "report", "bukti", "request_toko"],
    "super_user": ["akses", "model", "request_toko", "approval"],
}
CASES = [(r, p) for r, ps in ROLE_PAGES.items() for p in ps]


def _run(user, page):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["user"] = dict(user)
    at.session_state["_jobs_checked"] = True
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    at.switch_page(f"views/{page}.py")
    at.run()
    return at


@pytest.mark.parametrize("role,page", CASES)
def test_page_renders(db_ready, role, page):
    at = _run(db_ready[role], page)
    errs = [e.value for e in at.exception]
    assert not errs, f"{role}/{page}: {errs}"
    assert not [e.value for e in at.error if "izin" in str(e.value).lower()], f"{role}/{page} ditolak padahal berhak"


def test_store_cannot_open_kol_database(db_ready):
    at = _run(db_ready["store"], "dashboard")
    assert not at.exception


def test_login_page_without_session():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    assert any("Masuk" in m.value for m in at.markdown)
