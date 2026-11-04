"""Hak akses (RBAC) — Spesifikasi tabel 'Hak akses per role' & C.6.

Izin per aksi dipetakan ke role dan dicek di setiap aksi (bukan hanya menyembunyikan menu).
Cakupan data: role Store hanya melihat toko di scope_store_id-nya.
"""
from __future__ import annotations

ALL = {"ecommerce", "asst_manager", "manager", "store", "finance", "super_user"}
APPROVERS = {"asst_manager", "manager"}

PERMISSIONS: dict[str, set[str]] = {
    # Dashboard & social listening
    "dashboard.view": ALL,
    "social.view": {"ecommerce", "asst_manager", "manager", "super_user"},
    # Performa toko, upload traffic
    "stores.view": {"ecommerce", "asst_manager", "manager", "super_user"},
    "traffic.upload": {"ecommerce", "super_user"},
    # Database, analisa, mapping, seleksi
    "kol.view": {"ecommerce", "asst_manager", "manager", "super_user"},
    "kol.edit": {"ecommerce", "super_user"},
    "kol.block": {"ecommerce", "super_user"},
    # Campaign, draft & ajukan
    "campaign.view": {"ecommerce", "asst_manager", "manager", "super_user"},
    "campaign.edit": {"ecommerce", "super_user"},
    "submission.submit": {"ecommerce", "super_user"},
    # Approve / tolak pengajuan
    "submission.approve.level1": {"asst_manager", "super_user"},
    "submission.approve.level2": {"manager", "super_user"},
    # Form RO
    "ro.view": {"ecommerce", "asst_manager", "manager", "finance", "super_user"},
    "ro.manage": {"ecommerce", "asst_manager", "manager", "super_user"},
    # Kalender & timeline
    "calendar.view": {"ecommerce", "asst_manager", "manager", "store", "super_user"},
    "calendar.edit": {"ecommerce", "super_user"},
    # Creative brief
    "brief.edit": {"ecommerce", "super_user"},
    # Report & bukti tayang
    "report.view": ALL,
    "proof.input": {"ecommerce", "super_user"},
    # Pembayaran & status RO
    "payment.view": {"ecommerce", "finance", "super_user"},
    "payment.update_ro": {"ecommerce", "finance", "super_user"},
    "payment.manage": {"finance", "super_user"},
    "vendor_docs.view": {"finance", "super_user"},
    # Request KOL dari toko
    "request.create": {"store", "super_user"},
    "request.approve": {"ecommerce", "super_user"},
    # Model & testing
    "ml.view": {"ecommerce", "super_user"},
    "ml.manage": {"super_user"},
    # Akses & role
    "admin.users": {"super_user"},
    "data.reset_sample": {"super_user"},
}


def can(role: str | None, perm: str) -> bool:
    return bool(role) and role in PERMISSIONS.get(perm, set())


class Forbidden(Exception):
    pass


def require(role: str | None, perm: str):
    if not can(role, perm):
        raise Forbidden(f"Role ini tidak memiliki izin '{perm}'.")


def store_scope(user: dict) -> int | None:
    """Toko yang boleh dilihat role Store (None = semua toko)."""
    if user.get("role") == "store":
        return user.get("scope_store_id") or -1
    return None


def zone_scope(user: dict) -> int | None:
    if user.get("role") == "store":
        return None
    return user.get("scope_zone_id")
