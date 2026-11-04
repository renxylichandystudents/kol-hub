"""Layar 5 — Upload Data Traffic Offline: upload & preprocessing (B.3)."""
import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, db, docs, ui
from lib.preprocess import TRAFFIC_COLUMNS, StoreMatcher, clean_traffic, guess_column_mapping
from lib.rbac import require

user = auth.current_user()
require(user["role"], "traffic.upload")
ui.header("Upload Data Traffic Offline", "Data dibersihkan & divalidasi dulu sebelum dipakai model (B.1, B.3)")
ui.flash()

STEPS = ["Upload", "Cocokkan kolom", "Validasi & preprocessing", "Simpan"]
step = st.session_state.get("up_step", 0)
ui.steps(STEPS, step)

c1, c2 = st.columns([3, 1])
c2.download_button("Template Excel", docs.traffic_template(), file_name="template_traffic_offline.xlsx", use_container_width=True)

if step == 0:
    file = c1.file_uploader("File traffic harian (Excel / CSV)", type=["xlsx", "xls", "csv"])
    if file:
        try:
            raw = pd.read_csv(file) if file.name.lower().endswith(".csv") else pd.read_excel(file)
        except Exception as e:
            st.error(f"File tidak dapat dibaca: {e}")
            st.stop()
        if raw.empty:
            st.error("File kosong.")
            st.stop()
        st.session_state.update(up_raw=raw, up_name=file.name, up_step=1)
        st.rerun()

elif step == 1:
    raw = st.session_state["up_raw"]
    st.caption(f"**{st.session_state['up_name']}** · {len(raw):,} baris · {len(raw.columns)} kolom".replace(",", "."))
    st.dataframe(raw.head(8), use_container_width=True, hide_index=True)
    guess = guess_column_mapping(list(raw.columns))
    opts = ["—"] + list(raw.columns)
    mapping = {}
    cols = st.columns(4)
    for c, (key, label) in zip(cols, TRAFFIC_COLUMNS.items()):
        g = guess.get(key)
        mapping[key] = c.selectbox(label, opts, index=opts.index(g) if g in opts else 0, key=f"map_{key}")
    mapping = {k: (None if v == "—" else v) for k, v in mapping.items()}
    b1, b2 = st.columns([1, 5])
    if b1.button("Kembali"):
        st.session_state["up_step"] = 0
        st.rerun()
    if b2.button("Validasi & preprocessing", type="primary"):
        st.session_state["up_map"] = mapping
        st.session_state["up_step"] = 2
        st.rerun()

