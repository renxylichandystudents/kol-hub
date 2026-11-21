"""Impor file Excel realisasi KOL bulanan & daftar Portal promo → campaign, akun KOL/portal, link tayang, ratecard."""
import pandas as pd
import streamlit as st

from lib import auth, db, ui
from lib import formulas as F
from lib import importer as I
from lib.rbac import require

user = auth.current_user()
require(user["role"], "data.import")
ui.header("Impor Excel KOL & Portal",
          "Upload file realisasi KOL per bulan (mis. KOL_SEPT_2026.xlsx) dan/atau file Portal (satu sheet per promo)")
ui.flash()

with st.expander("Format yang dikenali", expanded=False):
    st.markdown("""
- **KOL bulanan** — nama file memuat bulan & tahun (`KOL_SEPT_2026.xlsx`, `KOL_NOV_2026.xlsx`). Kolom: **Toko**, akun
  (*KOL / KOL/Portal / KOL terpilih / Influencer*), *Followers*, *ER*, **Budget**, *Type Konten*, *Campaign*, link IG/TikTok
  (*Link …* atau *Bukti Tayang …*). Sel Toko yang di-merge otomatis diisi ke bawah.
- **Portal** — satu sheet per promo, baris 1 berisi judul `LIST PORTAL PROMO … - PERIODE TAYANG 10 NOVEMBER 2026`,
  baris 2 judul kolom (*Toko, Homeless Media, Type Konten, Budget, Link*). Bila ada dua kolom *Homeless Media*,
  akun di kolom terakhir yang terisi dianggap akun yang tayang.
- Link bertuliskan **cancel** → baris dicatat sebagai *ditolak/cancel* dan tidak dihitung ke budget.
- Tanggal tayang dibaca dari link Instagram; impor ulang file yang sama **menggantikan** campaign impor sebelumnya.
""")

files = st.file_uploader("File Excel (boleh beberapa sekaligus)", type=["xlsx"], accept_multiple_files=True, key="imp_files")
stores = db.query("SELECT id, nama, alias, zone_id FROM stores ORDER BY nama")
store_zone = {s["id"]: s["zone_id"] for s in stores}
store_names = {s["id"]: s["nama"] for s in stores}

if not files:
    last = db.df("""SELECT c.no_campaign AS "No", c.nama AS "Campaign", c.periode_mulai AS "Mulai", c.slot AS "Baris",
                           c.budget AS "Budget", c.status AS "Status"
                    FROM campaigns c WHERE c.impor_key IS NOT NULL ORDER BY c.periode_mulai DESC, c.id DESC""")
    if last.empty:
        st.info("Belum ada campaign hasil impor.")
    else:
        st.markdown("#### Campaign hasil impor")
        st.dataframe(last, hide_index=True, use_container_width=True,
                     column_config={"Budget": st.column_config.NumberColumn(format="Rp %d")})
    st.stop()

sig = tuple((f.name, f.size) for f in files)
if st.session_state.get("imp_sig") != sig:
    rows, issues = I.parse_files([(f.name, f.getvalue()) for f in files], stores)
    st.session_state.update(imp_sig=sig, imp_rows=rows, imp_issues=issues)
rows, issues = st.session_state["imp_rows"], st.session_state["imp_issues"]

if not rows:
    st.error("Tidak ada baris yang bisa diimpor.")
    for i in issues:
        st.caption("• " + i)
    st.stop()

summ = pd.DataFrame(I.summarize(rows))
ui.kpis([
    {"label": "Campaign", "value": str(len(summ)), "sub": f"{(summ['jenis'] == 'KOL').sum()} KOL · {(summ['jenis'] == 'Portal').sum()} Portal"},
    {"label": "Baris toko–akun", "value": F.angka(len(rows), False), "sub": f"{int(summ['cancel'].sum())} cancel"},
    {"label": "Akun unik", "value": F.angka(len({I.username_norm(r['username']) for r in rows}), False), "sub": "KOL + portal"},
    {"label": "Total budget", "value": F.rupiah(summ["budget"].sum()), "sub": "tanpa baris cancel", "highlight": True},
])
st.write("")
st.dataframe(summ.drop(columns=["key"]).rename(columns={
    "campaign": "Campaign", "jenis": "Jenis", "mulai": "Mulai", "baris": "Baris", "cancel": "Cancel", "budget": "Budget",
    "tanpa_link": "Tanpa link", "toko_belum_cocok": "Toko belum cocok"}),
    hide_index=True, use_container_width=True, column_config={"Budget": st.column_config.NumberColumn(format="Rp %d")})

