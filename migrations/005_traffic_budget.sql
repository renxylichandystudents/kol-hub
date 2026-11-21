-- Budget traffic harian & rekap bulanan aktual vs budget (laporan achievement toko)
CREATE TABLE IF NOT EXISTS traffic_target_daily (
  store_id INT NOT NULL REFERENCES stores(id),
  tanggal DATE NOT NULL,
  traffic NUMERIC(12,2),
  invoice NUMERIC(12,2),
  sales NUMERIC(18,2),
  PRIMARY KEY (store_id, tanggal)
);

CREATE TABLE IF NOT EXISTS traffic_monthly (
  store_id INT NOT NULL REFERENCES stores(id),
  bulan DATE NOT NULL,                 -- tanggal 1 tiap bulan
  aktual INT,
  budget NUMERIC(12,2),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (store_id, bulan)
);
