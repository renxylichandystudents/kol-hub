"""Uji integrasi alur C.4 + hak akses C.6 (C.9): draft → ajukan → tolak → revisi → setuju → RO → Finance."""
from datetime import date, datetime, timedelta

import pytest

from tests.conftest import needs_db

pytestmark = needs_db


def test_seed_and_master(db_ready):
    from lib import db
    assert db.scalar("SELECT COUNT(*) FROM stores") == 61
    assert db.scalar("SELECT COUNT(*) FROM zones") == 10
    assert db.scalar("SELECT COUNT(*) FROM kol_accounts") > 40


def test_login_lockout_and_password(db_ready):
    from lib import auth, db
    u, err = auth.attempt_login("ecom@test.local", "Uji-Sandi-2026")
    assert u and not err
    for _ in range(5):
        auth.attempt_login("fin@test.local", "salah")
    u, err = auth.attempt_login("fin@test.local", "Uji-Sandi-2026")
    assert u is None and "dikunci" in err
    db.execute("UPDATE users SET failed_attempts=0, locked_until=NULL WHERE email='fin@test.local'")
    assert auth.password_problems("pendek") and not auth.password_problems("Panjang-Sekali-2026")


def test_full_submission_flow(db_ready):
    from lib import db
    from lib import workflow as W
    from lib.rbac import Forbidden
    U = db_ready
    stores = db.query("SELECT id FROM stores WHERE nama IN ('Mitra10 Medan','Mitra10 Semarang') ORDER BY nama")
    kols = db.query("SELECT id FROM kol_accounts WHERE status='aktif' ORDER BY id LIMIT 3")
    blocked = db.scalar("SELECT id FROM kol_accounts WHERE status='diblokir' LIMIT 1")
    res = W.create_campaign(U["ecommerce"], "Uji Integrasi", "uji", date.today() + timedelta(days=10), date.today() + timedelta(days=20),
                            50_000_000, "grup", 3, [], [s["id"] for s in stores])
    sub = res["submission_id"]
    i1 = W.add_item(U["ecommerce"], sub, kols[0]["id"], stores[0]["id"], None, date.today() + timedelta(days=12))
    i2 = W.add_item(U["ecommerce"], sub, kols[1]["id"], stores[1]["id"], None, date.today() + timedelta(days=12))
    with pytest.raises(W.WorkflowError):
        W.add_item(U["ecommerce"], sub, blocked, stores[0]["id"], None, None)          # daftar blokir
    with pytest.raises(Forbidden):
        W.add_item(U["finance"], sub, kols[2]["id"], stores[0]["id"], None, None)      # finance tidak boleh
    W.submit(U["ecommerce"], sub)
    assert db.scalar("SELECT status FROM submissions WHERE id=%s", (sub,)) == "Review Asisten Manager"
    with pytest.raises(W.WorkflowError):
        W.decide(U["manager"], sub, 2, {i1: ("setuju", None), i2: ("setuju", None)})  # Manager belum giliran (masih level 1)
    with pytest.raises(Forbidden):
        W.decide(U["manager"], sub, 1, {i1: ("setuju", None), i2: ("setuju", None)})  # Manager tidak berhak level 1
    with pytest.raises(W.WorkflowError):
        W.decide(U["asst_manager"], sub, 1, {i1: ("setuju", None), i2: ("tolak", "")})  # catatan wajib
    W.decide(U["asst_manager"], sub, 1, {i1: ("setuju", None), i2: ("tolak", "audiens tidak relevan")})
    assert db.scalar("SELECT status FROM submissions WHERE id=%s", (sub,)) == "Ditolak"
    W.resubmit_prepare(U["ecommerce"], sub)
    with pytest.raises(W.WorkflowError):
        W.submit(U["ecommerce"], sub)                                                   # baris ditolak belum ditentukan
    W.replace_item(U["ecommerce"], i2, kols[2]["id"])
    W.submit(U["ecommerce"], sub)
    s = db.one("SELECT status, revisi_ke FROM submissions WHERE id=%s", (sub,))
    assert s["status"] == "Review Asisten Manager" and s["revisi_ke"] == 1
    items = [r["id"] for r in db.query("SELECT id FROM submission_items WHERE submission_id=%s AND aktif", (sub,))]
    W.decide(U["asst_manager"], sub, 1, {i: ("setuju", None) for i in items})
    W.decide(U["manager"], sub, 2, {i: ("setuju", None) for i in items})
    ro = db.one("SELECT * FROM ro_forms WHERE submission_id=%s", (sub,))
    assert ro and db.scalar("SELECT status FROM submissions WHERE id=%s", (sub,)) == "Form RO dibuat"
    pays = db.query("SELECT * FROM payments WHERE ro_id=%s", (ro["id"],))
    assert len(pays) == len(items) and all(p["status"] == "tertahan" for p in pays)
    assert all(p["pajak_nominal"] > 0 for p in pays)
    assert db.scalar("SELECT COUNT(*) FROM production_tasks WHERE item_id = ANY(%s)", (items,)) == 6 * len(items)
    W.upload_signed_ro(U["ecommerce"], ro["id"], "scan.pdf", b"%PDF-scan")
    assert db.scalar("SELECT status FROM submissions WHERE id=%s", (sub,)) == "Di Finance"
    assert db.scalar("SELECT status FROM payments WHERE item_id=%s", (items[0],)) == "tertahan"   # bukti belum ada
    with pytest.raises(W.WorkflowError):
        W.update_payment(U["finance"], pays[0]["id"], "lunas")
    for it in items:
        r = W.save_proof(U["ecommerce"], it, "https://example.com/p", datetime.now(), ("b.png", b"x" * 300), ("i.png", b"y" * 300),
                         {"views": 1000, "likes": 50, "komentar": 5, "share": 3, "save": 2})
        assert r["post_id"]
    assert {p["status"] for p in db.query("SELECT status FROM payments WHERE ro_id=%s", (ro["id"],))} == {"siap"}
    for p in db.query("SELECT id FROM payments WHERE ro_id=%s", (ro["id"],)):
        W.update_payment(U["finance"], p["id"], "lunas")
    assert db.scalar("SELECT status FROM submissions WHERE id=%s", (sub,)) == "Lunas"
    assert db.scalar("SELECT status FROM campaigns WHERE id=%s", (res["campaign_id"],)) == "Selesai"
    assert db.scalar("SELECT COUNT(*) FROM activity_log WHERE entitas='submission' AND entitas_id=%s", (str(sub),)) >= 5


