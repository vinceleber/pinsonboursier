"""
report_generator.py — Rapport Social Investing complet (PDF), généré chaque jour.

Police : Montserrat si les fichiers statiques sont dans bot/fonts/ (Montserrat-Regular/Medium/Bold/Light.ttf),
sinon Poppins (fournie). Aucun symbole hors des glyphes disponibles (pas d'émoji, pas de ✓/★).
"""
import math
import os
from datetime import datetime, date
from xml.sax.saxutils import escape as esc

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String, Wedge
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle, CondPageBreak, KeepTogether)
from social_fetcher import insider_signal_from

HERE = os.path.dirname(os.path.abspath(__file__))

# ─── POLICES ─────────────────────────────────────────────────────────────────
def _register_fonts() -> str:
    fdir = os.path.join(HERE, "fonts")
    for fam in ("Montserrat", "Poppins"):
        files = {"Body": f"{fam}-Regular.ttf", "Body-Medium": f"{fam}-Medium.ttf",
                 "Body-Bold": f"{fam}-Bold.ttf", "Body-Light": f"{fam}-Light.ttf"}
        paths = {k: os.path.join(fdir, v) for k, v in files.items()}
        if all(os.path.exists(p) for p in paths.values()):
            try:
                for name, p in paths.items():
                    pdfmetrics.registerFont(TTFont(name, p))
                registerFontFamily("Body", normal="Body", bold="Body-Bold",
                                   italic="Body", boldItalic="Body-Bold")
                return fam
            except Exception as e:  # police invalide (ex. police variable) → police suivante
                print(f"[WARN] Police {fam} inutilisable ({e})")
    print("[WARN] Aucune police TTF trouvée — Helvetica utilisée")
    return "Helvetica"

FONT_FAMILY = _register_fonts()
if FONT_FAMILY == "Helvetica":
    F, FM, FB, FL = "Helvetica", "Helvetica", "Helvetica-Bold", "Helvetica"
else:
    F, FM, FB, FL = "Body", "Body-Medium", "Body-Bold", "Body-Light"
print(f"[OK] Police du rapport : {FONT_FAMILY}")

# ─── PALETTE ─────────────────────────────────────────────────────────────────
WHITE = colors.HexColor("#FFFFFF"); PAPER = colors.HexColor("#F9FAFB"); PAPER2 = colors.HexColor("#F1F5F9")
NAVY = colors.HexColor("#0F2044"); BLUE = colors.HexColor("#1D4ED8"); BLUE_MED = colors.HexColor("#3B82F6")
EMERALD = colors.HexColor("#059669"); GREEN = colors.HexColor("#16A34A")
GREEN_LIGHT = colors.HexColor("#D1FAE5"); AMBER = colors.HexColor("#D97706"); AMBER_LIGHT = colors.HexColor("#FEF3C7")
RED = colors.HexColor("#DC2626"); RED_LIGHT = colors.HexColor("#FEE2E2"); CRIMSON = colors.HexColor("#7F1D1D")
SLATE_900 = colors.HexColor("#0F172A"); SLATE_700 = colors.HexColor("#334155")
SLATE_500 = colors.HexColor("#64748B"); SLATE_300 = colors.HexColor("#CBD5E1")

PAGE_W, PAGE_H = A4
M = 16 * mm
BW = PAGE_W - 2 * M

_CTX = {"date": "", "demo": False}   # contexte d'en-tête de page


# ─── STYLES & UTILITAIRES ────────────────────────────────────────────────────
def ps(name, **kw):
    d = dict(fontName=F, fontSize=9, leading=14, textColor=SLATE_900)
    d.update(kw)
    return ParagraphStyle(name, **d)

ST = {
    "c_tag": ps("ct", fontName=FB, fontSize=9, textColor=BLUE_MED, alignment=TA_CENTER),
    "c_title": ps("ctt", fontName=FB, fontSize=36, leading=44, textColor=NAVY, alignment=TA_CENTER),
    "c_sub": ps("cs", fontName=FL, fontSize=13, leading=20, textColor=SLATE_500, alignment=TA_CENTER),
    "c_date": ps("cd", fontSize=10, textColor=SLATE_500, alignment=TA_CENTER),
    "h2": ps("h2", fontName=FB, fontSize=11, leading=16, textColor=NAVY, spaceBefore=10, spaceAfter=3),
    "kicker": ps("kk", fontName=FB, fontSize=8, textColor=BLUE_MED, spaceBefore=10, spaceAfter=2),
    "body": ps("body", fontSize=8.5, leading=13.5, textColor=SLATE_700, alignment=TA_JUSTIFY, spaceAfter=4),
    "note": ps("note", fontName=FL, fontSize=7, leading=11, textColor=SLATE_500, alignment=TA_CENTER),
    "warn": ps("warn", fontName=FM, fontSize=7.5, leading=11, textColor=AMBER, alignment=TA_LEFT),
    "disc": ps("disc", fontName=FL, fontSize=6.5, leading=10, textColor=SLATE_500, alignment=TA_CENTER),
}

def sp(h=6): return Spacer(1, h)

def P(text, size=7.5, color=SLATE_700, bold=False, align=TA_LEFT, leading=None):
    return Paragraph(esc(str(text)), ParagraphStyle(
        "cell", fontName=FB if bold else F, fontSize=size, leading=leading or size + 3.5,
        textColor=color, alignment=align))

def fp(p, ticker=""):
    if p is None: return "N/D"
    cur = "C$" if ticker.endswith(".TO") else "$"
    return f"{cur}{p:,.0f}" if p >= 1000 else f"{cur}{p:,.2f}"

def fn(x, d=1, sign=False):
    if x is None: return "N/D"
    return f"{x:+,.{d}f}".replace("-", "−") if sign else f"{x:,.{d}f}".replace("-", "−")

def fpct(x, d=1):
    return "N/D" if x is None else fn(x, d, sign=True) + " %"

def sig_color(s):
    if s in ("ACHAT", "Achat", "Golden Cross"): return EMERALD
    if s in ("VENTE", "Vente", "Death Cross", "Survendu"): return RED
    if s in ("PRUDENCE", "Surachat"): return AMBER
    return SLATE_500

def rsi_color(label):
    return RED if label == "Survendu" else (AMBER if label == "Surachat" else SLATE_500)

def score_color(s):
    if s is None: return SLATE_500
    return RED if s <= 25 else AMBER if s <= 45 else SLATE_500 if s <= 55 else GREEN if s <= 75 else EMERALD

def days_since(iso: str) -> int:
    try:
        return (date.today() - datetime.strptime(iso, "%Y-%m-%d").date()).days
    except Exception:
        return 0

def date_fr_from_iso(iso: str) -> str:
    from data_fetcher import MONTHS_FR
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return f"{d.day} {MONTHS_FR[d.month - 1]} {d.year}"
    except Exception:
        return iso


def section_header(num, title, color=NAVY):
    t = Table([[Paragraph(esc(f"{num}   {title}"), ParagraphStyle(
        "sh", fontName=FB, fontSize=12.5, leading=17, textColor=WHITE))]], colWidths=[BW])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), color),
                           ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                           ("LEFTPADDING", (0, 0), (-1, -1), 14)]))
    return t


def table(rows, widths, hdr_bg=NAVY, left_cols=(), cell_styles=None, font_size=7.5):
    """Tableau sobre : en-tête coloré, lignes alternées, texte centré (colonnes texte à gauche)."""
    total = sum(widths)
    widths = [w * BW / total for w in widths] if total > BW else widths
    cell_styles = cell_styles or {}
    st = [("BACKGROUND", (0, 0), (-1, 0), hdr_bg), ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
          ("FONTNAME", (0, 0), (-1, 0), FB), ("FONTSIZE", (0, 0), (-1, 0), font_size - 0.5),
          ("FONTNAME", (0, 1), (-1, -1), F), ("FONTSIZE", (0, 1), (-1, -1), font_size),
          ("TEXTCOLOR", (0, 1), (-1, -1), SLATE_900), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 5),
          ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, -1), 0.3, SLATE_300),
          ("BOX", (0, 0), (-1, -1), 0.8, SLATE_300)]
    for i in range(1, len(rows)):
        st.append(("BACKGROUND", (0, i), (-1, i), WHITE if i % 2 else PAPER))
    for c in left_cols:
        st += [("ALIGN", (c, 0), (c, -1), "LEFT"), ("LEFTPADDING", (c, 0), (c, -1), 8)]
    for (r, c), (fg, bold) in cell_styles.items():
        st.append(("TEXTCOLOR", (c, r), (c, r), fg))
        if bold: st.append(("FONTNAME", (c, r), (c, r), FB))
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle(st))
    return t


class PageDeco:
    def __call__(self, c, doc):
        c.saveState()
        c.setFillColor(WHITE); c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        c.setFillColor(NAVY); c.rect(0, PAGE_H - 11 * mm, PAGE_W, 11 * mm, fill=1, stroke=0)
        c.setFillColor(EMERALD); c.rect(0, PAGE_H - 11 * mm - 2, PAGE_W, 2.5, fill=1, stroke=0)
        c.setFillColor(BLUE); c.rect(0, PAGE_H - 11 * mm, 3, 11 * mm, fill=1, stroke=0)
        c.setFillColor(WHITE); c.setFont(FB, 8)
        c.drawString(M + 8, PAGE_H - 7.5 * mm, "LE PINSON BOURSIER  ·  SOCIAL INVESTING")
        c.setFont(F, 8); c.setFillColor(SLATE_300)
        c.drawRightString(PAGE_W - M, PAGE_H - 7.5 * mm, f"{_CTX['date'].upper()}  ·  PAGE {doc.page}")
        if _CTX["demo"]:
            c.setFillColor(RED); c.setFont(FB, 8)
            c.drawCentredString(PAGE_W / 2, PAGE_H - 7.5 * mm, "DÉMO — DONNÉES SYNTHÉTIQUES")
        c.setFillColor(PAPER2); c.rect(0, 0, PAGE_W, 9 * mm, fill=1, stroke=0)
        c.setStrokeColor(SLATE_300); c.setLineWidth(0.5); c.line(0, 9 * mm, PAGE_W, 9 * mm)
        c.setFillColor(SLATE_500); c.setFont(F, 6.5)
        c.drawString(M, 3.5 * mm, "Document confidentiel — Ne constitue pas un conseil en placement")
        c.drawRightString(PAGE_W - M, 3.5 * mm, "© Le Pinson Boursier")
        c.setFillColor(NAVY); c.circle(PAGE_W / 2, 4.5 * mm, 3.5 * mm, fill=1, stroke=0)
        c.setFillColor(WHITE); c.setFont(FB, 7); c.drawCentredString(PAGE_W / 2, 4.5 * mm - 2.5, str(doc.page))
        c.restoreState()


