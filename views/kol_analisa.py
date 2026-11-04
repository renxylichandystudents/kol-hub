"""Layar 7 — Analisa & Scoring KOL: profil analitik satu KOL / Portal News."""
import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, db, ui
from lib import formulas as F
from lib import workflow as W
from lib.master import KATEGORI_LABEL
from lib.rbac import can, require

user = auth.current_user()
require(user["role"], "kol.view")
ui.header("Analisa & Scoring KOL", "Skor, saran harga, dan dampak dihitung ulang untuk toko/zona terpilih")

base = A.kol_table()
if base.empty:
    st.info("Database KOL kosong.")
    st.stop()
labels = (base["username"] + " — " + base["nama"] + " (" + base["platform"] + ")").tolist()
ids = base["id"].tolist()
sel = st.session_state.get("sel_kol")
idx = ids.index(sel) if sel in ids else 0
c0, c1, c2 = st.columns([2.2, 1.4, 1.4])
pick = c0.selectbox("KOL / Portal News", labels, index=idx)
kol_id = ids[labels.index(pick)]
st.session_state["sel_kol"] = kol_id
stores, zones = ui.stores(), ui.zones()
zsel = c1.selectbox("Filter zona", ["Semua zona"] + list(zones["nama"]), key="an_zone")
pool = stores if zsel == "Semua zona" else stores[stores["zona"] == zsel]
ssel = c2.selectbox("Filter toko", ["Semua toko"] + list(pool["nama"]), key="an_store")
store_id = None if ssel == "Semua toko" else int(pool[pool["nama"] == ssel]["id"].iloc[0])
zone_id = None if zsel == "Semua zona" else int(zones[zones["nama"] == zsel]["id"].iloc[0])
kt = A.kol_table(store_id=store_id, zone_id=zone_id) if (store_id or zone_id) else base
r = kt[kt["id"] == kol_id].iloc[0]
if st.session_state.get("_last_an") != kol_id:
    auth.log_activity(user["id"], "lihat_analisa", "kol", kol_id, f"Analisa {r['username']}")
    st.session_state["_last_an"] = kol_id

badges = [ui.status_badge(r["status"]), ui.badge(KATEGORI_LABEL.get(r["kategori"], r["kategori"]), "blue"),
          ui.badge(r["segmen"], "purple"), ui.badge(f"tier {r['tier']}", "gray")]
if r["data_terbatas"]:
    badges.append(ui.data_limited())
st.markdown(f"### {ui.esc(r['nama'])} <span class='kh-note'>{ui.esc(r['username'])} · {r['platform']} · {ui.esc(r['kota'] or '—')}</span><br>"
            + " ".join(badges), unsafe_allow_html=True)
if r["status"] == "diblokir":
    st.error(f"Diblokir: {r['alasan_blokir']}")

ui.kpis([
    {"label": "Skor (0–100)", "value": f"{r['skor']:.0f}", "sub": r["label"] + (f" · penalti −{r['penalti']:.0f}" if r["penalti"] else ""),
     "highlight": True, "tone": "pos"},
    {"label": "ER terkoreksi", "value": F.persen(r["er_adj"]), "sub": f"ER mentah {F.persen(r['er_kol'])} · n={int(r['n_post'])}"},
    {"label": "Ekspektasi views", "value": F.angka(r["views_q50"]), "sub": f"rentang {F.angka(r['views_q20'])} – {F.angka(r['views_q80'])}"},
    {"label": "Saran harga", "value": F.rupiah(r["harga_wajar"]), "sub": f"batas nego {F.rupiah(r['batas_nego'])} · ratecard {F.rupiah(r['harga'])}"},
    {"label": "Biaya per kunjungan tambahan", "value": F.rupiah(r["cpiv"]) if r["cpiv"] else "—",
     "sub": f"lift historis {F.persen(r['lift_hist'] * 100, tanda=True)}" if r["lift_hist"] is not None and r["lift_hist"] == r["lift_hist"] else "belum ada data dampak"},
])
st.write("")

left, right = st.columns([1.3, 1], gap="medium")
with left:
    st.markdown("#### Komponen skor")
    comp = pd.DataFrame({"Komponen": ["E · engagement (ER adj)", "K · konsistensi views", "C · efisiensi biaya", "R · relevansi audiens lokal",
                                      "D · dampak offline (lift)"],
                         "Persentil": [r["E"], r["K"], r["C"], r["R"], r["D"]]})
    w = F.WEIGHTS.copy()
    if r["D"] is None or pd.isna(r["D"]):
        extra = w.pop("D") / 4
        w = {k: v + extra for k, v in w.items()}
    comp["Bobot"] = [w.get(k) for k in "EKCRD"]
    comp["Kontribusi"] = [r["kontribusi"].get(k) for k in "EKCRD"]
    st.dataframe(comp, hide_index=True, use_container_width=True, column_config={
        "Persentil": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
        "Bobot": st.column_config.NumberColumn(format="%.2f"), "Kontribusi": st.column_config.NumberColumn(format="%.1f")})
    ui.note("Skor = 0,24·E + 0,16·K + 0,16·C + 0,24·R + 0,20·D − penalti (telat tayang −3/kejadian, bukti tidak lengkap −5). "
            "Bila belum ada data dampak, bobot D dibagi rata ke komponen lain.")
    k1, k2 = st.columns(2)
    k1.markdown("**Kekuatan**\n" + "\n".join(f"- {x}" for x in r["strength"]))
    k2.markdown("**Kelemahan**\n" + "\n".join(f"- {x}" for x in r["weakness"]))

