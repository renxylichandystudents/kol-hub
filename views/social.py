"""Layar 3 — Social Media Listening: komentar & mention Instagram dan TikTok secara terpisah."""
import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, db, nlp, ui
from lib import formulas as F
from lib.rbac import require

user = auth.current_user()
require(user["role"], "social.view")
ui.header("Social Media Listening", "Komentar & mention akun resmi Mitra10 — spam/bot disaring sebelum dianalisa")
f = ui.global_filters(user)
store_ids = tuple(f["store_ids"]) if not f["all"] else None
stores = ui.stores().set_index("id")

ACTION = {
    "Stok cat kosong": "Koordinasi stok dengan toko terkait; tunda konten produk yang stoknya kosong; balas komentar dengan info restock.",
    "Antrean kasir panjang": "Teruskan ke operasional toko; konten 'belanja cepat' (pesan online, ambil di toko).",
    "Pengiriman terlambat": "Eskalasi ke tim delivery; balas personal dengan nomor pesanan.",
    "Pelayanan kurang ramah": "Teruskan ke Store Manager terkait; pantau 7 hari ke depan.",
    "Tanya harga & promo": "Sematkan komentar berisi harga/promo; tambahkan harga di caption konten berikutnya.",
    "Jasa pasang / instalasi": "Brief KOL: tampilkan layanan pasang; cantumkan kontak jasa toko.",
    "Cabang & lokasi terdekat": "Tambahkan lokasi toko & jam buka di caption; tag lokasi.",
    "Ide renovasi kamar mandi": "Peluang konten before–after kamar mandi untuk KOL lifestyle.",
    "Inspirasi dapur & kitchen set": "Peluang konten kitchen set modular; cocok KOL culinary/lifestyle.",
    "Konten tutorial DIY": "Prioritaskan format tutorial < 45 detik.",
    "Warna cat favorit": "Konten pilihan warna cat; kolaborasi KOL interior.",
}

tabs = st.tabs(["Instagram", "TikTok", "Gabungan"])
for tab, plat in zip(tabs, ["Instagram", "TikTok", None]):
    with tab:
        d = A.comments_nlp(f["start"], f["end"], platform=plat, store_ids=store_ids)
        if d.empty:
            st.info("Belum ada komentar pada periode ini.")
            continue
        clean = d[~d["is_spam"]]
        s = A.sentiment_summary(d)
        amb = int((clean["metode"] == "ambigu").sum())
        ui.kpis([
            {"label": "Komentar dianalisa", "value": F.angka(len(clean), False), "sub": f"{int(d['is_spam'].sum())} spam/bot disaring"},
            {"label": "Sentimen netto", "value": f"{s['net']:+.0f}", "sub": f"positif {s['pos']:.0f}% · negatif {s['neg']:.0f}%"},
            {"label": "Pertanyaan / kebutuhan", "value": F.angka(int(clean["niat"].isin(["bertanya harga", "cari produk", "butuh jasa", "tanya lokasi"]).sum()), False),
             "sub": "niat terdeteksi"},
            {"label": "Perlu tinjauan manusia", "value": F.angka(amb, False), "sub": "keyakinan < 0,6 (cascade tahap 3)"},
        ])
        ui.sentiment_bar(s["pos"], s["neu"], s["neg"])
        spikes = A.topic_spikes(d)
        c1, c2 = st.columns([1.6, 1], gap="medium")
        with c1:
            st.markdown("#### Topik otomatis")
            if spikes.empty:
                st.caption("Belum ada topik.")
            else:
                sp = spikes.copy()
                sp["Toko terkait"] = sp["toko"].map(lambda ids: ", ".join(stores.loc[i, "short"] for i in ids if i in stores.index) or "—")
                sp["Jenis"] = sp["jenis"].map({"isu": "Isu", "kebutuhan": "Kebutuhan", "peluang": "Peluang konten"})
                sp["Status"] = sp.apply(lambda r: f"🔺 lonjakan z={r['z']:.1f}" if r["lonjakan"] else f"z={r['z']:.1f}", axis=1)
                cols = ["topik", "Jenis", "volume_30hr", "negatif_pct", "Status", "Toko terkait"]
                if plat is None:
                    cols.insert(0, "platform")
                st.dataframe(sp[cols], hide_index=True, use_container_width=True, column_config={
                    "topik": "Topik", "platform": "Platform", "volume_30hr": "Volume 30 hr",
                    "negatif_pct": st.column_config.NumberColumn("% negatif", format="%.0f%%")})
                ui.note("Lonjakan isu: z = (volume 3 hari terakhir − median 28 hari) / (1,4826 × MAD); isu bila z > 3. "
                        "Toko dikenali dari teks dengan gazetteer 61 toko + fuzzy matching.")
            st.markdown("#### Rekomendasi aksi")
            if not spikes.empty:
                for _, r in spikes.head(4).iterrows():
                    flag = ui.badge("lonjakan", "red") if r["lonjakan"] else ui.badge(r["jenis"], {"isu": "amber", "kebutuhan": "blue", "peluang": "green"}[r["jenis"]])
                    st.markdown(f"{flag} **{ui.esc(r['topik'])}** — {ui.esc(ACTION.get(r['topik'], 'Tinjau komentar terkait.'))}", unsafe_allow_html=True)
        with c2:
            st.markdown("#### Kata kunci dominan")
            kw = nlp.keywords(clean["teks_anonim"].tolist(), top=12)
            st.markdown(" ".join(ui.badge(f"{w} · {n}", "gray") for w, n in kw), unsafe_allow_html=True)
            st.markdown("#### Aspek negatif")
            neg = clean[clean["sentimen"] == "negatif"].explode("aspek")
            if not neg.empty and neg["aspek"].notna().any():
                st.bar_chart(neg["aspek"].value_counts(), horizontal=True, height=220)
            st.markdown("#### Konten paling ramai")
            q = "SELECT platform, judul, views, komentar FROM official_posts WHERE tanggal::date BETWEEN %s AND %s"
            params = [f["start"], f["end"]]
            if plat:
                q += " AND platform=%s"; params.append(plat)
            top = db.df(q + " ORDER BY komentar DESC LIMIT 5", params)
            if not top.empty:
                st.dataframe(top, hide_index=True, use_container_width=True)
        with st.expander("Contoh komentar (teks dianonimkan)"):
            fil = st.selectbox("Filter sentimen", ["semua", "negatif", "positif", "netral", "ambigu (perlu tinjauan)"], key=f"sf_{plat}")
            x = clean
            if fil == "ambigu (perlu tinjauan)":
                x = x[x["metode"] == "ambigu"]
            elif fil != "semua":
                x = x[x["sentimen"] == fil]
            st.dataframe(x.sort_values("waktu", ascending=False).head(200)[["waktu", "platform", "teks_anonim", "sentimen", "skor", "metode", "aspek", "niat", "topik"]],
                         hide_index=True, use_container_width=True)
st.caption("Cakupan: akun resmi Mitra10 & konten kerja sama (API Instagram Business / TikTok for Business). Listening di luar akun sendiri "
           "membutuhkan alat pihak ketiga berlisensi (B.8).")
