-- Integrasi API Instagram (Meta Graph) & TikTok (Display API)
CREATE TABLE IF NOT EXISTS api_tokens (
  nama VARCHAR(60) PRIMARY KEY,            -- 'meta', 'tiktok:mitra10', 'tiktok:kol:<id>'
  nilai_terenkripsi BYTEA NOT NULL,        -- JSON token (Fernet, kunci DOC_ENCRYPTION_KEY)
  info_json JSONB NOT NULL DEFAULT '{}',   -- data non-rahasia: akun, kedaluwarsa, scope
  updated_by INT REFERENCES users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS social_sync_log (
  id BIGSERIAL PRIMARY KEY,
  jenis VARCHAR(40) NOT NULL,
  mulai TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  selesai TIMESTAMPTZ,
  ringkasan_json JSONB NOT NULL DEFAULT '{}'
);

ALTER TABLE kol_accounts ADD COLUMN IF NOT EXISTS api_status VARCHAR(30);
ALTER TABLE kol_accounts ADD COLUMN IF NOT EXISTS api_checked_at TIMESTAMPTZ;
ALTER TABLE kol_accounts ADD COLUMN IF NOT EXISTS ext_id VARCHAR(40);

ALTER TABLE official_posts ADD COLUMN IF NOT EXISTS ext_id VARCHAR(60);
ALTER TABLE official_posts ADD COLUMN IF NOT EXISTS link VARCHAR(500);
ALTER TABLE official_posts ADD COLUMN IF NOT EXISTS reach INT;
CREATE UNIQUE INDEX IF NOT EXISTS official_posts_ext_uq ON official_posts(platform, ext_id) WHERE ext_id IS NOT NULL;

ALTER TABLE social_comments ADD COLUMN IF NOT EXISTS ext_id VARCHAR(60);
CREATE UNIQUE INDEX IF NOT EXISTS social_comments_ext_uq ON social_comments(platform, ext_id) WHERE ext_id IS NOT NULL;

-- metrik per posting dari API: satu baris per (post, tanggal ukur, sumber)
CREATE UNIQUE INDEX IF NOT EXISTS post_metrics_day_uq ON post_metrics(post_id, diukur_pada, sumber);

-- video TikTok milik KOL/portal yang memberi izin (Display API)
CREATE TABLE IF NOT EXISTS kol_tiktok_videos (
  video_id VARCHAR(40) PRIMARY KEY,
  kol_id INT NOT NULL REFERENCES kol_accounts(id) ON DELETE CASCADE,
  share_url VARCHAR(500),
  judul TEXT,
  dibuat TIMESTAMPTZ,
  durasi_detik INT,
  views BIGINT, likes INT, komentar INT, share INT,
  item_id INT REFERENCES submission_items(id) ON DELETE SET NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oauth_states (
  state VARCHAR(64) PRIMARY KEY,
  owner VARCHAR(60) NOT NULL,              -- 'tiktok:mitra10' atau 'tiktok:kol:<id>'
  created_by INT REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