# ---------------------------------------------------------------- toko yang belum cocok dengan master
unmatched = sorted({r["toko"] for r in rows if not r["store_id"]})
mapping = {}
if unmatched:
    st.markdown("#### Cocokkan toko dengan master")
    st.caption("Nama toko berikut tidak ditemukan / ambigu di master 61 toko. Pilih toko yang dimaksud.")
    opts = [None] + [s["id"] for s in stores]
    for t in unmatched:
        contoh = next(r for r in rows if r["toko"] == t)
        c1, c2 = st.columns([2, 2])
        c1.markdown(f"**{ui.esc(t[:80])}**  \n<span class='kh-note'>{ui.esc(contoh['file'])} baris {contoh['baris']} · "
                    f"@{ui.esc(contoh['username'])}</span>", unsafe_allow_html=True)
        mapping[t] = c2.selectbox("Toko", opts, key=f"imp_map_{t}", format_func=lambda x: "— pilih toko —" if x is None else store_names[x],
                                  label_visibility="collapsed")

if issues:
    with st.expander(f"Catatan pembacaan file ({len(issues)})"):
        for i in issues:
            st.caption("• " + i)

with st.expander("Lihat detail baris"):
    det = pd.DataFrame([{"Campaign": r["camp_nama"], "Toko": r["toko"], "Toko master": store_names.get(r["store_id"] or mapping.get(r["toko"]), "—"),
                         "Akun": "@" + r["username"], "Jenis": r["tipe"], "Konten": r["deliverable"], "Budget": r["budget"],
                         "Tayang": r["tanggal"], "Cancel": r["cancel"], "Link": (r["ig"] or r["other"] or [""])[0]} for r in rows])
    st.dataframe(det, hide_index=True, use_container_width=True,
                 column_config={"Budget": st.column_config.NumberColumn(format="Rp %d"), "Link": st.column_config.LinkColumn()})

missing = [t for t in unmatched if not mapping.get(t)]
existing = db.df("SELECT impor_key, no_campaign FROM campaigns WHERE impor_key = ANY(%s)", (list(summ["key"]),))
if not existing.empty:
    st.warning(f"{len(existing)} campaign sudah pernah diimpor ({', '.join(existing['no_campaign'])}) — akan **diganti** dengan isi file ini "
               "(termasuk pengajuan, link tayang & pembayaran yang terhubung ke campaign tersebut).")
if st.button(f"Impor {len(rows)} baris ke database", type="primary", disabled=bool(missing), icon=":material/database:"):
    for r in rows:
        if not r["store_id"]:
            r["store_id"] = mapping[r["toko"]]
    try:
        res = I.load(rows, user["id"], store_zone)
    except Exception as e:  # noqa: BLE001
        st.error(f"Impor gagal, tidak ada data yang disimpan: {e}")
        st.stop()
    auth.log_activity(user["id"], "impor_excel", "campaign", None,
                      f"Impor Excel: {res.get('campaign', 0)} campaign, {res.get('baris', 0)} baris, {res.get('akun_baru', 0)} akun baru")
    st.cache_data.clear()
    for k in ("imp_sig", "imp_rows", "imp_issues", "imp_files"):
        st.session_state.pop(k, None)
    st.session_state["flash_ok"] = (f"Impor selesai: {res.get('campaign', 0)} campaign ({res.get('campaign_diganti', 0)} diganti), "
                                    f"{res.get('baris', 0)} baris ({res.get('cancel', 0)} cancel), {res.get('akun_baru', 0)} akun baru, "
                                    f"{res.get('link_tayang', 0)} link tayang, {res.get('ratecard', 0)} riwayat ratecard.")
    st.rerun()
if missing:
    st.caption(f"Pilih toko untuk {len(missing)} nama di atas sebelum impor.")