with right:
    st.markdown("#### Mapping audiens")
    aud = pd.Series(r["audiens"]).sort_values(ascending=False)
    if not aud.empty:
        st.bar_chart(aud * 100, horizontal=True, height=200)
    cities = {c: v for c, v in r["audiens"].items() if c != "Lainnya"}
    near = stores[stores["kota"].isin(cities)].assign(audiens=lambda x: x["kota"].map(cities)).sort_values("audiens", ascending=False)
    if not near.empty:
        st.markdown("Toko di area audiens: " + ", ".join(f"{s.short} ({s.audiens * 100:.0f}%)" for s in near.head(6).itertuples()))
    st.markdown("#### Harga")
    if r["flag_harga"]:
        st.warning(f"Harga naik lebih cepat dari hasil: ratecard {F.persen(r['naik_ratecard'], 0, True)} vs views "
                   f"{F.persen(r['naik_views'], 0, True)} → gap {r['gap_harga']:.0f} poin (> 20).")
    rc = db.df("SELECT berlaku_mulai, deliverable, harga, sumber FROM ratecards WHERE kol_id=%s ORDER BY berlaku_mulai", (kol_id,))
    st.dataframe(rc, hide_index=True, use_container_width=True, column_config={"harga": st.column_config.NumberColumn(format="Rp %d")})
    ui.note(f"Harga wajar = CPM target ({F.rupiah(r['cpm_target'])}, median kategori-tier yang mencapai target) × V̂q50 / 1.000; "
            "batas nego memakai V̂q80.")

st.markdown("#### Riwayat kerja sama: harga vs hasil")
hist = db.df("""SELECT i.tanggal_posting AS tanggal, COALESCE(c.nama, 'Tunggal ' || s.no_pengajuan) AS campaign, st.nama AS toko,
                       i.harga_nego AS biaya, m.views, m.likes, m.komentar, m.share, m.save, p.telat_hari, s.status
                FROM submission_items i JOIN submissions s ON s.id=i.submission_id LEFT JOIN campaigns c ON c.id=s.campaign_id
                JOIN stores st ON st.id=i.store_id LEFT JOIN posts p ON p.item_id=i.id
                LEFT JOIN LATERAL (SELECT * FROM post_metrics pm WHERE pm.post_id=p.id ORDER BY (sumber='api') DESC, diukur_pada DESC LIMIT 1) m ON TRUE
                WHERE i.kol_id=%s AND i.aktif ORDER BY i.tanggal_posting DESC""", (kol_id,))
if hist.empty:
    st.caption("Belum pernah bekerja sama.")
else:
    hist["ER"] = [F.engagement_rate(a, b, c, d, v) for a, b, c, d, v in zip(hist["likes"], hist["komentar"], hist["share"], hist["save"], hist["views"])]
    hist["CPM"] = [F.cpm(b, v) if v else None for b, v in zip(hist["biaya"], hist["views"])]
    lifts = A.item_lifts()
    if not lifts.empty:
        kl = lifts[lifts["kol_id"] == kol_id][["tanggal", "lift"]].assign(tanggal=lambda x: x["tanggal"].dt.date)
        hist = hist.merge(kl, on="tanggal", how="left")
    st.dataframe(hist.drop(columns=["likes", "komentar", "share", "save"]), hide_index=True, use_container_width=True, column_config={
        "biaya": st.column_config.NumberColumn(format="Rp %d"), "views": st.column_config.NumberColumn(format="%d"),
        "ER": st.column_config.NumberColumn(format="%.1f%%"), "CPM": st.column_config.NumberColumn(format="Rp %d"),
        "lift": st.column_config.NumberColumn(format="%.3f")})
    st.caption(f"Jumlah kerja sama: {len(hist)} · terakhir {hist['tanggal'].max()}")

if can(user["role"], "campaign.edit"):
    b1, b2 = st.columns([1, 4])
    if b1.button("Bandingkan", use_container_width=True):
        st.session_state["cmp_kols"] = list(dict.fromkeys(st.session_state.get("cmp_kols", []) + [kol_id]))[-4:]
        ui.go("views/bandingkan.py")
    if b2.button("Pilih untuk campaign", type="primary"):
        ui.go("views/seleksi.py", pre_kol=kol_id)
if can(user["role"], "kol.block"):
    with st.expander("Blokir / buka blokir"):
        if r["status"] == "aktif":
            alasan = st.text_area("Alasan blokir", key="blk_reason")
            if st.button("Blokir", type="primary"):
                try:
                    W.set_block(user, kol_id, True, alasan); st.rerun()
                except W.WorkflowError as e:
                    st.error(str(e))
        elif st.button("Buka blokir"):
            W.set_block(user, kol_id, False); st.rerun()
