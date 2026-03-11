"""
Lektes PDF Report Generator
Generates a branded PDF screening report using reportlab.
"""
import io
from typing import List
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT


# ── Colour palette matching the UI ──────────────────────────────────────────
DARK_GREEN  = colors.HexColor('#1a2e1a')
EMERALD     = colors.HexColor('#2d7a4f')
EMERALD_LT  = colors.HexColor('#edf7f1')
EMERALD_BD  = colors.HexColor('#b8dfc8')
CREAM       = colors.HexColor('#faf7f2')
CREAM2      = colors.HexColor('#f3ede3')
SAND        = colors.HexColor('#c9a96e')
RED         = colors.HexColor('#c0392b')
RED_LT      = colors.HexColor('#fdf0ee')
RED_BD      = colors.HexColor('#f0b8b0')
TEXT_DARK   = colors.HexColor('#1c2b1c')
TEXT_MID    = colors.HexColor('#4a6355')
TEXT_LIGHT  = colors.HexColor('#8aaa95')
BORDER      = colors.HexColor('#ddd5c4')
GOLD        = colors.HexColor('#f0c040')
SILVER      = colors.HexColor('#cccccc')
BRONZE      = colors.HexColor('#e8a080')
WHITE       = colors.white


def _score_color(score: int):
    if score >= 70: return EMERALD
    if score >= 45: return SAND
    return RED

def _score_label(score: int) -> str:
    if score >= 70: return "Strong Match"
    if score >= 45: return "Partial Match"
    return "Weak Match"

def _rank_color(rank: int):
    if rank == 1: return GOLD
    if rank == 2: return SILVER
    if rank == 3: return BRONZE
    return BORDER