# ─── GRAPHIQUES ──────────────────────────────────────────────────────────────
def gauge(score, label="", sub="", w=130, h=100):
    """Jauge semi-circulaire 0-100. Angle(v) = 180° - 1.8·v ; secteurs dessinés en sens antihoraire."""
    d = Drawing(w, h)
    cx, cy, ro, ri = w / 2, 34, 44, 27
    for z0, z1, col in ((0, 25, RED), (25, 45, AMBER), (45, 55, SLATE_300), (55, 75, GREEN), (75, 100, EMERALD)):
        d.add(Wedge(cx, cy, ro, 180 - z1 * 1.8, 180 - z0 * 1.8, radius1=ri,
                    fillColor=col, strokeColor=WHITE, strokeWidth=0.8))
    if score is not None:
        a = math.radians(180 - score * 1.8)
        d.add(Line(cx, cy, cx + ro * 0.82 * math.cos(a), cy + ro * 0.82 * math.sin(a),
                   strokeColor=NAVY, strokeWidth=2.2))
    d.add(Circle(cx, cy, 4, fillColor=NAVY, strokeColor=WHITE, strokeWidth=1))
    d.add(String(cx, cy - 16, "N/D" if score is None else str(score), fontName=FB, fontSize=14,
                 fillColor=NAVY, textAnchor="middle"))
    if sub:
        d.add(String(cx, cy - 28, sub, fontName=FB, fontSize=7, fillColor=score_color(score), textAnchor="middle"))
    if label:
        d.add(String(cx, cy + ro + 10, label, fontName=FB, fontSize=7.2, fillColor=NAVY, textAnchor="middle"))
    for v in (0, 50, 100):
        a = math.radians(180 - v * 1.8)
        d.add(String(cx + (ro + 7) * math.cos(a), cy + (ro + 7) * math.sin(a) - 2, str(v),
                     fontName=F, fontSize=5.5, fillColor=SLATE_500, textAnchor="middle"))
    return d


def sparkline(values, w=130, h=80, col=BLUE, label=""):
    d = Drawing(w, h)
    if label:
        d.add(String(w / 2, h - 9, label, fontName=FB, fontSize=6.8, fillColor=SLATE_700, textAnchor="middle"))
    if not values or len(values) < 2:
        d.add(String(w / 2, h / 2 - 6, "N/D", fontName=FB, fontSize=9, fillColor=SLATE_500, textAnchor="middle"))
        return d
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    pad, top = 10, 18
    xs = [pad + i * (w - 2 * pad) / (len(values) - 1) for i in range(len(values))]
    ys = [8 + (v - lo) / rng * (h - top - 12) for v in values]
    pts = [(xs[0], 6)] + list(zip(xs, ys)) + [(xs[-1], 6)]
    d.add(Polygon([c for p in pts for c in p], fillColor=colors.Color(col.red, col.green, col.blue, 0.12), strokeColor=None))
    for i in range(len(xs) - 1):
        d.add(Line(xs[i], ys[i], xs[i + 1], ys[i + 1], strokeColor=col, strokeWidth=1.5))
    d.add(Circle(xs[-1], ys[-1], 3.2, fillColor=col, strokeColor=WHITE, strokeWidth=1))
    d.add(String(2, 1, f"min {lo}", fontName=F, fontSize=5.5, fillColor=SLATE_500))
    d.add(String(w - 2, 1, f"max {hi}", fontName=F, fontSize=5.5, fillColor=SLATE_500, textAnchor="end"))
    return d


def bars(items, width=BW):
    """items = [(libellé, valeur 0-100 | None, couleur)] → barres horizontales."""
    h = 17 * len(items) + 6
    d = Drawing(width, h)
    lw, bw = 150, width - 150 - 45
    for i, (lbl, val, col) in enumerate(items):
        y = h - 17 * (i + 1)
        d.add(String(0, y + 2, lbl, fontName=F, fontSize=7.5, fillColor=SLATE_700))
        d.add(Rect(lw, y, bw, 10, rx=4, ry=4, fillColor=PAPER2, strokeColor=None))
        if val is not None and val > 0:
            d.add(Rect(lw, y, bw * min(val, 100) / 100, 10, rx=4, ry=4, fillColor=col, strokeColor=None))
        d.add(String(lw + bw + 6, y + 2, "N/D" if val is None else f"{val:.0f}", fontName=FB, fontSize=8, fillColor=SLATE_900))
    return d


def upside_chart(rows, width=BW):
    """rows = [(ticker, potentiel %)] → barres (vert hausse, rouge baisse)."""
    n = len(rows)
    h = 15 * n + 22
    d = Drawing(width, h)
    lw = 48
    avail = width - lw - 60
    mx = max([abs(v) for _, v in rows] + [1])
    for i, (t, v) in enumerate(rows):
        y = h - 18 - 15 * i
        col = EMERALD if v >= 20 else BLUE if v >= 0 else RED
        d.add(String(lw - 6, y + 1, t, fontName=FB, fontSize=7.5, fillColor=NAVY, textAnchor="end"))
        d.add(Rect(lw, y - 1, avail, 9, rx=3, ry=3, fillColor=PAPER2, strokeColor=None))
        d.add(Rect(lw, y - 1, max(avail * abs(v) / mx, 2), 9, rx=3, ry=3, fillColor=col, strokeColor=None))
        d.add(String(lw + avail + 6, y + 1, fpct(v, 0), fontName=FB, fontSize=7.5, fillColor=col))
    d.add(String(width / 2, 2, "Écart entre la cible d'analystes (saisie éditoriale) et le cours du jour",
                 fontName=F, fontSize=6.3, fillColor=SLATE_500, textAnchor="middle"))
    return d


def aaii_chart(hist, width=BW, height=190):
    """Barres du spread Bull-Bear : échelle calculée sur les données, étiquettes de période dans une bande dédiée."""
    d = Drawing(width, height)
    n = max(len(hist), 1)
    lab_h, top_h, left = 24, 22, 40            # bande d'étiquettes (bas), titre (haut), marge gauche
    plot_bot, plot_top = lab_h + 14, height - top_h - 12
    vmax = max([abs(v) for _, v in hist] + [25]) * 1.05
    vmin_v = min([v for _, v in hist] + [-25])
    vmax_v = max([v for _, v in hist] + [25])
    scale = (plot_top - plot_bot) / (vmax_v - vmin_v + 1e-9)
    mid = plot_bot - vmin_v * scale
    slot = (width - left - 10) / n
    ticks = sorted({-50, -25, 0, 25, 50} & set(range(int(vmin_v) - 25, int(vmax_v) + 26)))
    for v in ticks:
        y = mid + v * scale
        if plot_bot - 12 <= y <= plot_top + 12:
            d.add(Line(left, y, width - 10, y, strokeColor=SLATE_300, strokeWidth=0.5))
            d.add(String(2, y - 3, fn(v, 0, True) + "%", fontName=F, fontSize=6, fillColor=SLATE_500))
    d.add(Line(left, mid, width - 10, mid, strokeColor=SLATE_700, strokeWidth=0.8))
    for i, (lbl, v) in enumerate(hist):
        cx = left + i * slot + slot / 2
        bwid = slot * 0.62
        col = RED if v < -20 else AMBER if v < 0 else GREEN
        hh = max(abs(v) * scale, 1)
        d.add(Rect(cx - bwid / 2, mid - hh if v < 0 else mid, bwid, hh, fillColor=col, strokeColor=None, rx=2, ry=2))
        d.add(String(cx, (mid - hh - 8) if v < 0 else (mid + hh + 3), fn(v, 1, True) + "%",
                     fontName=FB, fontSize=6.5, fillColor=col, textAnchor="middle"))
        lines = lbl.split("\n")
        for j, line in enumerate(lines):
            d.add(String(cx, lab_h - 8 - j * 8 + (0 if len(lines) > 1 else -4), line, fontName=F, fontSize=6,
                         fillColor=SLATE_500, textAnchor="middle"))
    d.add(String(width / 2, height - 10, "AAII Bull-Bear Spread — extrêmes historiques et lecture actuelle",
                 fontName=FB, fontSize=8, fillColor=NAVY, textAnchor="middle"))
    return d


def sector_donut(items, palette, width=BW * 0.46, height=130):
    """Donut : répartition des titres des deux listes par secteur (items = [(libellé, nombre)])."""
    d = Drawing(width, height)
    total = sum(v for _, v in items) or 1
    cx, cy, r_out, r_in = 62, height / 2, 54, 30
    start = 90.0
    for (lbl, v), col in zip(items, palette):
        sweep = 360.0 * v / total
        d.add(Wedge(cx, cy, r_out, start - sweep, start, radius1=r_in, fillColor=col, strokeColor=WHITE, strokeWidth=1.5))
        start -= sweep
    d.add(String(cx, cy + 1, str(total), fontName=FB, fontSize=14, fillColor=NAVY, textAnchor="middle"))
    d.add(String(cx, cy - 9, "titres", fontName=F, fontSize=6.5, fillColor=SLATE_500, textAnchor="middle"))
    for i, ((lbl, v), col) in enumerate(zip(items, palette)):
        y = height - 22 - i * 16
        d.add(Rect(135, y, 8, 8, fillColor=col, strokeColor=None, rx=2, ry=2))
        d.add(String(148, y + 1, f"{lbl} — {v} ({100 * v / total:.0f} %)", fontName=F, fontSize=7, fillColor=SLATE_700))
    return d


