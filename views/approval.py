"""Layar 13 — Review & Approval Pengajuan: keputusan Asisten Manager (level 1) / Manager (level 2)."""
import pandas as pd
import streamlit as st

from lib import auth, db, ui
from lib import formulas as F
from lib import workflow as W
from lib.rbac import Forbidden, can

user = auth.current_user()
levels = [l for l in (1, 2) if can(user["role"], f"submission.approve.level{l}")]
if not levels:
    st.error("Role ini tidak memiliki izin approval.")
    st.stop()
ui.header("Review & Approval Pengajuan", "Diajukan → Asisten Manager → Manager → Form RO → Finance (otomatis)")
ui.flash()

statuses = [{1: "Review Asisten Manager", 2: "Review Manager"}[l] for l in levels]
queue = db.df("""SELECT s.id, s.no_pengajuan, s.status, s.jenis, s.revisi_ke, s.submitted_at, s.submitted_by, u.nama AS pengaju,
                        c.no_campaign, c.nama, c.budget, c.tujuan, c.periode_mulai, c.periode_selesai
                 FROM submissions s LEFT JOIN campaigns c ON c.id=s.campaign_id LEFT JOIN users u ON u.id=s.submitted_by
                 WHERE s.status = ANY(%s) ORDER BY s.submitted_at""", (statuses,))
done = db.df("""SELECT s.no_pengajuan, COALESCE(c.nama,'Tunggal') AS nama, a.level, a.keputusan, a.catatan, a.waktu
                FROM approvals a JOIN submissions s ON s.id=a.submission_id LEFT JOIN campaigns c ON c.id=s.campaign_id
                WHERE a.approver_id=%s ORDER BY a.waktu DESC LIMIT 20""", (user["id"],))

if queue.empty:
    st.success("Tidak ada pengajuan yang menunggu keputusan Anda.")
    if not done.empty:
        st.markdown("#### Keputusan terakhir Anda")
        st.dataframe(done, hide_index=True, use_container_width=True)
    st.stop()

ids = queue["id"].tolist()
sel = st.session_state.get("sel_sub")
pick = st.selectbox(f"Antrean ({len(ids)})", ids, index=ids.index(sel) if sel in ids else 0,
                    format_func=lambda i: (lambda r: f"{r['no_pengajuan']} — {r['nama'] or 'Pengajuan tunggal'} · {r['status']}"
                                           + (f" · revisi {int(r['revisi_ke'])}" if r['revisi_ke'] else ""))(queue.set_index("id").loc[i]))
st.session_state["sel_sub"] = pick
s = queue.set_index("id").loc[pick]
level = 1 if s["status"] == "Review Asisten Manager" else 2
ui.steps(["Diajukan", "Asisten Manager", "Manager", "Form RO", "Finance"], level)
st.markdown(f"**{ui.esc(s['nama'] or 'Pengajuan tunggal')}** · {s['no_campaign'] if pd.notna(s['no_campaign']) else ''} · diajukan oleh "
            f"{ui.esc(s['pengaju'] or '—')} {s['submitted_at']:%d %b %Y %H.%M}" + (f"  \nTujuan: {ui.esc(s['tujuan'])}" if pd.notna(s["tujuan"]) else ""),
            unsafe_allow_html=True)
if s["submitted_by"] == user["id"]:
    st.warning("Anda yang mengajukan pengajuan ini — keputusan harus diambil approver lain (segregation of duties).")

items = db.df("""SELECT i.id, i.kol_id, i.store_id, k.username, k.platform, k.status AS kol_status, st.nama AS toko, z.nama AS zona, i.deliverable, i.tanggal_posting,
                        i.ratecard, i.harga_nego, i.skor_saat_itu, i.prediksi_json, i.revisi_aksi, i.keputusan_item, i.catatan_item
                 FROM submission_items i JOIN kol_accounts k ON k.id=i.kol_id JOIN stores st ON st.id=i.store_id JOIN zones z ON z.id=st.zone_id
                 WHERE i.submission_id=%s AND i.aktif ORDER BY z.id, st.nama""", (pick,))
pred = pd.Series(W.item_predictions(items), index=items.index, dtype=object)
items["batas"] = pred.map(lambda p: p.get("batas_nego"))
items["wajar"] = pred.map(lambda p: p.get("harga_wajar"))
items["kunj"] = pred.map(lambda p: p.get("kunjungan") or 0)
items["terbatas"] = pred.map(lambda p: bool(p.get("data_terbatas")))
for _c in ("ratecard", "harga_nego", "skor_saat_itu", "batas", "wajar", "kunj"):
    items[_c] = pd.to_numeric(items[_c], errors="coerce")
items["kunj"] = items["kunj"].fillna(0)

