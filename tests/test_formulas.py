"""Unit test rumus — angka contoh diambil dari Spesifikasi B.6."""
import math

import pytest

from lib import formulas as F


def test_er_and_shrinkage():
    assert F.engagement_rate(80, 10, 5, 5, 1000) == pytest.approx(10.0)
    # (1×9 + 3×4,5)/4 = 5,6%
    assert F.er_adjusted(1, 9.0, 4.5) == pytest.approx(5.625)


def test_time_weighted_median_prefers_recent():
    v = F.time_weighted_median([100, 200, 300], [720, 360, 0])
    assert v == 300


def test_price_suggestion_rumahminimalis():
    p = F.suggest_price(64_000, 168_000, 180_000)
    assert p.wajar == pytest.approx(10_752_000)       # ≈ Rp 10,8 jt
    assert p.batas_atas == pytest.approx(11_520_000)  # Rp 11,5 jt


def test_price_increase_gap():
    g = F.price_increase_gap(5_000_000, 12_500_000, 100, 162)
    assert g["delta_ratecard"] == pytest.approx(150)
    assert g["gap"] == pytest.approx(88)
    assert g["flag"] is True


def test_kol_score_example():
    s = F.kol_score(94, 90, 78, 96, 100)
    assert s["skor"] == pytest.approx(92.48)
    assert s["skor_bulat"] == 92
    assert s["label"] == "Rekomendasi"


def test_kol_score_without_D_redistributes_weight():
    s = F.kol_score(80, 80, 80, 80, None)
    assert s["skor"] == pytest.approx(80)
    assert sum(s["bobot"].values()) == pytest.approx(1.0)


def test_kol_score_penalties_and_labels():
    s = F.kol_score(70, 70, 70, 70, 70, telat=2, sentimen_negatif_dominan=True)
    assert s["skor"] == pytest.approx(70 - 6 - 5)
    assert F.score_label(64) == "Evaluasi" and F.score_label(49) == "Tidak disarankan" and F.score_label(65) == "Layak"


def test_did_cibubur_example():
    r = F.did_ratio(33_400, 41_200, 100, 101.8)
    assert r["counterfactual"] == pytest.approx(34_001, abs=1)
    assert r["kunjungan_tambahan"] == pytest.approx(7_199, abs=2)
    assert r["lift"] == pytest.approx(0.212, abs=0.001)
    assert F.cpiv(22_300_000, r["kunjungan_tambahan"]) == pytest.approx(3_098, abs=5)


def test_did_interval_and_placebo():
    store_pre = [1000, 1010, 990, 1005]
    store_post = [1200, 1210]
    comp_pre = [2000, 2020, 1980, 2010]
    comp_post = [2010, 2000]
    r = F.did_interval(store_pre, store_post, comp_pre, comp_post, n_boot=300)
    assert r["lift_low"] > 0 and r["signifikan"]
    flat_s = [1000 + (i % 3) * 5 for i in range(16)]
    flat_c = [2000 + (i % 2) * 8 for i in range(16)]
    pl = F.placebo_test(flat_s, flat_c, n_boot=100)
    assert pl["uji"] > 0


def test_store_need_mapping_ordering():
    rows = [
        {"store_id": 1, "penurunan_pct": 9.8, "hari_sejak": 94, "responsivitas": 0.15, "selisih_target": 8},
        {"store_id": 2, "penurunan_pct": -2.0, "hari_sejak": 10, "responsivitas": 0.02, "selisih_target": -3},
        {"store_id": 3, "penurunan_pct": 1.0, "hari_sejak": 40, "responsivitas": 0.05, "selisih_target": 0},
    ]
    out = {r["store_id"]: r["skor"] for r in F.store_need_scores(rows)}
    assert out[1] > out[3] > out[2]
    assert all(0 <= v <= 100 for v in out.values())


def test_rank_and_mmr():
    import random
    r = F.rank_kol_store(0.58, 92, 0.17, 0.5)
    assert 0 < r["rank"] <= 1 and not r["thompson"]
    t = F.rank_kol_store(0.5, 70, None, 0.5, rng=random.Random(1))
    assert t["thompson"]
    a = {"rank": 0.9, "audiens": {"Bekasi": 0.7, "Jakarta Timur": 0.3}}
    b = {"rank": 0.8, "audiens": {"Bekasi": 0.65, "Jakarta Timur": 0.35}}
    c = {"rank": 0.7, "audiens": {"Bandung": 0.8, "Bekasi": 0.2}}
    picked = F.mmr_diversify([a, b, c])
    assert a in picked and b not in picked and c in picked


def test_zone_budget_minimum_5pct():
    res = F.zone_budget(100_000_000, {"A": (90, 0.2), "B": (80, 0.2), "C": (1, 0.01)})
    assert sum(res.values()) == pytest.approx(100_000_000)
    assert res["C"] == pytest.approx(5_000_000)


def test_sentiment_and_spike():
    assert F.net_sentiment(58, 10, 100) == pytest.approx(48)
    assert F.net_sentiment(51, 14, 100) == pytest.approx(37)
    hist = [10, 12, 11, 9, 10, 11, 10] * 4
    assert F.robust_spike_z(40, hist) > 3
    assert F.robust_spike_z(11, hist) < 3
    assert F.content_score(100, 10, 5, 5, 1000) == pytest.approx((100 + 20 + 15 + 10) / 1000)


def test_posting_slots():
    slots = {("Sab", 19): (500, 5000), ("Sen", 9): (50, 5000)}
    best = F.best_posting_slots(slots)
    assert best[0][0] == ("Sab", 19)


def test_tax_rules():
    rules = {"PPh21": {"tarif": 0.05, "dasar": 0.5, "tarif_tanpa_npwp": 0.06},
             "PPh23": {"tarif": 0.02, "dasar": 1.0, "tarif_tanpa_npwp": 0.04}}
    assert F.tax_amount(10_000_000, False, True, rules)["pajak"] == 250_000
    assert F.tax_amount(10_000_000, True, True, rules)["pajak"] == 200_000
    assert F.tax_amount(10_000_000, True, False, rules)["pajak"] == 400_000


def test_saturation_curve():
    assert F.saturation(1, 100) == pytest.approx(50)
    assert F.saturation(2, 100) - F.saturation(1, 100) < F.saturation(1, 100)


def test_format():
    assert F.rupiah(10_750_000) == "Rp 10,8 jt"
    assert F.rupiah(3100) == "Rp 3.100"
    assert F.angka(1_240_000) == "1,24 jt"
    assert F.persen(21.2, tanda=True) == "+21,2%"
    assert F.percentile_rank(5, [1, 2, 3, 4, 5]) == pytest.approx(90)
    assert not math.isnan(F.percentile_rank(1, []))