elif step == 2:
    raw, mapping = st.session_state["up_raw"], st.session_state["up_map"]
    stores = db.query("SELECT id, nama, kode, alias, zone_id FROM stores")
    ev = db.query("SELECT mulai, selesai, store_id, zone_id FROM promo_offline_events")
    all_ids = [s["id"] for s in stores]
    events = [{"mulai": e["mulai"], "selesai": e["selesai"],
               "store_ids": [e["store_id"]] if e["store_id"] else
               ([s["id"] for s in stores if s["zone_id"] == e["zone_id"]] if e["zone_id"] else all_ids)} for e in ev]
    hist = A.traffic_daily()[["store_id", "tanggal", "kunjungan"]]
    with st.spinner("Mencocokkan nama toko, merapikan tanggal, membuang duplikat, imputasi, deteksi outlier…"):
        res = clean_traffic(raw, mapping, StoreMatcher(stores), events=events, history=hist)
    if not res["ok"]:
        st.error(res["error"])
        if st.button("Kembali"):
            st.session_state["up_step"] = 1
            st.rerun()
        st.stop()
    log = res["log"]
    ui.kpis([
        {"label": "Baris awal", "value": f"{log['baris_awal']:,}".replace(",", ".")},
        {"label": "Siap disimpan", "value": f"{log['baris_siap']:,}".replace(",", "."), "sub": f"{log['toko']} toko"},
        {"label": "Duplikat dibuang", "value": str(log["duplikat_dibuang"])},
        {"label": "Diimputasi", "value": str(log["diimputasi"]), "sub": f"{log['kosong_lebih_2_hari_ditandai']} hari kosong > 2 hari ditandai"},
        {"label": "Outlier", "value": str(log["outlier_ditandai"]), "sub": f"{log['outlier_bertepatan_event']} bertepatan event toko"},
    ])
    if log["nama_toko_tidak_dikenal"]:
        st.warning("Nama toko tidak dikenali (baris dilewati): " + ", ".join(log["nama_toko_tidak_dikenal"][:20]) +
                   ". Tambahkan alias toko atau perbaiki nama di file.")
    if log["nama_toko_distandarkan"]:
        st.info(f"{log['nama_toko_distandarkan']} nama toko distandarkan ke 61 toko (alias / fuzzy match ≥ 90).")
    if log["tanggal_tidak_valid"] or log["nilai_negatif"]:
        st.warning(f"{log['tanggal_tidak_valid']} tanggal tidak valid dan {log['nilai_negatif']} nilai negatif dibuang.")
    data = res["data"].copy()
    names = {s["id"]: s["nama"] for s in stores}
    data["toko"] = data["store_id"].map(names)
    st.dataframe(data[["toko", "tanggal", "kunjungan", "transaksi", "flag"]].sort_values(["toko", "tanggal"]), hide_index=True,
                 use_container_width=True, height=320)
    ui.note("Outlier = robust z-score > 3 dari residu pola mingguan; outlier yang bertepatan dengan event/promo toko diberi tanda "
            "'event' agar tidak dihitung sebagai efek KOL.")
    b1, b2 = st.columns([1, 5])
    if b1.button("Kembali"):
        st.session_state["up_step"] = 1
        st.rerun()
    if b2.button("Simpan ke database", type="primary"):
        with db.transaction() as cur:
            up = cur.execute("INSERT INTO uploads (jenis, nama_file, ringkasan_validasi_json, uploaded_by) VALUES ('traffic',%s,%s,%s) RETURNING id",
                             (st.session_state["up_name"], log, user["id"])).fetchone()
            rows = [(int(r.store_id), r.tanggal.date(), int(r.kunjungan), None if pd.isna(r.transaksi) else int(r.transaksi),
                     r.flag if isinstance(r.flag, str) else None, up["id"]) for r in data.itertuples()]
            cur.copy_values("""INSERT INTO offline_traffic_daily (store_id, tanggal, kunjungan, transaksi, flag, upload_id) VALUES %s
                               ON CONFLICT (store_id, tanggal) DO UPDATE SET kunjungan=EXCLUDED.kunjungan, transaksi=EXCLUDED.transaksi,
                               flag=EXCLUDED.flag, upload_id=EXCLUDED.upload_id""", rows)
        auth.log_activity(user["id"], "upload_traffic", "upload", up["id"], f"Upload traffic {st.session_state['up_name']} ({len(rows)} baris)")
        st.cache_data.clear()
        for k in ("up_raw", "up_map", "up_name"):
            st.session_state.pop(k, None)
        st.session_state["up_step"] = 0
        st.session_state["flash_ok"] = f"{len(rows)} baris traffic tersimpan. Forecast & lift dihitung ulang."
        st.rerun()

st.markdown("#### Riwayat upload")
hist = db.df("""SELECT u.uploaded_at, u.nama_file, us.nama AS oleh, u.ringkasan_validasi_json->>'baris_siap' AS baris,
                       u.ringkasan_validasi_json->>'toko' AS toko FROM uploads u LEFT JOIN users us ON us.id=u.uploaded_by
                WHERE u.jenis='traffic' ORDER BY u.uploaded_at DESC LIMIT 30""")
st.dataframe(hist, hide_index=True, use_container_width=True,
             column_config={"uploaded_at": st.column_config.DatetimeColumn("Waktu", format="DD MMM YYYY HH:mm")})
with st.expander("Integrasi POS otomatis (opsional)"):
    st.write("Traffic dapat ditarik otomatis dari POS/footfall counter lewat job harian `traffic_pipeline` (C.7). "
             "Siapkan endpoint/ekspor harian dari tim IT toko; format kolom sama dengan template di atas.")
