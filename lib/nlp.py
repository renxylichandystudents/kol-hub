"""Social media listening & text mining — Spesifikasi B.8.

Sentimen cascade:
  1) aturan cepat (emoji / kata kunci jelas)
  2) model leksikon berbobot Bahasa Indonesia (pengganti IndoBERT pada prototipe Streamlit)
  3) komentar dengan keyakinan < 0,6 ditandai 'ambigu' untuk ditinjau (atau LLM bila dikonfigurasi)
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .preprocess import normalize_text

POS_WORDS = {
    "bagus": 1.0, "mantap": 1.2, "keren": 1.0, "suka": 0.8, "puas": 1.2, "ramah": 1.0, "cepat": 0.6, "murah": 0.8,
    "lengkap": 0.9, "rekomendasi": 0.9, "recommended": 0.9, "terima kasih": 0.8, "membantu": 0.9, "rapi": 0.7,
    "nyaman": 0.8, "terbaik": 1.2, "senang": 1.0, "oke": 0.5, "top": 0.8, "worth": 0.9, "hemat": 0.8,
    "inspiratif": 1.0, "cakep": 0.9, "cantik": 0.8, "luas": 0.5, "promo": 0.3, "diskon": 0.4, "best": 0.9,
    "emo_pos": 1.2, "emo_lucu": 0.4, "lucu": 0.5, "kocak": 0.5, "seru": 0.8, "berkualitas": 1.0, "awet": 0.8,
}
NEG_WORDS = {
    "kecewa": 1.4, "jelek": 1.2, "lama": 0.7, "mahal": 0.8, "kosong": 0.9, "habis": 0.6, "rusak": 1.1,
    "lambat": 0.9, "parah": 1.2, "buruk": 1.2, "jutek": 1.2, "kasar": 1.2, "antre": 0.6, "antri": 0.6,
    "ribet": 0.8, "susah": 0.7, "telat": 0.9, "salah": 0.7, "bohong": 1.3, "tipu": 1.4, "zonk": 1.1, "nyesel": 1.2,
    "menyesal": 1.2, "kotor": 0.9, "panas": 0.4, "macet": 0.5, "ga ada": 0.7, "tidak ada": 0.6, "komplain": 1.0,
    "emo_neg": 1.2, "cacat": 1.2, "bocor": 1.0, "penipuan": 1.5, "lelet": 1.0, "cuek": 1.0, "mengecewakan": 1.4,
}
NEGATORS = {"tidak", "bukan", "belum", "kurang", "jangan"}
INTENSIFIERS = {"banget": 1.4, "sangat": 1.4, "sekali": 1.3, "paling": 1.3, "amat": 1.3}

ASPECTS = {
    "harga": ["harga", "mahal", "murah", "diskon", "promo", "berapa", "cicilan", "ongkos"],
    "stok": ["stok", "kosong", "habis", "tersedia", "ready", "ada tidak", "inden"],
    "pelayanan": ["pelayanan", "layanan", "pegawai", "karyawan", "sales", "ramah", "jutek", "cuek", "customer service", "admin"],
    "produk": ["cat", "keramik", "kloset", "pipa", "lampu", "kitchen set", "produk", "barang", "kualitas", "warna", "merk"],
    "lokasi": ["lokasi", "parkir", "alamat", "di mana", "cabang", "jauh", "dekat", "macet"],
    "kasir": ["kasir", "antre", "antri", "bayar", "struk", "edc", "qris"],
    "pengiriman": ["kirim", "pengiriman", "antar", "ongkir", "kurir", "delivery", "sampai", "telat"],
}

INTENTS = [
    ("bertanya harga", r"\b(berapa|harga|hrg|price|cicil)\b"),
    ("cari produk", r"\b(ada tidak|ready|tersedia|jual|cari|stok)\b"),
    ("butuh jasa", r"\b(pasang|dipasang|tukang|jasa|instalasi|bisa dipasang|survey)\b"),
    ("tanya lokasi", r"\b(cabang mana|di mana|alamat|lokasi|buka jam)\b"),
    ("keluhan", r"\b(kecewa|komplain|rusak|lama|telat|jutek|parah)\b"),
    ("pujian", r"\b(mantap|bagus|keren|puas|terbaik|suka)\b"),
]


def sentiment_rule(raw: str) -> tuple[str, float] | None:
    """Tahap 1: aturan cepat (emoji/kata kunci sangat jelas)."""
    t = normalize_text(raw)
    pos = t.count("emo_pos") + sum(t.count(w) for w in ("terima kasih", "mantap", "terbaik"))
    neg = t.count("emo_neg") + sum(t.count(w) for w in ("penipuan", "mengecewakan", "kecewa berat"))
    if pos >= 2 and neg == 0:
        return "positif", 0.95
    if neg >= 1 and pos == 0 and ("emo_neg" in t or "penipuan" in t or "mengecewakan" in t):
        return "negatif", 0.92
    return None


def sentiment_lexicon(raw: str) -> tuple[str, float, float]:
    """Tahap 2: leksikon berbobot dengan negasi & penguat → (label, keyakinan, skor)."""
    words = normalize_text(raw).split()
    score = 0.0
    hits = 0
    i = 0
    while i < len(words):
        bigram = " ".join(words[i:i + 2])
        w, step = (bigram, 2) if bigram in POS_WORDS or bigram in NEG_WORDS else (words[i], 1)
        val = POS_WORDS.get(w, 0) - NEG_WORDS.get(w, 0)
        if val:
            hits += 1
            prev = words[max(0, i - 2):i]
            if any(p in NEGATORS for p in prev):
                val = -val * 0.8
            nxt = words[i + step:i + step + 1]
            if nxt and nxt[0] in INTENSIFIERS:
                val *= INTENSIFIERS[nxt[0]]
            score += val
        i += step
    if hits == 0:
        return "netral", 0.65, 0.0
    conf = 1 / (1 + math.exp(-abs(score) * 1.6))  # 0,5 – 1
    if abs(score) < 0.35:
        return "netral", 0.55 + 0.1 * (0.35 - abs(score)), score
    return ("positif" if score > 0 else "negatif"), conf, score


def sentiment_cascade(raw: str) -> dict:
    r = sentiment_rule(raw)
    if r:
        return {"sentimen": r[0], "skor": r[1], "metode": "aturan"}
    label, conf, _ = sentiment_lexicon(raw)
    if conf < 0.6:
        return {"sentimen": label, "skor": round(conf, 2), "metode": "ambigu"}
    return {"sentimen": label, "skor": round(conf, 2), "metode": "model"}


def aspects(raw: str) -> list[str]:
    t = " " + normalize_text(raw) + " "
    return [a for a, kws in ASPECTS.items() if any(f" {k} " in t for k in kws)]


def intent(raw: str) -> str | None:
    t = normalize_text(raw)
    for name, pat in INTENTS:
        if re.search(pat, t):
            return name
    return None


STOP = set("""yang dan di ke dari ini itu untuk dengan ada tidak saya kamu kakak admin sudah juga bisa
lagi saja kalau tapi karena jadi sama apa mau ingin aja nya ya yah dong deh sih kok nih tuh pak bu bang
mitra10 mitra emo_pos emo_neg emo_lucu banget sangat sekali the a is to of in kak min gan sis bro oke""".split())


def keywords(texts: list[str], top: int = 12) -> list[tuple[str, int]]:
    c = Counter()
    for t in texts:
        ws = [w for w in normalize_text(t).split() if w not in STOP and len(w) > 2 and not w.isdigit()]
        c.update(ws)
        c.update(" ".join(p) for p in zip(ws, ws[1:]))
    # hilangkan unigram yang tertutup bigram yang sama seringnya
    items = c.most_common(top * 3)
    out = []
    for w, n in items:
        if " " not in w and any(w in b and nb >= n * 0.8 for b, nb in items if " " in b):
            continue
        out.append((w, n))
        if len(out) >= top:
            break
    return out


def assign_topic(raw: str, topics: list[dict]) -> int | None:
    """Topik = kumpulan kata kunci (ditinjau mingguan tim); skor = jumlah kata kunci cocok."""
    t = " " + normalize_text(raw) + " "
    best, best_n = None, 0
    for tp in topics:
        n = sum(1 for k in tp["kata_kunci"] if f" {k} " in t or (" " in k and k in t))
        if n > best_n:
            best, best_n = tp["id"], n
    return best


# ================================================================ kategori KOL
CATEGORY_KEYWORDS = {
    "comedy": ["komedi", "lucu", "sketsa", "receh", "lawak", "prank", "comedy", "ngakak", "parodi", "kocak"],
    "beauty": ["makeup", "skincare", "beauty", "kecantikan", "mua", "glowing", "kosmetik", "hijab", "fashion"],
    "lifestyle": ["rumah", "interior", "dekorasi", "minimalis", "home", "renovasi", "diy", "tukang", "desain",
                  "keluarga", "parenting", "lifestyle", "travel", "daily", "vlog", "properti", "taman"],
    "culinary": ["kuliner", "makan", "resep", "masak", "food", "dapur", "jajan", "review makanan", "chef", "foodie"],
}


def suggest_category(bio: str, caption: str = "", model=None) -> tuple[str, float]:
    """Saran kategori otomatis dari bio & caption. Pakai model terlatih bila ada; jika tidak, kata kunci."""
    text = f"{bio or ''} {caption or ''}"
    if model is not None:
        proba = model.predict_proba([text])[0]
        i = int(proba.argmax())
        return model.classes_[i], float(proba[i])
    t = normalize_text(text)
    scores = {c: sum(1 for k in kws if k in t) for c, kws in CATEGORY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "general", 0.5
    total = sum(scores.values())
    return best, min(0.95, 0.5 + 0.5 * scores[best] / total)


def train_category_model(texts: list[str], labels: list[str]):
    """TF-IDF + Logistic Regression (pengganti embedding pada prototipe). None bila data < 20 / sklearn tak ada."""
    if len(texts) < 20 or len(set(labels)) < 2:
        return None
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
    except ImportError:
        return None
    model = make_pipeline(TfidfVectorizer(preprocessor=normalize_text, ngram_range=(1, 2), min_df=1),
                          LogisticRegression(max_iter=1000, C=4.0))
    model.fit(texts, labels)
    return model
