"""Dokumen: Form Approval RO (PDF), Creative Brief (PPTX 9 slide & PDF), template Excel upload."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd

from .formulas import rupiah
from .master import BRIEF_SECTIONS

NAVY = (17, 26, 51)
BLUE = (29, 78, 216)
ORANGE = (249, 115, 22)


# ====================================================================== Form RO (layar 14)
def ro_pdf(ro: dict, sub: dict, items: list[dict], approvals: list[dict], campaign: dict | None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Form Approval RO {ro['no_ro']}")
    ss = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=ss["Title"], fontSize=15, alignment=0, spaceAfter=2)
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=8.5, leading=11)
    cell = ParagraphStyle("c", parent=ss["Normal"], fontSize=8, leading=10)
    money = ParagraphStyle("mny", parent=cell, alignment=2)
    el = [Paragraph("MITRA10 — Digital Marketing", ParagraphStyle("t", parent=ss["Normal"], fontSize=9, textColor=colors.HexColor("#f97316"))),
          Paragraph(f"FORM APPROVAL RO · {ro['no_ro']}", h),
          Paragraph(f"Referensi pengajuan <b>{sub['no_pengajuan']}</b> (revisi ke-{sub['revisi_ke']}) · "
                    f"{'Campaign <b>' + campaign['no_campaign'] + ' — ' + campaign['nama'] + '</b>' if campaign else 'Pengajuan tunggal'} · "
                    f"Tanggal {date.today():%d/%m/%Y}", small),
          Spacer(1, 6)]
    data = [["No", "KOL / Portal", "Toko", "Deliverable", "Tayang", "Harga", "Pajak", "Neto"]]
    total = pajak = 0
    for i, it in enumerate(items, start=1):
        total += it["harga_nego"]; pajak += it.get("pajak_nominal") or 0
        data.append([str(i), Paragraph(f"{it['kol_nama']}<br/><font size=7>{it['username']} · {it['platform']}</font>", cell),
                     Paragraph(it["toko"], cell), it["deliverable"], f"{it['tanggal_posting']:%d/%m/%Y}" if it.get("tanggal_posting") else "—",
                     rupiah(it["harga_nego"], singkat=False),
                     Paragraph(f"{rupiah(it.get('pajak_nominal') or 0, singkat=False)}<br/><font size=6.5>{it.get('pajak_jenis') or ''}</font>", money),
                     rupiah(it["harga_nego"] - (it.get("pajak_nominal") or 0), singkat=False)])
    data.append(["", "", "", "", "Total", rupiah(total, singkat=False), rupiah(pajak, singkat=False), rupiah(total - pajak, singkat=False)])
    t = Table(data, colWidths=[8 * mm, 38 * mm, 27 * mm, 16 * mm, 17 * mm, 25 * mm, 23 * mm, 24 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111a33")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")), ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f8fafc")]),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("ALIGN", (5, 1), (-1, -1), "RIGHT"),
    ]))
    el += [t, Spacer(1, 8)]
    appr_txt = " · ".join(f"Level {a['level']} ({'Asisten Manager' if a['level'] == 1 else 'Manager'}): {a['keputusan']} oleh {a['nama'] or '—'} "
                          f"{a['waktu']:%d/%m/%Y %H:%M}" for a in approvals) or "—"
    el += [Paragraph(f"<b>Jejak approval:</b> {appr_txt}", small), Spacer(1, 4),
           Paragraph("Pajak dihitung dari tabel aturan pajak yang berlaku (PPh 21 perorangan / PPh 23 badan usaha) dan divalidasi tim Tax.", small),
           Spacer(1, 14)]
    sig = Table([["Dibuat", "Diperiksa", "Disetujui", "Diterima"], ["\n\n\n\n", "", "", ""],
                 ["E-commerce / Digital Marketing", "Asisten Manager", "Manager", "Finance"],
                 ["Tgl:", "Tgl:", "Tgl:", "Tgl:"]], colWidths=[45 * mm] * 4, rowHeights=[7 * mm, 22 * mm, 7 * mm, 7 * mm])
    sig.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#64748b")), ("FONTSIZE", (0, 0), (-1, -1), 8),
                             ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3ff"))]))
    el += [sig, Spacer(1, 10),
           Paragraph(f"Kode verifikasi: <b>{ro['kode_verifikasi']}</b> — hardcopy bertanda tangan adalah bukti pengesahan; "
                     "scan diunggah kembali ke KOL Hub dan salinan digital otomatis masuk menu Finance.", small)]
    doc.build(el)
    return buf.getvalue()


# ====================================================================== Creative brief (layar 17–18)
def _sec_text(urutan: int, isi: dict) -> list[str]:
    if urutan == 5:
        return [f"Scene {s.get('no')}: {s.get('durasi', '')} — {s.get('visual', '')} | Audio: {s.get('audio', '')}" for s in isi.get("scene", [])]
    if urutan == 6:
        return [f"WAJIB: {isi.get('wajib', '')}", f"DILARANG: {isi.get('dilarang', '')}"]
    if urutan == 7:
        return [f"Caption: {isi.get('caption', '')}", f"Hashtag: {isi.get('hashtag', '')}"]
    if urutan == 8:
        return [f"Deliverable: {isi.get('deliverable', '')}", f"Timeline: {isi.get('timeline', '')}"]
    if urutan == 9:
        return [isi.get("referensi", "")]
    return [isi.get("teks", "")]


def brief_pptx(judul: str, meta: str, sections: dict[int, dict]) -> bytes:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    for n in range(1, 10):
        s = prs.slides.add_slide(blank)
        bar = s.shapes.add_shape(1, 0, 0, prs.slide_width, Inches(1.1))
        bar.fill.solid(); bar.fill.fore_color.rgb = RGBColor(*NAVY); bar.line.fill.background()
        tb = s.shapes.add_textbox(Inches(0.5), Inches(0.18), Inches(12), Inches(0.8)).text_frame
        tb.text = f"{n}. {BRIEF_SECTIONS[n - 1]}"
        tb.paragraphs[0].runs[0].font.size = Pt(30); tb.paragraphs[0].runs[0].font.bold = True
        tb.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)
        sub = s.shapes.add_textbox(Inches(0.5), Inches(1.25), Inches(12.3), Inches(0.5)).text_frame
        sub.text = f"{judul} · {meta}"
        sub.paragraphs[0].runs[0].font.size = Pt(13); sub.paragraphs[0].runs[0].font.color.rgb = RGBColor(100, 116, 139)
        body = s.shapes.add_textbox(Inches(0.6), Inches(1.95), Inches(12.1), Inches(5)).text_frame
        body.word_wrap = True
        lines = _sec_text(n, sections.get(n, {})) or ["—"]
        for i, line in enumerate(lines):
            p = body.paragraphs[0] if i == 0 else body.add_paragraph()
            p.text = line or "—"
            p.font.size = Pt(20 if n != 5 else 17)
            p.space_after = Pt(10)
        acc = s.shapes.add_shape(1, 0, prs.slide_height - Inches(0.12), prs.slide_width, Inches(0.12))
        acc.fill.solid(); acc.fill.fore_color.rgb = RGBColor(*ORANGE); acc.line.fill.background()
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def brief_pdf(judul: str, meta: str, sections: dict[int, dict]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=14 * mm,
                            title=f"Creative Brief — {judul}")
    ss = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=ss["Title"], fontSize=24, alignment=0, textColor=colors.HexColor("#111a33"))
    m = ParagraphStyle("m", parent=ss["Normal"], fontSize=11, textColor=colors.HexColor("#64748b"))
    b = ParagraphStyle("b", parent=ss["Normal"], fontSize=14, leading=20, spaceAfter=8)
    el = []
    for n in range(1, 10):
        el += [Paragraph(f"{n}. {BRIEF_SECTIONS[n - 1]}", h), Paragraph(f"{judul} · {meta}", m), Spacer(1, 10)]
        for line in _sec_text(n, sections.get(n, {})) or ["—"]:
            el.append(Paragraph(line.replace("&", "&amp;").replace("<", "&lt;"), b))
        if n < 9:
            el.append(PageBreak())
    doc.build(el)
    return buf.getvalue()


# ====================================================================== template Excel
def traffic_template() -> bytes:
    df = pd.DataFrame({"Nama Toko": ["Mitra10 Cibubur", "Mitra10 Cibubur", "Mitra10 Medan"],
                       "Tanggal": ["01/11/2026", "02/11/2026", "01/11/2026"], "Kunjungan": [1180, 1215, 990],
                       "Transaksi": [420, 433, 361]})
    return _xlsx({"traffic": df, "petunjuk": pd.DataFrame({"Petunjuk": [
        "Satu baris = satu toko per hari.", "Nama toko boleh tidak persis (dicocokkan otomatis ke 61 toko).",
        "Format tanggal DD/MM/YYYY.", "Kunjungan wajib angka ≥ 0; transaksi opsional."]})})


def kol_template() -> bytes:
    df = pd.DataFrame({"nama": ["Contoh Akun"], "platform": ["Instagram"], "username": ["@contoh.akun"],
                       "link": ["https://instagram.com/contoh.akun"], "tipe": ["kol"], "kategori": [""],
                       "bio": ["Inspirasi interior rumah minimalis"], "kota_domisili": ["Bekasi"], "follower": [125000],
                       "avg_views": [42000], "er": [4.8], "deliverable": ["reels"], "harga": [3500000], "kontak": ["+62 812 0000 0000"],
                       "badan_hukum": [False], "punya_npwp": [True]})
    return _xlsx({"kol": df, "petunjuk": pd.DataFrame({"Petunjuk": [
        "tipe: kol / portal · platform: Instagram / TikTok / Portal News.",
        "kategori boleh kosong — disarankan otomatis dari bio (Comedy/Beauty/Lifestyle/Culinary/General).",
        "Akun yang sudah ada (username/link sama) akan digabung, bukan dibuat ganda."]})})


def _xlsx(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, d in sheets.items():
            d.to_excel(w, sheet_name=name, index=False)
    return buf.getvalue()


def to_excel(df: pd.DataFrame, name: str = "data") -> bytes:
    return _xlsx({name: df})
