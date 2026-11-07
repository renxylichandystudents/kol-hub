"""Buka app KOL Hub yang sudah di-deploy, bangunkan bila sedang tidur, dan pastikan halaman login tampil tanpa error.

Dipakai oleh .github/workflows/keepalive.yml. Keluar dengan kode 1 bila app tidak sehat, agar terlihat merah di GitHub Actions.
"""
import sys
import time

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://kol-app-b5spr735acpivshmftdig3.streamlit.app/"


def app_text(page) -> str:
    """Teks di dalam iframe aplikasi Streamlit (atau halaman itu sendiri)."""
    for f in page.frames:
        try:
            t = f.locator("body").inner_text(timeout=2000)
        except Exception:
            continue
        if "Masuk" in t or "Traceback" in t or "Error" in t:
            return t
    return page.locator("body").inner_text()


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=120_000)
    time.sleep(8)
    wake = page.get_by_role("button", name="Yes, get this app back up!")
    if wake.count():
        print("App sedang tidur — membangunkan…")
        wake.click()
    deadline = time.time() + 600  # build ulang setelah tidur bisa beberapa menit
    status = "timeout"
    while time.time() < deadline:
        time.sleep(15)
        t = app_text(page)
        if "Traceback" in t or "This app has encountered an error" in t:
            status = "error"
            print(t[:2000])
            break
        if "Masuk" in t and "Email kantor" in t:
            status = "ok"
            break
    browser.close()

print(f"Status app: {status}")
sys.exit(0 if status == "ok" else 1)
