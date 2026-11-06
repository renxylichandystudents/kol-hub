"""Layar 10 — Seleksi & Review KOL: memilih KOL untuk campaign aktif (+ generator sesuai budget, rumus 11)."""
from datetime import timedelta

import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, db, ui
from lib import formulas as F
from lib import workflow as W
from lib.master import KATEGORI, KATEGORI_LABEL
from lib.optimize import Candidate, Constraints, _min_finite, finite, solve
from lib.rbac import require

user = auth.current_user()
require(user["role"], "campaign.edit")
ui.header("Seleksi & Review KOL", "Pilih KOL untuk campaign aktif — rekap otomatis per toko/zona & sisa budget")
ui.flash()

camps = db.df("""SELECT c.*, s.id AS sub_id, s.status AS sub_status FROM campaigns c JOIN submissions s ON s.campaign_id=c.id
                 WHERE s.status IN ('Draft','Revisi','Ditolak') ORDER BY c.created_at DESC""")
if camps.empty:
    ui.steps(["Campaign dibuat", "Pilih KOL", "Rekap", "Ajukan approval"], 0)
    st.info("Belum ada campaign draft. Buat campaign terlebih dahulu.")
    if st.button("Buat campaign baru", type="primary"):
        st.switch_page("views/campaign.py")
    st.stop()

ids = camps["id"].tolist()
sel = st.session_state.get("sel_campaign")
pick = st.selectbox("Campaign aktif", ids, index=ids.index(sel) if sel in ids else 0,
                    format_func=lambda i: f"{camps.set_index('id').loc[i, 'no_campaign']} — {camps.set_index('id').loc[i, 'nama']}")
st.session_state["sel_campaign"] = pick
c = camps.set_index("id").loc[pick]
sub_id = int(c["sub_id"])
items = db.df("""SELECT i.id, i.kol_id, i.store_id, i.harga_nego, k.username, st.nama AS toko, z.nama AS zona
                 FROM submission_items i JOIN kol_accounts k ON k.id=i.kol_id JOIN stores st ON st.id=i.store_id JOIN zones z ON z.id=st.zone_id
                 WHERE i.submission_id=%s AND i.aktif""", (sub_id,))
ui.steps(["Campaign dibuat", "Pilih KOL", "Rekap", "Ajukan approval"], 1 if items.empty else 2)

used = items["harga_nego"].sum() if not items.empty else 0
ui.kpis([
    {"label": "Budget", "value": F.rupiah(c["budget"]), "sub": f"{c['periode_mulai']:%d %b} – {c['periode_selesai']:%d %b %Y}"},
    {"label": "Terpakai di draft", "value": F.rupiah(used), "sub": f"{len(items)} dari {int(c['slot'] or 0)} slot terisi"},
    {"label": "Sisa budget", "value": F.rupiah(c["budget"] - used), "sub_tone": "neg" if used > c["budget"] else "",
     "sub": "melebihi budget!" if used > c["budget"] else "", "highlight": True},
    {"label": "Jenis", "value": str(c["jenis"]).title(), "sub": f"status {c['sub_status']}"},
])

stores, zones = ui.stores(), ui.zones()
target_ids = list(c["target_store_ids"] or [])
if not target_ids:
    needs = A.store_needs()
    zids = list(c["target_zone_ids"] or [])
    pool = needs[needs["zone_id"].isin(zids)] if zids else needs
    target_ids = pool.head(6)["store_id"].astype(int).tolist()

f1, f2, f3, f4 = st.columns(4)
zf = f1.selectbox("Zona", ["Semua"] + sorted(stores[stores["id"].isin(target_ids)]["zona"].unique()))
spool = stores[stores["id"].isin(target_ids)]
spool = spool if zf == "Semua" else spool[spool["zona"] == zf]
sf = f2.multiselect("Toko", list(spool["nama"]), default=list(spool["nama"]))
kf = f3.selectbox("Kategori", ["Semua"] + [KATEGORI_LABEL[k] for k in KATEGORI])
pf = f4.selectbox("Platform", ["Semua", "Instagram", "TikTok", "Portal News"])
sel_ids = [int(stores[stores["nama"] == s]["id"].iloc[0]) for s in sf]

