"""Layar 2 — Dashboard: ringkasan kerja harian dengan pilihan toko, rekomendasi toko, sentimen, dan konten terbaik."""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from lib import analytics as A
from lib import auth, db, ui
from lib import formulas as F
from lib.rbac import can

user = auth.current_user()
role = user["role"]

# ---------------------------------------------------------------- lanjutkan aktivitas terakhir
TARGET = {"submission": ("views/draft.py", "sel_sub"), "campaign": ("views/draft.py", "sel_campaign"),
          "brief": ("views/brief.py", "sel_brief"), "ro": ("views/ro.py", "sel_ro"), "kol": ("views/kol_analisa.py", "sel_kol")}
acts = db.query("""SELECT DISTINCT ON (entitas, entitas_id) entitas, entitas_id, label, waktu FROM activity_log
                   WHERE user_id=%s AND entitas = ANY(%s) ORDER BY entitas, entitas_id, waktu DESC""",
                (user["id"], list(TARGET)))
acts = sorted(acts, key=lambda a: a["waktu"], reverse=True)[:2]
if acts:
    cols = st.columns([1.2, 3, 3, 1.1])
    cols[0].markdown("<div style='padding-top:.4rem'><b style='color:#1d4ed8'>Lanjutkan aktivitas terakhir:</b></div>", unsafe_allow_html=True)
    for c, a in zip(cols[1:3], acts):
        c.markdown(f"{ui.esc(a['label'])}  \n<span class='kh-note'>{a['waktu']:%d %b %H.%M}</span>", unsafe_allow_html=True)
    page, key = TARGET[acts[0]["entitas"]]
    if can(role, "campaign.edit") or acts[0]["entitas"] in ("ro", "kol"):
        if cols[3].button("Buka", type="primary", use_container_width=True):
            ui.go(page, **{key: int(acts[0]["entitas_id"])})

ui.header("Dashboard Digital Marketing" if role != "store" else "Dashboard Toko",
          "Ringkasan kerja harian · data contoh" if role != "finance" else "Ringkasan untuk Finance")
f = ui.global_filters(user)
sids = f["store_ids"]
start, end = f["start"], f["end"]

# ---------------------------------------------------------------- KPI
t = A.traffic_daily()
tp = t[(t["store_id"].isin(sids)) & (t["tanggal"].dt.date >= start) & (t["tanggal"].dt.date <= end)]
traffic = tp["kunjungan"].sum()
op = db.df("SELECT platform, views FROM official_posts WHERE tanggal::date BETWEEN %s AND %s", (start, end))
kp = db.df("""SELECT k.platform, m.views FROM posts p JOIN kol_accounts k ON k.id=p.kol_id
              JOIN submission_items i ON i.id=p.item_id
              JOIN LATERAL (SELECT views FROM post_metrics pm WHERE pm.post_id=p.id ORDER BY (sumber='api') DESC, diukur_pada DESC LIMIT 1) m ON TRUE
              WHERE p.tanggal_tayang::date BETWEEN %s AND %s AND i.store_id = ANY(%s)""", (start, end, sids))
views = pd.concat([op, kp]) if not op.empty or not kp.empty else pd.DataFrame(columns=["platform", "views"])
v_ig = views.loc[views["platform"] == "Instagram", "views"].sum()
v_tt = views.loc[views["platform"] == "TikTok", "views"].sum()
lifts = A.item_lifts()
lp = lifts[(lifts["tanggal"].dt.date >= start - timedelta(days=14)) & (lifts["tanggal"].dt.date <= end) & lifts["store_id"].isin(sids)] \
    if not lifts.empty else lifts
dampak = (lp.drop_duplicates(["store_id", "tanggal"])["lift"].mean() * 100) if not lp.empty else None
cm = A.comments_nlp(start, end, store_ids=tuple(sids) if not f["all"] else None)
s_all, s_ig, s_tt = A.sentiment_summary(cm), A.sentiment_summary(cm[cm["platform"] == "Instagram"] if not cm.empty else cm), \
    A.sentiment_summary(cm[cm["platform"] == "TikTok"] if not cm.empty else cm)
pay = db.df("""SELECT p.nominal, p.status, p.created_at, i.store_id FROM payments p JOIN submission_items i ON i.id=p.item_id
               WHERE p.status <> 'lunas' AND i.store_id = ANY(%s)""", (sids,))
pending = pay["nominal"].sum() if not pay.empty else 0
lama = int(((pd.Timestamp.now(tz="UTC") - pd.to_datetime(pay["created_at"], utc=True)).dt.days > 30).sum()) if not pay.empty else 0

items = [
    {"label": "Views online", "value": F.angka(v_ig + v_tt), "sub": f"IG {F.angka(v_ig)} · TikTok {F.angka(v_tt)}"},
    {"label": "Traffic offline", "value": F.angka(traffic), "sub": f"kunjungan {len(sids)} toko"},
    {"label": "Dampak online → offline", "value": F.persen(dampak, tanda=True) if dampak is not None else "—",
     "sub": "toko ber-campaign vs pembanding" if dampak is not None else "belum ada campaign tayang", "tone": "pos", "highlight": True},
    {"label": "Sentimen netto komentar", "value": f"{s_all['net']:+.0f}",
     "sub": f"IG {s_ig['net']:+.0f} · TikTok {s_tt['net']:+.0f} · {F.angka(s_all['n'], False)} komentar"},
    {"label": "Pembayaran tertunda", "value": F.rupiah(pending), "sub": f"{lama} > 30 hari" if lama else "tidak ada > 30 hari",
     "sub_tone": "neg" if lama else ""},
]
if role == "finance":
    items = [items[1], items[4]]
