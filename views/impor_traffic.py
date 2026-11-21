"""Impor laporan traffic toko: aktual harian, budget harian, dan rekap bulanan aktual vs budget (2024–2026)."""
from datetime import date

import pandas as pd
import streamlit as st

from lib import auth, db, ui
from lib import formulas as F
from lib import traffic_import as T
from lib.rbac import require

user = auth.current_user()
require(user["role"], "traffic.upload")
ui.header("Impor Traffic & Budget Toko",
          "Laporan achievement traffic (Achv_traffic) & budget traffic (BUDGET_TRAFFIC) — format laporan internal dibaca otomatis")
ui.flash()

with st.expander("Format yang dikenali"):
    st.markdown("""
- **Harian aktual vs budget** — sheet berisi blok *ACTUAL · BUDGET · ACHIEVEMENT* dengan baris tanggal (mis. sheet *apr*, *okt*).
- **Rekap bulanan** — kolom *ACTUAL / BUDGET / ACH / LY / GROWTH* per toko dengan judul bulan (sheet *mar*): ACTUAL & BUDGET =
  tahun berjalan, LY = tahun lalu. Juga format lebar *MONTH · TYPE · year* (sheet *jan - des*, *jan*, *feb*).
- **Budget harian & bulanan** — file BUDGET_TRAFFIC: sheet per bulan (JAN…NOV) kolom *Traffic / Invoice / Budget Sales* tahun target,
  sheet *MONTHLY* = target bulanan.
- Baris *Total / Region / Grand Total* diabaikan; toko baru yang belum ada di master 61 toko dilewati dan disebutkan.
- Impor ulang aman: data dengan toko & tanggal yang sama diperbarui, bukan digandakan.
""")

files = st.file_uploader("File Excel (boleh beberapa sekaligus)", type=["xlsx"], accept_multiple_files=True, key="trf_files")
stores = db.query("SELECT id, nama, kode, alias, zone_id FROM stores ORDER BY nama")

if not files:
    cur = db.df("""SELECT EXTRACT(YEAR FROM bulan)::int AS "Tahun", COUNT(DISTINCT store_id) AS "Toko",
                          COUNT(aktual) AS "Bulan-toko aktual", COUNT(budget) AS "Bulan-toko budget",
                          SUM(aktual) AS "Total aktual", SUM(budget) AS "Total budget"
                   FROM traffic_monthly GROUP BY 1 ORDER BY 1""")
    d = db.one("""SELECT MIN(tanggal) AS a, MAX(tanggal) AS b, COUNT(*) AS n FROM offline_traffic_daily""")
    b = db.one("""SELECT MIN(tanggal) AS a, MAX(tanggal) AS b, COUNT(*) AS n FROM traffic_target_daily""")
    st.markdown("#### Data yang sudah ada")
    c1, c2 = st.columns(2)
    c1.metric("Traffic harian aktual", F.angka(d["n"], False) + " baris",
              f"{d['a']:%d %b %Y} – {d['b']:%d %b %Y}" if d["a"] else None, delta_color="off")
    c2.metric("Budget harian", F.angka(b["n"], False) + " baris", f"{b['a']:%d %b %Y} – {b['b']:%d %b %Y}" if b["a"] else None,
              delta_color="off")
    if not cur.empty:
        st.dataframe(cur, hide_index=True, use_container_width=True)
    st.stop()

tahun = st.number_input("Tahun berjalan pada laporan (ACTUAL/BUDGET; LY = tahun sebelumnya)", 2023, 2035,
                        st.session_state.get("trf_year_guess", date.today().year), key="trf_year")
sig = tuple((f.name, f.size) for f in files) + (int(tahun),)
if st.session_state.get("trf_sig") != sig:
    with st.spinner("Membaca semua sheet…"):
        out, notes = T.parse_files([(f.name, f.getvalue()) for f in files], stores, int(tahun))
    st.session_state.update(trf_sig=sig, trf_out=out, trf_notes=notes)
out, notes = st.session_state["trf_out"], st.session_state["trf_notes"]
sm = T.summary(out)


def rng(r):
    return f"{r[0]:%d %b %Y} – {r[1]:%d %b %Y}" if r[0] else "—"


ui.kpis([
    {"label": "Traffic harian aktual", "value": F.angka(sm["harian_aktual"], False), "sub": rng(sm["harian_aktual_rentang"])},
    {"label": "Budget harian", "value": F.angka(sm["harian_budget"], False), "sub": rng(sm["harian_budget_rentang"])},
    {"label": "Rekap bulanan toko", "value": F.angka(sm["bulanan"], False),
     "sub": f"{sm['bulanan_rentang'][0]:%b %Y} – {sm['bulanan_rentang'][1]:%b %Y}" if sm["bulanan_rentang"][0] else "—"},
    {"label": "Toko", "value": str(sm["toko"]), "sub": "dari 61 toko master", "highlight": True},
])
for n in notes:
    st.caption("• " + n)

mo = pd.DataFrame([{"bulan": b, "store_id": s, **v} for (s, b), v in out["monthly"].items()])
if not mo.empty:
    st.markdown("#### Pratinjau rekap bulanan nasional")
    g = mo.groupby("bulan").agg(aktual=("aktual", "sum"), budget=("budget", "sum"), toko=("store_id", "nunique")).reset_index()
    g["achievement"] = g["aktual"] / g["budget"].where(g["budget"] > 0) * 100
    g.loc[g["aktual"] == 0, ["aktual", "achievement"]] = None
    g["Bulan"] = pd.to_datetime(g["bulan"]).dt.strftime("%b %Y")
    st.dataframe(g[["Bulan", "toko", "aktual", "budget", "achievement"]].rename(
        columns={"toko": "Toko", "aktual": "Traffic aktual", "budget": "Budget traffic", "achievement": "Achievement %"}),
        hide_index=True, use_container_width=True, height=300,
        column_config={"Achievement %": st.column_config.NumberColumn(format="%.1f%%")})

if st.button("Simpan ke database", type="primary", icon=":material/database:"):
    with st.spinner("Membersihkan data harian (duplikat, outlier, event) & menyimpan…"):
        try:
            res = T.load(out, user["id"], ", ".join(f.name for f in files), stores)
        except Exception as e:  # noqa: BLE001
            st.error(f"Impor gagal, tidak ada data yang disimpan: {e}")
            st.stop()
    auth.log_activity(user["id"], "impor_traffic", "upload", None,
                      f"Impor traffic: {res.get('harian_aktual', 0)} harian, {res.get('harian_budget', 0)} budget harian, {res.get('bulanan', 0)} bulanan")
    st.cache_data.clear()
    for k in ("trf_sig", "trf_out", "trf_notes", "trf_files"):
        st.session_state.pop(k, None)
    st.session_state["flash_ok"] = (f"Tersimpan: {F.angka(res.get('harian_aktual', 0), False)} baris traffic harian, "
                                    f"{F.angka(res.get('harian_budget', 0), False)} baris budget harian, "
                                    f"{F.angka(res.get('bulanan', 0), False)} rekap bulanan. Forecast, lift & achievement dihitung ulang.")
    st.rerun()