def mention_chart(rows, width=BW):
    """Barres horizontales des mentions Reddit (24 h) : rows = [(ticker, mentions, variation %)]."""
    n = len(rows)
    h = n * 15 + 16
    d = Drawing(width, h)
    mx = max([m for _, m, _ in rows] + [1])
    x0, x1 = 44, width - 70
    for i, (t, m, chg) in enumerate(rows):
        y = h - 14 - i * 15
        d.add(String(2, y + 1, t, fontName=FB, fontSize=7, fillColor=NAVY))
        d.add(Rect(x0, y - 1, x1 - x0, 9, fillColor=PAPER2, strokeColor=None, rx=3, ry=3))
        d.add(Rect(x0, y - 1, max((x1 - x0) * m / mx, 2), 9, fillColor=BLUE if (chg or 0) >= 0 else AMBER, strokeColor=None, rx=3, ry=3))
        d.add(String(x1 + 6, y + 1, f"{m:,}".replace(",", " "), fontName=FB, fontSize=7, fillColor=SLATE_700))
        if chg is not None:
            d.add(String(width - 2, y + 1, ("+" if chg >= 0 else "−") + f"{abs(chg):.0f} %".replace(".", ","),
                         fontName=F, fontSize=6.5, fillColor=EMERALD if chg >= 0 else RED, textAnchor="end"))
    return d


def verdict(text, col):
    t = Table([[Paragraph(esc(text).replace("\n", "<br/>"), ParagraphStyle(
        "vp", fontName=FB, fontSize=10.5, leading=16, textColor=col, alignment=TA_CENTER))]], colWidths=[BW])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.Color(col.red, col.green, col.blue, 0.07)),
                           ("BOX", (0, 0), (-1, -1), 2.2, col), ("TOPPADDING", (0, 0), (-1, -1), 11),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 11)]))
    return t


def kpi_strip(items):
    w = BW / len(items)
    cells = []
    for label, value, sub, col in items:
        it = Table([[P(label, 7, SLATE_500, True, TA_CENTER)],
                    [Paragraph(esc(value), ParagraphStyle("kv", fontName=FB, fontSize=16, leading=20, textColor=col, alignment=TA_CENTER))],
                    [P(sub, 7.5, col, False, TA_CENTER)]], colWidths=[w - 8])
        it.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                                ("LINEBELOW", (0, 1), (-1, 1), 2, col)]))
        cells.append(it)
    r = Table([cells], colWidths=[w] * len(items))
    r.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, SLATE_300), ("LINEBEFORE", (1, 0), (-1, -1), 0.5, SLATE_300),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return r


def stale_note(iso, max_days, what):
    """Avertissement visible quand un contenu éditorial vieillit."""
    age = days_since(iso)
    txt = f"{what} : saisie éditoriale du {date_fr_from_iso(iso)}, non rafraîchie automatiquement."
    if age > max_days:
        txt += f" ATTENTION : {age} jours — à mettre à jour (bot/content.json)."
        return Paragraph(esc(txt), ST["warn"])
    return Paragraph(esc(txt), ST["note"])


# ─── SIGNAUX ─────────────────────────────────────────────────────────────────
SYM = {"ACHAT": "+", "VENTE": "−", "NEUTRE": "="}
SYM_BG = {"ACHAT": GREEN_LIGHT, "VENTE": RED_LIGHT, "NEUTRE": AMBER_LIGHT}


def pe_signal(pe, sector_pe):
    if not pe or not sector_pe: return "NEUTRE"
    r = pe / sector_pe
    return "ACHAT" if r < 0.85 else "VENTE" if r > 1.5 else "NEUTRE"

def fg_signal(score):
    if score is None: return "NEUTRE"
    return "ACHAT" if score <= 44 else "VENTE" if score >= 74 else "NEUTRE"

def vix_signal(v):
    if v is None: return "NEUTRE"
    return "ACHAT" if v > 30 else "VENTE" if v < 15 else "NEUTRE"

def rsi_signal(r):
    if r is None: return "NEUTRE"
    return "ACHAT" if r < 30 else "VENTE" if r > 70 else "NEUTRE"

def macd_signal(h):
    if h is None: return "NEUTRE"
    return "ACHAT" if h > 0 else "VENTE"

def ma200_signal(q):
    if not q or q.get("ma200") is None: return "NEUTRE"
    ratio = q["price"] / q["ma200"]
    return "ACHAT" if ratio >= 1 else "VENTE" if ratio < 0.95 else "NEUTRE"

def social_signal(ticker, data):
    """Signal Social : ApeWisdom (mentions Reddit sur 24 h) en priorité; à défaut, mentions Reddit directes."""
    ape = ((data.get("social") or {}).get("ape")) or {}
    if ape.get("available"):
        r = ape["by_ticker"].get(ticker.split(".")[0])
        m = r["mentions"] if r else 0
        return "NEUTRE" if m < 5 else ("VENTE" if m >= 300 else "ACHAT")
    reddit = data["reddit"]
    if not reddit.get("available"): return "NEUTRE"
    n = reddit["totals"].get(ticker, 0)
    return "NEUTRE" if n == 0 else ("VENTE" if n >= 10 else "ACHAT")

def insider_signal(it, data):
    """INIT. : Formulaire 4 de la SEC si disponible pour ce titre; sinon saisie manuelle de content.json."""
    ed = ((data.get("social") or {}).get("edgar")) or {}
    if ed.get("available") and it["ticker"] in ed["by_ticker"]:
        return insider_signal_from(ed["by_ticker"][it["ticker"]])
    return it.get("insider", "NEUTRE")

def aaii_signal(spread):
    if spread is None: return "NEUTRE"
    return "ACHAT" if spread < -20 else "VENTE" if spread > 25 else "NEUTRE"


def matrix_table(items, data, content, pe_key, hdr_bg):
    """Matrice de confluence : 9 signaux par titre (les 7 du guide + P/E et AAII)."""
    quotes, reddit = data["quotes"], data["reddit"]
    fgs = data["fg_stocks"]["score"]
    vixq = data["indices"].get("^VIX")
    vix = vixq["price"] if vixq else None
    aa = content["aaii"]
    spread = round(aa["bull"] - aa["bear"], 1)
    hdr = ["TICKER", "P/E", "F&G", "VIX", "RSI", "MACD", "MA200", "SOCIAL", "INIT.", "AAII", "SCORE", "VERDICT"]
    rows, cs = [hdr], {}
    for i, it in enumerate(items, 1):
        q = quotes.get(it["ticker"])
        sigs = [pe_signal(it.get(pe_key), it.get("sector_pe")), fg_signal(fgs), vix_signal(vix),
                rsi_signal(q["rsi"] if q else None), macd_signal(q["macd_hist"] if q else None),
                ma200_signal(q), social_signal(it["ticker"], data), insider_signal(it, data),
                aaii_signal(spread)]
        buy, sell = sigs.count("ACHAT"), sigs.count("VENTE")
        if buy >= 6: v, vc = "FORT ACHAT", EMERALD
        elif buy >= 4: v, vc = "ACHAT", GREEN
        elif sell >= 6: v, vc = "FORT VENTE", RED
        elif sell >= 4: v, vc = "VENTE", RED
        elif sell >= 3: v, vc = "PRUDENCE", AMBER
        else: v, vc = "NEUTRE", SLATE_500
        rows.append([it["ticker"]] + [SYM[s] for s in sigs] + [f"{buy}+ / {sell}−", v])
        for c, s in enumerate(sigs, 1):
            cs[(i, c)] = (sig_color(s), True)
        cs[(i, 11)] = (vc, True)
    t = table(rows, [40] + [30] * 9 + [44, 66], hdr_bg=hdr_bg, cell_styles=cs, font_size=7.5)
    for i in range(1, len(rows)):
        pass
    # fond coloré des cellules de signal
    extra = []
    for i, r in enumerate(rows[1:], 1):
        for c in range(1, 10):
            key = {"+": "ACHAT", "−": "VENTE", "=": "NEUTRE"}[r[c]]
            extra.append(("BACKGROUND", (c, i), (c, i), SYM_BG[key]))
    t.setStyle(TableStyle(extra))
    return t


MATRIX_LEGEND = ("+ signal favorable · − signal défavorable · = neutre. Colonnes : P/E vs médiane sectorielle (éditorial) · "
                 "F&G, VIX et AAII = lecture de marché identique pour tous les titres · RSI (survente < 30 / surachat > 70) · "
                 "MACD (histogramme > 0) · MA200 (prix au-dessus = favorable, > 5 % en dessous = défavorable) · "
                 "SOCIAL (ApeWisdom : 5 à 299 mentions Reddit sur 24 h = intérêt, 300 et plus = excès; à défaut, mentions Reddit directes : 1 à 9 / 10 et plus) · "
                 "INIT. = initiés (formulaire 4 de la SEC sur 45 jours : achats ouverts de 100 000 $ et plus = favorable; ventes de 25 M$ et plus sans achat = défavorable; à défaut, saisie manuelle).")


# ─── TABLEAUX TECHNIQUES ─────────────────────────────────────────────────────
def tech_table(tickers, quotes, hdr_bg=NAVY):
    hdr = ["TICKER", "PRIX", "VAR. 1J", "RSI(14)", "SIGNAL\nRSI", "MACD\nHISTO.", "SIGNAL\nMACD",
           "MA50", "MA200", "TENDANCE", "SIGNAL\nGLOBAL"]
    rows, cs = [hdr], {}
    for t in tickers:
        q = quotes.get(t)
        i = len(rows)
        if not q:
            rows.append([t] + ["N/D"] * 10)
            continue
        rows.append([t, fp(q["price"], t), fpct(q["chg_1d"]), fn(q["rsi"], 0), q["rsi_label"],
                     fn(q["macd_hist"], 2, True), q["macd_label"], fp(q["ma50"], t), fp(q["ma200"], t),
                     q["trend"], q["signal"]])
        cs[(i, 2)] = (EMERALD if q["chg_1d"] >= 0 else RED, True)
        cs[(i, 3)] = (rsi_color(q["rsi_label"]), True); cs[(i, 4)] = (rsi_color(q["rsi_label"]), True)
        cs[(i, 5)] = (sig_color(q["macd_label"]), True); cs[(i, 6)] = (sig_color(q["macd_label"]), True)
        cs[(i, 9)] = (sig_color(q["trend"]), True); cs[(i, 10)] = (sig_color(q["signal"]), True)
    return table(rows, [34, 42, 40, 32, 42, 38, 38, 42, 42, 54, 50], hdr_bg=hdr_bg, cell_styles=cs, font_size=7)