# kandidat: rekomendasi per toko (smart suggestion)
cands = []
for sid in sel_ids:
    rec = A.recommend_for_store(sid, k=10, seed=sid)
    if not rec.empty:
        rec = rec.assign(store_id=sid, toko=stores.set_index("id").loc[sid, "nama"], zona=stores.set_index("id").loc[sid, "zona"])
        cands.append(rec)
cand = pd.concat(cands, ignore_index=True) if cands else pd.DataFrame()
if not cand.empty:
    if kf != "Semua":
        cand = cand[cand["kategori"] == kf.lower()]
    if pf != "Semua":
        cand = cand[cand["platform"] == pf]
    in_draft = set(zip(items["kol_id"], items["store_id"])) if not items.empty else set()
    cand = cand[[(k, s) not in in_draft for k, s in zip(cand["id"], cand["store_id"])]]

tab_pick, tab_gen = st.tabs(["Pilih KOL (smart suggestion)", "Generator sesuai budget"])
with tab_pick:
    if cand.empty:
        st.info("Tidak ada kandidat untuk filter ini.")
    else:
        pre = set(st.session_state.pop("pre_kols", []) or []) | ({st.session_state.pop("pre_kol")} if st.session_state.get("pre_kol") else set())
        limit = st.toggle("Tampilkan semua kandidat", value=False, help="Bila database besar, hanya 15 saran teratas yang ditampilkan.")
        view = cand.sort_values("rank", ascending=False)
        view = view if limit else view.head(15)
        tbl = pd.DataFrame({"Pilih": view["id"].isin(pre), "KOL": view["username"], "Toko": view["toko"], "Kategori": view["kategori"].map(KATEGORI_LABEL),
                            "Skor": view["skor"].round(0), "Audiens lokal": view["audiens_lokal"] * 100,
                            "Prediksi kunjungan": [f"+{F.angka(a)} – {F.angka(b)}" for a, b in zip(view["prediksi_low"], view["prediksi_high"])],
                            "Ratecard": view["harga"], "Saran harga": view["harga_wajar"], "Alasan": view["alasan"].map(" · ".join),
                            "kol_id": view["id"], "store_id": view["store_id"]})
        ed = st.data_editor(tbl, hide_index=True, use_container_width=True, height=420, disabled=[x for x in tbl.columns if x != "Pilih"],
                            column_config={"kol_id": None, "store_id": None,
                                           "Skor": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
                                           "Audiens lokal": st.column_config.NumberColumn(format="%.0f%%"),
                                           "Ratecard": st.column_config.NumberColumn(format="Rp %d"),
                                           "Saran harga": st.column_config.NumberColumn(format="Rp %d")}, key=f"sel_{pick}")
        chosen = ed[ed["Pilih"]]
        tgl = st.date_input("Rencana tayang", c["periode_mulai"] or pd.Timestamp.today().date() + timedelta(days=14), key="sel_tgl")
        b1, b2, b3 = st.columns(3)
        if b1.button("Bandingkan KOL", disabled=not (2 <= chosen["kol_id"].nunique() <= 4), use_container_width=True):
            ui.go("views/bandingkan.py", cmp_kols=chosen["kol_id"].unique().astype(int).tolist())
        if b2.button(f"Masukkan {len(chosen)} ke draft", type="primary", disabled=chosen.empty, use_container_width=True):
            errs = []
            for _, r in chosen.iterrows():
                try:
                    harga = float(r["Saran harga"]) if r["Ratecard"] > r["Saran harga"] * 1.07 else float(r["Ratecard"])
                    W.add_item(user, sub_id, int(r["kol_id"]), int(r["store_id"]), None, tgl, harga)
                except W.WorkflowError as e:
                    errs.append(str(e))
            st.session_state["flash_ok"] = f"{len(chosen) - len(errs)} KOL masuk draft." + (" Gagal: " + "; ".join(errs) if errs else "")
            st.rerun()
        if b3.button("Rekap & ajukan approval", use_container_width=True, disabled=items.empty):
            ui.go("views/draft.py", sel_sub=sub_id)
        ui.note("Harga awal di draft = ratecard, atau saran harga bila ratecard > 7% di atas harga wajar (dapat dinego di draft).")

