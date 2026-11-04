"""Layar 15 — Kalender Event: ongoing & historis, tersinkron promo offline; saran waktu posting (rumus 14)."""
import calendar
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from lib import auth, db, ui
from lib import formulas as F
from lib.rbac import can, require

user = auth.current_user()
require(user["role"], "calendar.view")
ui.header("Kalender Event", "Jadwal posting KOL (banyak KOL per tanggal) tersinkron dengan promo offline toko")
ui.flash()

today = date.today()
c1, c2, _ = st.columns([1, 1, 2])
months = [(today.replace(day=1) + pd.DateOffset(months=k)).date() for k in range(-6, 4)]
m = c1.selectbox("Bulan", months, index=6, format_func=lambda d: d.strftime("%B %Y"))
zsel = c2.selectbox("Zona", ["Semua"] + list(ui.zones()["nama"]), key="cal_zone") if user["role"] != "store" else None
first = m
last = (pd.Timestamp(m) + pd.offsets.MonthEnd(0)).date()

params = [first, last]
scope = ""
if user["role"] == "store":
    scope = " AND i.store_id = %s"
    params.append(user.get("scope_store_id") or -1)
elif zsel and zsel != "Semua":
    scope = " AND z.nama = %s"
    params.append(zsel)
posts = db.df(f"""SELECT i.id, i.tanggal_posting AS tgl, k.username, k.platform, st.id AS store_id, st.nama AS toko, z.nama AS zona,
                         s.status, s.no_pengajuan, COALESCE(c.nama, 'Tunggal') AS campaign, c.periode_mulai, c.periode_selesai,
                         p.tanggal_tayang
                  FROM submission_items i JOIN submissions s ON s.id=i.submission_id LEFT JOIN campaigns c ON c.id=s.campaign_id
                  JOIN kol_accounts k ON k.id=i.kol_id JOIN stores st ON st.id=i.store_id JOIN zones z ON z.id=st.zone_id
                  LEFT JOIN posts p ON p.item_id=i.id
                  WHERE i.aktif AND i.tanggal_posting BETWEEN %s AND %s AND s.status NOT IN ('Ditolak'){scope}""", params)
ev = db.df("""SELECT e.nama, e.mulai, e.selesai, e.store_id, e.zone_id, st.nama AS toko, z.nama AS zona FROM promo_offline_events e
              LEFT JOIN stores st ON st.id=e.store_id LEFT JOIN zones z ON z.id=e.zone_id
              WHERE e.mulai <= %s AND e.selesai >= %s""", (last, first))

by_day = defaultdict(list)
for r in posts.itertuples():
    by_day[r.tgl].append(r)
ev_day = defaultdict(list)
for e in ev.itertuples():
    d = max(e.mulai, first)
    while d <= min(e.selesai, last):
        ev_day[d].append(e)
        d += timedelta(days=1)

# ---------------------------------------------------------------- peringatan bentrok
conflicts = []
for d, lst in by_day.items():
    per_store = defaultdict(list)
    for r in lst:
        per_store[r.toko].append(r.username)
    for t, us in per_store.items():
        if len(us) > 1:
            conflicts.append(f"{d:%d %b}: {len(us)} KOL tayang di {t} pada hari sama ({', '.join(us)})")
    for r in lst:
        if pd.notna(r.periode_mulai) and not (r.periode_mulai <= d <= r.periode_selesai):
            conflicts.append(f"{d:%d %b}: {r.username} tayang di luar periode campaign {r.campaign}")

# ---------------------------------------------------------------- grid bulan
cal = calendar.Calendar(firstweekday=0)
html = ["<table style='width:100%;border-collapse:collapse;table-layout:fixed'><tr>" +
        "".join(f"<th style='padding:.3rem;color:#64748b;font-weight:600;text-align:left'>{h}</th>" for h in ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]) + "</tr>"]
for week in cal.monthdatescalendar(m.year, m.month):
    html.append("<tr>")
    for d in week:
        out = d.month != m.month
        bg = "#f8fafc" if out else ("#eef3ff" if d == today else "#fff")
        cell = [f"<div style='font-weight:700;color:{'#cbd5e1' if out else '#0f172a'}'>{d.day}</div>"]
        if not out:
            for e in ev_day.get(d, [])[:2]:
                cell.append(f"<div class='kh-badge kh-b-amber' style='display:block;margin:.1rem 0;white-space:normal'>🏷 {ui.esc(e.nama)}</div>")
            for r in by_day.get(d, [])[:4]:
                tone = "green" if pd.notna(r.tanggal_tayang) else "blue" if r.status not in ("Draft", "Review Asisten Manager", "Review Manager", "Revisi") else "gray"
                cell.append(f"<div class='kh-badge kh-b-{tone}' style='display:block;margin:.1rem 0;white-space:normal'>{ui.esc(r.username)} · {ui.esc(r.toko.replace('Mitra10 ', ''))}</div>")
            if len(by_day.get(d, [])) > 4:
                cell.append(f"<div class='kh-note'>+{len(by_day[d]) - 4} lainnya</div>")
        html.append(f"<td style='vertical-align:top;border:1px solid #e5e9f2;padding:.35rem;height:96px;background:{bg}'>{''.join(cell)}</td>")
    html.append("</tr>")
html.append("</table>")
st.markdown("".join(html), unsafe_allow_html=True)
ui.note("Hijau = sudah tayang · biru = disetujui/terjadwal · abu = draft/menunggu approval · kuning = promo offline toko.")