def simple_live_table(items, quotes, hdr_bg=NAVY):
    rows, cs = [["TICKER", "SOCIÉTÉ", "SPÉCIALITÉ / THÈME", "PRIX", "VAR. 1M", "RSI", "TENDANCE", "SIGNAL"]], {}
    for it in items:
        t = it["ticker"]; q = quotes.get(t); i = len(rows)
        if q:
            rows.append([t, P(it["name"]), P(it["note"]), fp(q["price"], t), fpct(q["chg_1m"]), fn(q["rsi"], 0),
                         q["trend"], q["signal"]])
            cs[(i, 4)] = (EMERALD if q["chg_1m"] >= 0 else RED, True)
            cs[(i, 5)] = (rsi_color(q["rsi_label"]), True)
            cs[(i, 6)] = (sig_color(q["trend"]), True); cs[(i, 7)] = (sig_color(q["signal"]), True)
        else:
            rows.append([t, P(it["name"]), P(it["note"])] + ["N/D"] * 5)
    return table(rows, [36, 78, 130, 46, 42, 28, 56, 50], hdr_bg=hdr_bg, left_cols=(1, 2), cell_styles=cs)


def avg(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


# ═════════════════════════════════════════════════════════════════════════════
def build_report(data: dict, content: dict, out_path: str) -> str:
    _CTX["date"] = data["date_fr"]; _CTX["demo"] = data.get("demo", False)
    doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=15 * mm, bottomMargin=14 * mm,
                            title=f"Le Pinson Boursier — Rapport de marché — {data['date_fr']}", author="Le Pinson Boursier")
    deco = PageDeco()
    S = []
    q = data["quotes"]; idx = data["indices"]; fgs = data["fg_stocks"]; fgc = data["fg_crypto"]
    crypto = data["crypto"]; reddit = data["reddit"]
    vixq = idx.get("^VIX"); spx = idx.get("^GSPC"); tsx = idx.get("^GSPTSE")
    aa = content["aaii"]; spread = round(aa["bull"] - aa["bear"], 1)
    under, over = content["undervalued"], content["overvalued"]
    ed_iso = content["editorial_as_of"]

    # ── 1. COUVERTURE ───────────────────────────────────────────────────────
    S += [sp(26), Paragraph("LE PINSON BOURSIER  ·  SOCIAL INVESTING", ST["c_tag"]), sp(8),
          Paragraph("Rapport de Marché", ST["c_title"]), sp(6)]
    div = Drawing(BW, 6)
    div.add(Rect(0, 2, BW * 0.48, 4, fillColor=NAVY, strokeColor=None))
    div.add(Rect(BW * 0.49, 2, BW * 0.51, 4, fillColor=EMERALD, strokeColor=None))
    S += [div, sp(10), Paragraph("TSX  ·  NYSE  ·  NASDAQ  ·  Crypto  ·  Commerce de détail", ST["c_sub"]), sp(4),
          Paragraph(esc(data["date_long_fr"]), ST["c_date"]), sp(18)]
    g = Table([[gauge(fgs["score"], "FEAR & GREED — ACTIONS US", fgs["label"].upper()),
                gauge(fgc["score"], "FEAR & GREED — CRYPTO", fgc["label"].upper()),
                gauge(None if not vixq else min(100, round(vixq["price"] / 40 * 100)), "VIX (ÉCHELLE 0-40)",
                      "N/D" if not vixq else f"VIX {vixq['price']:.1f}")]], colWidths=[BW / 3] * 3)
    g.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("BOX", (0, 0), (-1, -1), 0.8, SLATE_300),
                           ("BACKGROUND", (0, 0), (-1, -1), PAPER), ("TOPPADDING", (0, 0), (-1, -1), 8),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    S += [g, sp(10)]
    btc = crypto.get("BTC")
    S.append(kpi_strip([
        ("BITCOIN", fp(btc["price"]) if btc else "N/D", fpct(btc["chg_24h"]) + " (24 h)" if btc else "N/D", NAVY),
        ("VIX", f"{vixq['price']:.2f}" if vixq else "N/D", fpct(vixq["chg_1d"]) + " (veille)" if vixq else "N/D", AMBER),
        ("TSX COMPOSITE", fn(tsx["price"], 0) if tsx else "N/D", fpct(tsx["chg_1d"]) + " (veille)" if tsx else "N/D", EMERALD),
        ("S&P 500", fn(spx["price"], 0) if spx else "N/D", fpct(spx["chg_1d"]) + " (veille)" if spx else "N/D", BLUE),
    ]))
    S += [sp(14), Paragraph(esc(
        "Les cours des actions sont les clôtures du jour (le rapport est produit après la fermeture des marchés). "
        "Fear & Greed, VIX, crypto, Reddit et indicateurs techniques sont recalculés chaque jour; les listes de valorisation, "
        "cibles d'analystes, commentaires et l'AAII sont des saisies éditoriales datées."), ST["body"]), sp(8)]
    if data.get("demo"):
        S.append(Paragraph(esc("MODE DÉMONSTRATION : toutes les données de ce document sont synthétiques. Ne pas utiliser pour décider."), ST["warn"]))
    S.append(PageBreak())

    # ── 2. TABLEAU DE BORD ──────────────────────────────────────────────────
    S += [section_header("00", "TABLEAU DE BORD"), sp(8), Paragraph("SENTIMENT ET LARGEUR DE MARCHÉ", ST["kicker"]), sp(4)]
    d = Table([[gauge(fgs["score"], "Actions US", fgs["label"].upper(), 115, 100),
                gauge(fgc["score"], "Crypto", fgc["label"].upper(), 115, 100),
                sparkline(fgs["history"], 130, 100, BLUE, "F&G Actions — 7 derniers points"),
                sparkline(fgc["history"], 130, 100, EMERALD, "F&G Crypto — 7 jours")]],
              colWidths=[BW * 0.23, BW * 0.23, BW * 0.27, BW * 0.27])
    d.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("BOX", (0, 0), (-1, -1), 0.8, SLATE_300), ("LINEBEFORE", (1, 0), (-1, -1), 0.5, SLATE_300),
                           ("BACKGROUND", (0, 0), (-1, -1), PAPER), ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    tracked = [t for t in q]
    pct_above = (100 * sum(1 for t in tracked if q[t]["above_ma200"]) / max(1, sum(1 for t in tracked if q[t]["above_ma200"] is not None))) if tracked else None
    pct_macd = (100 * sum(1 for t in tracked if q[t]["macd_label"] == "Achat") / max(1, sum(1 for t in tracked if q[t]["macd_label"] != "N/D"))) if tracked else None
    S += [d, sp(8), Paragraph("INDICATEURS EN UN COUP D'ŒIL (0 = très bas, 100 = très haut)", ST["kicker"]), sp(4),
          bars([("Fear & Greed — actions", fgs["score"], score_color(fgs["score"])),
                ("Fear & Greed — crypto", fgc["score"], score_color(fgc["score"])),
                ("RSI du S&P 500", spx["rsi"] if spx else None, BLUE_MED),
                ("RSI moyen des titres suivis", avg([q[t]["rsi"] for t in tracked]), BLUE_MED),
                ("% des titres au-dessus de la MA200", pct_above, GREEN),
                ("% des titres avec MACD positif", pct_macd, GREEN)]), sp(8),
          Paragraph("FAITS SAILLANTS (COMMENTAIRE ÉDITORIAL)", ST["kicker"]), sp(3)]
    S.append(Paragraph("<br/>".join("•  " + esc(h) for h in content["highlights"]), ST["body"]))
    S += [stale_note(ed_iso, 7, "Faits saillants"), PageBreak()]

    # ── 2 bis. ZONES ET RÉPARTITION SECTORIELLE (reprise de la V3) ──────────
    S += [section_header("00", "TABLEAU DE BORD (SUITE) — ZONES DE LECTURE ET RÉPARTITION SECTORIELLE"), sp(8),
          Paragraph("COMMENT LIRE LES INDICATEURS DE SENTIMENT", ST["kicker"]), sp(3)]
    def zp(html, col):
        return Paragraph(html, ParagraphStyle("zp", fontName=F, fontSize=7.6, leading=11, textColor=col))
    zl = Table([[zp("<b>Zone peur / survente</b><br/>Fear &amp; Greed &lt; 30, RSI &lt; 30 : signal contrarien fort, observer l'accumulation progressive.", RED),
                 zp("<b>Zone neutre / attention</b><br/>30 à 60 : surveiller; achats échelonnés (DCA) prudents, sans précipitation.", AMBER),
                 zp("<b>Zone avidité / surachat</b><br/>Fear &amp; Greed &gt; 70, RSI &gt; 70 : euphorie, réduire l'exposition ou resserrer les arrêts.", EMERALD)]],
               colWidths=[BW / 3] * 3)
    zl.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, SLATE_300), ("LINEBEFORE", (1, 0), (-1, -1), 0.5, SLATE_300),
                            ("BACKGROUND", (0, 0), (-1, -1), PAPER), ("TOPPADDING", (0, 0), (-1, -1), 7),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    buckets = {}
    for it in under + over:
        b = it.get("bucket") or it["sector"]
        buckets[b] = buckets.get(b, 0) + 1
    donut_items = sorted(buckets.items(), key=lambda kv: -kv[1])
    S += [zl, sp(10), Paragraph("RÉPARTITION DES 20 TITRES DES LISTES PAR SECTEUR (CALCULÉE)", ST["kicker"]), sp(4),
          Table([[sector_donut(donut_items, [NAVY, BLUE, EMERALD, AMBER, BLUE_MED, SLATE_500][:len(donut_items)], BW, 140)]], colWidths=[BW],
                style=TableStyle([("BOX", (0, 0), (-1, -1), 0.6, SLATE_300), ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                                  ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)])),
          sp(4), Paragraph(esc("Compte les titres des listes sous-évalués et surévalués selon le secteur saisi dans content.json. "
                               "Ce n'est pas une allocation recommandée : sert à repérer la concentration des idées."), ST["note"]),
          PageBreak()]

    # ── 3. ANALYSE TECHNIQUE ────────────────────────────────────────────────
    S += [section_header("01", "ANALYSE TECHNIQUE DES COMPAGNIES", BLUE), sp(6), Paragraph(esc(
        "Indicateurs calculés aujourd'hui à partir des clôtures quotidiennes sur un an. RSI(14) de Wilder; MACD (12, 26, 9) : "
        "valeur de l'histogramme (MACD moins sa ligne de signal); MA50 / MA200 : moyennes mobiles simples. "
        "Golden Cross = MA50 au-dessus de la MA200 (haussier); Death Cross = MA50 sous la MA200 (baissier)."), ST["body"]), sp(4)]
    leg = Table([[P("RSI : < 30 survendu · 30 à 70 neutre · > 70 surachat", 7.2),
                  P("MACD histogramme : > 0 achat · < 0 vente", 7.2),
                  P("Signal global : +1/−1 par critère (RSI extrême, MACD, prix vs MA200, MA50 vs MA200). Total 3 et plus : ACHAT; −3 et moins : VENTE; −1 à −2 : PRUDENCE", 7.2)]],
                colWidths=[BW * 0.28, BW * 0.24, BW * 0.48])
    leg.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, SLATE_300), ("LINEBEFORE", (1, 0), (-1, -1), 0.5, SLATE_300),
                             ("BACKGROUND", (0, 0), (-1, -1), PAPER), ("TOPPADDING", (0, 0), (-1, -1), 5),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    S += [leg, sp(6)]
    sem_t = [x["ticker"] for x in content["semis"]]
    S += [Paragraph("TITRES SOUS-ÉVALUÉS (LISTE ÉDITORIALE)", ST["kicker"]), sp(3),
          tech_table([x["ticker"] for x in under], q, NAVY), sp(6),
          Paragraph("TITRES SURÉVALUÉS / À RISQUE (LISTE ÉDITORIALE)", ST["kicker"]), sp(3),
          tech_table([x["ticker"] for x in over], q, CRIMSON), sp(6)]
    others = [t for t in dict.fromkeys(sem_t + content.get("extra_tickers", [])) if t not in {x["ticker"] for x in under + over}]
    S += [CondPageBreak(140), Paragraph("SEMI-CONDUCTEURS ET AUTRES TITRES SUIVIS", ST["kicker"]), sp(3), tech_table(others, q, BLUE), PageBreak()]

    # ── 4. LECTURE DÉTAILLÉE ────────────────────────────────────────────────
    S += [section_header("02", "LECTURE DÉTAILLÉE — MOUVEMENTS MARQUANTS", BLUE), sp(6)]
    for b in content["detail_blocks"]:
        S += [Paragraph(esc(b["title"]), ST["h2"]), Paragraph(esc(b["text"]), ST["body"]), sp(4)]
    S += [stale_note(ed_iso, 7, "Commentaire"), CondPageBreak(265), sp(6), Paragraph("SIGNAUX TECHNIQUES EXTRÊMES DU JOUR (CALCULÉS)", ST["kicker"]), sp(3)]
    extremes = sorted([(t, v) for t, v in q.items() if v["rsi"] is not None], key=lambda x: x[1]["rsi"])
    ex_rows = [["TICKER", "PRIX", "RSI(14)", "ÉTAT", "TENDANCE", "SIGNAL GLOBAL"]]
    ex_cs = {}
    for t, v in extremes[:4] + extremes[-4:]:
        ex_rows.append([t, fp(v["price"], t), fn(v["rsi"], 0), v["rsi_label"], v["trend"], v["signal"]])
        i = len(ex_rows) - 1
        ex_cs[(i, 3)] = (rsi_color(v["rsi_label"]), True); ex_cs[(i, 4)] = (sig_color(v["trend"]), True)
        ex_cs[(i, 5)] = (sig_color(v["signal"]), True)
    S += [table(ex_rows, [50, 60, 50, 60, 80, 80], cell_styles=ex_cs),
          Paragraph(esc("Les 4 RSI les plus bas et les 4 plus hauts parmi les titres suivis."), ST["note"]), PageBreak()]

    # ── 5. TOP 10 SOUS-ÉVALUÉS ──────────────────────────────────────────────
    S += [section_header("03", "TOP 10 TITRES SOUS-ÉVALUÉS"), sp(6), Paragraph(esc(
        "Sélection éditoriale fondée sur le P/E prévisionnel relatif à la médiane du secteur et sur le consensus des analystes. "
        "Le prix et la tendance sont ceux du jour; le potentiel est recalculé chaque jour à partir de la cible saisie."), ST["body"]), sp(4)]
    rows, cs, ups = [["#", "TICKER", "SOCIÉTÉ", "SECTEUR", "PRIX", "CIBLE", "POTENTIEL", "P/E FWD", "CONV.", "TENDANCE"]], {}, []
    for n, it in enumerate(under, 1):
        qq = q.get(it["ticker"]); price = qq["price"] if qq else None; tg = it.get("target")
        pot = (tg / price - 1) * 100 if (tg and price) else None
        if pot is not None: ups.append((it["ticker"], pot))
        rows.append([str(n), it["ticker"], P(it["name"]), P(it["sector"]), fp(price, it["ticker"]),
                     fp(tg) if tg else "À valider", fpct(pot, 0), f"{it['pe_fwd']:g}x", f"{it['conviction']}/5",
                     qq["trend"] if qq else "N/D"])
        cs[(n, 6)] = (EMERALD if (pot or 0) >= 0 else RED, True)
        cs[(n, 9)] = (sig_color(qq["trend"]) if qq else SLATE_500, True)
    S += [table(rows, [14, 36, 92, 80, 46, 46, 50, 40, 34, 56], left_cols=(2, 3), cell_styles=cs), sp(8)]
    if ups:
        S += [Paragraph("POTENTIEL ESTIMÉ PAR TITRE", ST["kicker"]), sp(3), upside_chart(ups)]
    S += [sp(4), Paragraph(esc(content["valuation_note"]), ST["note"]), stale_note(ed_iso, 30, "Cibles, P/E et convictions"), PageBreak()]

    # ── 6. TOP 10 SURÉVALUÉS ────────────────────────────────────────────────
    S += [section_header("04", "TOP 10 TITRES SURÉVALUÉS / À RISQUE", CRIMSON), sp(6), Paragraph(esc(
        "Titres dont la valorisation ou le momentum appelle à la prudence. Un titre cher peut le rester longtemps : "
        "la colonne de signal technique est recalculée chaque jour et sert à calibrer le risque, pas à anticiper une correction."), ST["body"]), sp(4)]
    rows, cs = [["#", "TICKER", "SOCIÉTÉ", "SECTEUR", "PRIX", "VAR. 1M", "P/E FWD", "P/E SECT.", "RISQUE", "SIGNAL TECH."]], {}
    for n, it in enumerate(over, 1):
        qq = q.get(it["ticker"])
        rows.append([str(n), it["ticker"], P(it["name"]), P(it["sector"]), fp(qq["price"], it["ticker"]) if qq else "N/D",
                     fpct(qq["chg_1m"]) if qq else "N/D", f"{it['pe']:g}x" if it["pe"] else "N/M",
                     f"{it['sector_pe']:g}x" if it["sector_pe"] else "N/M", it["risk"], qq["signal"] if qq else "N/D"])
        if qq: cs[(n, 5)] = (EMERALD if qq["chg_1m"] >= 0 else RED, True); cs[(n, 9)] = (sig_color(qq["signal"]), True)
        cs[(n, 8)] = (RED if it["risk"] in ("EXTRÊME", "TRÈS ÉLEVÉ") else AMBER if it["risk"] == "ÉLEVÉ" else SLATE_500, True)
    S += [table(rows, [14, 36, 86, 78, 46, 46, 36, 42, 56, 60], hdr_bg=CRIMSON, left_cols=(2, 3), cell_styles=cs), sp(6),
          Paragraph(esc("N/M = non mesurable (bénéfices négatifs). Les P/E sont des saisies éditoriales qui peuvent être périmées si le cours a beaucoup bougé depuis; "
                        "comparez-les au prix du jour avant de conclure."), ST["note"]), stale_note(ed_iso, 30, "P/E et risques"), PageBreak()]

    # ── 7-8. MATRICES DE CONFLUENCE ─────────────────────────────────────────
    S += [section_header("05", "MATRICE DE CONFLUENCE — TOP 10 SOUS-ÉVALUÉS"), sp(6),
          Paragraph(esc(MATRIX_LEGEND), ST["body"]), sp(4), matrix_table(under, data, content, "pe_fwd", NAVY), sp(6),
          Paragraph(esc("Règle : agir progressivement quand au moins 4 signaux sur 9 sont favorables; la confluence réduit le risque d'agir sur un seul indicateur."), ST["note"]), PageBreak()]
    S += [section_header("06", "MATRICE DE CONFLUENCE — TOP 10 SURÉVALUÉS", CRIMSON), sp(6),
          Paragraph(esc(MATRIX_LEGEND), ST["body"]), sp(4), matrix_table(over, data, content, "pe", CRIMSON), sp(6),
          Paragraph(esc("Un Fear & Greed bas donne un signal favorable à tous les titres, même chers : c'est pourquoi le P/E, la MA200 et le MACD pèsent dans la lecture."), ST["note"]), PageBreak()]

    # ── 9. SECTEURS ─────────────────────────────────────────────────────────
    S += [section_header("07", "SECTEURS TECHNOLOGIQUES — SEMI-CONDUCTEURS ET CYBERSÉCURITÉ"), sp(6),
          Paragraph("SEMI-CONDUCTEURS", ST["kicker"]), sp(3), simple_live_table(content["semis"], q), sp(10),
          Paragraph("CYBERSÉCURITÉ", ST["kicker"]), sp(3), simple_live_table(content["cyber"], q, BLUE), sp(4),
          Paragraph(esc("Prix, variation sur un mois, RSI, tendance et signal sont calculés chaque jour; la description est éditoriale."), ST["note"]), PageBreak()]

    # ── 10. COMMERCE DE DÉTAIL & MARQUES ────────────────────────────────────
    S += [section_header("08", "COMMERCE DE DÉTAIL ET MARQUES ÉMERGENTES", EMERALD), sp(6), Paragraph(esc(
        "Objectif Social Investing : repérer les marques virales avant qu'elles ne soient intégrées aux portefeuilles institutionnels. "
        "Deux angles : détaillants établis et marques à fort momentum social (cotées, ou privées avec IPO possible)."), ST["body"]), sp(4),
          Paragraph("DÉTAILLANTS ÉTABLIS", ST["kicker"]), sp(3), simple_live_table(content["retail"], q, EMERALD), sp(10),
          Paragraph("MARQUES ÉMERGENTES", ST["kicker"]), sp(3)]
    rows, cs = [["MARQUE", "STATUT", "THÈME SOCIAL", "PROXY COTÉ", "PRIX", "SIGNAL"]], {}
    for b in content["brands"]:
        px = b.get("proxy"); qq = q.get(px) if px else None; i = len(rows)
        rows.append([P(b["brand"], 7.5, NAVY, True), P(b["status"]), P(b["theme"]), px or "—",
                     fp(qq["price"], px) if qq else "—", qq["signal"] if qq else "—"])
        if qq: cs[(i, 5)] = (sig_color(qq["signal"]), True)
    S += [table(rows, [64, 84, 150, 50, 50, 54], hdr_bg=EMERALD, left_cols=(0, 1, 2), cell_styles=cs), sp(4),
          Paragraph(esc("Pour une marque privée : surveiller le dépôt d'un formulaire S-1 auprès de la SEC (IPO américaine) ou d'un prospectus au Canada. "
                        "DECK = Deckers Outdoor (HOKA, UGG); URBN = Urban Outfitters (FP Movement, Anthropologie)."), ST["note"]), PageBreak()]

    # ── 11. AAII ────────────────────────────────────────────────────────────
    hist = [(h["label"], h["value"]) for h in aa["history"]] + [("Dernière\nlecture", spread)]
    S += [section_header("09", "INDICE AAII — DÉFINITION, CALCUL ET LECTURE ACTUELLE"), sp(6),
          Paragraph("QU'EST-CE QUE L'INDICE AAII ?", ST["kicker"]), Paragraph(esc(
              "L'AAII Sentiment Survey (American Association of Individual Investors) est une enquête hebdomadaire menée depuis 1987 auprès "
              "des investisseurs individuels américains. Elle demande dans quelle direction le marché évoluera au cours des six prochains mois. "
              "C'est un indicateur contrarien : le pessimisme extrême des particuliers coïncide souvent avec des creux de marché, et l'euphorie avec des sommets."), ST["body"]),
          sp(4), Paragraph("MÉCANISME DE CALCUL", ST["kicker"]), sp(3)]
    ccs = {(4, 3): (EMERALD if spread > 6.5 else RED if spread < -20 else AMBER, True)}
    S += [table([["COMPOSANTE", "FORMULE", "MOYENNE HISTORIQUE", f"LECTURE DU {date_fr_from_iso(aa['as_of']).upper()}"],
                 ["% haussiers (bullish)", "votes haussiers ÷ total des votes", "37,5 %", f"{aa['bull']:.1f} %".replace(".", ",")],
                 ["% neutres", "votes neutres ÷ total des votes", "31,5 %", f"{aa['neutral']:.1f} %".replace(".", ",")],
                 ["% baissiers (bearish)", "votes baissiers ÷ total des votes", "31,0 %", f"{aa['bear']:.1f} %".replace(".", ",")],
                 ["Bull-Bear Spread", "% haussiers − % baissiers", "+6,5 %", fpct(spread)]],
                [110, 150, 90, 120], left_cols=(0, 1), cell_styles=ccs), sp(8),
          Paragraph("EXTRÊMES HISTORIQUES ET LECTURE ACTUELLE", ST["kicker"]), sp(3), aaii_chart(hist), sp(4),
          Paragraph(esc("Lecture : un spread sous −20 % signale un pessimisme extrême (historiquement favorable à l'accumulation); "
                        "au-dessus de +25 %, un optimisme excessif (prudence). Entre les deux, le signal est neutre."), ST["body"]),
          sp(2), Paragraph(esc(aa.get("reading_note", "")), ST["body"]),
          stale_note(aa["as_of"], 9, "Lecture AAII (publiée chaque jeudi)"), sp(6),
          CondPageBreak(230), Paragraph("TABLEAU DES SIGNAUX HISTORIQUES", ST["kicker"]), sp(3)]
    sig_rows, sig_cs = [["PÉRIODE", "BULL-BEAR", "SIGNAL", "S&P 500 À 12 MOIS", "LEÇON"]], {}
    for i, sg in enumerate(aa.get("signals", []), 1):
        sig_rows.append([sg["period"], fpct(sg["spread"]), sg["signal"], sg["sp12"], P(sg["lesson"])])
        sig_cs[(i, 1)] = (RED if sg["spread"] < -20 else AMBER if sg["spread"] > 20 else SLATE_700, True)
        sig_cs[(i, 2)] = (RED if sg["spread"] < -20 else AMBER, True)
    sig_rows.append([f"{date_fr_from_iso(aa['as_of'])} — ACTUEL", fpct(spread), "Neutre" if -20 <= spread <= 25 else ("Extrême peur" if spread < -20 else "Extrême avidité"),
                     "À surveiller", P("Aucun extrême : lecture neutre")])
    sig_cs[(len(sig_rows) - 1, 1)] = (EMERALD if spread > 6.5 else AMBER, True)
    S += [table(sig_rows, [112, 52, 78, 78, 120], left_cols=(0, 4), cell_styles=sig_cs, font_size=7.2), sp(3),
          Paragraph(esc(aa.get("signals_note", "")), ST["note"]), PageBreak()]

    # ── 11 bis. RADAR SOCIAL INVESTING ──────────────────────────────────────
    soc = data.get("social") or {}
    ape, stw, wk, gt = (soc.get("ape") or {}), (soc.get("stocktwits") or {}), (soc.get("wiki") or {}), (soc.get("trends") or {})
    S += [section_header("10", "RADAR SOCIAL INVESTING — CE QUI CIRCULE AUJOURD'HUI", BLUE), sp(6), Paragraph(esc(
        "Ce que les investisseurs individuels regardent et commentent. Ces données mesurent l'attention, pas la valeur : un pic de mentions "
        "peut annoncer un élan, mais aussi un excès (effet de foule). Chaque canal est relevé aujourd'hui; « N/D » signifie que la source n'a pas répondu."), ST["body"]), sp(4)]
    status = [("Reddit (direct)", reddit.get("available")), ("ApeWisdom", ape.get("available")), ("StockTwits", stw.get("available")),
              ("Wikipédia", wk.get("available")), ("Google Trends", gt.get("available")),
              ("SEC EDGAR", (soc.get("edgar") or {}).get("available")), ("YouTube", (soc.get("youtube") or {}).get("available"))]
    st_row = [[Paragraph(f"<font color='#475569'>{esc(n)}</font><br/><b><font color='{'#059669' if ok else '#DC2626'}'>{'OK' if ok else 'N/D'}</font></b>",
                         ParagraphStyle("stt", fontName=F, fontSize=7.5, leading=11, alignment=TA_CENTER)) for n, ok in status]]
    stt = Table(st_row, colWidths=[BW / 7] * 7)
    stt.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, SLATE_300), ("LINEBEFORE", (1, 0), (-1, -1), 0.5, SLATE_300),
                             ("BACKGROUND", (0, 0), (-1, -1), PAPER), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    S += [stt, sp(8)]

    if ape.get("available"):
        top = ape["stocks"][:10]
        def dchg(r): return (r["mentions"] / r["mentions_24h"] - 1) * 100 if r.get("mentions_24h") else None
        S += [Paragraph("TITRES LES PLUS MENTIONNÉS SUR REDDIT (24 H) — SOURCE : APEWISDOM", ST["kicker"]), sp(3),
              mention_chart([(r["ticker"], r["mentions"], dchg(r)) for r in top]), sp(2),
              Paragraph(esc("Barre bleue : mentions en hausse sur 24 h; barre orange : en baisse. Pourcentage à droite : variation des mentions."), ST["note"]), sp(6)]
    else:
        S += [Paragraph("TITRES LES PLUS MENTIONNÉS SUR REDDIT (24 H)", ST["kicker"]), sp(3), Paragraph(esc("ApeWisdom : N/D aujourd'hui."), ST["note"]), sp(6)]

    if stw.get("available"):
        trs = [["#", "SYMBOLE", "SOCIÉTÉ", "SCORE DE TENDANCE", "LISTES DE SUIVI"]]
        for r in stw["rows"][:8]:
            trs.append([str(r["rank"]), r["symbol"], P(r["title"]), f"{r['score']:.1f}".replace(".", ","), f"{r['watchlist']:,}".replace(",", " ")])
        S += [Paragraph("SYMBOLES EN TENDANCE SUR STOCKTWITS", ST["kicker"]), sp(3), table(trs, [24, 62, 190, 100, 100], left_cols=(2,), hdr_bg=BLUE), sp(6)]

    if ape.get("crypto"):
        crs = [["#", "CRYPTO", "NOM", "MENTIONS 24 H", "VARIATION"]]
        for r in ape["crypto"][:5]:
            ch = (r["mentions"] / r["mentions_24h"] - 1) * 100 if r.get("mentions_24h") else None
            crs.append([str(r["rank"]), r["ticker"], P(r["name"]), f"{r['mentions']:,}".replace(",", " "), fpct(ch, 0) if ch is not None else "N/D"])
        S += [Paragraph("BUZZ CRYPTO SUR REDDIT (24 H)", ST["kicker"]), sp(3), table(crs, [24, 62, 190, 100, 100], left_cols=(2,), hdr_bg=EMERALD), sp(6)]
    S.append(PageBreak())

    # ── croisement avec nos listes ──
    S += [section_header("10", "RADAR SOCIAL INVESTING (SUITE) — NOS TITRES ET LES SIGNAUX D'ATTENTION", BLUE), sp(6), Paragraph(esc(
        "Croisement des 20 titres des listes avec chaque canal. Lecture : « Intérêt » = présence modérée (signal favorable); « Excès » = foule très active "
        "(300 mentions ou plus : prudence); « Discret » = peu de mentions."), ST["body"]), sp(4)]
    xrows = [["TICKER", "REDDIT APEWISDOM", "VARIATION 24 H", "STOCKTWITS", "WIKIPÉDIA (7 J)", "REDDIT DIRECT", "LECTURE"]]
    xcs = {}
    for i, it in enumerate(under + over, 1):
        t = it["ticker"]
        a = (ape.get("by_ticker") or {}).get(t)
        s_ = (stw.get("by_symbol") or {}).get(t)
        w = (wk.get("by_ticker") or {}).get(t)
        achg = (a["mentions"] / a["mentions_24h"] - 1) * 100 if a and a.get("mentions_24h") else None
        sg = social_signal(t, data)
        lecture = "N/D" if not (ape.get("available") or reddit.get("available")) else {"ACHAT": "Intérêt", "VENTE": "Excès", "NEUTRE": "Discret"}[sg]
        xrows.append([t, (f"#{a['rank']} · {a['mentions']}" if a else ("—" if ape.get("available") else "N/D")),
                      fpct(achg, 0) if achg is not None else "—",
                      (f"#{s_['rank']}" if s_ else ("—" if stw.get("available") else "N/D")),
                      (fpct(w["chg"], 0) if w and w.get("chg") is not None else ("—" if wk.get("available") else "N/D")),
                      (str(reddit["totals"].get(t, 0)) if reddit.get("available") else "N/D"), lecture])
        xcs[(i, 6)] = (EMERALD if lecture == "Intérêt" else RED if lecture == "Excès" else SLATE_500, True)
        if achg is not None: xcs[(i, 2)] = (EMERALD if achg >= 0 else RED, True)
        if w and w.get("chg") is not None: xcs[(i, 4)] = (EMERALD if w["chg"] >= 0 else RED, True)
    S += [table(xrows, [44, 86, 70, 62, 72, 66, 56], cell_styles=xcs, font_size=7.2), sp(4),
          Paragraph(esc("« — » : titre absent du palmarès du jour (les 200 premiers pour ApeWisdom). Wikipédia : variation de la moyenne quotidienne des pages vues "
                        "des 7 derniers jours par rapport aux 7 jours précédents."), ST["note"]), sp(8)]
    S.append(PageBreak())

    # ── initiés, vidéo et veille manuelle ──
    edg, yt = (soc.get("edgar") or {}), (soc.get("youtube") or {})
    mw = content.get("manual_watch", {})
    def usd(x):
        return f"{x / 1e6:.1f} M$".replace(".", ",") if x >= 1e6 else (f"{x / 1e3:.0f} k$" if x >= 1e3 else "0 $")
    S += [section_header("11", "AUTRES SIGNAUX — RECHERCHE, INITIÉS, VIDÉO ET VEILLE MANUELLE", BLUE), sp(6), Paragraph(esc(
        "Trois angles complémentaires : ce que les dirigeants font avec leurs propres actions (SEC EDGAR), ce que le grand public regarde en vidéo (YouTube) "
        "et les tendances virales de marques que seule une veille manuelle permet de suivre (TikTok). Google Trends mesure, lui, la curiosité du public en recherche."), ST["body"]), sp(4)]
    if gt.get("available"):
        grs = [["MOT-CLÉ (ÉTATS-UNIS)", "INTÉRÊT RÉCENT (0-100)", "MOYENNE PRÉCÉDENTE", "VARIATION"]]
        gcs = {}
        for i, r in enumerate(gt["rows"], 1):
            grs.append([r["keyword"], f"{r['current']:.0f}", f"{r['baseline']:.0f}" if r.get("baseline") == r.get("baseline") else "N/D",
                        fpct(r["chg"], 0) if r.get("chg") is not None else "N/D"])
            if r.get("chg") is not None: gcs[(i, 3)] = (EMERALD if r["chg"] >= 0 else RED, True)
        S.append(KeepTogether([Paragraph("GOOGLE TRENDS — INTÉRÊT DE RECHERCHE (3 DERNIERS MOIS)", ST["kicker"]), sp(3), table(grs, [150, 120, 110, 80], left_cols=(0,), cell_styles=gcs), sp(2),
              Paragraph(esc("Indice relatif (100 = pic de la période), pas un volume de recherches. Un intérêt élevé pour « stock market crash » coïncide souvent avec la peur; "
                            "pour « buy stocks », avec l'euphorie."), ST["note"])]))
    else:
        S.append(KeepTogether([Paragraph("GOOGLE TRENDS", ST["kicker"]), sp(3), Paragraph(esc(
            "N/D aujourd'hui : Google bloque souvent les requêtes automatisées venant de serveurs (l'API officielle est encore sur invitation). "
            "Consultez trends.google.com manuellement pour : " + ", ".join(content.get("trends_keywords", [])) + "."), ST["note"])]))
    S += [sp(8), CondPageBreak(470), Paragraph("TRANSACTIONS D'INITIÉS — FORMULAIRE 4 DE LA SEC (45 DERNIERS JOURS)", ST["kicker"]), sp(3)]
    if edg.get("available"):
        er = [["TICKER", "DÉCLARATIONS", "ACHATS OUVERTS", "VENTES OUVERTES", "ACHETEURS DISTINCTS", "SIGNAL"]]
        ecs = {}
        for it in under + over:
            e = edg["by_ticker"].get(it["ticker"])
            if not e:
                continue
            sg = insider_signal_from(e)
            er.append([it["ticker"], str(e["filings"]), usd(e["buys"]), usd(e["sells"]), str(e["buyers"]), sg])
            ecs[(len(er) - 1, 5)] = (sig_color(sg), True)
            if e["buys"] > 0: ecs[(len(er) - 1, 2)] = (EMERALD, True)
        S += [table(er, [54, 78, 92, 92, 100, 74], cell_styles=ecs, font_size=7.2), sp(3),
              Paragraph(esc("Seules les transactions en marché ouvert sont comptées (code P = achat, code S = vente); exercices d'options et octrois sont exclus. "
                            "Beaucoup de ventes sont planifiées à l'avance (plans 10b5-1) et ont peu de valeur prédictive : un achat ouvert par un dirigeant est un signal nettement plus fort. "
                            "Sociétés canadiennes : consulter SEDI (sedi.ca)."), ST["note"])]
    else:
        S += [Paragraph(esc("N/D aujourd'hui" + (f" ({edg.get('reason')})" if edg.get("reason") else "") + ". Pour activer cette section, ajoutez le secret SEC_USER_AGENT "
                            "(voir la notice) : la SEC exige que les outils automatisés s'identifient par un nom et un courriel de contact. "
                            "En attendant, la colonne INIT. des matrices utilise la saisie manuelle (NEUTRE par défaut)."), ST["note"])]
    S.append(sp(8))
    S += [CondPageBreak(300), Paragraph("VIDÉOS YOUTUBE LES PLUS VUES SUR NOS TITRES (7 DERNIERS JOURS)", ST["kicker"]), sp(3)]
    if yt.get("available"):
        yr = [["#", "TICKER", "VUES (TOP VIDÉO)", "CHAÎNE", "TITRE"]]
        for n, (t, v) in enumerate(sorted(yt["by_ticker"].items(), key=lambda kv: -kv[1]["views"])[:12], 1):
            ttl = v["title"] if len(v["title"]) <= 72 else v["title"][:69] + "…"
            yr.append([str(n), t, f"{v['views']:,}".replace(",", " "), P(v["channel"], 6.8), P(ttl, 6.8)])
        S += [table(yr, [22, 46, 80, 100, 248], left_cols=(3, 4), font_size=7), sp(3),
              Paragraph(esc("Recherche « TICKER stock » (ou le nom de la société pour les symboles ambigus), triée par nombre de vues. Un grand nombre de vues mesure l'attention, "
                            "pas la qualité de l'analyse : méfiez-vous des titres racoleurs et des promotions payées."), ST["note"])]
    else:
        S += [Paragraph(esc("N/D aujourd'hui" + (f" ({yt.get('reason')})" if yt.get("reason") else "") + ". Pour activer cette section, créez une clé gratuite YouTube Data API v3 "
                            "dans Google Cloud et ajoutez-la au secret YOUTUBE_API_KEY (voir la notice)."), ST["note"])]
    S.append(sp(8))
    S += [CondPageBreak(150), Paragraph("TIKTOK ET AUTRES CANAUX — VEILLE MANUELLE", ST["kicker"]), sp(3), Paragraph(esc(
        "TikTok n'offre aucun accès de données utilisable par un particulier (API réservée aux chercheurs, Creative Center limité aux 100 principaux mots-clics). "
        "La veille est donc manuelle. Mots-clics à surveiller : " + ", ".join(mw.get("hashtags", [])) + ". " + mw.get("how", "")), ST["body"]), sp(3)]
    items = mw.get("items", [])
    if items:
        mr = [["DATE", "CANAL", "SUJET", "OBSERVATION"]]
        for x in items[-10:]:
            mr.append([x.get("date", ""), P(x.get("canal", "")), P(x.get("sujet", "")), P(x.get("observation", ""))])
        S += [table(mr, [62, 70, 110, 254], left_cols=(1, 2, 3), font_size=7), stale_note(items[-1].get("date", ed_iso), 14, "Veille manuelle")]
    else:
        S += [Paragraph(esc("Aucune observation saisie pour l'instant (champ manual_watch.items de content.json)."), ST["note"])]
    S.append(PageBreak())

    # ── catalogue des sources ──
    S += [section_header("12", "CATALOGUE DES SOURCES DE SOCIAL INVESTING", EMERALD), sp(6), Paragraph(esc(
        "Où observer le sentiment des investisseurs individuels, ce que chaque source mesure, ce qu'elle coûte et si le robot l'utilise déjà. "
        "Les colonnes d'accès et de coût ont été vérifiées le 14 octobre 2026 et changent souvent : revérifiez avant de vous abonner."), ST["body"]), sp(4)]
    crow = [["CANAL", "CE QU'IL MESURE", "ACCÈS ET COÛT", "LIMITES", "DANS LE ROBOT"]]
    ccs = {}
    for i, sc in enumerate(content.get("social_sources", []), 1):
        crow.append([P(sc["canal"], 7, NAVY, True), P(sc["mesure"], 6.6), P(sc["acces"], 6.6), P(sc["limites"], 6.6), P(sc["statut"], 6.6, EMERALD if sc["statut"].startswith("Automatisé") else AMBER if sc["statut"].startswith("Manuel") else SLATE_500, True)])
    S += [table(crow, [66, 128, 128, 94, 64], hdr_bg=EMERALD, left_cols=(0, 1, 2, 3, 4), font_size=6.8), sp(4),
          stale_note(content.get("social_sources_as_of", ed_iso), 90, "Catalogue des sources"), sp(4),
          Paragraph("BONNES PRATIQUES", ST["kicker"]), sp(3),
          Paragraph("<br/>".join("•  " + esc(x) for x in [
              "Le social est un indicateur contrarien aux extrêmes : un enthousiasme de foule n'est pas une raison d'acheter, un silence complet n'est pas une raison de vendre.",
              "Recoupez toujours au moins deux canaux et confirmez avec le prix (MA200, MACD) et la valorisation avant d'agir.",
              "Méfiez-vous des campagnes coordonnées (pump), des robots et des comptes promotionnels, surtout sur les petites capitalisations et la crypto.",
              "Les données sociales sont une photo du jour : notez la date et comparez à la semaine précédente plutôt qu'à un seuil unique."]), ST["body"]),
          PageBreak()]

    # ── 12. GUIDE DES 7 INDICATEURS ─────────────────────────────────────────
    spx_ma = ("au-dessus" if spx and spx["above_ma200"] else "sous") + " la MA200" if spx and spx["ma200"] else "N/D"
    soc_total = sum(reddit["totals"].values()) if reddit.get("available") else None
    now_state = {
        "F&G": f"{fgs['score']} — {fgs['label']}" if fgs["score"] is not None else "N/D",
        "VIX": f"{vixq['price']:.1f}" if vixq else "N/D",
        "AAII": fpct(spread),
        "RSI": f"S&P 500 : {fn(spx['rsi'], 0)}" if spx else "N/D",
        "MA200": f"S&P 500 {spx_ma}",
        "MACD": f"S&P 500 : {spx['macd_label']}" if spx else "N/D",
        "Social": f"{soc_total} mentions (titres suivis)" if soc_total is not None else "Reddit indisponible",
    }
    guide = [["IND.", "DÉFINITION", "SIGNAL ACHAT", "SIGNAL VENTE", "ÉTAT AUJOURD'HUI"],
             ["F&G", "CNN Fear & Greed : 7 sous-indicateurs (momentum, volume, put/call, largeur, valeurs refuges, obligations à rendement élevé)", "< 25 peur extrême : accumulation progressive", "> 75 avidité extrême : réduire l'exposition", now_state["F&G"]],
             ["VIX", "Volatilité implicite du S&P 500 sur 30 jours (CBOE)", "> 30 panique : opportunité contrarienne", "< 15 complaisance : risque sous-estimé", now_state["VIX"]],
             ["AAII", "Sondage hebdomadaire des investisseurs individuels (depuis 1987)", "Spread < −20 %", "Spread > +25 %", now_state["AAII"]],
             ["RSI", "Relative Strength Index sur 14 jours (0 à 100)", "< 30 survendu : rebond possible", "> 70 surachat : prise de profit partielle", now_state["RSI"]],
             ["MA50 / MA200", "Moyennes mobiles 50 et 200 jours; Golden Cross / Death Cross", "Prix au-dessus de la MA200; Golden Cross", "Prix sous la MA200; Death Cross", now_state["MA200"]],
             ["MACD", "MACD (12, 26, 9) : convergence / divergence des moyennes mobiles", "Croisement à la hausse; histogramme > 0", "Croisement à la baisse; divergence baissière", now_state["MACD"]],
             ["Social", "Mentions Reddit (ApeWisdom, r/wallstreetbets, r/stocks, r/investing), StockTwits, Wikipédia, Google Trends", "Intérêt croissant et sain", "FOMO : pic de mentions de +500 % ou 300 mentions et plus", now_state["Social"]]]
    guide = [[P(c, 7.2, NAVY if j == 0 else SLATE_700, j == 0) if i else c for j, c in enumerate(r)] for i, r in enumerate(guide)]
    S += [section_header("13", "GUIDE DES 7 INDICATEURS DE TIMING"), sp(6),
          Paragraph(esc("Règle de confluence : attendre l'alignement d'au moins 4 indicateurs sur 7 avant d'agir; ne jamais décider sur un seul."), ST["body"]), sp(4),
          table(guide, [48, 150, 100, 100, 100], left_cols=(0, 1, 2, 3, 4)), PageBreak()]

    # ── 13. RÉSUMÉ & VERDICT ────────────────────────────────────────────────
    sig7 = [("Fear & Greed actions", now_state["F&G"], fg_signal(fgs["score"])),
            ("Fear & Greed crypto", f"{fgc['score']} — {fgc['label']}" if fgc["score"] is not None else "N/D", fg_signal(fgc["score"])),
            ("VIX", now_state["VIX"], vix_signal(vixq["price"] if vixq else None)),
            ("AAII Bull-Bear", now_state["AAII"], aaii_signal(spread)),
            ("RSI S&P 500", fn(spx["rsi"], 0) if spx else "N/D", rsi_signal(spx["rsi"] if spx else None)),
            ("MA200 S&P 500", spx_ma, ma200_signal(spx)),
            ("MACD S&P 500", spx["macd_label"] if spx else "N/D", macd_signal(spx["macd_hist"] if spx else None))]
    buy = sum(1 for *_, s in sig7 if s == "ACHAT"); sell = sum(1 for *_, s in sig7 if s == "VENTE")
    if buy >= 4: vtxt, vcol = f"{buy} SIGNAUX FAVORABLES SUR 7\nZONE D'ACCUMULATION PROGRESSIVE (DCA)", EMERALD
    elif sell >= 4: vtxt, vcol = f"{sell} SIGNAUX DÉFAVORABLES SUR 7\nPRUDENCE : RÉDUIRE L'EXPOSITION", RED
    else: vtxt, vcol = f"{buy} FAVORABLES · {sell} DÉFAVORABLES SUR 7\nSIGNAUX MIXTES : SÉLECTIVITÉ REQUISE", AMBER
    gcs = {(i, 2): (sig_color(s), True) for i, (_, _, s) in enumerate(sig7, 1)}
    S += [section_header("14", "RÉSUMÉ STRATÉGIQUE ET VERDICT GLOBAL", EMERALD), sp(8), Paragraph("CONFLUENCE DU MARCHÉ AUJOURD'HUI", ST["kicker"]), sp(3),
          table([["INDICATEUR", "VALEUR", "SIGNAL"]] + [[a, b, s] for a, b, s in sig7], [150, 200, 100], left_cols=(0, 1), cell_styles=gcs), sp(8),
          verdict(vtxt, vcol), sp(8), Paragraph("SYNTHÈSE PAR CATÉGORIE (CALCULÉE)", ST["kicker"]), sp(3)]
    cats = [("Sous-évalués", [x["ticker"] for x in under]), ("Surévalués / à risque", [x["ticker"] for x in over]),
            ("Semi-conducteurs", sem_t), ("Cybersécurité", [x["ticker"] for x in content["cyber"]]),
            ("Commerce de détail", [x["ticker"] for x in content["retail"]])]
    rows = [["CATÉGORIE", "TITRES", "RSI MOYEN", "AU-DESSUS MA200", "MACD POSITIF", "ACHAT / NEUTRE / PRUDENCE / VENTE"]]
    for name, ts in cats:
        qs = [q[t] for t in ts if t in q]
        if not qs:
            rows.append([name, "0", "N/D", "N/D", "N/D", "N/D"]); continue
        a = sum(1 for v in qs if v["above_ma200"]); m = sum(1 for v in qs if v["macd_label"] == "Achat")
        c = {k: sum(1 for v in qs if v["signal"] == k) for k in ("ACHAT", "NEUTRE", "PRUDENCE", "VENTE")}
        rows.append([name, str(len(qs)), fn(avg([v["rsi"] for v in qs]), 0), f"{a}/{len(qs)}", f"{m}/{len(qs)}",
                     f"{c['ACHAT']} / {c['NEUTRE']} / {c['PRUDENCE']} / {c['VENTE']}"])
    cr_note = ""
    if btc and fgc["score"] is not None:
        cr_note = f"Crypto : Bitcoin {fp(btc['price'])} ({fpct(btc['chg_24h'])} sur 24 h), Fear & Greed crypto {fgc['score']} ({fgc['label']})."
    S += [table(rows, [100, 40, 60, 80, 70, 150], left_cols=(0,)), sp(4)]
    if cr_note: S.append(Paragraph(esc(cr_note), ST["note"]))
    S += [sp(10), HRFlowable(width="100%", thickness=0.5, color=SLATE_300), Paragraph(esc(
        "AVERTISSEMENT — Ce rapport est produit à des fins d'information et d'éducation. Il ne constitue ni un conseil en placement, ni une "
        "recommandation d'achat ou de vente de valeurs mobilières. Les indicateurs techniques sont rétrospectifs et ne garantissent pas les mouvements "
        "futurs. Les listes de valorisation, cibles, commentaires, signaux d'initiés et l'AAII sont des saisies éditoriales datées; les données de marché "
        "proviennent de sources gratuites (CNN, Alternative.me, CoinGecko, Yahoo Finance, Reddit, ApeWisdom, StockTwits, Wikipédia, Google Trends) qui peuvent être retardées, incomplètes ou indisponibles — "
        "une valeur « N/D » signifie que la source n'a pas répondu. Vérifiez les prix en temps réel avant toute décision. Tout investissement comporte un "
        "risque de perte en capital. Consultez un conseiller financier agréé."), ST["disc"])]

    doc.build(S, onFirstPage=deco, onLaterPages=deco)
    print(f"  [OK] PDF généré : {out_path}")
    return out_path
