"""Layar 12 — Draft Pengajuan Campaign: daftar KOL dalam satu campaign, dapat dimodifikasi lalu diajukan sebagai satu file."""
import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, db, ui
from lib import formulas as F
from lib import workflow as W
from lib.rbac import require

user = auth.current_user()
require(user["role"], "campaign.edit")
ui.flash()

subs = db.df("""SELECT s.id, s.no_pengajuan, s.status, s.jenis, s.revisi_ke, s.campaign_id, c.no_campaign, c.nama, c.budget
                FROM submissions s LEFT JOIN campaigns c ON c.id=s.campaign_id
                WHERE s.status IN ('Draft','Ditolak','Revisi') ORDER BY s.created_at DESC""")
sel = st.session_state.get("sel_sub")
if st.session_state.get("sel_campaign") and not sel:
    s0 = W.draft_submission(st.session_state["sel_campaign"])
    sel = s0["id"] if s0 else None
if sel and sel not in set(subs["id"]):
    extra = db.df("""SELECT s.id, s.no_pengajuan, s.status, s.jenis, s.revisi_ke, s.campaign_id, c.no_campaign, c.nama, c.budget
                     FROM submissions s LEFT JOIN campaigns c ON c.id=s.campaign_id WHERE s.id=%s""", (sel,))
    subs = pd.concat([extra, subs], ignore_index=True)
if subs.empty:
    ui.header("Draft Pengajuan Campaign")
    st.info("Tidak ada draft. Buat campaign dulu lalu pilih KOL.")
    st.stop()
ids = subs["id"].tolist()
pick = st.selectbox("Pengajuan", ids, index=ids.index(sel) if sel in ids else 0,
                    format_func=lambda i: (lambda r: f"{r['no_pengajuan']} — {r['nama'] or 'Pengajuan tunggal'} ({r['status']})")(subs.set_index('id').loc[i]))
st.session_state["sel_sub"] = pick
s = subs.set_index("id").loc[pick]
editable = s["status"] in ("Draft", "Ditolak", "Revisi")

has_campaign = pd.notna(s["campaign_id"])
ui.header(f"Draft Pengajuan · {s['no_pengajuan']}", f"{s['no_campaign'] + ' — ' + s['nama'] if has_campaign else 'Pengajuan tunggal'}"
          f" · mode {str(s['jenis']).title()}" + (f" · revisi ke-{int(s['revisi_ke'])}" if s["revisi_ke"] else ""))
st.markdown(ui.status_badge(s["status"]), unsafe_allow_html=True)

items = db.df("""SELECT i.id, i.dicentang, k.id AS kol_id, k.username, k.platform, k.status AS kol_status, st.id AS store_id, st.nama AS toko,
                        z.nama AS zona, i.deliverable, i.tanggal_posting, i.ratecard, i.harga_nego, i.skor_saat_itu, i.prediksi_json,
                        i.keputusan_item, i.catatan_item, i.revisi_aksi
                 FROM submission_items i JOIN kol_accounts k ON k.id=i.kol_id JOIN stores st ON st.id=i.store_id JOIN zones z ON z.id=st.zone_id
                 WHERE i.submission_id=%s AND i.aktif ORDER BY z.id, st.nama""", (pick,))

if s["status"] == "Ditolak":
    appr = db.df("""SELECT a.level, a.keputusan, a.catatan, a.waktu, u.nama FROM approvals a LEFT JOIN users u ON u.id=a.approver_id
                    WHERE a.submission_id=%s AND a.revisi_ke=%s ORDER BY a.waktu""", (pick, int(s["revisi_ke"])))
    st.error("Pengajuan ditolak. " + " · ".join(f"Level {r.level}: {r.keputusan}" + (f" — {r.catatan}" if r.catatan else "") for r in appr.itertuples()))
    rej = items[items["keputusan_item"] == "tolak"]
    for r in rej.itertuples():
        st.markdown(f"- ❌ **{r.username}** ({r.toko}): {ui.esc(r.catatan_item)}")
    if st.button("Mulai revisi (ganti / pertahankan baris)", type="primary"):
        W.resubmit_prepare(user, pick)
        st.rerun()
    st.stop()

if items.empty:
    st.info("Belum ada KOL di draft ini.")
    if has_campaign:
        if st.button("Pilih KOL", type="primary"):
            ui.go("views/seleksi.py", sel_campaign=int(s["campaign_id"]))
    st.stop()