def test_segregation_of_duties(db_ready):
    from lib import db
    from lib import workflow as W
    from lib.rbac import Forbidden
    U = db_ready
    su = U["super_user"]
    st_id = db.scalar("SELECT id FROM stores WHERE nama='Mitra10 Garut'")
    kol = db.scalar("SELECT id FROM kol_accounts WHERE status='aktif' ORDER BY id DESC LIMIT 1")
    s = W.create_single_submission(su, kol, st_id, 2_000_000, date.today() + timedelta(days=9))
    W.submit(su, s["submission_id"])
    items = {r["id"]: ("setuju", None) for r in db.query("SELECT id FROM submission_items WHERE submission_id=%s", (s["submission_id"],))}
    with pytest.raises(Forbidden):
        W.decide(su, s["submission_id"], 1, items)          # tidak boleh menyetujui pengajuan sendiri


def test_store_request_flow(db_ready):
    from lib import db
    from lib import workflow as W
    from lib.rbac import Forbidden
    U = db_ready
    store = U["store"]
    other = db.scalar("SELECT id FROM stores WHERE id <> %s LIMIT 1", (store["scope_store_id"],))
    acc = {"nama": "Akun Uji Baru", "platform": "TikTok", "username": "@akunujibaru", "link": "https://www.tiktok.com/@akunujibaru",
           "follower": 50000, "kontak": "-", "bio": "review kuliner medan", "kota": "Medan"}
    with pytest.raises(Forbidden):
        W.create_request(store, other, "x", date.today(), date.today(), None, acc, 2_000_000, None)
    no = W.create_request(store, store["scope_store_id"], "butuh KOL kuliner", date.today() + timedelta(days=5),
                          date.today() + timedelta(days=15), None, acc, 2_000_000, None)
    rid = db.scalar("SELECT id FROM store_requests WHERE no_request=%s", (no,))
    cek = db.scalar("SELECT cek_sistem_json FROM store_requests WHERE id=%s", (rid,))
    assert cek["kategori_saran"] == "culinary"
    with pytest.raises(W.WorkflowError):
        W.review_request(U["ecommerce"], rid, "tolak", "")
    res = W.review_request(U["ecommerce"], rid, "setujui", None, "culinary")
    assert res.get("kol_baru") and "tunggal" in res["masuk"]
    assert db.scalar("SELECT status FROM store_requests WHERE id=%s", (rid,)) == "Disetujui"
    assert db.scalar("SELECT COUNT(*) FROM kol_accounts WHERE username_norm='akunujibaru'") == 1