def generate_pdf_report(job_title: str, hr_email: str, candidates: List[dict]) -> bytes:
    """
    Generate a branded PDF report and return as bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=16*mm,  bottomMargin=16*mm,
    )
    W = A4[0] - 36*mm  # usable width

    styles = getSampleStyleSheet()

    # ── Custom styles ─────────────────────────────────────────────────────────
    sTitle = ParagraphStyle('sTitle',
        fontSize=9, textColor=TEXT_LIGHT, fontName='Helvetica',
        spaceAfter=2)
    sJobTitle = ParagraphStyle('sJobTitle',
        fontSize=22, textColor=TEXT_DARK, fontName='Helvetica-Bold',
        spaceAfter=4)
    sMeta = ParagraphStyle('sMeta',
        fontSize=10, textColor=TEXT_LIGHT, fontName='Helvetica',
        spaceAfter=0)
    sCandName = ParagraphStyle('sCandName',
        fontSize=13, textColor=TEXT_DARK, fontName='Helvetica-Bold',
        spaceAfter=1)
    sCandMeta = ParagraphStyle('sCandMeta',
        fontSize=9,  textColor=TEXT_LIGHT, fontName='Helvetica',
        spaceAfter=2)
    sBody = ParagraphStyle('sBody',
        fontSize=9, textColor=TEXT_DARK, fontName='Helvetica',
        leading=13, spaceAfter=0)
    sBodyGreen = ParagraphStyle('sBodyGreen',
        fontSize=9, textColor=colors.HexColor('#1a4a2e'),
        fontName='Helvetica', leading=13)
    sBodyRed = ParagraphStyle('sBodyRed',
        fontSize=9, textColor=colors.HexColor('#7a1a1a'),
        fontName='Helvetica', leading=13)
    sLabel = ParagraphStyle('sLabel',
        fontSize=7, textColor=TEXT_LIGHT, fontName='Helvetica-Bold',
        spaceAfter=2)

    story = []

    # ── HEADER BANNER ─────────────────────────────────────────────────────────
    header_data = [[
        Paragraph('<font color="#ffffff" size="14"><b>🌿 Lektes</b></font>', styles['Normal']),
        Paragraph('<font color="#8aaa95" size="8">AI Recruitment Screening Report</font>', styles['Normal']),
    ]]
    header_tbl = Table(header_data, colWidths=[W*0.5, W*0.5])
    header_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), DARK_GREEN),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING',(0,0), (-1,-1), 14),
        ('RIGHTPADDING',(0,0),(-1,-1), 14),
        ('TOPPADDING', (0,0), (-1,-1), 12),
        ('BOTTOMPADDING',(0,0),(-1,-1), 12),
        ('ALIGN',      (1,0), (1,0),   'RIGHT'),
        ('ROUNDEDCORNERS', [6,6,6,6]),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 10*mm))

    # ── JOB TITLE BLOCK ───────────────────────────────────────────────────────
    story.append(Paragraph('SCREENING RESULTS FOR', sTitle))
    story.append(Paragraph(job_title, sJobTitle))
    story.append(Paragraph(f'{len(candidates)} candidates screened and ranked · {hr_email}', sMeta))
    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width=W, thickness=1, color=BORDER))
    story.append(Spacer(1, 5*mm))

    # ── CANDIDATE CARDS ───────────────────────────────────────────────────────
    for c in candidates:
        rank    = c.get('rank') or c.get('position', '—')
        name    = c.get('name') or c.get('full_name') or 'Unknown'
        email   = c.get('email') or '—'
        score   = int(c.get('match_score') or 0)
        exp     = c.get('experience_years')
        edu     = c.get('education') or ''
        just    = c.get('justification') or ''
        flags   = c.get('red_flags') or ''
        sc      = _score_color(score)
        rc      = _rank_color(int(rank) if str(rank).isdigit() else 99)

        # Strip verified profiles line from justification
        ver_idx = just.find(' Verified profiles:')
        pros    = just[:ver_idx].strip() if ver_idx > -1 else just.strip()
        ver     = just[ver_idx:].strip() if ver_idx > -1 else ''

        # Rank + Name + Score row
        top_data = [[
            Paragraph(f'<b>{rank}</b>', ParagraphStyle('rk',
                fontSize=14, textColor=TEXT_DARK,
                fontName='Helvetica-Bold', alignment=TA_CENTER)),
            Paragraph(f'<b>{name}</b><br/>'
                      f'<font size="8" color="#8aaa95">{email}'
                      f'{" · " + str(exp) + " yrs exp" if exp else ""}'
                      f'{"  🎓 " + edu if edu else ""}</font>',
                      ParagraphStyle('nm', fontSize=12, fontName='Helvetica-Bold',
                          textColor=TEXT_DARK, leading=16)),
            Paragraph(f'<b><font size="20" color="{sc.hexval()}">{score}%</font></b><br/>'
                      f'<font size="8" color="{sc.hexval()}">{_score_label(score)}</font>',
                      ParagraphStyle('sc', fontSize=20, fontName='Helvetica-Bold',
                          alignment=TA_CENTER, leading=22)),
        ]]
        top_tbl = Table(top_data, colWidths=[12*mm, W-12*mm-20*mm, 20*mm])
        top_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,-1), CREAM),
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN',         (0,0), (0,0),   'CENTER'),
            ('ALIGN',         (2,0), (2,0),   'CENTER'),
            ('LEFTPADDING',   (0,0), (-1,-1), 8),
            ('RIGHTPADDING',  (0,0), (-1,-1), 8),
            ('TOPPADDING',    (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('BOX',           (0,0), (0,0),   1.5, rc),
            ('ROUNDEDCORNERS',(0,0), (0,0),   [20]),
        ]))

        card_elements = [top_tbl]

        # Strengths box
        if pros:
            pros_text = pros + (f' {ver}' if ver else '')
            pros_data = [[
                Paragraph('✅  STRENGTHS', ParagraphStyle('pl',
                    fontSize=7, fontName='Helvetica-Bold',
                    textColor=EMERALD, spaceAfter=3)),
            ],[
                Paragraph(pros_text, sBodyGreen),
            ]]
            pros_tbl = Table(pros_data, colWidths=[W])
            pros_tbl.setStyle(TableStyle([
                ('BACKGROUND',    (0,0), (-1,-1), EMERALD_LT),
                ('LEFTPADDING',   (0,0), (-1,-1), 10),
                ('RIGHTPADDING',  (0,0), (-1,-1), 10),
                ('TOPPADDING',    (0,0), (-1,-1), 7),
                ('BOTTOMPADDING', (0,0), (-1,-1), 7),
                ('BOX',           (0,0), (-1,-1), 1, EMERALD_BD),
                ('ROUNDEDCORNERS',(0,0), (-1,-1), [4]),
            ]))
            card_elements.append(Spacer(1, 2*mm))
            card_elements.append(pros_tbl)

        # Concerns box
        if flags:
            flag_data = [[
                Paragraph('⚠️  CONCERNS', ParagraphStyle('fl',
                    fontSize=7, fontName='Helvetica-Bold',
                    textColor=RED, spaceAfter=3)),
            ],[
                Paragraph(flags, sBodyRed),
            ]]
            flag_tbl = Table(flag_data, colWidths=[W])
            flag_tbl.setStyle(TableStyle([
                ('BACKGROUND',    (0,0), (-1,-1), RED_LT),
                ('LEFTPADDING',   (0,0), (-1,-1), 10),
                ('RIGHTPADDING',  (0,0), (-1,-1), 10),
                ('TOPPADDING',    (0,0), (-1,-1), 7),
                ('BOTTOMPADDING', (0,0), (-1,-1), 7),
                ('BOX',           (0,0), (-1,-1), 1, RED_BD),
                ('ROUNDEDCORNERS',(0,0), (-1,-1), [4]),
            ]))
            card_elements.append(Spacer(1, 2*mm))
            card_elements.append(flag_tbl)

        story.append(KeepTogether(card_elements))
        story.append(Spacer(1, 5*mm))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=1, color=BORDER))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(
        'Generated by Lektes · lektes.nimbus-24.com · AI-powered recruitment screening',
        ParagraphStyle('ft', fontSize=8, textColor=TEXT_LIGHT,
            fontName='Helvetica', alignment=TA_CENTER)
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