pred = pd.Series(W.item_predictions(items), index=items.index, dtype=object)
items["saran_harga"] = pred.map(lambda p: p.get("harga_wajar"))
items["batas_nego"] = pred.map(lambda p: p.get("batas_nego"))
items["kunjungan"] = pred.map(lambda p: p.get("kunjungan") or 0)
# Nilai dari JSON/NUMERIC bisa None/Decimal → jadikan angka (None → NaN) agar perbandingan & penjumlahan aman
for _c in ("ratecard", "harga_nego", "saran_harga", "batas_nego", "kunjungan", "skor_saat_itu"):
    items[_c] = pd.to_numeric(items[_c], errors="coerce")
items["kunjungan"] = items["kunjungan"].fillna(0)
items["kunj_rng"] = pred.map(lambda p: f"+{F.angka(p.get('kunjungan_low', 0))} – {F.angka(p.get('kunjungan_high', 0))}" if p else "—")

st.markdown("#### Baris pengajuan")
tbl = pd.DataFrame({"✓": items["dicentang"], "KOL": items["username"], "Platform": items["platform"], "Toko": items["toko"], "Zona": items["zona"],
                    "Deliverable": items["deliverable"], "Tanggal tayang": pd.to_datetime(items["tanggal_posting"]).dt.date,
                    "Ratecard": items["ratecard"], "Harga nego": items["harga_nego"], "Saran harga": items["saran_harga"],
                    "Skor": items["skor_saat_itu"], "Prediksi kunjungan": items["kunj_rng"]})
if s["status"] == "Revisi":
    tbl["Keputusan"] = items["keputusan_item"].fillna("—")
    tbl["Catatan approver"] = items["catatan_item"].fillna("")
    tbl["Aksi revisi"] = items["revisi_aksi"].replace({"perlu_aksi": "pilih…"}).fillna("pertahankan")
editable_cols = ("✓", "Harga nego", "Tanggal tayang", "Deliverable", "Aksi revisi")
ed = st.data_editor(tbl, hide_index=True, use_container_width=True,
                    disabled=True if not editable else [c for c in tbl.columns if c not in editable_cols],
                    column_config={
                        "Ratecard": st.column_config.NumberColumn(format="Rp %d"), "Saran harga": st.column_config.NumberColumn(format="Rp %d"),
                        "Harga nego": st.column_config.NumberColumn(format="Rp %d", min_value=0, step=100_000),
                        "Deliverable": st.column_config.SelectboxColumn(options=["video", "reels", "story", "artikel"]),
                        "Skor": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
                        "Aksi revisi": st.column_config.SelectboxColumn(options=["pilih…", "pertahankan", "ganti", "hapus"])},
                    key=f"draft_{pick}")

def _same(a, b) -> bool:
    """Bandingkan dua sel; dua nilai kosong (None/NaN/NaT) dianggap sama."""
    if pd.isna(a) and pd.isna(b):
        return True
    return a == b


changed = [i for i in range(len(tbl))
           if any(not _same(tbl.iloc[i][c], ed.iloc[i][c]) for c in editable_cols if c in tbl.columns)]
if editable:
    c1, c2 = st.columns([1, 3])
    if c1.button("Simpan perubahan", disabled=not changed):
        try:
            for i in changed:
                iid = int(items.iloc[i]["id"])
                row = ed.iloc[i]
                act = row.get("Aksi revisi") if "Aksi revisi" in ed else None
                if act == "hapus":
                    W.remove_item(user, iid)
                    continue
                if pd.isna(row["Harga nego"]):
                    raise W.WorkflowError(f"Harga nego baris {i + 1} ({row['KOL']}) belum diisi.")
                W.update_item(user, iid, dicentang=bool(row["✓"]), harga_nego=float(row["Harga nego"]), tanggal_posting=row["Tanggal tayang"],
                              deliverable=row["Deliverable"], **({"revisi_aksi": act} if act in ("pertahankan", "ganti") else {}))
            st.session_state["flash_ok"] = "Perubahan disimpan."
            st.rerun()
        except W.WorkflowError as e:
            st.error(str(e))
    c2.caption(f"{len(changed)} baris berubah" if changed else "Ubah centang, harga nego, tanggal, atau aksi revisi lalu simpan.")

    with st.expander("Ganti / hapus baris"):
        labels = (items["username"] + " → " + items["toko"]).tolist()
        target = st.selectbox("Baris", range(len(items)), format_func=lambda i: labels[i])
        row = items.iloc[target]
        rec = A.recommend_for_store(int(row["store_id"]), k=8, seed=int(row["store_id"]))
        rec = rec[~rec["id"].isin(items["kol_id"])] if not rec.empty else rec
        g1, g2 = st.columns([3, 1])
        if not rec.empty:
            alt = g1.selectbox("Ganti dengan", rec["id"].tolist(),
                               format_func=lambda k: (lambda r: f"{r['username']} · skor {r['skor']:.0f} · {F.rupiah(r['harga_wajar'])}")(rec.set_index('id').loc[k]))
            if g2.button("Ganti", use_container_width=True):
                try:
                    W.replace_item(user, int(row["id"]), int(alt))
                    st.rerun()
                except W.WorkflowError as e:
                    st.error(str(e))
        if st.button("Hapus baris ini"):
            try:
                W.remove_item(user, int(row["id"]))
                st.rerun()
            except W.WorkflowError as e:
                st.error(str(e))
