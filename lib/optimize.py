"""Alokasi budget & pemilihan KOL — Spesifikasi B.6 no. 11.

Maksimalkan Σ xᵢ · Ê[kunjungan tambahanᵢ]
  dengan  Σ xᵢ · hargaᵢ ≤ Budget
          Σ xᵢ = jumlah KOL
          setiap toko terpilih ≥ 1 KOL
          porsi zona di antara min–maks
          xᵢ = 0 bila diblokir atau skor < 50 ; xᵢ ∈ {0,1}
Kurva jenuh per toko f(n) = β·n/(n+γ): KOL ke-k di toko yang sama diberi bobot
marginal f(k) − f(k−1) (linearisasi berdasarkan urutan Ê di toko tsb).

Solver: OR-Tools CP-SAT; bila paket tidak tersedia dipakai branch-and-bound sederhana.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations


def finite(*values, default: float = 0.0) -> float:
    """Nilai pertama yang berupa angka hingga (bukan None/NaN/inf) dan > 0; selain itu `default`.

    Catatan: NaN bernilai True di Python, sehingga pola `x or default` tidak menangkap NaN dari pandas.
    """
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f) and f > 0:
            return f
    return default


def _min_finite(*values, default: float = 0.0) -> float:
    """Minimum dari nilai yang valid (abaikan None/NaN); `default` bila tidak ada."""
    ok = [finite(v, default=-1) for v in values]
    ok = [v for v in ok if v > 0]
    return min(ok) if ok else default


@dataclass
class Candidate:
    key: str              # id unik (kol_id:store_id)
    kol_id: int
    store_id: int
    zone: str
    harga: float
    expected_visits: float
    skor: float
    diblokir: bool = False


@dataclass
class Constraints:
    budget: float
    jumlah_kol: int
    wajib_toko: list[int] = field(default_factory=list)   # toko terpilih yang wajib ≥ 1 KOL
    zona_min: float = 0.0                                   # porsi biaya per zona aktif
    zona_maks: float = 1.0
    gamma: float = 1.0
    satu_kol_satu_kali: bool = True


def _marginals(cands: list[Candidate], gamma: float) -> dict[str, float]:
    """Nilai marginal tiap kandidat setelah kurva jenuh, menurut urutan Ê di tokonya."""
    by_store: dict[int, list[Candidate]] = {}
    for c in cands:
        by_store.setdefault(c.store_id, []).append(c)
    val = {}
    for _, lst in by_store.items():
        lst.sort(key=lambda c: -c.expected_visits)
        for k, c in enumerate(lst, start=1):
            f_k = k / (k + gamma)
            f_prev = (k - 1) / (k - 1 + gamma)
            first = 1 / (1 + gamma)
            val[c.key] = c.expected_visits * (f_k - f_prev) / first
    return val


def eligible(cands: list[Candidate]) -> list[Candidate]:
    """Kandidat yang boleh dipilih: tidak diblokir, skor ≥ 50, dan harga valid.
    Ê kunjungan yang kosong/NaN dianggap 0 agar solver tidak gagal."""
    out = []
    for c in cands:
        skor = c.skor if c.skor is not None and math.isfinite(c.skor) else 0.0
        if c.diblokir or skor < 50 or not (c.harga and math.isfinite(c.harga) and c.harga > 0):
            continue
        if c.expected_visits is None or not math.isfinite(c.expected_visits):
            c.expected_visits = 0.0
        out.append(c)
    return out


def check_constraints(selected: list[Candidate], cons: Constraints) -> dict:
    total = sum(c.harga for c in selected)
    res = {
        "budget": total <= cons.budget + 1e-6,
        "jumlah_kol": len(selected) == cons.jumlah_kol,
        "wajib_toko": all(any(c.store_id == s for c in selected) for s in cons.wajib_toko),
        "blokir_skor": all(not c.diblokir and c.skor >= 50 for c in selected),
        "unik_kol": (len({c.kol_id for c in selected}) == len(selected)) if cons.satu_kol_satu_kali else True,
    }
    if total > 0 and (cons.zona_min > 0 or cons.zona_maks < 1):
        zones = {}
        for c in selected:
            zones[c.zone] = zones.get(c.zone, 0) + c.harga
        res["porsi_zona"] = all(cons.zona_min - 1e-9 <= v / total <= cons.zona_maks + 1e-9 for v in zones.values())
    else:
        res["porsi_zona"] = True
    res["semua"] = all(res.values())
    return res


def solve(cands: list[Candidate], cons: Constraints, time_limit: float = 5.0) -> dict:
    pool = eligible(cands)
    val = _marginals(pool, cons.gamma)
    try:
        from ortools.sat.python import cp_model  # type: ignore
        sel = _solve_cpsat(pool, cons, val, cp_model, time_limit)
        solver = "OR-Tools CP-SAT"
    except ImportError:
        sel = _solve_bnb(pool, cons, val)
        solver = "branch-and-bound"
    if sel is None:
        return {"status": "tidak layak", "solver": solver, "terpilih": [], "cek": {"semua": False}}
    return {
        "status": "optimal",
        "solver": solver,
        "terpilih": sel,
        "total_harga": sum(c.harga for c in sel),
        "total_kunjungan": sum(val[c.key] for c in sel),
        "cek": check_constraints(sel, cons),
    }


def _solve_cpsat(pool, cons, val, cp_model, time_limit):
    m = cp_model.CpModel()
    x = {c.key: m.NewBoolVar(c.key) for c in pool}
    m.Add(sum(int(c.harga) * x[c.key] for c in pool) <= int(cons.budget))
    m.Add(sum(x.values()) == cons.jumlah_kol)
    for s in cons.wajib_toko:
        m.Add(sum(x[c.key] for c in pool if c.store_id == s) >= 1)
    if cons.satu_kol_satu_kali:
        for kid in {c.kol_id for c in pool}:
            m.Add(sum(x[c.key] for c in pool if c.kol_id == kid) <= 1)
    if cons.zona_min > 0 or cons.zona_maks < 1:
        total = sum(int(c.harga) * x[c.key] for c in pool)
        for z in {c.zone for c in pool}:
            zc = [c for c in pool if c.zone == z]
            used = m.NewBoolVar(f"z_{z}")
            m.Add(sum(x[c.key] for c in zc) >= 1).OnlyEnforceIf(used)
            m.Add(sum(x[c.key] for c in zc) == 0).OnlyEnforceIf(used.Not())
            zsum = sum(int(c.harga) * x[c.key] for c in zc)
            m.Add(zsum * 1000 >= int(cons.zona_min * 1000) * total).OnlyEnforceIf(used)
            m.Add(zsum * 1000 <= int(cons.zona_maks * 1000) * total)
    m.Maximize(sum(int(round(val[c.key] * 100)) * x[c.key] for c in pool))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return [c for c in pool if solver.Value(x[c.key])]


def _solve_bnb(pool, cons, val, max_nodes: int = 200_000):
    """Branch-and-bound untuk ukuran kecil–menengah; batasan dicek pada daun."""
    pool = sorted(pool, key=lambda c: -val[c.key] / max(c.harga, 1))
    n = len(pool)
    k = cons.jumlah_kol
    if k > n:
        return None
    if n <= 22:
        best, best_v = None, -1.0
        for combo in combinations(pool, k):
            v = sum(val[c.key] for c in combo)
            if v > best_v and check_constraints(list(combo), cons)["semua"]:
                best, best_v = list(combo), v
        return best
    best = {"v": -1.0, "sel": None}
    nodes = [0]
    vals = [val[c.key] for c in pool]

    def bound(i, remaining):
        return sum(sorted(vals[i:], reverse=True)[:remaining])

    def rec(i, chosen, cost, v):
        nodes[0] += 1
        if nodes[0] > max_nodes:
            return
        if len(chosen) == k:
            if v > best["v"] and check_constraints(chosen, cons)["semua"]:
                best["v"], best["sel"] = v, list(chosen)
            return
        if i >= n or n - i < k - len(chosen):
            return
        if v + bound(i, k - len(chosen)) <= best["v"]:
            return
        c = pool[i]
        if cost + c.harga <= cons.budget and not (cons.satu_kol_satu_kali and any(o.kol_id == c.kol_id for o in chosen)):
            chosen.append(c)
            rec(i + 1, chosen, cost + c.harga, v + vals[i])
            chosen.pop()
        rec(i + 1, chosen, cost, v)

    rec(0, [], 0.0, 0.0)
    return best["sel"]
