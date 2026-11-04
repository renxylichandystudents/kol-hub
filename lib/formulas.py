"""Rumus inti — Spesifikasi Bagian B.6 (nomor rumus di docstring).

Semua fungsi murni (tanpa database) agar dapat diuji unit (C.9).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import median
from typing import Iterable, Sequence


# ---------------------------------------------------------------- helpers
def _safe_div(a: float, b: float) -> float | None:
    return None if not b else a / b


def percentile_rank(value: float, population: Sequence[float]) -> float:
    """Persentil (0–100) sebuah nilai dalam populasi (midrank)."""
    pop = [p for p in population if p is not None and not (isinstance(p, float) and math.isnan(p))]
    if not pop or value is None:
        return 50.0
    below = sum(1 for p in pop if p < value)
    equal = sum(1 for p in pop if p == value)
    return 100.0 * (below + 0.5 * equal) / len(pop)


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def zscores(values: Sequence[float]) -> list[float]:
    vals = [float(v) for v in values]
    if len(vals) < 2:
        return [0.0] * len(vals)
    mu = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / (len(vals) - 1))
    return [0.0 if sd == 0 else (v - mu) / sd for v in vals]


# ---------------------------------------------------------------- 1–3
def engagement_rate(likes: float, komentar: float, share: float, save: float, views: float) -> float | None:
    """(1) ER = (likes + komentar + share + save) / views × 100%."""
    r = _safe_div((likes or 0) + (komentar or 0) + (share or 0) + (save or 0), views or 0)
    return None if r is None else r * 100


def er_adjusted(n: int, er_kol: float, er_kategori: float, k: int = 3) -> float:
    """(2) Empirical Bayes shrinkage: (n·ER_kol + k·ER_kategori) / (n + k)."""
    return (n * er_kol + k * er_kategori) / (n + k)


def time_weighted_median(values: Sequence[float], ages_days: Sequence[float], half_life: float = 180) -> float | None:
    """(3) V̂ = median tertimbang waktu, wᵢ = 0,5^(umur/180)."""
    pairs = sorted((v, 0.5 ** (a / half_life)) for v, a in zip(values, ages_days) if v is not None)
    if not pairs:
        return None
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= total / 2:
            return v
    return pairs[-1][0]


def weighted_quantile(values: Sequence[float], ages_days: Sequence[float], q: float, half_life: float = 180) -> float | None:
    """Kuantil tertimbang waktu (dipakai untuk V̂q20/q50/q80)."""
    pairs = sorted((v, 0.5 ** (a / half_life)) for v, a in zip(values, ages_days) if v is not None)
    if not pairs:
        return None
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= total * q:
            return v
    return pairs[-1][0]


# ---------------------------------------------------------------- 4–6
def cpm(biaya: float, views: float) -> float | None:
    """(4) CPM = biaya / views × 1.000."""
    r = _safe_div(biaya, views)
    return None if r is None else r * 1000


def cpiv(biaya: float, kunjungan_tambahan: float) -> float | None:
    """(4) CPIV = biaya / kunjungan toko tambahan."""
    if not kunjungan_tambahan or kunjungan_tambahan <= 0:
        return None
    return biaya / kunjungan_tambahan


@dataclass
class PriceSuggestion:
    wajar: float
    batas_atas: float


def suggest_price(cpm_target: float, v_q50: float, v_q80: float) -> PriceSuggestion:
    """(5) Harga wajar = CPM_target × V̂q50 / 1.000 ; batas atas pakai V̂q80."""
    return PriceSuggestion(cpm_target * v_q50 / 1000, cpm_target * v_q80 / 1000)


def price_increase_gap(ratecard_lama: float, ratecard_baru: float, views_lama: float, views_baru: float) -> dict:
    """(6) Gap = Δ%ratecard − Δ%V̂ ; tandai bila Gap > 20 poin."""
    d_rc = (ratecard_baru / ratecard_lama - 1) * 100 if ratecard_lama else 0.0
    d_v = (views_baru / views_lama - 1) * 100 if views_lama else 0.0
    gap = d_rc - d_v
    return {"delta_ratecard": d_rc, "delta_views": d_v, "gap": gap, "flag": gap > 20}


# ---------------------------------------------------------------- 7 skor KOL
WEIGHTS = {"E": 0.24, "K": 0.16, "C": 0.16, "R": 0.24, "D": 0.20}


def consistency(views: Sequence[float]) -> float | None:
    """K mentah = 1 − koefisien variasi views."""
    v = [x for x in views if x is not None]
    if len(v) < 2:
        return None
    mu = sum(v) / len(v)
    if mu == 0:
        return None
    sd = math.sqrt(sum((x - mu) ** 2 for x in v) / (len(v) - 1))
    return 1 - sd / mu


def kol_score(E: float, K: float, C: float, R: float, D: float | None = None,
              telat: int = 0, sentimen_negatif_dominan: bool = False,
              bukti_tidak_lengkap: int = 0) -> dict:
    """(7) Skor = 0,24·E + 0,16·K + 0,16·C + 0,24·R + 0,20·D − penalti.

    Bila D belum ada, bobot D dibagi rata ke empat komponen lain.
    Penalti: telat tayang −3/kejadian, sentimen negatif dominan −5, bukti tidak lengkap −5 (per kejadian).
    """
    w = dict(WEIGHTS)
    comps = {"E": E, "K": K, "C": C, "R": R, "D": D}
    if D is None:
        extra = w.pop("D") / 4
        for key in w:
            w[key] += extra
        comps.pop("D")
    kontribusi = {key: w[key] * comps[key] for key in w}
    base = sum(kontribusi.values())
    penalti = 3 * telat + (5 if sentimen_negatif_dominan else 0) + 5 * bukti_tidak_lengkap
    skor = max(0.0, min(100.0, base - penalti))
    return {"skor": skor, "skor_bulat": int(round(skor)),
            "kontribusi": kontribusi, "penalti": penalti, "bobot": w, "label": score_label(skor)}


def score_label(skor: float) -> str:
    if skor >= 80:
        return "Rekomendasi"
    if skor >= 65:
        return "Layak"
    if skor >= 50:
        return "Evaluasi"
    return "Tidak disarankan"


# ---------------------------------------------------------------- 8 DiD
def did_ratio(store_pre: float, store_post: float, comp_pre: float, comp_post: float) -> dict:
    """(8) Counterfactual = Ȳ_toko,pre × (Ȳ_pembanding,post / Ȳ_pembanding,pre)."""
    cf = store_pre * (comp_post / comp_pre) if comp_pre else store_pre
    extra = store_post - cf
    lift = store_post / cf - 1 if cf else 0.0
    return {"counterfactual": cf, "kunjungan_tambahan": extra, "lift": lift}


def did_interval(store_pre: Sequence[float], store_post: Sequence[float],
                 comp_pre: Sequence[float], comp_post: Sequence[float],
                 n_boot: int = 500, level: float = 0.90, seed: int = 7) -> dict:
    """Bootstrap interval untuk lift DiD (resample minggu)."""
    rng = random.Random(seed)
    base = did_ratio(_m(store_pre), _m(store_post), _m(comp_pre), _m(comp_post))
    lifts, extras = [], []
    for _ in range(n_boot):
        sp = [rng.choice(store_pre) for _ in store_pre]
        so = [rng.choice(store_post) for _ in store_post]
        cp = [rng.choice(comp_pre) for _ in comp_pre]
        co = [rng.choice(comp_post) for _ in comp_post]
        r = did_ratio(_m(sp), _m(so), _m(cp), _m(co))
        lifts.append(r["lift"])
        extras.append(r["kunjungan_tambahan"])
    lo_q, hi_q = (1 - level) / 2, 1 - (1 - level) / 2
    lifts.sort(); extras.sort()
    base.update({
        "lift_low": lifts[int(lo_q * (n_boot - 1))], "lift_high": lifts[int(hi_q * (n_boot - 1))],
        "extra_low": extras[int(lo_q * (n_boot - 1))], "extra_high": extras[int(hi_q * (n_boot - 1))],
    })
    base["signifikan"] = base["lift_low"] > 0 or base["lift_high"] < 0
    return base


def placebo_test(store_weekly: Sequence[float], comp_weekly: Sequence[float], window: int = 2,
                 n_boot: int = 200) -> dict:
    """Uji plasebo: ulang DiD pada minggu tanpa campaign; % yang 'signifikan' seharusnya ≤ 10%."""
    hits, total = 0, 0
    for t in range(window * 2, len(store_weekly) - window + 1):
        pre = slice(t - window * 2, t)
        post = slice(t, t + window)
        r = did_interval(store_weekly[pre], store_weekly[post], comp_weekly[pre], comp_weekly[post], n_boot=n_boot)
        total += 1
        hits += 1 if r["signifikan"] else 0
    return {"uji": total, "signifikan": hits, "rasio": hits / total if total else 0.0}


def _m(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


# ---------------------------------------------------------------- 9 kebutuhan toko
def store_need_scores(rows: list[dict]) -> list[dict]:
    """(9) Butuh = 0,35·z(penurunan vs forecast) + 0,25·z(hari sejak campaign)
       + 0,25·z(responsivitas) + 0,15·z(selisih ke target) − penalti saturasi; dipetakan 0–100.

    rows: {store_id, penurunan_pct (positif = turun), hari_sejak, responsivitas, selisih_target, campaign_30hr}
    """
    if not rows:
        return []
    zp = zscores([r["penurunan_pct"] for r in rows])
    zh = zscores([min(r["hari_sejak"], 365) for r in rows])
    zr = zscores([r["responsivitas"] for r in rows])
    zt = zscores([r["selisih_target"] for r in rows])
    out = []
    for i, r in enumerate(rows):
        comp = 0.35 * zp[i] + 0.25 * zh[i] + 0.25 * zr[i] + 0.15 * zt[i]
        if r.get("campaign_30hr", 0) >= 2:
            comp -= 1.0
        skor = round(100 * norm_cdf(comp * 1.6))
        alasan = []
        if r["penurunan_pct"] > 2:
            alasan.append(f"traffic −{r['penurunan_pct']:.1f}% vs forecast")
        alasan.append("belum pernah campaign" if r["hari_sejak"] >= 365 else f"{int(r['hari_sejak'])} hari tanpa campaign")
        if r["responsivitas"] > 0.05:
            alasan.append(f"respons historis +{r['responsivitas'] * 100:.0f}%")
        out.append({**r, "komposit": comp, "skor": skor, "alasan": alasan})
    return out


# ---------------------------------------------------------------- 10 rekomendasi KOL × toko
def rank_kol_store(audiens_lokal: float, skor_kol: float, lift_hist: float | None,
                   kemiripan: float, rng: random.Random | None = None,
                   prior_a: float = 2.0, prior_b: float = 18.0) -> dict:
    """(10) Rank = 0,35·audiens_lokal + 0,25·skor/100 + 0,25·lift + 0,15·kemiripan.

    audiens_lokal & kemiripan dalam 0–1; lift dinormalisasi: lift 0,25 (=+25%) → 1.
    KOL tanpa histori: lift disampel dari Beta(a,b) (Thompson sampling).
    """
    thompson = False
    if lift_hist is None:
        rng = rng or random.Random()
        lift_hist = rng.betavariate(prior_a, prior_b)
        thompson = True
    lift_norm = max(0.0, min(1.0, lift_hist / 0.25))
    nilai = 0.35 * audiens_lokal + 0.25 * skor_kol / 100 + 0.25 * lift_norm + 0.15 * kemiripan
    return {"rank": nilai, "lift_dipakai": lift_hist, "thompson": thompson}


def audience_overlap(a: dict, b: dict) -> float:
    """Tumpang tindih audiens (Σ min proporsi kota)."""
    keys = set(a) | set(b)
    return sum(min(a.get(k, 0), b.get(k, 0)) for k in keys)


def mmr_diversify(candidates: list[dict], max_overlap: float = 0.60, k: int = 10) -> list[dict]:
    """Keberagaman: hindari > 1 KOL dengan audiens tumpang tindih > 60% di toko yang sama."""
    chosen: list[dict] = []
    for c in sorted(candidates, key=lambda x: -x["rank"]):
        if all(audience_overlap(c.get("audiens", {}), o.get("audiens", {})) <= max_overlap for o in chosen):
            chosen.append(c)
        if len(chosen) >= k:
            break
    return chosen


def saturation(n: int, beta: float, gamma: float = 1.0) -> float:
    """(11) Kurva jenuh f(n) = β · n / (n + γ)."""
    return beta * n / (n + gamma)


# ---------------------------------------------------------------- 12 budget zona
def zone_budget(budget: float, zones: dict[str, tuple[float, float]], minimal: float = 0.05) -> dict[str, float]:
    """(12) Budget_zona = Budget × (Butuh × Responsivitas) / Σ ; minimal 5% per zona aktif."""
    raw = {z: max(b, 0) * max(r, 0) for z, (b, r) in zones.items()}
    total = sum(raw.values())
    if total == 0:
        return {z: budget / len(zones) for z in zones}
    share = {z: v / total for z, v in raw.items()}
    # tegakkan minimal 5%: zona di bawah minimal dinaikkan, sisanya diskala ulang
    fixed = {z for z, s in share.items() if s < minimal}
    while True:
        rest = 1 - minimal * len(fixed)
        free_total = sum(share[z] for z in share if z not in fixed)
        new = {z: (minimal if z in fixed else share[z] / free_total * rest) for z in share}
        newly = {z for z, s in new.items() if s < minimal - 1e-12 and z not in fixed}
        if not newly:
            break
        fixed |= newly
    return {z: budget * s for z, s in new.items()}


# ---------------------------------------------------------------- 13 sentimen & isu
def net_sentiment(pos: int, neg: int, total: int) -> float:
    """(13) Sentimen netto = (positif − negatif) / total × 100."""
    return 0.0 if not total else (pos - neg) / total * 100


def robust_spike_z(today: float, history: Sequence[float]) -> float:
    """(13) z = (volume − median_28hr) / (1,4826 × MAD_28hr)."""
    h = list(history)[-28:]
    if not h:
        return 0.0
    med = median(h)
    mad = median([abs(x - med) for x in h])
    denom = 1.4826 * mad
    if denom == 0:
        denom = 1.0
    return (today - med) / denom


def content_score(likes: float, komentar: float, share: float, save: float, views: float) -> float | None:
    """(13) Skor konten = (likes + 2·komentar + 3·share + 2·save) / views."""
    return _safe_div((likes or 0) + 2 * (komentar or 0) + 3 * (share or 0) + 2 * (save or 0), views or 0)


# ---------------------------------------------------------------- 14 waktu posting
def best_posting_slots(slots: dict[tuple[str, int], tuple[float, float]], thompson: bool = False,
                       rng: random.Random | None = None) -> list[tuple[tuple[str, int], float]]:
    """(14) α = 1 + Σ interaksi ; β = 1 + Σ(views − interaksi) ; posterior = α/(α+β)."""
    rng = rng or random.Random(11)
    res = []
    for slot, (interaksi, views) in slots.items():
        a = 1 + interaksi
        b = 1 + max(views - interaksi, 0)
        res.append((slot, rng.betavariate(a, b) if thompson else a / (a + b)))
    return sorted(res, key=lambda x: -x[1])


# ---------------------------------------------------------------- 15 pajak
def tax_amount(bruto: float, badan_hukum: bool, punya_npwp: bool, rules: dict) -> dict:
    """(15) Perorangan: PPh 21 = tarif × (dasar × bruto); Badan: PPh 23 = tarif × bruto.

    rules: {'PPh21': {'tarif', 'dasar', 'tarif_tanpa_npwp'}, 'PPh23': {...}} — dari tabel tax_rules.
    """
    jenis = "PPh23" if badan_hukum else "PPh21"
    r = rules[jenis]
    tarif = r["tarif"] if punya_npwp or not r.get("tarif_tanpa_npwp") else r["tarif_tanpa_npwp"]
    dasar = r.get("dasar", 1.0)
    pajak = round(tarif * dasar * bruto)
    return {"jenis": jenis, "tarif": tarif, "dasar": dasar, "pajak": pajak, "neto": bruto - pajak}


# ---------------------------------------------------------------- format
def rupiah(x: float | None, singkat: bool = True) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    x = float(x)
    if singkat and abs(x) >= 1e9:
        return f"Rp {x / 1e9:,.2f} M".replace(",", "#").replace(".", ",").replace("#", ".")
    if singkat and abs(x) >= 1e6:
        return f"Rp {x / 1e6:,.1f} jt".replace(",", "#").replace(".", ",").replace("#", ".")
    return f"Rp {x:,.0f}".replace(",", ".")


def angka(x: float | None, singkat: bool = True) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    x = float(x)
    if singkat and abs(x) >= 1e6:
        return f"{x / 1e6:,.2f} jt".replace(",", "#").replace(".", ",").replace("#", ".")
    if singkat and abs(x) >= 1e3:
        return f"{x / 1e3:,.1f} rb".replace(",", "#").replace(".", ",").replace("#", ".")
    return f"{x:,.0f}".replace(",", ".")


def persen(x: float | None, desimal: int = 1, tanda: bool = False) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    s = f"{x:+.{desimal}f}%" if tanda else f"{x:.{desimal}f}%"
    return s.replace(".", ",")
