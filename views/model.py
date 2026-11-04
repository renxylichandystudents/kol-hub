"""Layar 24 — Model & Testing: setiap saran diuji sebelum ditampilkan (B.10)."""
import json

import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, db, jobs, ui
from lib.rbac import can, require

user = auth.current_user()
require(user["role"], "ml.view")
ui.header("Model & Testing", "Uji dulu baru tampil: model yang gagal gate tidak dipakai — sistem kembali ke versi sebelumnya")
ui.flash()

if can(user["role"], "ml.manage"):
    if st.button("Jalankan job sekarang (cek data → NLP → uji model → skor & rekomendasi)", type="primary"):
        with st.spinner("Menjalankan job…"):
            out = jobs.run_all()
        st.session_state["flash_ok"] = f"Job selesai: {out.get('nlp', {}).get('diproses', 0)} komentar diproses, " \
                                       f"{out.get('scoring', {}).get('prediksi', 0)} prediksi disimpan." + (" " + out["catatan"] if out.get("catatan") else "")
        st.rerun()

checks = db.df("""SELECT DISTINCT ON (nama) nama, hasil, detail, dijalankan FROM data_checks ORDER BY nama, dijalankan DESC""")
runs = db.df("""SELECT DISTINCT ON (model) model, versi, algoritma, metode_uji, metrik_json, pembanding_json, ambang, gate, aktif, dijalankan
                FROM model_runs ORDER BY model, dijalankan DESC""")
active = db.df("SELECT DISTINCT ON (model) model, versi AS versi_aktif FROM model_runs WHERE aktif ORDER BY model, dijalankan DESC")
kt = A.kol_table()
limited = int(kt["data_terbatas"].sum()) if not kt.empty else 0
drift = jobs.drift_report()

ui.kpis([
    {"label": "Cek kualitas data", "value": f"{int((checks['hasil'] == 'lulus').sum())}/{len(checks)}" if not checks.empty else "—",
     "sub": f"{int((checks['hasil'] == 'peringatan').sum())} peringatan · {int((checks['hasil'] == 'gagal').sum())} gagal" if not checks.empty else "belum dijalankan",
     "sub_tone": "neg" if not checks.empty and (checks["hasil"] == "gagal").any() else ""},
    {"label": "Model lulus gate", "value": f"{int((runs['gate'] == 'lulus').sum())}/{len(runs)}" if not runs.empty else "—",
     "sub": "versi terakhir per model"},
    {"label": "Saran ditahan (data kurang)", "value": str(limited), "sub": "KOL < 3 kerja sama → label 'data terbatas'"},
    {"label": "Drift data", "value": ", ".join(d["status"] for d in drift if d["status"] not in ("—",)) or "—", "sub": "PSI fitur utama"},
])
if not runs.empty:
    st.caption(f"Job terakhir: {runs['dijalankan'].max():%d %b %Y %H.%M} · dijalankan otomatis bila hasil > 24 jam saat app dibuka.")

st.markdown("#### Model")
if runs.empty:
    st.info("Belum ada hasil uji model.")
else:
    m = runs.merge(active, on="model", how="left")

    def fmt(d):
        if not isinstance(d, dict) or not d:
            return "—"
        return " · ".join(f"{k} {v:.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{k} {v}" for k, v in d.items() if v is not None)

    show = pd.DataFrame({"Model": m["model"], "Algoritma": m["algoritma"], "Metode uji": m["metode_uji"], "Hasil": m["metrik_json"].map(fmt),
                         "Pembanding": m["pembanding_json"].map(fmt), "Ambang lulus": m["ambang"],
                         "Gate": m["gate"].map({"lulus": "✅ lulus", "gagal": "⛔ gagal"}),
                         "Versi dipakai": m.apply(lambda r: r["versi"] if r["gate"] == "lulus" else (r["versi_aktif"] if pd.notna(r["versi_aktif"]) else "pembanding sederhana"), axis=1)})
    st.dataframe(show, hide_index=True, use_container_width=True)
    ui.note("Model yang gagal gate tidak dipakai; layar memakai versi aktif sebelumnya atau aturan pembanding sederhana (B.7). "
            "Uji sentimen saat ini memakai 60 komentar berlabel — siapkan 300–1.000 komentar asli berlabel manual (C.12) agar hasil uji representatif.")

c1, c2 = st.columns(2, gap="medium")
with c1:
    st.markdown("#### Cek kualitas data")
    if not checks.empty:
        st.dataframe(checks.assign(hasil=checks["hasil"].map({"lulus": "✅ lulus", "peringatan": "⚠️ peringatan", "gagal": "⛔ gagal"})),
                     hide_index=True, use_container_width=True,
                     column_config={"dijalankan": st.column_config.DatetimeColumn(format="DD MMM HH:mm")})
    st.markdown("#### Drift data (PSI)")
    st.dataframe(pd.DataFrame(drift), hide_index=True, use_container_width=True,
                 column_config={"psi": st.column_config.NumberColumn("PSI", format="%.3f")})
    ui.note("PSI < 0,1 stabil · 0,1–0,25 perlu dipantau · > 0,25 drift (latih ulang).")
with c2:
    st.markdown("#### Aturan sebelum saran ditampilkan")
    st.markdown("""- Data lolos validasi skema, rentang, duplikat & kecocokan 61 toko; cek gagal → job berhenti, skor tidak diperbarui
- Setiap prediksi punya **rentang** (q20–q80 / bootstrap 90%), bukan angka tunggal
- **Abstain**: n < 3 kerja sama atau rentang terlalu lebar → label *data terbatas*
- Setiap skor & saran membawa **2–3 alasan teratas** (komponen skor)
- Model canggih dipakai hanya bila **lebih baik dari pembanding sederhana**
- Model baru berjalan bayangan (*shadow*) 2–4 minggu sebelum dipromosikan
- Keputusan akhir tetap pada approver; umpan balik setuju/tolak dicatat sebagai data latih""")
    fb = db.df("SELECT keputusan, COUNT(*) AS n FROM approvals GROUP BY keputusan")
    if not fb.empty:
        tot = fb["n"].sum()
        rej = fb[fb["keputusan"] == "tolak"]["n"].sum()
        st.metric("Tingkat penolakan saran oleh approver", f"{rej / tot * 100:.0f}%", help="Dipantau sebagai sinyal kualitas rekomendasi.")

with st.expander("Riwayat uji model"):
    hist = db.df("SELECT dijalankan, model, versi, gate, aktif, metrik_json FROM model_runs ORDER BY dijalankan DESC LIMIT 200")
    hist["metrik_json"] = hist["metrik_json"].map(lambda d: json.dumps(d, ensure_ascii=False))
    st.dataframe(hist, hide_index=True, use_container_width=True)
