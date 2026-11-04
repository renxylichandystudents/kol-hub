import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

needs_db = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL tidak di-set (uji integrasi dijalankan di CI)")


@pytest.fixture(scope="session")
def db_ready():
    """Jalankan migrasi (skema + data contoh) sekali dan buat akun uji per role."""
    from lib import auth, db, migrate
    migrate.ensure_schema(os.environ["DATABASE_URL"])
    users = {}
    for role, email in [("ecommerce", "ecom@test.local"), ("asst_manager", "asmen@test.local"), ("manager", "mgr@test.local"),
                        ("finance", "fin@test.local"), ("store", "store@test.local"), ("super_user", "su@test.local")]:
        u = db.one("SELECT id FROM users WHERE email=%s", (email,))
        if not u:
            scope = db.scalar("SELECT id FROM stores WHERE nama='Mitra10 Medan'") if role == "store" else None
            u = db.execute("""INSERT INTO users (nama, email, password_hash, must_change_password, scope_store_id)
                              VALUES (%s,%s,%s,FALSE,%s) RETURNING id""", (f"Uji {role}", email, auth.hash_password("Uji-Sandi-2026"), scope),
                           returning=True)
            db.execute("INSERT INTO user_roles (user_id, role) VALUES (%s,%s)", (u["id"], role))
        full = auth.find_user(email)
        users[role] = {"id": full["id"], "nama": full["nama"], "email": email, "role": role, "roles": list(full["roles"]),
                       "scope_store_id": full["scope_store_id"], "scope_zone_id": full["scope_zone_id"]}
    return users
