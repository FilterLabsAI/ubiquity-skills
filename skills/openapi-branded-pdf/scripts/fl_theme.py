"""Shared look-and-feel for the API PDFs: palette (with WCAG checks), headings,
stat boxes, callout box, section tracking for the running header, and code highlighting."""
import re
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import Flowable, Table, TableStyle, Paragraph, XPreformatted

HEX = dict(ink='#1F2937', navy='#1B2430', red='#D10000', mute='#5B6470', rule='#E5E7EB',
           band='#F4F4F5', codebg='#F6F6F7', hdr='#5B6B80', white='#FFFFFF')
METHOD = {'GET': '#2E7D5B', 'POST': '#1B6FB8', 'PUT': '#9A6412', 'PATCH': '#7C4DAA', 'DELETE': '#B83A3A'}
CODE = dict(key='#0B5CAD', string='#1A6B35', number='#A3470A', ph='#7B3FA8', kw='#B02A5B',
            comment='#5B6470', ell='#5B6470', punct='#1F2937')

def _lum(h):
    h = h.lstrip('#'); r, g, b = [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
def contrast(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True); return (hi + 0.05) / (lo + 0.05)

def _check():
    """WCAG 2.x AA: 4.5:1 for normal text. Fails loudly if any text/background pair drops below it."""
    pairs = [('white on header fill', HEX['white'], HEX['hdr'])]
    for n, c in (('red', HEX['red']), ('mute', HEX['mute']), ('ink', HEX['ink']), ('navy', HEX['navy'])):
        for bn in ('white', 'band', 'codebg'): pairs.append(('%s on %s' % (n, bn), c, HEX[bn]))
    for m, c in METHOD.items(): pairs += [('%s on white' % m, c, HEX['white']), ('%s on band' % m, c, HEX['band'])]
    for n, c in CODE.items(): pairs += [('code %s on codebg' % n, c, HEX['codebg']), ('code %s on white' % n, c, HEX['white'])]
    bad = [(n, round(contrast(a, b), 2)) for n, a, b in pairs if contrast(a, b) < 4.5]
    assert not bad, 'WCAG AA contrast failures: %s' % bad
_check()

INK, NAVY, RED, MUTE, RULE, BAND, CODEBG, HDR = [colors.HexColor(HEX[k]) for k in
    ('ink', 'navy', 'red', 'mute', 'rule', 'band', 'codebg', 'hdr')]
MC = METHOD
W, H = 612.0, 792.0   # letter

STAT_PAD = (12.0, 17.0)    # top, bottom inside the stat boxes (tuned by pixel measurement so gaps look equal)
CALL_PAD = (18.0, 17.0)    # top, bottom inside the cover callout

def _esc(t): return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def stat_table(items, width):
    num = ParagraphStyle('statn', fontName='Helvetica-Bold', fontSize=22, leading=24, textColor=RED)
    lab = ParagraphStyle('statl', fontName='Helvetica', fontSize=9, leading=11, textColor=INK)
    t = Table([[[Paragraph(n, num), Paragraph(l, lab)] for n, l in items]], colWidths=[width / len(items)] * len(items))
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BAND), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), STAT_PAD[0]), ('BOTTOMPADDING', (0, 0), (-1, -1), STAT_PAD[1]),
        ('LEFTPADDING', (0, 0), (-1, -1), 14), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('LINEAFTER', (0, 0), (-2, -1), 2, colors.white)]))
    return t

def callout_box(title, text, width):
    ts = ParagraphStyle('cvt', fontName='Helvetica-Bold', fontSize=11.5, leading=15, textColor=NAVY)
    bs = ParagraphStyle('cvb', fontName='Helvetica', fontSize=10.5, leading=16, textColor=INK)
    t = Table([[Paragraph(title, ts)], [Paragraph(text, bs)]], colWidths=[width])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BAND), ('LINEBEFORE', (0, 0), (0, -1), 4, RED),
        ('LEFTPADDING', (0, 0), (-1, -1), 20), ('RIGHTPADDING', (0, 0), (-1, -1), 20),
        ('TOPPADDING', (0, 0), (0, 0), CALL_PAD[0]), ('BOTTOMPADDING', (0, 0), (0, 0), 4),
        ('TOPPADDING', (0, 1), (0, 1), 2), ('BOTTOMPADDING', (0, 1), (0, 1), CALL_PAD[1])]))
    return t

