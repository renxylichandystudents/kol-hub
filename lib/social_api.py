"""Integrasi API resmi Instagram (Meta Graph API) & TikTok (Display API).

Instagram (login via Facebook, akun IG Mitra10 = Business yang terhubung ke Facebook Page):
- Akun resmi Mitra10: daftar media + insight (views, reach, likes, komentar, share, save) → official_posts, komentar → social_comments.
- KOL / portal (akun Business/Creator): Business Discovery → follower terbaru + like/komentar/views tiap posting.
  Link tayang di tabel posts dicocokkan lewat shortcode → post_metrics (sumber 'api'). Akun pribadi tidak bisa dibaca API.
TikTok (Display API, perlu izin pemilik akun lewat OAuth):
- Akun resmi Mitra10 → official_posts (views, likes, komentar, share).
- KOL yang memberi izin lewat link undangan → kol_tiktok_videos.
Token disimpan terenkripsi (Fernet, kunci DOC_ENCRYPTION_KEY di Secrets) di tabel api_tokens.
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
import time
from datetime import date, datetime, timedelta, timezone

import requests

from . import db

GRAPH = "https://graph.facebook.com"
TT = "https://open.tiktokapis.com"
TT_AUTH = "https://www.tiktok.com/v2/auth/authorize/"
TIMEOUT = 30
RATE_LIMIT_CODES = {4, 17, 32, 613, 80002}


class ApiError(Exception):
    def __init__(self, msg: str, code: int | None = None, sub: int | None = None):
        super().__init__(msg)
        self.code, self.sub = code, sub

    @property
    def rate_limited(self) -> bool:
        return self.code in RATE_LIMIT_CODES


# ====================================================================== secrets & token store
def secret(name: str, default=None):
    import os

    import streamlit as st
    try:
        v = st.secrets.get(name)
    except Exception:
        v = None
    return v or os.environ.get(name) or default


def graph_version() -> str:
    return secret("META_GRAPH_VERSION", "v25.0")


def _fernet():
    """Kunci enkripsi token. Prioritas: DOC_ENCRYPTION_KEY di Secrets; bila tidak ada/tidak valid, kunci diturunkan
    dari DATABASE_URL (rahasia yang hanya ada di Secrets, tidak tersimpan di database) sehingga token tetap terenkripsi."""
    from cryptography.fernet import Fernet
    key = secret("DOC_ENCRYPTION_KEY")
    if key:
        try:
            return Fernet(key.encode() if isinstance(key, str) else key)
        except (ValueError, TypeError):
            pass
    url = db.database_url()
    if not url:
        return None
    import base64
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("kolhub-token:" + url).encode()).digest()))


def key_source() -> str:
    key = secret("DOC_ENCRYPTION_KEY")
    if key:
        from cryptography.fernet import Fernet
        try:
            Fernet(key.encode() if isinstance(key, str) else key)
            return "secret"
        except (ValueError, TypeError):
            return "invalid"
    return "derived"


def can_store_tokens() -> bool:
    return _fernet() is not None


def save_token(nama: str, token: dict, info: dict, user_id: int | None):
    f = _fernet()
    if f is None:
        raise ApiError("DOC_ENCRYPTION_KEY belum di-set di Secrets — token tidak boleh disimpan tanpa enkripsi.")
    db.execute("""INSERT INTO api_tokens (nama, nilai_terenkripsi, info_json, updated_by, updated_at) VALUES (%s,%s,%s,%s,NOW())
                  ON CONFLICT (nama) DO UPDATE SET nilai_terenkripsi=EXCLUDED.nilai_terenkripsi, info_json=EXCLUDED.info_json,
                  updated_by=EXCLUDED.updated_by, updated_at=NOW()""",
               (nama, f.encrypt(json.dumps(token).encode()), json.dumps(info, default=str), user_id))


def load_token(nama: str) -> dict | None:
    r = db.one("SELECT nilai_terenkripsi, info_json FROM api_tokens WHERE nama=%s", (nama,))
    if not r:
        return None
    f = _fernet()
    if f is None:
        return None
    try:
        tok = json.loads(f.decrypt(bytes(r["nilai_terenkripsi"])).decode())
    except Exception:
        return None
    return {**tok, "_info": r["info_json"] or {}}


def delete_token(nama: str):
    db.execute("DELETE FROM api_tokens WHERE nama=%s", (nama,))


def token_info(prefix: str) -> list[dict]:
    return db.query("SELECT nama, info_json, updated_at FROM api_tokens WHERE nama LIKE %s ORDER BY nama", (prefix + "%",))


# ====================================================================== util
def shortcode(url: str | None) -> str | None:
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]{5,})", url or "")
    return m.group(1) if m else None


def author_hash(username: str | None) -> str:
    return hashlib.sha256((username or "").encode()).hexdigest()[:16]


def _log(jenis: str, ringkasan: dict, mulai: datetime):
    db.execute("INSERT INTO social_sync_log (jenis, mulai, selesai, ringkasan_json) VALUES (%s,%s,NOW(),%s)",
               (jenis, mulai, json.dumps(ringkasan, default=str)))


# ====================================================================== Meta Graph API
def graph_get(path: str, token: str, params: dict | None = None, session: requests.Session | None = None) -> dict:
    url = path if path.startswith("http") else f"{GRAPH}/{graph_version()}/{path.lstrip('/')}"
    p = dict(params or {})
    if "access_token=" not in url:
        p["access_token"] = token
    r = (session or requests).get(url, params=p, timeout=TIMEOUT)
    try:
        data = r.json()
    except ValueError:
        raise ApiError(f"Respons Meta bukan JSON (HTTP {r.status_code}).")
    if "error" in data:
        e = data["error"]
        raise ApiError(e.get("message", "Error Meta API"), e.get("code"), e.get("error_subcode"))
    return data


def meta_discover_accounts(token: str) -> list[dict]:
    """Facebook Page yang dikelola token + akun IG Business yang terhubung."""
    d = graph_get("me/accounts", token, {"fields": "id,name,instagram_business_account{id,username,followers_count}", "limit": 100})
    out = []
    for p in d.get("data", []):
        ig = p.get("instagram_business_account")
        if ig:
            out.append({"page_id": p["id"], "page": p.get("name"), "ig_user_id": ig["id"], "username": ig.get("username"),
                        "followers": ig.get("followers_count")})
    return out


def meta_token_debug(token: str) -> dict:
    """Masa berlaku token (bila bisa dicek)."""
    try:
        d = graph_get("debug_token", token, {"input_token": token}).get("data", {})
        exp = d.get("expires_at") or d.get("data_access_expires_at")
        return {"valid": d.get("is_valid"), "expires_at": datetime.fromtimestamp(exp, timezone.utc).isoformat() if exp else "tidak kedaluwarsa",
                "scopes": d.get("scopes", [])}
    except ApiError as e:
        return {"error": str(e)}


def meta_cfg() -> dict | None:
    t = load_token("meta")
    if not t or not t.get("access_token") or not t.get("_info", {}).get("ig_user_id"):
        return None
    return {"token": t["access_token"], "ig_user_id": t["_info"]["ig_user_id"], "username": t["_info"].get("username")}


DISC_MEDIA = "id,permalink,timestamp,media_type,media_product_type,like_count,comments_count,view_count"


def business_discovery(cfg: dict, username: str, after: str | None = None, limit: int = 50, session=None) -> dict:
    media = f"media.after({after}).limit({limit})" if after else f"media.limit({limit})"
    fields = f"business_discovery.username({username}){{id,username,name,biography,followers_count,media_count,{media}{{{DISC_MEDIA}}}}}"
    return graph_get(cfg["ig_user_id"], cfg["token"], {"fields": fields}, session=session)["business_discovery"]


def sync_kol_instagram(max_accounts: int = 60, kol_ids: list[int] | None = None, max_pages: int = 6) -> dict:
    """Follower terbaru + metrik posting KOL/portal Instagram via Business Discovery.
    Diproses dari akun yang paling lama belum dicek; berhenti rapi saat kena batas rate."""
    cfg = meta_cfg()
    if not cfg:
        return {"status": "belum terhubung"}
    mulai = datetime.now(timezone.utc)
    q = """SELECT k.id, k.username_norm, MIN(p.tanggal_tayang) AS tayang_awal
           FROM kol_accounts k LEFT JOIN posts p ON p.kol_id=k.id AND p.link ILIKE '%%instagram.com%%'
           WHERE lower(k.platform)='instagram' AND k.status='aktif' {extra}
           GROUP BY k.id ORDER BY k.api_checked_at NULLS FIRST, k.id LIMIT %s"""
    if kol_ids:
        accs = db.query(q.format(extra="AND k.id = ANY(%s)"), (kol_ids, len(kol_ids)))
    else:
        accs = db.query(q.format(extra=""), (max_accounts,))
    today = date.today()
    s = requests.Session()
    out = {"akun_dicek": 0, "akun_ok": 0, "akun_bukan_bisnis": 0, "posting_cocok": 0, "error": 0, "berhenti_rate_limit": False}
    for a in accs:
        st_api, follower, metrics = "ok", None, {}
        recent = []
        try:
            after, pages = None, 0
            oldest_need = (a["tayang_awal"] - timedelta(days=3)) if a["tayang_awal"] else None
            while True:
                bd = business_discovery(cfg, a["username_norm"], after, session=s)
                follower = bd.get("followers_count")
                med = bd.get("media", {})
                for m in med.get("data", []):
                    sc = shortcode(m.get("permalink"))
                    ts = datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00")) if m.get("timestamp") else None
                    if sc:
                        metrics[sc] = {**m, "_ts": ts}
                    if len(recent) < 12:
                        recent.append(m)
                pages += 1
                after = med.get("paging", {}).get("cursors", {}).get("after")
                last_ts = metrics[list(metrics)[-1]]["_ts"] if metrics else None
                if not after or pages >= max_pages or not oldest_need or (last_ts and last_ts < oldest_need):
                    break
        except ApiError as e:
            if e.rate_limited:
                out["berhenti_rate_limit"] = True
                break
            msg = str(e).lower()
            st_api = "bukan_bisnis" if (e.code == 110 or "cannot be found" in msg or "not a business" in msg
                                        or "invalid user id" in msg or e.code == 100) else "error"
            out["akun_bukan_bisnis" if st_api == "bukan_bisnis" else "error"] += 1
        except requests.RequestException:
            st_api = "error"
            out["error"] += 1
        out["akun_dicek"] += 1
        with db.transaction() as cur:
            cur.execute("UPDATE kol_accounts SET api_status=%s, api_checked_at=NOW() WHERE id=%s", (st_api, a["id"]))
            if st_api != "ok":
                continue
            out["akun_ok"] += 1
            views = [m.get("view_count") for m in recent if m.get("view_count")]
            inter = [(m.get("like_count") or 0) + (m.get("comments_count") or 0) for m in recent]
            er = round(statistics.median(inter) / follower * 100, 2) if follower and inter else None
            avg_views = int(statistics.median(views)) if views else None
            cur.execute("""INSERT INTO kol_metrics_snapshot (kol_id, tanggal, follower, avg_views, er) VALUES (%s,%s,%s,%s,%s)
                           ON CONFLICT (kol_id, tanggal) DO UPDATE SET follower=EXCLUDED.follower,
                           avg_views=COALESCE(EXCLUDED.avg_views, kol_metrics_snapshot.avg_views), er=COALESCE(EXCLUDED.er, kol_metrics_snapshot.er)""",
                        (a["id"], today, follower, avg_views, er))
            posts = cur.execute("SELECT id, link FROM posts WHERE kol_id=%s AND link ILIKE '%%instagram.com%%'", (a["id"],)).fetchall()
            rows = []
            for p in posts:
                m = metrics.get(shortcode(p["link"]) or "")
                if m:
                    rows.append((p["id"], m.get("view_count"), m.get("like_count"), m.get("comments_count"), None, None, "api", today))
            if rows:
                cur.copy_values("""INSERT INTO post_metrics (post_id, views, likes, komentar, share, save, sumber, diukur_pada) VALUES %s
                                   ON CONFLICT (post_id, diukur_pada, sumber) DO UPDATE SET views=EXCLUDED.views, likes=EXCLUDED.likes,
                                   komentar=EXCLUDED.komentar""", rows)
                out["posting_cocok"] += len(rows)
        time.sleep(0.2)
    _log("instagram_kol", out, mulai)
    return out


MEDIA_FIELDS = "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count"


def _media_insights(cfg: dict, m: dict, session) -> dict:
    metrics = ["views", "reach", "saved", "shares", "total_interactions"]
    try:
        d = graph_get(f"{m['id']}/insights", cfg["token"], {"metric": ",".join(metrics)}, session=session)
    except ApiError:
        try:  # beberapa jenis media tidak mendukung semua metrik → coba set minimal
            d = graph_get(f"{m['id']}/insights", cfg["token"], {"metric": "reach,saved"}, session=session)
        except ApiError:
            return {}
    return {x["name"]: (x.get("values") or [{}])[0].get("value") for x in d.get("data", [])}


def sync_official_instagram(days: int = 120, with_comments: bool = True, max_media: int = 150) -> dict:
    cfg = meta_cfg()
    if not cfg:
        return {"status": "belum terhubung"}
    mulai = datetime.now(timezone.utc)
    since = mulai - timedelta(days=days)
    s = requests.Session()
    out = {"media": 0, "komentar_baru": 0}
    url, n = f"{cfg['ig_user_id']}/media", 0
    params = {"fields": MEDIA_FIELDS, "limit": 50}
    while url and n < max_media:
        d = graph_get(url, cfg["token"], params, session=s)
        params = None
        stop = False
        for m in d.get("data", []):
            ts = datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00"))
            if ts < since:
                stop = True
                break
            ins = _media_insights(cfg, m, s)
            jenis = "reels" if m.get("media_product_type") == "REELS" else "carousel" if m.get("media_type") == "CAROUSEL_ALBUM" else "feed"
            judul = re.sub(r"\s+", " ", (m.get("caption") or "").strip())[:190] or f"Posting {ts:%d %b %Y}"
            db.execute("""INSERT INTO official_posts (platform, judul, jenis_konten, tanggal, views, likes, komentar, share, save, reach, ext_id, link)
                          VALUES ('Instagram',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                          ON CONFLICT (platform, ext_id) WHERE ext_id IS NOT NULL DO UPDATE SET judul=EXCLUDED.judul, views=EXCLUDED.views,
                          likes=EXCLUDED.likes, komentar=EXCLUDED.komentar, share=EXCLUDED.share, save=EXCLUDED.save, reach=EXCLUDED.reach""",
                       (judul, jenis, ts, ins.get("views"), m.get("like_count"), m.get("comments_count"), ins.get("shares"), ins.get("saved"),
                        ins.get("reach"), m["id"], m.get("permalink")))
            n += 1
            if with_comments and m.get("comments_count"):
                out["komentar_baru"] += _sync_comments(cfg, m, s)
        url = None if stop else d.get("paging", {}).get("next")
    out["media"] = n
    _log("instagram_resmi", out, mulai)
    return out


def _sync_comments(cfg: dict, m: dict, session) -> int:
    rows, url, params = [], f"{m['id']}/comments", {"fields": "id,text,timestamp,username", "limit": 50}
    pages = 0
    while url and pages < 10:
        d = graph_get(url, cfg["token"], params, session=session)
        params = None
        for c in d.get("data", []):
            if c.get("text"):
                rows.append(("Instagram", m["id"], author_hash(c.get("username")), c["text"][:2000],
                             datetime.fromisoformat(c["timestamp"].replace("+0000", "+00:00")), c["id"]))
        url = d.get("paging", {}).get("next")
        pages += 1
    if not rows:
        return 0
    before = db.scalar("SELECT COUNT(*) FROM social_comments WHERE platform='Instagram' AND post_ref=%s", (m["id"],))
    with db.transaction() as cur:
        cur.copy_values("""INSERT INTO social_comments (platform, post_ref, author_hash, teks_anonim, waktu, ext_id) VALUES %s
                           ON CONFLICT (platform, ext_id) WHERE ext_id IS NOT NULL DO NOTHING""", rows)
    return db.scalar("SELECT COUNT(*) FROM social_comments WHERE platform='Instagram' AND post_ref=%s", (m["id"],)) - before


# ====================================================================== TikTok Display API
TT_SCOPES = "user.info.basic,user.info.profile,user.info.stats,video.list"
TT_VIDEO_FIELDS = "id,title,video_description,create_time,duration,share_url,view_count,like_count,comment_count,share_count"


def tiktok_ready() -> bool:
    return bool(secret("TIKTOK_CLIENT_KEY") and secret("TIKTOK_CLIENT_SECRET") and secret("APP_URL"))


def tiktok_auth_url(state: str) -> str:
    from urllib.parse import urlencode
    return TT_AUTH + "?" + urlencode({"client_key": secret("TIKTOK_CLIENT_KEY"), "scope": TT_SCOPES, "response_type": "code",
                                     "redirect_uri": secret("APP_URL"), "state": state})


def _tt_token_request(data: dict) -> dict:
    r = requests.post(f"{TT}/v2/oauth/token/", data={"client_key": secret("TIKTOK_CLIENT_KEY"),
                                                    "client_secret": secret("TIKTOK_CLIENT_SECRET"), **data},
                      headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=TIMEOUT)
    d = r.json()
    if "access_token" not in d:
        raise ApiError(d.get("error_description") or d.get("error") or f"Token TikTok gagal (HTTP {r.status_code}).")
    now = datetime.now(timezone.utc)
    d["access_expires"] = (now + timedelta(seconds=int(d.get("expires_in", 86400)))).isoformat()
    d["refresh_expires"] = (now + timedelta(seconds=int(d.get("refresh_expires_in", 31536000)))).isoformat()
    return d


def tiktok_exchange_code(code: str) -> dict:
    return _tt_token_request({"code": code, "grant_type": "authorization_code", "redirect_uri": secret("APP_URL")})


def _tt_access(nama: str) -> str:
    t = load_token(nama)
    if not t:
        raise ApiError("Token TikTok tidak ditemukan.")
    if datetime.fromisoformat(t["access_expires"]) - datetime.now(timezone.utc) < timedelta(minutes=10):
        info = t.pop("_info", {})
        t = _tt_token_request({"grant_type": "refresh_token", "refresh_token": t["refresh_token"]})
        save_token(nama, t, info, None)
    return t["access_token"]


def tiktok_user(access: str) -> dict:
    r = requests.get(f"{TT}/v2/user/info/", params={"fields": "open_id,display_name,username,follower_count,likes_count,video_count"},
                     headers={"Authorization": f"Bearer {access}"}, timeout=TIMEOUT).json()
    if r.get("error", {}).get("code", "ok") != "ok":
        raise ApiError(r["error"].get("message", "Error TikTok"))
    return r.get("data", {}).get("user", {})


def tiktok_videos(access: str, since: datetime | None = None, max_pages: int = 20) -> list[dict]:
    out, cursor = [], None
    for _ in range(max_pages):
        body = {"max_count": 20}
        if cursor:
            body["cursor"] = cursor
        r = requests.post(f"{TT}/v2/video/list/", params={"fields": TT_VIDEO_FIELDS}, json=body,
                          headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"}, timeout=TIMEOUT).json()
        if r.get("error", {}).get("code", "ok") != "ok":
            raise ApiError(r["error"].get("message", "Error TikTok"))
        d = r.get("data", {})
        vids = d.get("videos", [])
        out += vids
        if not d.get("has_more") or not vids or (since and datetime.fromtimestamp(vids[-1]["create_time"], timezone.utc) < since):
            break
        cursor = d.get("cursor")
    return out


def sync_official_tiktok(days: int = 120) -> dict:
    if not load_token("tiktok:mitra10"):
        return {"status": "belum terhubung"}
    mulai = datetime.now(timezone.utc)
    access = _tt_access("tiktok:mitra10")
    vids = tiktok_videos(access, since=mulai - timedelta(days=days))
    for v in vids:
        ts = datetime.fromtimestamp(v["create_time"], timezone.utc)
        judul = re.sub(r"\s+", " ", (v.get("title") or v.get("video_description") or "").strip())[:190] or f"Video {ts:%d %b %Y}"
        db.execute("""INSERT INTO official_posts (platform, judul, jenis_konten, durasi_detik, tanggal, views, likes, komentar, share, ext_id, link)
                      VALUES ('TikTok',%s,'video',%s,%s,%s,%s,%s,%s,%s,%s)
                      ON CONFLICT (platform, ext_id) WHERE ext_id IS NOT NULL DO UPDATE SET judul=EXCLUDED.judul, views=EXCLUDED.views,
                      likes=EXCLUDED.likes, komentar=EXCLUDED.komentar, share=EXCLUDED.share""",
                   (judul, v.get("duration"), ts, v.get("view_count"), v.get("like_count"), v.get("comment_count"), v.get("share_count"),
                    str(v["id"]), v.get("share_url")))
    out = {"video": len(vids)}
    _log("tiktok_resmi", out, mulai)
    return out


def sync_kol_tiktok() -> dict:
    """Video TikTok KOL yang sudah memberi izin; dicocokkan ke baris pengajuan lewat ID video di catatan/link."""
    mulai = datetime.now(timezone.utc)
    out = {"kol": 0, "video": 0, "cocok": 0, "error": 0}
    tokens = token_info("tiktok:kol:")
    if tokens:
        resolve_tiktok_ids()
    for t in tokens:
        kol_id = int(t["nama"].rsplit(":", 1)[1])
        try:
            access = _tt_access(t["nama"])
            user = tiktok_user(access)
            vids = tiktok_videos(access, since=datetime(date.today().year - 1, 1, 1, tzinfo=timezone.utc))
        except (ApiError, requests.RequestException):
            out["error"] += 1
            continue
        out["kol"] += 1
        if user.get("follower_count") is not None:
            db.execute("""INSERT INTO kol_metrics_snapshot (kol_id, tanggal, follower) VALUES (%s,%s,%s)
                          ON CONFLICT (kol_id, tanggal) DO UPDATE SET follower=GREATEST(kol_metrics_snapshot.follower, EXCLUDED.follower)""",
                       (kol_id, date.today(), user["follower_count"]))
        items = db.query("SELECT id, catatan_item FROM submission_items WHERE kol_id=%s AND catatan_item ILIKE '%%tiktok%%'", (kol_id,))
        for v in vids:
            vid = str(v["id"])
            item = next((i["id"] for i in items if vid in (i["catatan_item"] or "")), None)
            out["cocok"] += int(item is not None)
            db.execute("""INSERT INTO kol_tiktok_videos (video_id, kol_id, share_url, judul, dibuat, durasi_detik, views, likes, komentar, share, item_id, synced_at)
                          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                          ON CONFLICT (video_id) DO UPDATE SET views=EXCLUDED.views, likes=EXCLUDED.likes, komentar=EXCLUDED.komentar,
                          share=EXCLUDED.share, item_id=COALESCE(EXCLUDED.item_id, kol_tiktok_videos.item_id), synced_at=NOW()""",
                       (vid, kol_id, v.get("share_url"), (v.get("title") or v.get("video_description") or "")[:500],
                        datetime.fromtimestamp(v["create_time"], timezone.utc), v.get("duration"), v.get("view_count"), v.get("like_count"),
                        v.get("comment_count"), v.get("share_count"), item))
            out["video"] += 1
    _log("tiktok_kol", out, mulai)
    return out


def resolve_tiktok_ids(limit: int = 300) -> int:
    """Ubah link pendek vt.tiktok.com di catatan baris menjadi ID video (agar bisa dicocokkan dengan API)."""
    rows = db.query("""SELECT id, catatan_item FROM submission_items WHERE catatan_item ~ 'vt\\.tiktok\\.com|vm\\.tiktok\\.com'
                       AND catatan_item !~ 'tiktok_id:' LIMIT %s""", (limit,))
    n = 0
    s = requests.Session()
    for r in rows:
        ids = []
        for u in re.findall(r"https?://v[tm]\.tiktok\.com/[A-Za-z0-9]+/?", r["catatan_item"]):
            try:
                final = s.head(u, allow_redirects=True, timeout=15).url
            except requests.RequestException:
                continue
            m = re.search(r"/video/(\d+)", final)
            if m:
                ids.append(m.group(1))
        if ids:
            db.execute("UPDATE submission_items SET catatan_item = catatan_item || %s WHERE id=%s", (" | tiktok_id:" + ",".join(ids), r["id"]))
            n += 1
    return n


# ====================================================================== OAuth state (callback bisa datang tanpa sesi login)
def new_oauth_state(owner: str, user_id: int | None) -> str:
    import secrets as _s
    st_ = _s.token_urlsafe(24)
    db.execute("INSERT INTO oauth_states (state, owner, created_by) VALUES (%s,%s,%s)", (st_, owner, user_id))
    return st_


def handle_tiktok_callback(code: str, state: str) -> str:
    """Tukar kode OAuth TikTok → token, simpan sesuai pemilik state. Return pesan untuk ditampilkan."""
    r = db.one("SELECT owner, created_by FROM oauth_states WHERE state=%s AND created_at > NOW() - INTERVAL '14 days'", (state,))
    if not r:
        return "Link otorisasi tidak dikenal atau sudah kedaluwarsa. Minta link baru ke tim Digital Marketing Mitra10."
    tok = tiktok_exchange_code(code)
    user = tiktok_user(tok["access_token"])
    save_token(r["owner"], tok, {"akun": user.get("username") or user.get("display_name"), "open_id": tok.get("open_id"),
                                 "follower": user.get("follower_count"), "scope": tok.get("scope")}, r["created_by"])
    db.execute("DELETE FROM oauth_states WHERE state=%s", (state,))
    nama = user.get("display_name") or user.get("username") or "akun TikTok"
    return f"Terima kasih — {nama} berhasil terhubung dengan KOL Hub Mitra10. Halaman ini boleh ditutup."


# ====================================================================== orkestrasi
def last_sync(jenis: str) -> datetime | None:
    return db.scalar("SELECT MAX(selesai) FROM social_sync_log WHERE jenis=%s", (jenis,))


def run_daily(max_accounts: int = 60) -> dict:
    """Dipanggil oleh job harian: lewati sumber yang belum terhubung atau sudah sinkron < 20 jam."""
    out = {}
    fresh = lambda j: (last_sync(j) or datetime(2000, 1, 1, tzinfo=timezone.utc)) > datetime.now(timezone.utc) - timedelta(hours=20)  # noqa: E731
    for jenis, fn in (("instagram_resmi", sync_official_instagram), ("instagram_kol", lambda: sync_kol_instagram(max_accounts)),
                      ("tiktok_resmi", sync_official_tiktok), ("tiktok_kol", sync_kol_tiktok)):
        if fresh(jenis):
            continue
        try:
            out[jenis] = fn()
        except (ApiError, requests.RequestException) as e:
            out[jenis] = {"error": str(e)[:300]}
    return out