def test_rbac_matrix():
    from lib.rbac import can
    assert can("store", "request.create") and not can("store", "kol.view") and not can("store", "payment.view")
    assert can("finance", "payment.manage") and not can("finance", "campaign.edit")
    assert can("asst_manager", "submission.approve.level1") and not can("asst_manager", "submission.approve.level2")
    assert can("manager", "submission.approve.level2") and not can("manager", "campaign.edit")
    assert can("super_user", "admin.users") and not can("ecommerce", "admin.users")


def test_jobs_and_gates(db_ready):
    from lib import db, jobs
    out = jobs.run_all()
    assert out["nlp"]["diproses"] >= 0
    assert db.scalar("SELECT COUNT(*) FROM comment_nlp") > 3000
    assert db.scalar("SELECT COUNT(*) FROM model_runs") >= 8
    assert db.scalar("SELECT COUNT(*) FROM predictions WHERE tipe='skor'") > 40
    gates = {r["model"]: r["gate"] for r in db.query("SELECT DISTINCT ON (model) model, gate FROM model_runs ORDER BY model, dijalankan DESC")}
    errors = {r["model"]: r["metrik_json"] for r in db.query("SELECT model, metrik_json FROM model_runs WHERE metrik_json ? 'error'")}
    print("GATES", gates, "ERRORS", errors)
    assert not errors, f"Fungsi gate crash: {errors}"
    assert gates.get("Optimasi budget") == "lulus"
    assert gates.get("Sentimen komentar") == "lulus"


def test_item_predictions_fill_empty(db_ready):
    """Baris tanpa prediksi tersimpan (data contoh) tetap mendapat prediksi kunjungan & harga wajar."""
    import pandas as pd
    from lib import db
    from lib import workflow as W
    rows = db.df("""SELECT i.kol_id, i.store_id, '{}'::jsonb AS prediksi_json FROM submission_items i
                    JOIN kol_accounts k ON k.id=i.kol_id WHERE k.status='aktif' LIMIT 3""")
    preds = W.item_predictions(rows)
    assert len(preds) == len(rows) > 0
    assert all(p.get("kunjungan", 0) > 0 and p.get("harga_wajar", 0) > 0 for p in preds), preds
    # prediksi yang sudah tersimpan tidak ditimpa
    kept = W.item_predictions(pd.DataFrame([{"kol_id": rows.iloc[0]["kol_id"], "store_id": rows.iloc[0]["store_id"],
                                             "prediksi_json": {"kunjungan": 123, "harga_wajar": 5e6}}]))
    assert kept[0]["kunjungan"] == 123
