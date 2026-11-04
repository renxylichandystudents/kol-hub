"""Alur status (state machine) — Spesifikasi C.4, dengan RBAC (C.6), activity log & notifikasi.

Campaign / Pengajuan:
  Draft → Review Asisten Manager → Review Manager → Disetujui → Form RO dibuat → RO ditandatangani → Di Finance
  → Dibayar sebagian → Lunas → Selesai ; Ditolak (catatan per baris) → Revisi → Diajukan (revisi_ke + 1)
Pembayaran per baris: tertahan → siap → diproses → lunas
Request toko: Diajukan → Review DM → Disetujui (akun baru masuk database) → pengajuan tunggal / draft campaign | Ditolak | Minta info
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta

import streamlit as st

from . import analytics as A
from . import db
from .auth import log_activity
from .rbac import Forbidden, require
from .ui import notify

YEAR = date.today().year


class WorkflowError(Exception):
    pass


def _next_no(cur, table: str, col: str, prefix: str) -> str:
    r = cur.execute(f"SELECT {col} AS no FROM {table} WHERE {col} LIKE %s ORDER BY {col} DESC LIMIT 1",
                    (f"{prefix}-{YEAR}-%",)).fetchone()
    n = int(r["no"].rsplit("-", 1)[1]) + 1 if r else 1
    return f"{prefix}-{YEAR}-{n:03d}"


def _clear():
    st.cache_data.clear()


# ====================================================================== campaign & draft
def create_campaign(user: dict, nama: str, tujuan: str, mulai: date, selesai: date, budget: float, jenis: str,
                    slot: int, zone_ids: list[int], store_ids: list[int]) -> dict:
    require(user["role"], "campaign.edit")
    if not nama.strip():
        raise WorkflowError("Nama campaign wajib diisi.")
    if selesai < mulai:
        raise WorkflowError("Periode selesai tidak boleh sebelum periode mulai.")
    with db.transaction() as cur:
        no = _next_no(cur, "campaigns", "no_campaign", "CMP")
        c = cur.execute("""INSERT INTO campaigns (no_campaign, nama, tujuan, periode_mulai, periode_selesai, budget, jenis, slot,
                                                  target_zone_ids, target_store_ids, status, created_by)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Draft',%s) RETURNING id, no_campaign""",
                        (no, nama.strip(), tujuan, mulai, selesai, budget, jenis, slot, zone_ids, store_ids, user["id"])).fetchone()
        sno = _next_no(cur, "submissions", "no_pengajuan", "PGJ")
        s = cur.execute("""INSERT INTO submissions (no_pengajuan, campaign_id, jenis, status) VALUES (%s,%s,%s,'Draft')
                           RETURNING id""", (sno, c["id"], jenis)).fetchone()
    log_activity(user["id"], "buat_campaign", "campaign", c["id"], f"Campaign {no} — {nama} dibuat")
    _clear()
    return {"campaign_id": c["id"], "submission_id": s["id"], "no": no}


def create_single_submission(user: dict, kol_id: int, store_id: int, harga: float, tanggal: date,
                             deliverable: str | None = None, request_id: int | None = None) -> dict:
    """Pengajuan tunggal (tanpa campaign) — mis. dari request toko yang disetujui."""
    require(user["role"], "campaign.edit")
    with db.transaction() as cur:
        sno = _next_no(cur, "submissions", "no_pengajuan", "PGJ")
        s = cur.execute("""INSERT INTO submissions (no_pengajuan, campaign_id, jenis, status, store_request_id)
                           VALUES (%s, NULL, 'tunggal', 'Draft', %s) RETURNING id""", (sno, request_id)).fetchone()
    add_item(user, s["id"], kol_id, store_id, deliverable, tanggal, harga)
    log_activity(user["id"], "buat_pengajuan_tunggal", "submission", s["id"], f"Pengajuan tunggal {sno} dibuat")
    return {"submission_id": s["id"], "no": sno}


def draft_submission(campaign_id: int) -> dict | None:
    return db.one("SELECT * FROM submissions WHERE campaign_id=%s ORDER BY id DESC LIMIT 1", (campaign_id,))


def _editable(cur, submission_id: int) -> dict:
    s = cur.execute("SELECT * FROM submissions WHERE id=%s FOR UPDATE", (submission_id,)).fetchone()
    if not s:
        raise WorkflowError("Pengajuan tidak ditemukan.")
    if s["status"] not in ("Draft", "Ditolak", "Revisi"):
        raise WorkflowError(f"Pengajuan berstatus '{s['status']}' tidak dapat diubah.")
    return s


def item_prediction(kol_id: int, store_id: int) -> dict:
    kt = A.kol_table(store_id=store_id)
    row = kt[kt["id"] == kol_id]
    if row.empty:
        return {}
    r = row.iloc[0]
    base = A.store_baseline_table()
    b = base[base["store_id"] == store_id]
    weekly = float(b["traffic_4mgg"].iloc[0] / 4) if not b.empty else 7000
    lift = r["lift_hist"] if r["lift_hist"] is not None and r["lift_hist"] == r["lift_hist"] else 0.08
    extra = weekly * 2 * lift * min(1.0, 0.5 + r["audiens_lokal"])
    return {"skor": round(float(r["skor"]), 1), "harga_wajar": float(r["harga_wajar"]), "batas_nego": float(r["batas_nego"]),
            "views_q50": float(r["views_q50"] or 0), "kunjungan": round(extra), "kunjungan_low": round(extra * 0.6),
            "kunjungan_high": round(extra * 1.3), "audiens_lokal": float(r["audiens_lokal"]), "data_terbatas": bool(r["data_terbatas"])}