left, right = st.columns(2, gap="medium")
with left:
    st.markdown("#### Peringatan bentrok")
    if conflicts:
        st.warning("\n".join(f"- {c}" for c in conflicts))
    else:
        st.success("Tidak ada bentrok jadwal bulan ini.")
    st.markdown("#### Promo offline bulan ini")
    if ev.empty:
        st.caption("Tidak ada promo offline.")
    else:
        st.dataframe(ev.assign(cakupan=ev["toko"].fillna(ev["zona"]).fillna("Semua toko"))[["nama", "mulai", "selesai", "cakupan"]],
                     hide_index=True, use_container_width=True)
    if can(user["role"], "calendar.edit"):
        with st.expander("Tambah promo offline"):
            with st.form("ev"):
                nama = st.text_input("Nama promo")
                a, b = st.columns(2)
                mulai = a.date_input("Mulai", today)
                selesai = b.date_input("Selesai", today + timedelta(days=3))
                stores, zones = ui.stores(), ui.zones()
                cak = st.selectbox("Cakupan", ["Semua toko"] + ["Zona: " + z for z in zones["nama"]] + list(stores["nama"]))
                ok = st.form_submit_button("Simpan")
            if ok and nama:
                sid = int(stores[stores["nama"] == cak]["id"].iloc[0]) if cak in set(stores["nama"]) else None
                zid = int(zones[zones["nama"] == cak[6:]]["id"].iloc[0]) if cak.startswith("Zona: ") else None
                db.execute("INSERT INTO promo_offline_events (nama, store_id, zone_id, mulai, selesai) VALUES (%s,%s,%s,%s,%s)",
                           (nama, sid, zid, mulai, selesai))
                auth.log_activity(user["id"], "tambah_promo", "promo", None, f"Promo offline {nama}")
                st.cache_data.clear()
                st.rerun()

with right:
    st.markdown("#### Saran waktu posting")
    data = db.df("""SELECT platform, EXTRACT(ISODOW FROM tanggal) AS dow, EXTRACT(HOUR FROM tanggal AT TIME ZONE 'Asia/Jakarta') AS jam,
                           views, likes + komentar + share + save AS interaksi FROM official_posts
                    UNION ALL
                    SELECT p.platform, EXTRACT(ISODOW FROM p.tanggal_tayang), EXTRACT(HOUR FROM p.tanggal_tayang AT TIME ZONE 'Asia/Jakarta'),
                           m.views, m.likes + m.komentar + m.share + m.save FROM posts p
                    JOIN LATERAL (SELECT * FROM post_metrics pm WHERE pm.post_id=p.id ORDER BY (sumber='api') DESC LIMIT 1) m ON TRUE
                    WHERE p.tanggal_tayang IS NOT NULL""")
    hari = {1: "Senin", 2: "Selasa", 3: "Rabu", 4: "Kamis", 5: "Jumat", 6: "Sabtu", 7: "Minggu"}
    for plat in ("TikTok", "Instagram"):
        d = data[data["platform"] == plat]
        if d.empty:
            continue
        d = d.assign(slot=d["jam"].astype(int).map(lambda h: 9 if h < 11 else 12 if h < 15 else 17 if h < 19 else 19 if h < 21 else 21))
        agg = d.groupby(["dow", "slot"]).agg(i=("interaksi", "sum"), v=("views", "sum")).reset_index()
        slots = {(hari[int(r.dow)], int(r.slot)): (float(r.i), float(r.v)) for r in agg.itertuples()}
        best = F.best_posting_slots(slots)[:3]
        st.markdown(f"**{plat}:** " + " · ".join(f"{d_} {h:02d}.00 ({p * 100:.1f}% ER posterior)" for (d_, h), p in best))
    upcoming = db.df("SELECT nama, mulai FROM promo_offline_events WHERE mulai >= CURRENT_DATE ORDER BY mulai LIMIT 3")
    for e in upcoming.itertuples():
        st.markdown(f"- Promo **{ui.esc(e.nama)}** mulai {e.mulai:%d %b}: jadwalkan tayang {e.mulai - timedelta(days=3):%d}–{e.mulai - timedelta(days=1):%d %b} "
                    "agar audiens datang saat promo berlangsung.")
    ui.note("Rata-rata posterior Beta per slot hari × jam: α = 1 + Σ interaksi, β = 1 + Σ(views − interaksi) (rumus B.6 no. 14).")

if can(user["role"], "calendar.edit") and not posts.empty:
    with st.expander("Jadwalkan ulang posting"):
        pend = posts[posts["tanggal_tayang"].isna()]
        if pend.empty:
            st.caption("Semua posting bulan ini sudah tayang.")
        else:
            lab = (pend["username"] + " · " + pend["toko"] + " · " + pend["tgl"].astype(str)).tolist()
            i = st.selectbox("Posting", range(len(pend)), format_func=lambda k: lab[k])
            nd = st.date_input("Tanggal baru", pend.iloc[i]["tgl"])
            if st.button("Simpan jadwal"):
                iid = int(pend.iloc[i]["id"])
                db.execute("UPDATE submission_items SET tanggal_posting=%s WHERE id=%s", (nd, iid))
                db.execute("""UPDATE production_tasks t SET mulai = t.mulai + (%s::date - %s::date), selesai = t.selesai + (%s::date - %s::date)
                              WHERE item_id=%s AND status <> 'selesai'""", (nd, pend.iloc[i]["tgl"], nd, pend.iloc[i]["tgl"], iid))
                auth.log_activity(user["id"], "jadwal_ulang", "item", iid, f"Jadwal {lab[i]} → {nd}")
                st.cache_data.clear()
                st.rerun()
