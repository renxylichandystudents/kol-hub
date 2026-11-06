# KOL Hub — Aplikasi Digital Marketing Mitra10

Aplikasi web internal tim Digital Marketing Mitra10 untuk mengelola KOL & Portal News dari hulu ke hilir,
dibangun mengikuti **KOL Hub — Spesifikasi Final v1.0** (25 layar, 6 role, Bagian B algoritma, Bagian C blueprint).

Implementasi ini memakai jalur **prototipe Streamlit + PostgreSQL (Supabase)** yang disebut di Spesifikasi C.1,
sehingga bisa langsung berjalan di Streamlit Community Cloud tanpa server terpisah.

## Struktur

```
app.py                 # entry: koneksi DB, migrasi otomatis, login, menu per role
views/                 # 25 layar (satu file per layar, lihat tabel di bawah)
lib/
  auth.py              # login Argon2id, kunci akun, TOTP 2FA, wajib ganti sandi, activity log
  rbac.py              # izin per aksi & cakupan toko (C.6)
  workflow.py          # state machine campaign/pengajuan/RO/pembayaran/request toko (C.4)
  formulas.py          # rumus inti B.6 no. 1–15
  analytics.py         # skor KOL, saran harga, lift DiD, kebutuhan toko, rekomendasi
  optimize.py          # generator pengajuan: ILP OR-Tools CP-SAT + kurva jenuh (B.6 no. 11)
  preprocess.py        # preprocessing traffic, KOL, komentar (B.3)
  nlp.py               # sentimen cascade, aspek, niat, topik, kategori KOL (B.8)
  jobs.py              # job terjadwal: cek data, NLP, quality gate model, scoring (B.10, C.7)
  docs.py              # Form RO (PDF, ReportLab) & Creative Brief (PPTX, python-pptx)
  migrate.py           # migrasi skema otomatis saat app dibuka
migrations/            # 001_schema.sql (C.3) · 002_seed.sql (61 toko/10 zona + data contoh)
tests/                 # unit rumus, pipeline, integrasi alur approval, RBAC, smoke test 25 layar per role
```

## Layar

| No | Layar | File | No | Layar | File |
|----|-------|------|----|-------|------|
| 1 | Login & Pilih Role | `login.py` | 14 | Form Approval RO | `ro.py` |
| 2 | Dashboard | `dashboard.py` | 15 | Kalender Event | `kalender.py` |
| 3 | Social Media Listening | `social.py` | 16 | Timeline Produksi | `timeline.py` |
| 4 | Performa Toko & Zona | `performa.py` | 17–18 | Creative Brief (9 bagian, PPTX/PDF) | `brief.py` |
| 5 | Upload Traffic Offline | `upload_traffic.py` | 19 | Report & Hasil | `report.py` |
| 6 | Database KOL & Portal | `kol_db.py` | 20 | Bukti Tayang & Status RO | `bukti.py` |
| 7 | Analisa & Scoring KOL | `kol_analisa.py` | 21 | Pembayaran & Pajak | `pembayaran.py` |
| 8 | Mapping Toko, Zona & KOL | `mapping.py` | 22 | Request KOL (Toko) | `request_toko.py` |
| 9 | Campaign & Pengajuan | `campaign.py` | 23 | Approval Request Toko | `request_approval.py` |
| 10 | Seleksi & Review KOL | `seleksi.py` | 24 | Model & Testing | `model.py` |
| 11 | Bandingkan KOL | `bandingkan.py` | 25 | Akses & Role | `akses.py` |
| 12 | Draft Pengajuan | `draft.py` | – | Akun Saya (ganti sandi/2FA) | `akun.py` |
| 13 | Review & Approval | `approval.py` | | | |

## Deploy (Streamlit Community Cloud + Supabase)

1. Main file: `app.py`, branch `main`.
2. **Settings → Secrets** (lihat `.streamlit/secrets.toml.example`):
   ```toml
   DATABASE_URL = "postgresql://postgres.<project>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres"
   SUPERUSER_EMAIL = "nama@mitra10.co.id"
   SUPERUSER_INITIAL_PASSWORD = "kata-sandi-sementara"
   ```
3. Saat pertama dibuka, app menjalankan migrasi (skema + 61 toko + data contoh) dan membuat akun Super User awal.
   Tabel prototipe lama tidak dihapus — disimpan sebagai `legacy_*`.
4. Login sebagai Super User → ganti kata sandi → aktifkan 2FA → daftarkan akun tim di **Akses & Role**.

Paket sistem (`packages.txt`): Tesseract OCR untuk membaca angka insight dari screenshot bukti tayang.

## Pengujian

```bash
pip install -r requirements.txt pytest
DATABASE_URL=postgresql://... python -m pytest -q tests   # tanpa DATABASE_URL: hanya uji unit & pipeline
```
CI GitHub Actions menjalankan semua uji pada PostgreSQL 16 di setiap push.

## Catatan

- Angka dan nama akun KOL adalah **data contoh**; nama toko dan zona adalah data Mitra10.
- Integrasi API Instagram/TikTok, SSO Google Workspace, dan model berat (LightGBM, BERTopic, IndoBERT) belum
  disambungkan; layar memakai data contoh dan model ringan berbasis rumus Bagian B, dengan quality gate di layar 24.
- Tarif pajak disimpan sebagai tabel aturan (`tax_rules`) dan perlu divalidasi tim Tax sebelum go-live.