with tab_gen:
    st.caption("Generate pengajuan sesuai budget, jumlah KOL & toko — Integer Linear Programming (OR-Tools CP-SAT) dengan kurva jenuh per toko.")
    g1, g2, g3, g4 = st.columns(4)
    budget = g1.number_input("Budget (Rp)", min_value=0, step=1_000_000, value=int(max(c["budget"] - used, 0)))
    n_kol = g2.number_input("Jumlah KOL", min_value=1, max_value=40, value=max(1, int((c["slot"] or 5) - len(items))))
    zmin, zmax = g3.slider("Porsi biaya per zona", 0, 100, (0 if len(set(stores[stores['id'].isin(sel_ids)]['zona'])) < 2 else 10, 70), step=5)
    wajib = g4.multiselect("Toko wajib ≥ 1 KOL", sf, default=sf[: min(len(sf), int(n_kol))])
    if st.button("Jalankan generator", type="primary", disabled=cand.empty):
        cs = [Candidate(f"{r.id}:{r.store_id}", int(r.id), int(r.store_id), r.zona,
                        _min_finite(r.harga, r.batas_nego, default=finite(r.harga_wajar, default=0.0)),
                        finite(r.prediksi_kunjungan, default=0.0), finite(r.skor, default=0.0), r.status != "aktif")
              for r in cand.itertuples()]
        cons = Constraints(budget=float(budget), jumlah_kol=int(n_kol), wajib_toko=[int(stores[stores["nama"] == s]["id"].iloc[0]) for s in wajib],
                           zona_min=zmin / 100, zona_maks=zmax / 100)
        st.session_state["gen_result"] = solve(cs, cons)
    res = st.session_state.get("gen_result")
    if res:
        if res["status"] != "optimal":
            st.error("Tidak ada kombinasi yang memenuhi semua batasan. Naikkan budget, kurangi jumlah KOL/toko wajib, atau longgarkan porsi zona.")
        else:
            sel = res["terpilih"]
            names = cand.set_index(["id", "store_id"])
            out = pd.DataFrame([{"KOL": names.loc[(x.kol_id, x.store_id), "username"], "Toko": names.loc[(x.kol_id, x.store_id), "toko"],
                                 "Zona": x.zone, "Harga": x.harga, "Prediksi kunjungan": x.expected_visits, "Skor": x.skor,
                                 "kol_id": x.kol_id, "store_id": x.store_id} for x in sel])
            st.dataframe(out.drop(columns=["kol_id", "store_id"]), hide_index=True, use_container_width=True, column_config={
                "Harga": st.column_config.NumberColumn(format="Rp %d"), "Prediksi kunjungan": st.column_config.NumberColumn(format="%d")})
            ok = all(res["cek"].values())
            st.markdown(f"Total {F.rupiah(res['total_harga'])} · ±{F.angka(res['total_kunjungan'])} kunjungan tambahan (setelah kurva jenuh) · "
                        f"solver {res['solver']} · " + (ui.badge("semua batasan terpenuhi", "green") if ok else ui.badge("cek batasan gagal", "red")),
                        unsafe_allow_html=True)
            if st.button("Masukkan hasil generator ke draft", type="primary"):
                for r in out.itertuples():
                    try:
                        W.add_item(user, sub_id, int(r.kol_id), int(r.store_id), None, c["periode_mulai"], float(r.Harga))
                    except W.WorkflowError as e:
                        st.warning(str(e))
                st.session_state.pop("gen_result", None)
                ui.go("views/draft.py", sel_sub=sub_id, flash_ok=f"{len(out)} KOL dari generator masuk draft.")

st.markdown("#### Rekap draft saat ini")
if items.empty:
    st.caption("Draft masih kosong.")
else:
    r1, r2 = st.columns(2)
    r1.dataframe(items.groupby("zona").agg(KOL=("id", "count"), Total=("harga_nego", "sum")).reset_index(), hide_index=True,
                 use_container_width=True, column_config={"Total": st.column_config.NumberColumn(format="Rp %d")})
    r2.dataframe(items.groupby("toko").agg(KOL=("id", "count"), Total=("harga_nego", "sum")).reset_index(), hide_index=True,
                 use_container_width=True, column_config={"Total": st.column_config.NumberColumn(format="Rp %d")})
