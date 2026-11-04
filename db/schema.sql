-- =====================================================================
-- KOL Hub - Skema database (PostgreSQL / Supabase)
-- Cara pakai: Supabase Dashboard → SQL Editor → New query →
--             paste seluruh isi file ini → Run.
-- Aman dijalankan ulang (IF NOT EXISTS / ON CONFLICT).
-- =====================================================================

-- Role user
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole') THEN
        CREATE TYPE userrole AS ENUM
            ('ecommerce', 'asst_manager', 'manager', 'store', 'finance', 'super_user');
    END IF;
END$$;

-- Zona
CREATE TABLE IF NOT EXISTS zones (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ
);

-- Store
CREATE TABLE IF NOT EXISTS stores (
    id          SERIAL PRIMARY KEY,
    code        VARCHAR(50) UNIQUE NOT NULL,
    name        VARCHAR(255) NOT NULL,
    zone_id     INTEGER REFERENCES zones(id),
    city        VARCHAR(100) NOT NULL,
    lat         NUMERIC(10, 7),
    lon         NUMERIC(10, 7),
    alias       JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ
);

-- User (dipakai halaman Login & Register di app.py)
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    totp_secret     VARCHAR(255),
    role            userrole NOT NULL DEFAULT 'ecommerce',
    scope_zone_id   INTEGER REFERENCES zones(id),
    scope_store_id  INTEGER REFERENCES stores(id),
    is_active       BOOLEAN DEFAULT TRUE,
    is_2fa_enabled  BOOLEAN DEFAULT FALSE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ
);

-- Akun KOL / Portal News
CREATE TABLE IF NOT EXISTS kol_accounts (
    id              SERIAL PRIMARY KEY,
    type            VARCHAR(20) NOT NULL,          -- 'kol' / 'portal_news'
    platform        VARCHAR(50) NOT NULL,          -- Instagram, TikTok, Portal News, ...
    name            VARCHAR(255),
    username        VARCHAR(255) NOT NULL,
    link            VARCHAR(500) NOT NULL,
    followers       INTEGER,
    engagement_rate NUMERIC(6, 2),
    category        VARCHAR(50),
    niche           VARCHAR(255),
    city_domisili   VARCHAR(100),
    zone_id         INTEGER REFERENCES zones(id),
    score           NUMERIC(5, 2),
    status          VARCHAR(20) DEFAULT 'aktif',   -- 'aktif' / 'blokir'
    alasan_blokir   TEXT,
    blocked_by      INTEGER REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ
);

-- Campaign
CREATE TABLE IF NOT EXISTS campaigns (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    category    VARCHAR(50),
    objective   TEXT,
    start_date  DATE,
    end_date    DATE,
    budget      NUMERIC(15, 2),
    status      VARCHAR(20) DEFAULT 'draft',       -- draft / in_progress / done
    created_by  INTEGER REFERENCES users(id),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ
);

-- Relasi campaign ↔ KOL
CREATE TABLE IF NOT EXISTS campaign_kols (
    campaign_id INTEGER REFERENCES campaigns(id) ON DELETE CASCADE,
    kol_id      INTEGER REFERENCES kol_accounts(id) ON DELETE CASCADE,
    fee         NUMERIC(15, 2),
    PRIMARY KEY (campaign_id, kol_id)
);

-- ---------------------------------------------------------------------
-- Data awal
-- ---------------------------------------------------------------------
INSERT INTO zones (name) VALUES
    ('Sumatera'), ('Bali - Lombok'), ('Jakarta'), ('Bekasi'),
    ('Banten'), ('Jawa Barat'), ('Jawa Timur'), ('Jawa Tengah'),
    ('Sulawesi'), ('Kalimantan')
ON CONFLICT (name) DO NOTHING;

-- ---------------------------------------------------------------------
-- Setelah Anda register akun pertama lewat app, jadikan super user:
--   UPDATE users SET role = 'super_user' WHERE email = 'email-anda@mitra10.co.id';
-- ---------------------------------------------------------------------