def add_item(user: dict, submission_id: int, kol_id: int, store_id: int, deliverable: str | None, tanggal: date | None,
             harga: float | None = None) -> int:
    require(user["role"], "campaign.edit")
    if not deliverable:
        d = db.scalar("""SELECT deliverable FROM ratecards WHERE kol_id=%s AND deliverable <> 'story'
                         ORDER BY berlaku_mulai DESC LIMIT 1""", (kol_id,))
        deliverable = d or "video"
    kol = db.one("SELECT k.status, k.nama, (SELECT harga FROM ratecards r WHERE r.kol_id=k.id AND r.deliverable=%s "
                 "ORDER BY berlaku_mulai DESC LIMIT 1) AS rc, (SELECT harga FROM ratecards r WHERE r.kol_id=k.id "
                 "ORDER BY berlaku_mulai DESC LIMIT 1) AS rc_any FROM kol_accounts k WHERE k.id=%s", (deliverable, kol_id))
    if not kol:
        raise WorkflowError("KOL tidak ditemukan.")
    if kol["status"] == "diblokir":
        raise WorkflowError(f"{kol['nama']} ada di daftar blokir dan tidak dapat diajukan.")
    pred = item_prediction(kol_id, store_id)
    rc = float(kol["rc"] or kol["rc_any"] or 0)
    with db.transaction() as cur:
        _editable(cur, submission_id)
        dup = cur.execute("SELECT 1 FROM submission_items WHERE submission_id=%s AND kol_id=%s AND store_id=%s AND aktif",
                          (submission_id, kol_id, store_id)).fetchone()
        if dup:
            raise WorkflowError(f"{kol['nama']} sudah ada di draft untuk toko ini.")
        it = cur.execute("""INSERT INTO submission_items (submission_id, kol_id, store_id, deliverable, tanggal_posting, ratecard,
                                                          harga_nego, skor_saat_itu, prediksi_json)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                         (submission_id, kol_id, store_id, deliverable, tanggal, rc, harga if harga is not None else rc,
                          pred.get("skor"), pred)).fetchone()
    log_activity(user["id"], "tambah_ke_draft", "submission", submission_id, f"{kol['nama']} dimasukkan ke draft")
    _clear()
    return it["id"]


def update_item(user: dict, item_id: int, **fields):
    require(user["role"], "campaign.edit")
    allowed = {"harga_nego", "tanggal_posting", "deliverable", "dicentang", "store_id", "revisi_aksi"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    with db.transaction() as cur:
        it = cur.execute("SELECT submission_id FROM submission_items WHERE id=%s", (item_id,)).fetchone()
        _editable(cur, it["submission_id"])
        cur.execute("UPDATE submission_items SET " + ", ".join(f"{k}=%s" for k in sets) + " WHERE id=%s", (*sets.values(), item_id))
    _clear()


def remove_item(user: dict, item_id: int):
    require(user["role"], "campaign.edit")
    with db.transaction() as cur:
        it = cur.execute("SELECT submission_id FROM submission_items WHERE id=%s", (item_id,)).fetchone()
        _editable(cur, it["submission_id"])
        cur.execute("UPDATE submission_items SET aktif=FALSE, dicentang=FALSE WHERE id=%s", (item_id,))
    log_activity(user["id"], "hapus_baris", "submission", it["submission_id"], f"Baris #{item_id} dihapus dari draft")
    _clear()


def replace_item(user: dict, item_id: int, new_kol_id: int, harga: float | None = None) -> int:
    old = db.one("SELECT * FROM submission_items WHERE id=%s", (item_id,))
    new_id = add_item(user, old["submission_id"], new_kol_id, old["store_id"], old["deliverable"], old["tanggal_posting"], harga)
    with db.transaction() as cur:
        cur.execute("UPDATE submission_items SET aktif=FALSE, dicentang=FALSE, revisi_aksi='diganti' WHERE id=%s", (item_id,))
        cur.execute("UPDATE submission_items SET revisi_aksi='pengganti' WHERE id=%s", (new_id,))
    _clear()
    return new_id


def submit(user: dict, submission_id: int):
    """Ajukan 1 file campaign (atau pengajuan tunggal) ke Asisten Manager."""
    require(user["role"], "submission.submit")
    with db.transaction() as cur:
        s = _editable(cur, submission_id)
        n = cur.execute("SELECT COUNT(*) AS n FROM submission_items WHERE submission_id=%s AND aktif AND dicentang",
                        (submission_id,)).fetchone()["n"]
        if n == 0:
            raise WorkflowError("Belum ada baris yang dicentang untuk diajukan.")
        pending = cur.execute("""SELECT COUNT(*) AS n FROM submission_items WHERE submission_id=%s AND aktif
                                 AND revisi_aksi='perlu_aksi'""", (submission_id,)).fetchone()["n"]
        if pending:
            raise WorkflowError(f"{pending} baris yang ditolak belum ditentukan: ganti, pertahankan, atau hapus.")
        # baris yang tidak dicentang dikeluarkan dari pengajuan ini
        cur.execute("UPDATE submission_items SET aktif=FALSE WHERE submission_id=%s AND aktif AND NOT dicentang", (submission_id,))
        rev = s["revisi_ke"] + (1 if s["status"] in ("Ditolak", "Revisi") else 0)
        cur.execute("UPDATE submission_items SET keputusan_item=NULL WHERE submission_id=%s AND aktif", (submission_id,))
        cur.execute("""UPDATE submissions SET status='Review Asisten Manager', revisi_ke=%s, submitted_by=%s, submitted_at=NOW()
                       WHERE id=%s""", (rev, user["id"], submission_id))
        if s["campaign_id"]:
            cur.execute("UPDATE campaigns SET status='Diajukan' WHERE id=%s", (s["campaign_id"],))
    label = f"Pengajuan {s['no_pengajuan']}" + (f" (revisi ke-{rev})" if rev else "") + " diajukan"
    log_activity(user["id"], "ajukan", "submission", submission_id, label)
    notify(f"{label} — menunggu review Asisten Manager", role="asst_manager", link=f"approval:{submission_id}")
    _clear()


def decide(user: dict, submission_id: int, level: int, keputusan: dict[int, tuple[str, str | None]], catatan: str | None = None):
    """Keputusan per baris (setuju/tolak + catatan). Satu baris ditolak → pengajuan Ditolak untuk direvisi."""
    require(user["role"], f"submission.approve.level{level}")
    expected = {1: "Review Asisten Manager", 2: "Review Manager"}[level]
    with db.transaction() as cur:
        s = cur.execute("SELECT * FROM submissions WHERE id=%s FOR UPDATE", (submission_id,)).fetchone()
        if s["status"] != expected:
            raise WorkflowError(f"Pengajuan sedang berstatus '{s['status']}', bukan '{expected}'.")
        if s["submitted_by"] == user["id"]:
            raise Forbidden("Approver tidak dapat menyetujui pengajuan yang ia ajukan sendiri (segregation of duties).")
        if level == 2:
            l1 = cur.execute("SELECT approver_id FROM approvals WHERE submission_id=%s AND revisi_ke=%s AND level=1 ORDER BY waktu DESC LIMIT 1",
                             (submission_id, s["revisi_ke"])).fetchone()
            if l1 and l1["approver_id"] == user["id"]:
                raise Forbidden("Level 2 harus diputuskan oleh orang yang berbeda dari level 1.")
        items = cur.execute("SELECT id FROM submission_items WHERE submission_id=%s AND aktif", (submission_id,)).fetchall()
        ids = {i["id"] for i in items}
        missing = ids - set(keputusan)
        if missing:
            raise WorkflowError("Setiap baris harus diberi keputusan setuju/tolak.")
        for iid, (k, cat) in keputusan.items():
            if k == "tolak" and not (cat or "").strip():
                raise WorkflowError("Baris yang ditolak wajib diberi catatan penolakan.")
            cur.execute("UPDATE submission_items SET keputusan_item=%s, catatan_item=%s WHERE id=%s AND submission_id=%s",
                        (k, cat, iid, submission_id))
        any_reject = any(k == "tolak" for k, _ in keputusan.values())
        cur.execute("INSERT INTO approvals (submission_id, revisi_ke, level, approver_id, keputusan, catatan) VALUES (%s,%s,%s,%s,%s,%s)",
                    (submission_id, s["revisi_ke"], level, user["id"], "tolak" if any_reject else "setuju", catatan))
        if any_reject:
            new_status = "Ditolak"
        elif level == 1:
            new_status = "Review Manager"
        else:
            new_status = "Disetujui"
        cur.execute("UPDATE submissions SET status=%s WHERE id=%s", (new_status, submission_id))
        if s["campaign_id"]:
            cur.execute("UPDATE campaigns SET status=%s WHERE id=%s",
                        ("Ditolak" if any_reject else ("Diajukan" if level == 1 else "Disetujui"), s["campaign_id"]))
    lvl = "Asisten Manager" if level == 1 else "Manager"
    log_activity(user["id"], "approve" if not any_reject else "tolak", "submission", submission_id,
                 f"{s['no_pengajuan']}: {'ditolak' if any_reject else 'disetujui'} oleh {lvl}")
    if any_reject:
        notify(f"{s['no_pengajuan']} ditolak oleh {lvl} — lihat catatan per baris lalu revisi", role="ecommerce", link=f"draft:{submission_id}")
    elif level == 1:
        notify(f"{s['no_pengajuan']} disetujui Asisten Manager — menunggu Manager", role="manager", link=f"approval:{submission_id}")
    else:
        create_ro(user, submission_id)
    _clear()


def resubmit_prepare(user: dict, submission_id: int):
    """Tandai pengajuan ditolak sebagai 'Revisi' agar baris bisa diganti / dipertahankan."""
    require(user["role"], "campaign.edit")
    with db.transaction() as cur:
        s = cur.execute("SELECT * FROM submissions WHERE id=%s FOR UPDATE", (submission_id,)).fetchone()
        if s["status"] != "Ditolak":
            raise WorkflowError("Hanya pengajuan yang ditolak yang dapat direvisi.")
        cur.execute("UPDATE submissions SET status='Revisi' WHERE id=%s", (submission_id,))
        cur.execute("""UPDATE submission_items SET revisi_aksi = CASE WHEN keputusan_item='tolak' THEN 'perlu_aksi' ELSE 'pertahankan' END
                       WHERE submission_id=%s AND aktif""", (submission_id,))
    log_activity(user["id"], "mulai_revisi", "submission", submission_id, f"Revisi {s['no_pengajuan']} dimulai")
    _clear()


# ====================================================================== Form RO
def create_ro(user: dict, submission_id: int) -> dict:
    with db.transaction() as cur:
        ex = cur.execute("SELECT * FROM ro_forms WHERE submission_id=%s", (submission_id,)).fetchone()
        if ex:
            return ex
        s = cur.execute("SELECT * FROM submissions WHERE id=%s", (submission_id,)).fetchone()
        no = _next_no(cur, "ro_forms", "no_ro", "RO")
        kode = hashlib.sha256(f"{no}|{submission_id}|{datetime.now().isoformat()}".encode()).hexdigest()[:10].upper()
        ro = cur.execute("INSERT INTO ro_forms (no_ro, submission_id, status, kode_verifikasi) VALUES (%s,%s,'dibuat',%s) RETURNING *",
                         (no, submission_id, kode)).fetchone()
        cur.execute("UPDATE submissions SET status='Form RO dibuat' WHERE id=%s", (submission_id,))
        if s["campaign_id"]:
            cur.execute("UPDATE campaigns SET status='Form RO dibuat' WHERE id=%s", (s["campaign_id"],))
        items = cur.execute("""SELECT i.*, k.badan_hukum, k.punya_npwp FROM submission_items i JOIN kol_accounts k ON k.id=i.kol_id
                               WHERE i.submission_id=%s AND i.aktif AND i.keputusan_item='setuju'""", (submission_id,)).fetchall()
        rules = tax_rules(cur)
        from .formulas import tax_amount
        for it in items:
            tx = tax_amount(float(it["harga_nego"]), it["badan_hukum"], it["punya_npwp"], rules)
            inv = _next_invoice(cur)
            cur.execute("""INSERT INTO payments (ro_id, item_id, invoice_no, nominal, pajak_jenis, pajak_nominal, status, alasan_tertahan)
                           VALUES (%s,%s,%s,%s,%s,%s,'tertahan','RO belum ditandatangani; bukti tayang belum ada')
                           ON CONFLICT (item_id) DO NOTHING""", (ro["id"], it["id"], inv, it["harga_nego"], tx["jenis"], tx["pajak"]))
            _create_production_tasks(cur, it["id"], it["tanggal_posting"])
    log_activity(user["id"], "buat_ro", "ro", ro["id"], f"Form RO {no} dibuat untuk {s['no_pengajuan']}")
    notify(f"Form RO {no} siap dicetak & ditandatangani ({s['no_pengajuan']})", role="ecommerce", link=f"ro:{ro['id']}")
    notify(f"RO baru {no} masuk otomatis dari approval", role="finance", link=f"payment:{ro['id']}")
    _clear()
    return ro


def _next_invoice(cur) -> str:
    r = cur.execute("SELECT invoice_no FROM payments WHERE invoice_no LIKE %s ORDER BY invoice_no DESC LIMIT 1",
                    (f"INV/KOL/{YEAR}/%",)).fetchone()
    n = int(r["invoice_no"].rsplit("/", 1)[1]) + 1 if r else 1
    return f"INV/KOL/{YEAR}/{n:04d}"


def tax_rules(cur=None) -> dict:
    sql = "SELECT DISTINCT ON (jenis) jenis, tarif, dasar, tarif_tanpa_npwp FROM tax_rules WHERE berlaku_mulai <= CURRENT_DATE ORDER BY jenis, berlaku_mulai DESC"
    rows = cur.execute(sql).fetchall() if cur else db.query(sql)
    return {r["jenis"]: {"tarif": float(r["tarif"]), "dasar": float(r["dasar"]),
                         "tarif_tanpa_npwp": float(r["tarif_tanpa_npwp"]) if r["tarif_tanpa_npwp"] else None} for r in rows}


def _create_production_tasks(cur, item_id: int, posting: date | None):
    posting = posting or date.today() + timedelta(days=21)
    plan = [("pitching", -18, 2), ("brief", -15, 3), ("take", -11, 3), ("review", -7, 4), ("posting", 0, 0), ("lapor", 1, 2)]
    for n, (tahap, off, dur) in enumerate(plan, start=1):
        start = posting + timedelta(days=off)
        cur.execute("""INSERT INTO production_tasks (item_id, tahap, urutan, mulai, selesai) VALUES (%s,%s,%s,%s,%s)
                       ON CONFLICT (item_id, tahap) DO NOTHING""", (item_id, tahap, n, start, start + timedelta(days=dur)))


def mark_ro_printed(user: dict, ro_id: int, pdf: bytes | None = None):
    require(user["role"], "ro.manage")
    db.execute("UPDATE ro_forms SET status = CASE WHEN status='dibuat' THEN 'dicetak' ELSE status END, pdf=COALESCE(%s, pdf) WHERE id=%s",
               (pdf, ro_id))
    log_activity(user["id"], "cetak_ro", "ro", ro_id, "Form RO dicetak")
    _clear()


def upload_signed_ro(user: dict, ro_id: int, filename: str, content: bytes):
    require(user["role"], "ro.manage")
    if not content:
        raise WorkflowError("File scan kosong.")
    with db.transaction() as cur:
        ro = cur.execute("SELECT * FROM ro_forms WHERE id=%s FOR UPDATE", (ro_id,)).fetchone()
        cur.execute("UPDATE ro_forms SET scan_ttd=%s, scan_nama=%s, status='ditandatangani' WHERE id=%s", (content, filename, ro_id))
        s = cur.execute("SELECT * FROM submissions WHERE id=%s", (ro["submission_id"],)).fetchone()
        cur.execute("UPDATE submissions SET status='Di Finance' WHERE id=%s", (s["id"],))
        if s["campaign_id"]:
            cur.execute("UPDATE campaigns SET status='Di Finance' WHERE id=%s", (s["campaign_id"],))
    for p in db.query("SELECT item_id FROM payments WHERE ro_id=%s", (ro_id,)):
        recompute_payment(p["item_id"])
    log_activity(user["id"], "unggah_scan_ro", "ro", ro_id, f"Scan RO {ro['no_ro']} bertanda tangan diunggah")
    notify(f"RO {ro['no_ro']} sudah ditandatangani — salinan digital masuk menu Finance", role="finance", link=f"payment:{ro_id}")
    _clear()


# ====================================================================== bukti tayang & pembayaran
def recompute_payment(item_id: int):
    """Aturan: pembayaran diproses bila bukti tayang, link, insight lengkap dan RO ditandatangani."""
    r = db.one("""SELECT p.id, p.status, ro.status AS ro_status, po.link, po.bukti IS NOT NULL AS bukti, po.insight IS NOT NULL AS insight
                  FROM payments p JOIN ro_forms ro ON ro.id=p.ro_id LEFT JOIN posts po ON po.item_id=p.item_id
                  WHERE p.item_id=%s""", (item_id,))
    if not r or r["status"] in ("diproses", "lunas"):
        return
    kurang = []
    if r["ro_status"] != "ditandatangani":
        kurang.append("RO belum ditandatangani")
    if not r["bukti"]:
        kurang.append("bukti tayang")
    if not r["link"]:
        kurang.append("link posting")
    if not r["insight"]:
        kurang.append("insight")
    status = "siap" if not kurang else "tertahan"
    db.execute("UPDATE payments SET status=%s, alasan_tertahan=%s, updated_at=NOW() WHERE id=%s",
               (status, None if not kurang else "Belum lengkap: " + ", ".join(kurang), r["id"]))


OCR_PATTERNS = {
    "views": r"(?:views?|tayangan|penayangan|plays?|diputar|jangkauan|reach)\D{0,12}([\d.,]+\s*(?:rb|k|jt|m)?)",
    "likes": r"(?:likes?|suka|menyukai)\D{0,12}([\d.,]+\s*(?:rb|k|jt|m)?)",
    "komentar": r"(?:komentar|comments?)\D{0,12}([\d.,]+\s*(?:rb|k|jt|m)?)",
    "share": r"(?:shares?|bagikan|dibagikan|kirim)\D{0,12}([\d.,]+\s*(?:rb|k|jt|m)?)",
    "save": r"(?:saves?|simpan|disimpan)\D{0,12}([\d.,]+\s*(?:rb|k|jt|m)?)",
}


def _num(s: str) -> int | None:
    s = s.strip().lower().replace(" ", "")
    mult = 1
    for suf, m in (("jt", 1e6), ("m", 1e6), ("rb", 1e3), ("k", 1e3)):
        if s.endswith(suf):
            mult, s = m, s[: -len(suf)]
            break
    if mult > 1:
        s = s.replace(",", ".")
    else:
        s = s.replace(".", "").replace(",", "")
    try:
        return int(float(s) * mult)
    except ValueError:
        return None


def ocr_insight(image_bytes: bytes) -> dict:
    """Baca angka insight dari screenshot (Tesseract). Kosong bila OCR tidak tersedia."""
    try:
        import io
        import pytesseract
        from PIL import Image
        text = pytesseract.image_to_string(Image.open(io.BytesIO(image_bytes)), lang="eng+ind")
    except Exception:
        try:
            import io
            import pytesseract
            from PIL import Image
            text = pytesseract.image_to_string(Image.open(io.BytesIO(image_bytes)))
        except Exception:
            return {}
    out = {}
    low = text.lower()
    for k, pat in OCR_PATTERNS.items():
        m = re.search(pat, low)
        if m:
            v = _num(m.group(1))
            if v is not None:
                out[k] = v
    return out


def save_proof(user: dict, item_id: int, link: str, tanggal_tayang: datetime | None, bukti: tuple[str, bytes] | None,
               insight: tuple[str, bytes] | None, metrics: dict, sumber: str = "manual") -> dict:
    require(user["role"], "proof.input")
    it = db.one("SELECT i.*, k.platform FROM submission_items i JOIN kol_accounts k ON k.id=i.kol_id WHERE i.id=%s", (item_id,))
    if not it:
        raise WorkflowError("Baris tidak ditemukan.")
    telat = 0
    if tanggal_tayang and it["tanggal_posting"]:
        telat = max(0, (tanggal_tayang.date() - it["tanggal_posting"]).days)
    with db.transaction() as cur:
        p = cur.execute("SELECT id FROM posts WHERE item_id=%s", (item_id,)).fetchone()
        if p:
            sets, vals = ["link=%s", "tanggal_tayang=%s", "telat_hari=%s", "updated_by=%s", "updated_at=NOW()"], [link, tanggal_tayang, telat, user["id"]]
            if bukti:
                sets += ["bukti=%s", "bukti_nama=%s"]; vals += [bukti[1], bukti[0]]
            if insight:
                sets += ["insight=%s", "insight_nama=%s"]; vals += [insight[1], insight[0]]
            cur.execute(f"UPDATE posts SET {', '.join(sets)} WHERE id=%s", (*vals, p["id"]))
            pid = p["id"]
        else:
            pid = cur.execute("""INSERT INTO posts (item_id, kol_id, link, platform, tanggal_tayang, bukti, bukti_nama, insight, insight_nama,
                                                    telat_hari, updated_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                              (item_id, it["kol_id"], link, it["platform"], tanggal_tayang, bukti[1] if bukti else None,
                               bukti[0] if bukti else None, insight[1] if insight else None, insight[0] if insight else None,
                               telat, user["id"])).fetchone()["id"]
        if any(metrics.get(k) for k in ("views", "likes", "komentar", "share", "save")):
            cur.execute("""INSERT INTO post_metrics (post_id, views, likes, komentar, share, save, sumber, diukur_pada)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,CURRENT_DATE)""",
                        (pid, metrics.get("views"), metrics.get("likes"), metrics.get("komentar"), metrics.get("share"),
                         metrics.get("save"), sumber))
        api = cur.execute("SELECT views FROM post_metrics WHERE post_id=%s AND sumber='api' ORDER BY diukur_pada DESC LIMIT 1", (pid,)).fetchone()
    selisih = None
    if api and metrics.get("views") and api["views"]:
        selisih = abs(metrics["views"] - api["views"]) / api["views"] * 100
    recompute_payment(item_id)
    log_activity(user["id"], "unggah_bukti_tayang", "item", item_id, "Bukti tayang diperbarui")
    _clear()
    return {"post_id": pid, "telat_hari": telat, "selisih_api_pct": selisih, "ditandai": selisih is not None and selisih > 5}


def update_payment(user: dict, payment_id: int, status: str, invoice_no: str | None = None):
    require(user["role"], "payment.manage")
    order = ["tertahan", "siap", "diproses", "lunas"]
    with db.transaction() as cur:
        p = cur.execute("SELECT * FROM payments WHERE id=%s FOR UPDATE", (payment_id,)).fetchone()
        if p["status"] == "tertahan" and status in ("diproses", "lunas"):
            raise WorkflowError("Pembayaran masih tertahan: " + (p["alasan_tertahan"] or "dokumen belum lengkap"))
        if order.index(status) < order.index(p["status"]) and status != "siap":
            raise WorkflowError("Status pembayaran tidak boleh mundur.")
        cur.execute("""UPDATE payments SET status=%s, invoice_no=COALESCE(%s, invoice_no), updated_by=%s, updated_at=NOW(),
                       paid_at = CASE WHEN %s='lunas' THEN NOW() ELSE paid_at END WHERE id=%s""",
                    (status, invoice_no, user["id"], status, payment_id))
        sub = cur.execute("""SELECT s.id, s.campaign_id, COUNT(*) AS n, COUNT(*) FILTER (WHERE p.status='lunas') AS lunas
                             FROM payments p JOIN ro_forms r ON r.id=p.ro_id JOIN submissions s ON s.id=r.submission_id
                             WHERE r.id=%s GROUP BY s.id, s.campaign_id""", (p["ro_id"],)).fetchone()
        if sub:
            st_ = "Lunas" if sub["lunas"] == sub["n"] else ("Dibayar sebagian" if sub["lunas"] else "Di Finance")
            cur.execute("UPDATE submissions SET status=%s WHERE id=%s", (st_, sub["id"]))
            if sub["campaign_id"]:
                cur.execute("UPDATE campaigns SET status=%s WHERE id=%s", ("Selesai" if st_ == "Lunas" else st_, sub["campaign_id"]))
    log_activity(user["id"], "update_pembayaran", "payment", payment_id, f"Status pembayaran → {status}",
                 sebelum={"status": p["status"]}, sesudah={"status": status})
    _clear()


# ====================================================================== KOL
def set_block(user: dict, kol_id: int, blok: bool, alasan: str | None = None):
    require(user["role"], "kol.block")
    if blok and not (alasan or "").strip():
        raise WorkflowError("Alasan blokir wajib diisi.")
    before = db.one("SELECT status, alasan_blokir FROM kol_accounts WHERE id=%s", (kol_id,))
    db.execute("UPDATE kol_accounts SET status=%s, alasan_blokir=%s, blocked_by=%s, updated_at=NOW() WHERE id=%s",
               ("diblokir" if blok else "aktif", alasan if blok else None, user["id"] if blok else None, kol_id))
    log_activity(user["id"], "blokir_kol" if blok else "buka_blokir_kol", "kol", kol_id,
                 ("Diblokir: " + alasan) if blok else "Blokir dibuka", sebelum=before)
    _clear()


# ====================================================================== request toko
def system_check_new_account(data: dict, ratecard: float | None) -> dict:
    """Cek otomatis akun baru: metrik publik, kategori, harga wajar vs ratecard, duplikat, daftar blokir."""
    from .nlp import suggest_category
    from .preprocess import normalize_username
    un = normalize_username(data.get("username", ""))
    plat = data.get("platform", "")
    dup = db.one("""SELECT id, nama, status, alasan_blokir FROM kol_accounts WHERE (lower(platform)=lower(%s) AND username_norm=%s)
                    OR rtrim(lower(link),'/')=rtrim(lower(%s),'/')""", (plat, un, data.get("link", "")))
    kat, conf = suggest_category(data.get("bio", "") + " " + data.get("nama", ""))
    follower = float(data.get("follower") or 0)
    ratio = {"TikTok": 0.35, "Instagram": 0.22}.get(plat, 0.1)
    est_views = follower * ratio
    cpm_t = A.DEFAULT_CPM.get(kat, 55_000)
    wajar = cpm_t * est_views / 1000
    out = {
        "metrik_publik": {"follower": follower, "estimasi_views": est_views},
        "kategori_saran": kat, "keyakinan_kategori": conf,
        "harga_wajar": wajar, "ratecard": ratecard,
        "harga_vs_wajar_pct": ((ratecard / wajar - 1) * 100) if ratecard and wajar else None,
        "duplikat": bool(dup and dup["status"] != "diblokir"), "duplikat_id": dup["id"] if dup else None,
        "diblokir": bool(dup and dup["status"] == "diblokir"), "alasan_blokir": dup["alasan_blokir"] if dup else None,
    }
    flags = []
    if out["duplikat"]:
        flags.append(f"akun sudah ada di database ({dup['nama']})")
    if out["diblokir"]:
        flags.append("akun ada di daftar blokir")
    if out["harga_vs_wajar_pct"] is not None and out["harga_vs_wajar_pct"] > 30:
        flags.append(f"ratecard {out['harga_vs_wajar_pct']:.0f}% di atas harga wajar")
    if follower < 1000:
        flags.append("follower sangat kecil / belum terverifikasi")
    out["catatan"] = flags or ["lolos cek otomatis"]
    out["lolos"] = not flags
    return out


def create_request(user: dict, store_id: int, kebutuhan: str, mulai: date, selesai: date, kol_id: int | None,
                   new_account: dict | None, ratecard: float | None, file: tuple[str, bytes] | None) -> str:
    require(user["role"], "request.create")
    if user["role"] == "store" and user.get("scope_store_id") != store_id:
        raise Forbidden("Role Store hanya dapat mengajukan untuk tokonya sendiri.")
    cek = system_check_new_account(new_account, ratecard) if new_account else None
    with db.transaction() as cur:
        no = _next_no(cur, "store_requests", "no_request", "REQ")
        cur.execute("""INSERT INTO store_requests (no_request, store_id, kol_id, data_akun_baru_json, kebutuhan, periode_mulai, periode_selesai,
                                                   ratecard, file_nama, file_isi, cek_sistem_json, status, submitted_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Diajukan',%s)""",
                    (no, store_id, kol_id, new_account, kebutuhan, mulai, selesai, ratecard, file[0] if file else None,
                     file[1] if file else None, cek, user["id"]))
    log_activity(user["id"], "request_kol", "store_request", no, f"Request {no} diajukan")
    notify(f"Request KOL baru {no} dari toko", role="ecommerce", link=f"request:{no}")
    _clear()
    return no


def review_request(user: dict, request_id: int, aksi: str, catatan: str | None = None, kategori: str | None = None,
                   tujuan: str = "tunggal", campaign_submission_id: int | None = None, tanggal: date | None = None) -> dict:
    """aksi: setujui | tolak | minta_info. Disetujui & akun baru → masuk database → pengajuan tunggal / draft campaign."""
    require(user["role"], "request.approve")
    r = db.one("SELECT * FROM store_requests WHERE id=%s", (request_id,))
    if r["status"] not in ("Diajukan", "Minta info"):
        raise WorkflowError(f"Request berstatus '{r['status']}'.")
    if aksi in ("tolak", "minta_info") and not (catatan or "").strip():
        raise WorkflowError("Catatan/alasan wajib diisi.")
    result = {}
    if aksi == "setujui":
        kol_id = r["kol_id"]
        if not kol_id:
            d = r["data_akun_baru_json"] or {}
            from .preprocess import normalize_username
            un = normalize_username(d.get("username", ""))
            with db.transaction() as cur:
                k = cur.execute("""INSERT INTO kol_accounts (tipe, platform, nama, username, username_norm, link, kategori, kategori_otomatis,
                                                            bio, kota_domisili, kontak, sumber)
                                   VALUES ('kol',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'request_toko')
                                   ON CONFLICT (platform, username_norm) DO UPDATE SET updated_at=NOW() RETURNING id""",
                                (d.get("platform"), d.get("nama"), "@" + un, un, d.get("link"), kategori or d.get("kategori") or "general",
                                 (r["cek_sistem_json"] or {}).get("kategori_saran"), d.get("bio"), d.get("kota"), d.get("kontak"))).fetchone()
                kol_id = k["id"]
                deliv = "video" if d.get("platform") == "TikTok" else "reels"
                cur.execute("INSERT INTO ratecards (kol_id, deliverable, harga, berlaku_mulai, sumber) VALUES (%s,%s,%s,CURRENT_DATE,'toko')",
                            (kol_id, deliv, r["ratecard"] or 0))
                cur.execute("""INSERT INTO kol_metrics_snapshot (kol_id, tanggal, follower, avg_views, er, audiens_kota_json)
                               VALUES (%s, CURRENT_DATE, %s, %s, NULL, %s) ON CONFLICT DO NOTHING""",
                            (kol_id, d.get("follower"), int((r["cek_sistem_json"] or {}).get("metrik_publik", {}).get("estimasi_views") or 0),
                             {d.get("kota") or "Lainnya": 0.5, "Lainnya": 0.5}))
            result["kol_baru"] = kol_id
        tanggal = tanggal or r["periode_mulai"] or date.today() + timedelta(days=14)
        if tujuan == "draft" and campaign_submission_id:
            add_item(user, campaign_submission_id, kol_id, r["store_id"], None, tanggal, r["ratecard"])
            result["masuk"] = "draft campaign"
            cat = catatan or "Disetujui — dimasukkan ke draft campaign"
        else:
            s = create_single_submission(user, kol_id, r["store_id"], r["ratecard"] or 0, tanggal, request_id=request_id)
            result["masuk"] = f"pengajuan tunggal {s['no']}"
            cat = catatan or f"Disetujui — diproses sebagai pengajuan tunggal {s['no']}"
        db.execute("UPDATE store_requests SET status='Disetujui', kol_id=%s, catatan=%s, reviewed_by=%s, updated_at=NOW() WHERE id=%s",
                   (kol_id, cat, user["id"], request_id))
    else:
        status = "Ditolak" if aksi == "tolak" else "Minta info"
        db.execute("UPDATE store_requests SET status=%s, catatan=%s, reviewed_by=%s, updated_at=NOW() WHERE id=%s",
                   (status, catatan, user["id"], request_id))
    log_activity(user["id"], f"request_{aksi}", "store_request", r["no_request"], f"Request {r['no_request']}: {aksi}")
    if r["submitted_by"]:
        notify(f"Request {r['no_request']} — {aksi.replace('_', ' ')}", user_id=r["submitted_by"], link=f"request:{r['no_request']}")
    _clear()
    return result


# ====================================================================== brief
def save_brief(user: dict, brief_id: int | None, item_id: int | None, campaign_id: int | None, judul: str,
               sections: dict[int, dict], status: str = "draft") -> int:
    require(user["role"], "brief.edit")
    from .master import BRIEF_SECTIONS
    with db.transaction() as cur:
        if brief_id:
            cur.execute("UPDATE briefs SET judul=%s, versi=versi+1, status=%s, updated_by=%s, updated_at=NOW() WHERE id=%s",
                        (judul, status, user["id"], brief_id))
        else:
            brief_id = cur.execute("""INSERT INTO briefs (item_id, campaign_id, judul, status, updated_by) VALUES (%s,%s,%s,%s,%s)
                                      RETURNING id""", (item_id, campaign_id, judul, status, user["id"])).fetchone()["id"]
        for n, isi in sections.items():
            cur.execute("""INSERT INTO brief_sections (brief_id, urutan, judul, isi_json) VALUES (%s,%s,%s,%s)
                           ON CONFLICT (brief_id, urutan) DO UPDATE SET isi_json=EXCLUDED.isi_json, judul=EXCLUDED.judul""",
                        (brief_id, n, BRIEF_SECTIONS[n - 1], isi))
    log_activity(user["id"], "simpan_brief", "brief", brief_id, f"Brief '{judul}' disimpan")
    _clear()
    return brief_id


def duplicate_brief(user: dict, brief_id: int, item_ids: list[int]) -> list[int]:
    """Duplikasi brief ke banyak KOL di tanggal sama."""
    require(user["role"], "brief.edit")
    src = db.one("SELECT * FROM briefs WHERE id=%s", (brief_id,))
    secs = {r["urutan"]: r["isi_json"] for r in db.query("SELECT urutan, isi_json FROM brief_sections WHERE brief_id=%s", (brief_id,))}
    new_ids = []
    for iid in item_ids:
        k = db.one("SELECT k.username FROM submission_items i JOIN kol_accounts k ON k.id=i.kol_id WHERE i.id=%s", (iid,))
        judul = re.sub(r"@\S+", k["username"], src["judul"]) if "@" in src["judul"] else f"{src['judul']} — {k['username']}"
        new_ids.append(save_brief(user, None, iid, src["campaign_id"], judul, secs))
    return new_ids
