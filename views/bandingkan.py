"""Layar 11 — Bandingkan KOL: perbandingan 2–4 KOL berdampingan."""
from itertools import combinations

import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, ui
from lib import formulas as F
from lib import workflow as W
from lib.rbac import can, require

user = auth.current_user()
require(user["role"], "kol.view")
ui.header("Bandingkan KOL", "Metrik sejajar 2–4 KOL; nilai terbaik per baris ditandai")

stores = ui.stores()
base = A.kol_table()
labels = dict(zip(base["id"], base["username"] + " — " + base["nama"]))
default = [k for k in st.session_state.get("cmp_kols", []) if k in labels][:4]
c1, c2 = st.columns([3, 1.4])
chosen = c1.multiselect("Pilih 2–4 KOL", list(labels), default=default, format_func=labels.get, max_selections=4)
st.session_state["cmp_kols"] = chosen
ssel = c2.selectbox("Untuk toko", list(stores["nama"]), index=int(stores.index[stores["nama"] == "Mitra10 Cibubur"][0]) if (stores["nama"] == "Mitra10 Cibubur").any() else 0)
store_id = int(stores[stores["nama"] == ssel]["id"].iloc[0])
if len(chosen) < 2:
    st.info("Pilih minimal 2 KOL untuk dibandingkan.")
    st.stop()

kt = A.kol_table(store_id=store_id).set_index("id")
rows = {}
posts = A.post_history()
for k in chosen:
    r = kt.loc[k]
    pred = W.item_prediction(k, store_id)
    kp = posts[posts["kol_id"] == k] if not posts.empty else pd.DataFrame()
    on_time = (kp["telat_hari"] == 0).mean() * 100 if len(kp) else None
    rows[labels[k].split(" — ")[0]] = {
        "Skor": r["skor"], "ER terkoreksi (%)": r["er_adj"], "Ekspektasi views": r["views_q50"],
        "Konsistensi (1 − CV)": r["konsistensi"], "Audiens lokal toko (%)": r["audiens_lokal"] * 100,
        "Saran harga (Rp)": r["harga_wajar"], "Biaya per 1.000 views (Rp)": r["cpm_harapan"],
        "Lift historis (%)": (r["lift_hist"] * 100) if r["lift_hist"] == r["lift_hist"] and r["lift_hist"] is not None else None,
        "Prediksi kunjungan tambahan": pred.get("kunjungan"),
        "Sentimen konten": None,
        "Ketepatan jadwal (%)": on_time,
    }
tbl = pd.DataFrame(rows).apply(pd.to_numeric, errors="coerce")
higher_better = {"Skor", "ER terkoreksi (%)", "Ekspektasi views", "Konsistensi (1 − CV)", "Audiens lokal toko (%)", "Lift historis (%)",
                 "Prediksi kunjungan tambahan", "Ketepatan jadwal (%)"}
lower_better = {"Saran harga (Rp)", "Biaya per 1.000 views (Rp)"}


def hl(row):
    vals = pd.to_numeric(row, errors="coerce")
    if vals.notna().sum() < 2:
        return [""] * len(row)
    best = vals.max() if row.name in higher_better else vals.min() if row.name in lower_better else None
    return ["background-color:#dcfce7;font-weight:700" if best is not None and v == best else "" for v in vals]


st.dataframe(tbl.style.apply(hl, axis=1).format(lambda v: "—" if v is None or pd.isna(v) else
                                                  (f"{v:,.0f}".replace(",", ".") if abs(v) >= 100 else f"{v:,.2f}".replace(".", ","))),
             use_container_width=True, height=440)
ui.note("Sentimen konten kerja sama akan terisi setelah komentar posting KOL tersinkron dari API (job sync_social).")

st.markdown("#### Analisa perbandingan")
names = list(tbl.columns)
ranked = [i for i in tbl.index if i in higher_better | lower_better and tbl.loc[i].notna().sum() >= 2]
wins = {n: sum(1 for i in ranked if tbl.loc[i, n] == (tbl.loc[i].max() if i in higher_better else tbl.loc[i].min())) for n in names}
leader = max(wins, key=wins.get)
eff = tbl.loc["Biaya per 1.000 views (Rp)"].idxmin()
loc = tbl.loc["Audiens lokal toko (%)"].idxmax()
st.markdown(f"- **{leader}** unggul di {wins[leader]} metrik.\n- Paling efisien biaya: **{eff}**.\n- Audiens paling lokal untuk {ssel}: **{loc}**.")
best_pair, best_val = None, -1
for a, b in combinations(chosen, 2):
    ov = F.audience_overlap(kt.loc[a, "audiens"], kt.loc[b, "audiens"])
    val = (W.item_prediction(a, store_id).get("kunjungan", 0) + W.item_prediction(b, store_id).get("kunjungan", 0)) * (1 - max(0, ov - 0.6))
    if val > best_val:
        best_pair, best_val, best_ov = (a, b), val, ov
if best_pair:
    a, b = best_pair
    st.success(f"Saran kombinasi: **{labels[a].split(' — ')[0]} + {labels[b].split(' — ')[0]}** — prediksi ±{F.angka(best_val)} kunjungan tambahan, "
               f"tumpang tindih audiens {best_ov * 100:.0f}% (batas 60%), total harga wajar "
               f"{F.rupiah(kt.loc[a, 'harga_wajar'] + kt.loc[b, 'harga_wajar'])}.")
if can(user["role"], "campaign.edit") and st.button("Masukkan pilihan ke draft campaign", type="primary"):
    ui.go("views/seleksi.py", pre_kols=chosen, pre_store=store_id)
