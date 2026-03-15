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
    HRFlowable, KeepTogether, Flowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
import math


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


class LektesIcon(Flowable):
    """
    Draws the Lektes diamond icon (Option C) directly on the canvas.
    size: diameter of the bounding square in points.
    on_dark: True = white dots (for dark banner), False = green diamond (for light bg)
    """
    def __init__(self, size=28, on_dark=True):
        Flowable.__init__(self)
        self.size = size
        self.on_dark = on_dark
        self.width  = size
        self.height = size

    def draw(self):
        c = self.canv
        s = self.size
        cx, cy = s / 2, s / 2
        r = s * 0.46          # half-diagonal of diamond
        dot_r   = s * 0.055   # outer dots
        centre_r= s * 0.095   # centre gold dot
        grid    = s * 0.235   # dot grid offset

        # Diamond background
        c.saveState()
        c.transform(1, 0, 0, 1, cx, cy)
        c.rotate(45)
        corner_r = s * 0.22
        fill_col = colors.HexColor('#2d7a4f')
        c.setFillColor(fill_col)
        c.setStrokeColor(colors.HexColor('#38a169'))
        c.setLineWidth(0.6)
        w = r * 1.42
        c.roundRect(-w/2, -w/2, w, w, corner_r, stroke=1, fill=1)
        c.restoreState()

        # Outer 8 dots (white/cream)
        dot_color = colors.HexColor('#faf7f2')
        c.setFillColor(dot_color)
        c.setFillColor(colors.Color(250/255, 247/255, 242/255, alpha=0.7))
        for dx, dy in [(-grid,-grid),(0,-grid),(grid,-grid),
                        (-grid,0),            (grid,0),
                        (-grid, grid),(0, grid),(grid, grid)]:
            c.circle(cx+dx, cy+dy, dot_r, stroke=0, fill=1)

        # Centre gold dot
        c.setFillColor(colors.HexColor('#c9a96e'))
        c.setFillColor(colors.Color(201/255, 169/255, 110/255, alpha=0.95))
        c.circle(cx, cy, centre_r, stroke=0, fill=1)

        # Connecting lines
        c.setStrokeColor(colors.HexColor('#faf7f2'))
        c.setStrokeColor(colors.Color(250/255, 247/255, 242/255, alpha=0.3))
        c.setLineWidth(0.5)
        c.line(cx-grid, cy-grid, cx+grid, cy+grid)
        c.line(cx+grid, cy-grid, cx-grid, cy+grid)
        c.line(cx-grid, cy,      cx+grid, cy)
        c.line(cx,      cy-grid, cx,      cy+grid)

        # Reset alpha
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)


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
    icon_cell = Table([[LektesIcon(size=30, on_dark=True),
                        Paragraph('<font color="#ffffff" size="14"><b>Lektes</b></font>', styles['Normal'])]],
                      colWidths=[36, W*0.4])
    icon_cell.setStyle(TableStyle([
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING',   (0,0), (-1,-1), 0),
        ('RIGHTPADDING',  (0,0), (-1,-1), 4),
        ('TOPPADDING',    (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('BACKGROUND',    (0,0), (-1,-1), DARK_GREEN),
    ]))
    header_data = [[
        icon_cell,
        Paragraph('<font color="#8aaa95" size="8">AI Recruitment Screening Report</font>', styles['Normal']),
    ]]
    header_tbl = Table(header_data, colWidths=[W*0.55, W*0.45])
    header_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), DARK_GREEN),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING',(0,0), (-1,-1), 14),
        ('RIGHTPADDING',(0,0),(-1,-1), 14),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING',(0,0),(-1,-1), 10),
        ('ALIGN',      (1,0), (1,0),   'RIGHT'),
        ('ROUNDEDCORNERS', [6,6,6,6]),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 10*mm))

    # ── JOB TITLE BLOCK ───────────────────────────────────────────────────────
    story.append(Paragraph('SCREENING RESULTS FOR', sTitle))
    story.append(Paragraph(job_title, sJobTitle))
    story.append(Paragraph(f'{len(candidates)} candidates screened and ranked', sMeta))
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
        'Generated by Lektes  ·  lektes.nimbus-24.com  ·  AI-powered recruitment screening',
        ParagraphStyle('ft', fontSize=8, textColor=TEXT_LIGHT,
            fontName='Helvetica', alignment=TA_CENTER)
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()