else:
    st.info(f"Pengajuan berstatus **{s['status']}** — baris tidak dapat diubah. "
            "Perubahan hanya bisa dilakukan saat status Draft, Revisi, atau Ditolak.")

# ---------------------------------------------------------------- analisa singkat
chk = items[items["dicentang"]]
total = chk["harga_nego"].sum()
budget = float(s["budget"]) if pd.notna(s["budget"]) and s["budget"] else None
kunj = chk["kunjungan"].sum()
over_nego = chk[chk["batas_nego"].notna() & (chk["harga_nego"] > chk["batas_nego"])]
st.markdown("#### Analisa singkat")
ui.kpis([
    {"label": "Total dicentang", "value": F.rupiah(total), "sub": f"{len(chk)} baris" + (f" · budget {F.rupiah(budget)}" if budget else ""),
     "sub_tone": "neg" if budget and total > budget else ""},
    {"label": "Prediksi kunjungan tambahan", "value": f"+{F.angka(kunj)}", "sub": "rentang per baris di tabel"},
    {"label": "Perkiraan CPIV", "value": F.rupiah(F.cpiv(total, kunj)) if kunj else "—", "sub": "biaya per kunjungan tambahan"},
    {"label": "Skor rata-rata", "value": f"{chk['skor_saat_itu'].mean():.0f}" if len(chk) else "—", "sub": f"{chk['zona'].nunique()} zona · {chk['toko'].nunique()} toko"},
])
notes = []
if budget and total > budget:
    notes.append(f"Total melebihi budget {F.rupiah(total - budget)}.")
for r in over_nego.itertuples():
    notes.append(f"{r.username}: harga nego {F.rupiah(r.harga_nego)} di atas batas nego {F.rupiah(r.batas_nego)}.")
low = chk[chk["skor_saat_itu"] < 65]
for r in low.itertuples():
    notes.append(f"{r.username}: skor {r.skor_saat_itu:.0f} (di bawah 'Layak').")
blocked = chk[chk["kol_status"] == "diblokir"]
for r in blocked.itertuples():
    notes.append(f"{r.username} kini diblokir — harus diganti.")
dup_toko = chk.groupby("toko").size()
for t, n in dup_toko[dup_toko >= 3].items():
    notes.append(f"{t}: {n} KOL — tambahan dari KOL ke-3 makin kecil (kurva jenuh).")
if notes:
    st.warning("\n".join(f"- {n}" for n in notes))
else:
    st.success("Tidak ada catatan: harga dalam batas nego, skor ≥ 65, budget cukup.")

st.markdown("#### Ringkasan per zona")
st.dataframe(chk.groupby("zona").agg(Toko=("toko", "nunique"), KOL=("id", "count"), Total=("harga_nego", "sum"), Prediksi=("kunjungan", "sum")).reset_index(),
             hide_index=True, use_container_width=True,
             column_config={"Total": st.column_config.NumberColumn(format="Rp %d"), "Prediksi": st.column_config.NumberColumn("Prediksi kunjungan", format="%d")})

if editable:
    label = "Ajukan 1 file campaign" if s["jenis"] == "grup" else "Ajukan pengajuan tunggal"
    if st.button(label, type="primary", disabled=chk.empty or bool(blocked.shape[0])):
        try:
            W.submit(user, pick)
            st.session_state["flash_ok"] = f"{s['no_pengajuan']} diajukan ke Asisten Manager."
            st.switch_page("views/campaign.py")
        except W.WorkflowError as e:
            st.error(str(e))
