-- =====================================================================
-- KOL Hub — skema database (Spesifikasi Final v1.0, Bagian C.3)
-- Dijalankan otomatis oleh app (lib/migrate.py) satu kali.
-- =====================================================================

-- Tabel prototipe lama disimpan sebagai legacy_* (tidak dihapus)
DO $$
DECLARE t text;
BEGIN
  IF to_regclass('public.users') IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM information_schema.columns
       WHERE table_schema='public' AND table_name='users' AND column_name='must_change_password') THEN
    FOREACH t IN ARRAY ARRAY['campaign_kols','campaigns','kol_accounts','users','stores','zones'] LOOP
      IF to_regclass('public.'||t) IS NOT NULL THEN
        EXECUTE format('ALTER TABLE public.%I RENAME TO %I', t, 'legacy_'||t);
      END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname='userrole') THEN
      ALTER TYPE userrole RENAME TO legacy_userrole;
    END IF;
  END IF;
END$$;

-- ---------- Master toko & zona ----------
CREATE TABLE zones (
  id SERIAL PRIMARY KEY,
  nama VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE stores (
  id SERIAL PRIMARY KEY,
  kode VARCHAR(20) UNIQUE NOT NULL,
  nama VARCHAR(150) UNIQUE NOT NULL,
  zone_id INT NOT NULL REFERENCES zones(id),
  kota VARCHAR(100) NOT NULL,
  lat NUMERIC(10,7), lon NUMERIC(10,7),
  alias TEXT[] DEFAULT '{}',
  target_kunjungan_mingguan INT
);

-- ---------- Akses ----------
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  nama VARCHAR(150) NOT NULL,
  email VARCHAR(200) UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  totp_secret VARCHAR(64),
  totp_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
  scope_zone_id INT REFERENCES zones(id),
  scope_store_id INT REFERENCES stores(id),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  failed_attempts INT NOT NULL DEFAULT 0,
  locked_until TIMESTAMPTZ,
  last_login_at TIMESTAMPTZ,
  created_by INT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_roles (
  user_id INT REFERENCES users(id) ON DELETE CASCADE,
  role VARCHAR(20) NOT NULL CHECK (role IN ('ecommerce','asst_manager','manager','store','finance','super_user')),
  PRIMARY KEY (user_id, role)
);

CREATE TABLE activity_log (
  id BIGSERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id),
  aksi VARCHAR(80) NOT NULL,
  entitas VARCHAR(50),
  entitas_id VARCHAR(50),
  label TEXT,
  sebelum_json JSONB, sesudah_json JSONB,
  waktu TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ip VARCHAR(64)
);
CREATE INDEX ON activity_log(user_id, waktu DESC);

CREATE TABLE notifications (
  id BIGSERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id) ON DELETE CASCADE,
  role VARCHAR(20),
  pesan TEXT NOT NULL,
  link VARCHAR(100),
  dibaca BOOLEAN NOT NULL DEFAULT FALSE,
  waktu TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------- KOL & Portal News ----------
CREATE TABLE kol_accounts (
  id SERIAL PRIMARY KEY,
  tipe VARCHAR(10) NOT NULL CHECK (tipe IN ('kol','portal')),
  platform VARCHAR(20) NOT NULL,
  nama VARCHAR(150) NOT NULL,
  username VARCHAR(150) NOT NULL,
  username_norm VARCHAR(150) NOT NULL,
  link VARCHAR(500) NOT NULL,
  kategori VARCHAR(20) NOT NULL DEFAULT 'general'
     CHECK (kategori IN ('comedy','beauty','lifestyle','culinary','general')),
  kategori_otomatis VARCHAR(20),
  niche VARCHAR(200),
  bio TEXT,
  kota_domisili VARCHAR(100),
  badan_hukum BOOLEAN NOT NULL DEFAULT FALSE,
  punya_npwp BOOLEAN NOT NULL DEFAULT TRUE,
  kontak VARCHAR(200),
  status VARCHAR(10) NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif','diblokir')),
  alasan_blokir TEXT,
  blocked_by INT REFERENCES users(id),
  sumber VARCHAR(20) DEFAULT 'input',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (platform, username_norm)
);

