-- Kunci campaign hasil impor Excel (KOL bulanan / Portal) agar impor ulang menggantikan, bukan menggandakan.
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS impor_key VARCHAR(60);
CREATE UNIQUE INDEX IF NOT EXISTS campaigns_impor_key_uq ON campaigns(impor_key) WHERE impor_key IS NOT NULL;