def section_heading(num, title, count, width):
    """Level-2 section heading (one per resource group): big, numbered, ruled in red."""
    left = Paragraph('<font color="%s">%02d</font>  %s' % (HEX['red'], num, _esc(title)),
                     ParagraphStyle('sec', fontName='Helvetica-Bold', fontSize=16, leading=20, textColor=NAVY))
    right = Paragraph('%d endpoint%s' % (count, '' if count == 1 else 's'),
                      ParagraphStyle('secn', fontName='Helvetica', fontSize=8.5, leading=11, textColor=MUTE, alignment=TA_RIGHT))
    t = Table([[left, right]], colWidths=[width - 1.1 * inch, 1.1 * inch])
    t.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, 0), 1.8, RED), ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    return t

def endpoint_heading(num, method, path, width):
    """Level-3 heading (one per endpoint): deliberately smaller and lighter than the section heading."""
    n = Paragraph(num, ParagraphStyle('epn', fontName='Helvetica-Bold', fontSize=7.8, leading=10, textColor=MUTE))
    m = Paragraph('<font color="%s"><b>%s</b></font>' % (MC[method], method), ParagraphStyle('epm', fontName='Helvetica', fontSize=8.4, leading=10.5))
    p = Paragraph(_esc(path), ParagraphStyle('epp', fontName='Courier-Bold', fontSize=8.4, leading=10.5, textColor=NAVY, wordWrap='CJK'))
    t = Table([[n, m, p]], colWidths=[0.42 * inch, 0.62 * inch, width - 1.04 * inch])
    t.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, 0), 0.6, RULE), ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    return t

STATE = {'first': {}, 'latest': {}, 'carry': ''}

class SectionMark(Flowable):
    """Zero-size marker: records which section is active on each page so the header can name it."""
    def __init__(self, label): Flowable.__init__(self); self.label = label
    def wrap(self, aw, ah): return (0, 0)
    def draw(self):
        c = self.canv; pg = c.getPageNumber(); y = c.absolutePosition(0, 0)[1]
        STATE['latest'][pg] = self.label
        if y > H - 1.5 * inch: STATE['first'].setdefault(pg, self.label)

def draw_running_header(c, doc, base, margin=0.75 * inch):
    pg = doc.page
    label = STATE['first'].get(pg) or STATE['carry']
    STATE['carry'] = STATE['latest'].get(pg, label)
    c.saveState(); c.setFillColor(MUTE); c.setFont('Helvetica', 8)
    c.drawRightString(W - margin, H - 0.5 * inch, base + ('  ›  ' + label if label else ''))
    c.restoreState()

_TOK = re.compile(r'''
 (?P<comment>//[^\n]*)
|(?P<str>"(?:[^"\\\n]|\\.)*")
|(?P<ph><[^<>\n"]+>)
|(?P<ell>\.\.\.)
|(?P<kw>\b(?:true|false|null)\b)
|(?P<fkey>(?<![\w"<])[A-Za-z_][\w.\[\]-]*(?==))
|(?P<num>(?<![\w.])-?\d+(?:\.\d+)?(?!\w))
''', re.X)

def highlight(text):
    out, pos = [], 0
    def span(kind, s, extra=''): return '<font color="%s"%s>%s</font>' % (CODE[kind], extra, _esc(s))
    for m in _TOK.finditer(text):
        out.append(_esc(text[pos:m.start()])); s = m.group(); k = m.lastgroup
        if k == 'comment': out.append(span('comment', s, ' name="Courier-Oblique"'))
        elif k == 'str':
            is_key = text[m.end():].lstrip(' ').startswith(':')
            out.append(span('key' if is_key else ('ph' if s.startswith('"<') else 'string'), s))
        elif k == 'ph': out.append(span('ph', s))
        elif k == 'ell': out.append(span('ell', s))
        elif k == 'kw': out.append(span('kw', s))
        elif k == 'fkey': out.append(span('key', s))
        else: out.append(span('number', s))
        pos = m.end()
    out.append(_esc(text[pos:]))
    return ''.join(out)

_codest = ParagraphStyle('code', fontName='Courier', fontSize=7.1, leading=9.0, textColor=INK)
def code_block(text, width, chunk=14):
    """Code panel split into 14-line rows so long blocks can break across pages."""
    lines = text.split('\n')
    rows = [[XPreformatted(highlight('\n'.join(lines[i:i + chunk])), _codest)] for i in range(0, len(lines), chunk)]
    t = Table(rows, colWidths=[width])
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), CODEBG), ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (0, 0), 6), ('BOTTOMPADDING', (0, -1), (0, -1), 6), ('LINEBEFORE', (0, 0), (0, -1), 2, RULE)]))
    return t

INLINE_CODE = '<font name="Courier" size="7.8" color="%s">' % CODE['key']