CREATE TABLE kol_metrics_snapshot (
  id SERIAL PRIMARY KEY,
  kol_id INT NOT NULL REFERENCES kol_accounts(id) ON DELETE CASCADE,
  tanggal DATE NOT NULL,
  follower INT, avg_views INT, er NUMERIC(6,2),
  audiens_kota_json JSONB,
  UNIQUE (kol_id, tanggal)
);

CREATE TABLE ratecards (
  id SERIAL PRIMARY KEY,
  kol_id INT NOT NULL REFERENCES kol_accounts(id) ON DELETE CASCADE,
  deliverable VARCHAR(30) NOT NULL,
  harga NUMERIC(14,0) NOT NULL CHECK (harga >= 0),
  berlaku_mulai DATE NOT NULL,
  sumber VARCHAR(10) NOT NULL DEFAULT 'kol' CHECK (sumber IN ('kol','toko','nego')),
  file_url TEXT
);

CREATE TABLE vendor_documents (
  id SERIAL PRIMARY KEY,
  kol_id INT NOT NULL REFERENCES kol_accounts(id) ON DELETE CASCADE,
  jenis VARCHAR(20) NOT NULL CHECK (jenis IN ('KTP','NPWP','rekening','media_kit','lainnya')),
  nama_file VARCHAR(200),
  isi_terenkripsi BYTEA,
  terverifikasi BOOLEAN NOT NULL DEFAULT FALSE,
  uploaded_by INT REFERENCES users(id),
  uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------- Campaign & pengajuan ----------
CREATE TABLE campaigns (
  id SERIAL PRIMARY KEY,
  no_campaign VARCHAR(30) UNIQUE NOT NULL,
  nama VARCHAR(200) NOT NULL,
  tujuan TEXT,
  periode_mulai DATE, periode_selesai DATE,
  budget NUMERIC(14,0) NOT NULL DEFAULT 0,
  jenis VARCHAR(10) NOT NULL DEFAULT 'grup' CHECK (jenis IN ('grup','tunggal')),
  slot INT,
  target_zone_ids INT[] DEFAULT '{}',
  target_store_ids INT[] DEFAULT '{}',
  status VARCHAR(30) NOT NULL DEFAULT 'Draft',
  created_by INT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE submissions (
  id SERIAL PRIMARY KEY,
  no_pengajuan VARCHAR(30) UNIQUE NOT NULL,
  campaign_id INT REFERENCES campaigns(id) ON DELETE CASCADE,
  jenis VARCHAR(10) NOT NULL DEFAULT 'grup' CHECK (jenis IN ('grup','tunggal')),
  revisi_ke INT NOT NULL DEFAULT 0,
  status VARCHAR(30) NOT NULL DEFAULT 'Draft',
  submitted_by INT REFERENCES users(id),
  submitted_at TIMESTAMPTZ,
  store_request_id INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE submission_items (
  id SERIAL PRIMARY KEY,
  submission_id INT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
  kol_id INT NOT NULL REFERENCES kol_accounts(id),
  store_id INT REFERENCES stores(id),
  deliverable VARCHAR(30) NOT NULL DEFAULT 'video',
  tanggal_posting DATE,
  ratecard NUMERIC(14,0) NOT NULL DEFAULT 0,
  harga_nego NUMERIC(14,0) NOT NULL DEFAULT 0,
  skor_saat_itu NUMERIC(5,1),
  prediksi_json JSONB,
  dicentang BOOLEAN NOT NULL DEFAULT TRUE,
  keputusan_item VARCHAR(10) CHECK (keputusan_item IN ('setuju','tolak')),
  catatan_item TEXT,
  revisi_aksi VARCHAR(15),
  aktif BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE approvals (
  id SERIAL PRIMARY KEY,
  submission_id INT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
  revisi_ke INT NOT NULL DEFAULT 0,
  level INT NOT NULL CHECK (level IN (1,2)),
  approver_id INT REFERENCES users(id),
  keputusan VARCHAR(10) NOT NULL CHECK (keputusan IN ('setuju','tolak')),
  catatan TEXT,
  waktu TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ro_forms (
  id SERIAL PRIMARY KEY,
  no_ro VARCHAR(30) UNIQUE NOT NULL,
  submission_id INT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
  pdf BYTEA,
  scan_ttd BYTEA, scan_nama VARCHAR(200),
  status VARCHAR(20) NOT NULL DEFAULT 'dibuat' CHECK (status IN ('dibuat','dicetak','ditandatangani')),
  kode_verifikasi VARCHAR(20) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE tax_rules (
  id SERIAL PRIMARY KEY,
  jenis VARCHAR(20) NOT NULL,
  keterangan TEXT,
  tarif NUMERIC(6,4) NOT NULL,
  dasar NUMERIC(6,4) NOT NULL DEFAULT 1,
  tarif_tanpa_npwp NUMERIC(6,4),
  berlaku_mulai DATE NOT NULL
);

CREATE TABLE payments (
  id SERIAL PRIMARY KEY,
  ro_id INT NOT NULL REFERENCES ro_forms(id) ON DELETE CASCADE,
  item_id INT NOT NULL REFERENCES submission_items(id) ON DELETE CASCADE,
  invoice_no VARCHAR(40),
  nominal NUMERIC(14,0) NOT NULL,
  pajak_jenis VARCHAR(20),
  pajak_nominal NUMERIC(14,0) NOT NULL DEFAULT 0,
  status VARCHAR(15) NOT NULL DEFAULT 'tertahan' CHECK (status IN ('tertahan','siap','diproses','lunas')),
  alasan_tertahan TEXT,
  paid_at TIMESTAMPTZ,
  updated_by INT REFERENCES users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (item_id)
);

-- ---------- Kalender, produksi, brief ----------
CREATE TABLE promo_offline_events (
  id SERIAL PRIMARY KEY,
  store_id INT REFERENCES stores(id),
  zone_id INT REFERENCES zones(id),
  nama VARCHAR(200) NOT NULL,
  mulai DATE NOT NULL, selesai DATE NOT NULL
);

CREATE TABLE production_tasks (
  id SERIAL PRIMARY KEY,
  item_id INT NOT NULL REFERENCES submission_items(id) ON DELETE CASCADE,
  tahap VARCHAR(15) NOT NULL CHECK (tahap IN ('pitching','brief','take','review','posting','lapor')),
  urutan INT NOT NULL,
  mulai DATE NOT NULL, selesai DATE NOT NULL,
  status VARCHAR(15) NOT NULL DEFAULT 'belum' CHECK (status IN ('belum','berjalan','selesai')),
  revisi INT NOT NULL DEFAULT 0,
  UNIQUE (item_id, tahap)
);

CREATE TABLE briefs (
  id SERIAL PRIMARY KEY,
  item_id INT REFERENCES submission_items(id) ON DELETE SET NULL,
  campaign_id INT REFERENCES campaigns(id) ON DELETE CASCADE,
  judul VARCHAR(200) NOT NULL,
  versi INT NOT NULL DEFAULT 1,
  status VARCHAR(15) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','final','terkirim')),
  updated_by INT REFERENCES users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE brief_sections (
  brief_id INT REFERENCES briefs(id) ON DELETE CASCADE,
  urutan INT NOT NULL CHECK (urutan BETWEEN 1 AND 9),
  judul VARCHAR(100) NOT NULL,
  isi_json JSONB NOT NULL DEFAULT '{}',
  PRIMARY KEY (brief_id, urutan)
);

-- ---------- Posting, bukti tayang ----------
CREATE TABLE posts (
  id SERIAL PRIMARY KEY,
  item_id INT UNIQUE REFERENCES submission_items(id) ON DELETE CASCADE,
  kol_id INT REFERENCES kol_accounts(id),
  link VARCHAR(500),
  platform VARCHAR(20),
  tanggal_tayang TIMESTAMPTZ,
  jenis_konten VARCHAR(30),
  durasi_detik INT,
  bukti BYTEA, bukti_nama VARCHAR(200),
  insight BYTEA, insight_nama VARCHAR(200),
  telat_hari INT NOT NULL DEFAULT 0,
  updated_by INT REFERENCES users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE post_metrics (
  id SERIAL PRIMARY KEY,
  post_id INT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  views INT, likes INT, komentar INT, share INT, save INT,
  sumber VARCHAR(10) NOT NULL CHECK (sumber IN ('api','ocr','manual')),
  diukur_pada DATE NOT NULL
);

-- Konten akun resmi Mitra10 (untuk rekap konten terbaik)
CREATE TABLE official_posts (
  id SERIAL PRIMARY KEY,
  platform VARCHAR(20) NOT NULL,
  judul VARCHAR(200) NOT NULL,
  jenis_konten VARCHAR(30),
  durasi_detik INT,
  tanggal TIMESTAMPTZ NOT NULL,
  views INT, likes INT, komentar INT, share INT, save INT
);

-- ---------- Traffic offline ----------
CREATE TABLE uploads (
  id SERIAL PRIMARY KEY,
  jenis VARCHAR(20) NOT NULL CHECK (jenis IN ('traffic','kol_db')),
  nama_file VARCHAR(200),
  ringkasan_validasi_json JSONB,
  uploaded_by INT REFERENCES users(id),
  uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE offline_traffic_daily (
  store_id INT NOT NULL REFERENCES stores(id),
  tanggal DATE NOT NULL,
  kunjungan INT NOT NULL,
  transaksi INT,
  flag VARCHAR(15) CHECK (flag IN ('imputasi','outlier','event')),
  upload_id INT REFERENCES uploads(id),
  PRIMARY KEY (store_id, tanggal)
);

-- ---------- Request toko ----------
CREATE TABLE store_requests (
  id SERIAL PRIMARY KEY,
  no_request VARCHAR(30) UNIQUE NOT NULL,
  store_id INT NOT NULL REFERENCES stores(id),
  kol_id INT REFERENCES kol_accounts(id),
  data_akun_baru_json JSONB,
  kebutuhan TEXT,
  periode_mulai DATE, periode_selesai DATE,
  ratecard NUMERIC(14,0),
  file_nama VARCHAR(200), file_isi BYTEA,
  cek_sistem_json JSONB,
  status VARCHAR(20) NOT NULL DEFAULT 'Diajukan',
  catatan TEXT,
  submitted_by INT REFERENCES users(id),
  reviewed_by INT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------- Social listening ----------
CREATE TABLE topics (
  id SERIAL PRIMARY KEY,
  label VARCHAR(150) NOT NULL,
  kata_kunci TEXT[] NOT NULL,
  jenis VARCHAR(15) NOT NULL CHECK (jenis IN ('isu','kebutuhan','peluang'))
);

CREATE TABLE social_comments (
  id BIGSERIAL PRIMARY KEY,
  platform VARCHAR(20) NOT NULL,
  post_ref VARCHAR(100),
  author_hash VARCHAR(20),
  teks_anonim TEXT NOT NULL,
  waktu TIMESTAMPTZ NOT NULL
);

CREATE TABLE comment_nlp (
  comment_id BIGINT PRIMARY KEY REFERENCES social_comments(id) ON DELETE CASCADE,
  is_spam BOOLEAN NOT NULL DEFAULT FALSE,
  teks_bersih TEXT,
  sentimen VARCHAR(10),
  skor NUMERIC(4,2),
  metode VARCHAR(10),
  aspek TEXT[],
  niat VARCHAR(30),
  topic_id INT REFERENCES topics(id),
  store_id INT REFERENCES stores(id)
);

-- ---------- ML ops ----------
CREATE TABLE predictions (
  id BIGSERIAL PRIMARY KEY,
  entity VARCHAR(10) NOT NULL,
  entity_id INT NOT NULL,
  entity2_id INT,
  tipe VARCHAR(20) NOT NULL,
  nilai NUMERIC, q_low NUMERIC, q_high NUMERIC,
  alasan_json JSONB,
  model_version VARCHAR(30),
  dibuat TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON predictions(entity, tipe, entity_id);

CREATE TABLE model_runs (
  id SERIAL PRIMARY KEY,
  model VARCHAR(50) NOT NULL,
  versi VARCHAR(20) NOT NULL,
  algoritma TEXT,
  metode_uji TEXT,
  metrik_json JSONB,
  pembanding_json JSONB,
  ambang TEXT,
  gate VARCHAR(10) NOT NULL CHECK (gate IN ('lulus','gagal')),
  aktif BOOLEAN NOT NULL DEFAULT FALSE,
  dijalankan TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE data_checks (
  id SERIAL PRIMARY KEY,
  nama VARCHAR(100) NOT NULL,
  hasil VARCHAR(10) NOT NULL CHECK (hasil IN ('lulus','peringatan','gagal')),
  detail TEXT,
  dijalankan TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------- Keamanan: blokir akses publik via API Supabase ----------
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.tablename);
  END LOOP;
END$$;