# ---------------------------------------------------------------- analisa untuk approver
total, kunj = items["harga_nego"].sum(), items["kunj"].sum()
ui.kpis([
    {"label": "Total pengajuan", "value": F.rupiah(total), "sub": f"budget {F.rupiah(s['budget'])}" if pd.notna(s["budget"]) else "tunggal",
     "sub_tone": "neg" if pd.notna(s["budget"]) and total > s["budget"] else ""},
    {"label": "Prediksi kunjungan tambahan", "value": f"+{F.angka(kunj)}", "sub": f"CPIV ≈ {F.rupiah(F.cpiv(total, kunj))}" if kunj else ""},
    {"label": "Baris", "value": str(len(items)), "sub": f"{items['toko'].nunique()} toko · {items['zona'].nunique()} zona"},
    {"label": "Skor rata-rata", "value": f"{items['skor_saat_itu'].mean():.0f}", "sub": f"{int((items['skor_saat_itu'] < 65).sum())} di bawah 'Layak'"},
])
flags = []
for r in items.itertuples():
    f = []
    if r.batas and r.harga_nego > r.batas:
        f.append(f"harga {F.persen((r.harga_nego / r.batas - 1) * 100, 0, True)} di atas batas nego")
    if r.skor_saat_itu is not None and r.skor_saat_itu < 65:
        f.append("skor < 65")
    if r.terbatas:
        f.append("data terbatas")
    if r.kol_status == "diblokir":
        f.append("KOL diblokir")
    flags.append(" · ".join(f) or "—")
items["catatan_sistem"] = flags

hist = db.df("""SELECT a.revisi_ke, a.level, a.keputusan, a.catatan, a.waktu, u.nama FROM approvals a LEFT JOIN users u ON u.id=a.approver_id
                WHERE a.submission_id=%s ORDER BY a.waktu""", (pick,))
if not hist.empty:
    with st.expander(f"Riwayat revisi & keputusan ({len(hist)})", expanded=bool(s["revisi_ke"])):
        st.dataframe(hist, hide_index=True, use_container_width=True)
        prev = items[items["revisi_aksi"].isin(["pertahankan", "pengganti"])]
        if not prev.empty:
            st.markdown("Baris revisi: " + ", ".join(f"{r.username} ({'dipertahankan' if r.revisi_aksi == 'pertahankan' else 'pengganti'})" for r in prev.itertuples()))

st.markdown("#### Keputusan per baris")
tbl = pd.DataFrame({"KOL": items["username"], "Toko": items["toko"], "Tayang": items["tanggal_posting"], "Harga nego": items["harga_nego"],
                    "Harga wajar": items["wajar"], "Batas nego": items["batas"], "Skor": items["skor_saat_itu"], "Prediksi kunjungan": items["kunj"],
                    "Catatan sistem": items["catatan_sistem"], "Keputusan": "setuju", "Catatan penolakan": ""})
ed = st.data_editor(tbl, hide_index=True, use_container_width=True, key=f"appr_{pick}_{level}",
                    disabled=[c for c in tbl.columns if c not in ("Keputusan", "Catatan penolakan")],
                    column_config={"Harga nego": st.column_config.NumberColumn(format="Rp %d"), "Harga wajar": st.column_config.NumberColumn(format="Rp %d"),
                                   "Batas nego": st.column_config.NumberColumn(format="Rp %d"),
                                   "Skor": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
                                   "Prediksi kunjungan": st.column_config.NumberColumn(format="%d"),
                                   "Keputusan": st.column_config.SelectboxColumn(options=["setuju", "tolak"], required=True)})
catatan = st.text_area("Catatan umum (opsional)")
n_tolak = int((ed["Keputusan"] == "tolak").sum())
if n_tolak:
    st.info(f"{n_tolak} baris ditolak → pengajuan dikembalikan ke E-commerce untuk revisi (ganti / pertahankan baris).")
if st.button("Tolak & kembalikan untuk revisi" if n_tolak else f"Setujui (level {level})", type="primary", disabled=s["submitted_by"] == user["id"]):
    dec = {int(items.iloc[i]["id"]): (ed.iloc[i]["Keputusan"], ed.iloc[i]["Catatan penolakan"] or None) for i in range(len(items))}
    try:
        W.decide(user, pick, level, dec, catatan or None)
        st.session_state["flash_ok"] = (f"{s['no_pengajuan']} dikembalikan untuk revisi." if n_tolak else
                                        ("Diteruskan ke Manager." if level == 1 else "Disetujui — Form RO dibuat & masuk menu Finance."))
        st.session_state.pop("sel_sub", None)
        st.rerun()
    except (W.WorkflowError, Forbidden) as e:
        st.error(str(e))