ui.kpis(items)
st.write("")

if role == "finance":
    st.markdown("#### Ringkasan pembayaran")
    summ = db.df("""SELECT p.status, COUNT(*) AS baris, SUM(p.nominal) AS nominal FROM payments p GROUP BY p.status ORDER BY 1""")
    st.dataframe(summ, hide_index=True, use_container_width=True,
                 column_config={"nominal": st.column_config.NumberColumn("Nominal", format="Rp %d")})
    if st.button("Buka menu Pembayaran & Pajak", type="primary"):
        st.switch_page("views/pembayaran.py")
    st.stop()

# ---------------------------------------------------------------- toko butuh KOL + sentimen + konten
left, right = st.columns([1.55, 1], gap="medium")
with left:
    st.markdown("#### ✦ Toko yang membutuhkan KOL / Portal News")
    needs = A.store_needs()
    nd = needs[needs["store_id"].isin(sids)].head(8 if not f["single_store"] else 1)
    if nd.empty:
        st.info("Belum ada data traffic untuk toko terpilih.")
    else:
        show = pd.DataFrame({
            "Toko": nd["toko"], "Zona": nd["zona"], "Traffic 4 mgg": nd["traffic_4mgg"].map(F.angka),
            "vs forecast": nd["vs_forecast"].map(lambda x: F.persen(x, tanda=True)),
            "Campaign trkhr": nd["hari_sejak"].map(lambda h: "Belum pernah" if h >= 365 else f"{int(h)} hari lalu"),
            "Skor butuh": nd["skor"], "Saran": nd["saran"]})
        st.dataframe(show, hide_index=True, use_container_width=True, column_config={
            "Skor butuh": st.column_config.ProgressColumn("Skor butuh", min_value=0, max_value=100, format="%d")})
        ui.note("Skor butuh = penurunan traffic vs forecast + lama tanpa campaign + respons historis toko + selisih ke target "
                "(rumus B.6 no. 9).")
        if role in ("ecommerce", "super_user"):
            pick = st.selectbox("Lihat KOL yang disarankan untuk toko", nd["toko"], key="dash_pick")
            if st.button("Buka mapping toko", icon=":material/map:"):
                ui.go("views/mapping.py", sel_store=int(nd[nd["toko"] == pick]["store_id"].iloc[0]))

with right:
    st.markdown("#### Sentimen komentar akun resmi")
    for name, s in (("Instagram @mitra10official", s_ig), ("TikTok @mitra10official", s_tt)):
        st.markdown(f"<span class='kh-note'>{name} · netto {s['net']:+.0f}</span>", unsafe_allow_html=True)
        ui.sentiment_bar(s["pos"], s["neu"], s["neg"])
    spikes = A.topic_spikes(cm) if not cm.empty else pd.DataFrame()
    isu = spikes[(spikes["jenis"] == "isu")] if not spikes.empty else spikes
    if not isu.empty:
        top = isu.iloc[0]
        st.markdown(f"<span class='kh-note'>Positif · Netral · Negatif — isu teratas: </span>"
                    f"<b style='color:#dc2626'>{ui.esc(top['topik'].lower())} ({top['platform']})</b>"
                    + (" " + ui.badge("lonjakan", "red") if top["lonjakan"] else ""), unsafe_allow_html=True)

    st.markdown("#### Konten terbaik periode ini")
    best = db.df("""SELECT platform, judul, jenis_konten, durasi_detik, views, likes, komentar, share, save FROM official_posts
                    WHERE tanggal::date BETWEEN %s AND %s""", (start, end))
    if best.empty:
        st.caption("Belum ada konten di periode ini.")
    else:
        best["skor_konten"] = [F.content_score(r.likes, r.komentar, r.share, r.save, r.views) for r in best.itertuples()]
        top = best.sort_values("views", ascending=False).head(3)
        st.dataframe(pd.DataFrame({"Konten": (top["platform"].map({"Instagram": "IG", "TikTok": "TT"}) + " · " + top["judul"]),
                                   "Views": top["views"].map(F.angka), "Likes": top["likes"].map(F.angka),
                                   "Komen": top["komentar"].map(lambda x: F.angka(x, False)), "Repost": top["share"].map(lambda x: F.angka(x, False))}),
                     hide_index=True, use_container_width=True)
        tut = best[(best["jenis_konten"] == "tutorial") & (best["durasi_detik"] < 45)]
        other = best.drop(tut.index)
        if len(tut) >= 2 and len(other) >= 2:
            ratio = tut["views"].median() / max(other["views"].median(), 1)
            ui.note(f"✦ Format tutorial < 45 detik {'unggul' if ratio > 1 else 'kalah'} {ratio:.1f}× (median views) — "
                    f"{'disarankan untuk brief berikutnya' if ratio > 1.2 else 'belum ada format dominan'}.")
