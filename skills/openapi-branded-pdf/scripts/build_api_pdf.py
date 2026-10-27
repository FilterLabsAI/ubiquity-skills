#!/usr/bin/env python3
"""Build a branded API reference PDF from an OpenAPI 3.x spec plus a content.json file."""
import argparse, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, KeepTogether, NextPageTemplate, CondPageBreak)
from fl_theme import (INK, NAVY, RED, MUTE, RULE, BAND, HDR, MC, stat_table, callout_box, section_heading,
                      endpoint_heading, SectionMark, draw_running_header, code_block as _code_block, INLINE_CODE)

ap = argparse.ArgumentParser()
ap.add_argument('--spec', required=True); ap.add_argument('--content', required=True)
ap.add_argument('--mode', choices=['overview', 'detailed'], required=True)
ap.add_argument('--out', required=True); ap.add_argument('--logo', default=None)
ap.add_argument('--strict', action='store_true', help='exit non-zero if any text needed a fallback')
args = ap.parse_args()
DETAILED = args.mode == 'detailed'

SPEC = json.load(open(args.spec)); C = json.load(open(args.content))
META = C['meta']; OV = C['overview']; EP = C.get('endpoints', {}); PN = C.get('param_notes', {})
LOGO = args.logo if args.logo and os.path.exists(args.logo) else None
if not LOGO: print('NOTE: no logo found, using a text wordmark. Ask the user to attach the logo PNG.')
WARN = []

BAD = re.compile(r'CONFIRMED|UNCONFIRMED|UNVERIFIED|PLANNED|\bskill|SPA\b|\bUI\b|browser|XHR|retracted|reasoned|'
                 r'see summary|pitfalls|Hermes|interceptor|Angular|\bubiquity-[a-z-]+', re.I)
FALLBACK = 'Not documented yet.'
def clean(text, where):
    if text and BAD.search(text):
        WARN.append('internal wording replaced at %s: %s' % (where, text[:90])); return FALLBACK
    return text

def S(name, **kw):
    base = dict(fontName='Helvetica', fontSize=9.5, leading=13.5, textColor=INK); base.update(kw)
    return ParagraphStyle(name, **base)
body = S('body'); small = S('small', fontSize=8.5, leading=11.5, textColor=MUTE)
h1 = S('h1', fontName='Helvetica-Bold', fontSize=19, leading=24, textColor=NAVY, spaceAfter=4)
h2 = S('h2', fontName='Helvetica-Bold', fontSize=13.5, leading=17, textColor=NAVY, spaceBefore=13, spaceAfter=4)
lead = S('lead', fontSize=10.5, leading=15.5)
cell = S('cell', fontSize=8.3, leading=10.8)
path = S('path', fontName='Courier', fontSize=7.4, leading=9.6, wordWrap='CJK')
th = S('th', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white)
lab = S('lab', fontName='Helvetica-Bold', fontSize=7.8, leading=10, textColor=MUTE, spaceBefore=8, spaceAfter=3, keepWithNext=1)
note = S('note', fontSize=8.6, leading=12)

W, H = letter; M = 0.75 * inch; CW = W - 2 * M

def esc(t): return str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
def fmt(t):
    """content mini-markup: `code`, **bold**, newline -> <br/>"""
    t = esc(t)
    t = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)
    t = re.sub(r'`([^`]+)`', INLINE_CODE + r'\1</font>', t)
    return t.replace('\n', '<br/>')
def para(t, st=body): return Paragraph(t, st)
def badge(m, sz=7.8): return Paragraph('<font color="%s"><b>%s</b></font>' % (MC[m], m), S('b%s' % sz, fontSize=sz, leading=sz + 2.2))
def chip(code):
    return '<font color="%s"><b>%s</b></font>' % ('#2E7D5B' if code.startswith('2') else '#B83A3A', code)
def grid(rows, widths, header=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    st = [('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, -1), 0.4, RULE),
          ('TOPPADDING', (0, 0), (-1, -1), 3.5 if DETAILED else 2.4), ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5 if DETAILED else 2.4),
          ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5)]
    if header: st.append(('BACKGROUND', (0, 0), (-1, 0), HDR))
    t.setStyle(TableStyle(st)); return t
def code_block(text): return _code_block(text, CW)

eps = []
for p, v in SPEC['paths'].items():
    for m in v:
        if m in ('get', 'post', 'put', 'patch', 'delete'): eps.append((m.upper(), p, v[m]))
def ekey(m, p): return '%s %s' % (m, p)

def first_sentence(text):
    s = re.split(r'(?<=[.!?])\s+', (text or '').strip())[0]
    return s if len(s) < 200 else s[:197] + '...'
def desc_of(m, p, op):
    d = EP.get(ekey(m, p), {}).get('desc')
    if d: return d
    WARN.append('no content description for %s %s (derived from spec summary)' % (m, p))
    return clean(first_sentence(op.get('summary', '')), 'summary of ' + ekey(m, p)) or FALLBACK

def rule_ok(rule, p):
    if 'exact' in rule: return p == rule['exact']
    ok = ('prefix' in rule and p.startswith(rule['prefix'])) or ('contains' in rule and rule['contains'] in p)
    return ok and not any(x in p for x in rule.get('exclude', []))
GROUPS = C.get('groups')
if not GROUPS:   # fallback: group by first tag, else first path segment
    names = []
    for m, p, op in eps:
        n = (op.get('tags') or [p.strip('/').split('/')[0] or 'General'])[0]
        if n not in names: names.append(n)
    GROUPS = [{'name': n, 'blurb': '', 'tag': n} for n in names]
grouped = {g['name']: [] for g in GROUPS}
for m, p, op in eps:
    for g in GROUPS:
        if g.get('tag') and g['tag'] == (op.get('tags') or [p.strip('/').split('/')[0]])[0] or any(rule_ok(r, p) for r in g.get('match', [])):
            grouped[g['name']].append((m, p, op)); break
    else:
        WARN.append('endpoint not matched by any group, added to "Other": ' + ekey(m, p))
        grouped.setdefault('Other', []).append((m, p, op))
if 'Other' in grouped and not any(g['name'] == 'Other' for g in GROUPS): GROUPS.append({'name': 'Other', 'blurb': ''})
GROUPS = [g for g in GROUPS if grouped.get(g['name'])]

def tname(v):
    t = v.get('type', 'object')
    if t == 'array':
        it = v.get('items', {}); return 'array of ' + it.get('type', 'object') if it else 'array'
    f = v.get('format'); return t + (' (%s)' % f if f else '')
def sch_notes(v):
    n = []
    if 'enum' in v: n.append('One of: ' + ', '.join('`%s`' % e for e in v['enum']) + '.')
    if 'minimum' in v or 'maximum' in v: n.append('Range %s to %s.' % (v.get('minimum', ''), v.get('maximum', '')))
    if 'default' in v: n.append('Default: `%s`.' % json.dumps(v['default']).strip('"'))
    if v.get('nullable'): n.append('May be null.')
    return n
def override(m, p, name): return EP.get(ekey(m, p), {}).get('fields', {}).get(name)
def body_rows(m, p, schema, prefix=''):
    out = []; reqs = set(schema.get('required', []))
    for k, v in schema.get('properties', {}).items():
        name = prefix + k
        d = override(m, p, name)
        if d is None: d = clean(v.get('description', ''), '%s field %s' % (ekey(m, p), name))
        isreq = 'Yes' if (k in reqs or d.startswith('Required') or d == 'required') else ''
        out.append((name, tname(v), ' '.join(([d] if d else []) + sch_notes(v)), isreq))
        if v.get('type') == 'object' and v.get('properties'): out += body_rows(m, p, v, name + '.')
        if v.get('type') == 'array' and v.get('items', {}).get('type') == 'object' and v['items'].get('properties'):
            out += body_rows(m, p, v['items'], name + '[].')
    return out
def example(v, name='value', drop=()):
    t = v.get('type')
    if t == 'object' or 'properties' in v: return {k: example(c, k) for k, c in v.get('properties', {}).items() if k not in drop}
    if t == 'array': return [example(v['items'], name)] if v.get('items') else []
    if 'example' in v: return v['example']
    if 'enum' in v: return v['enum'][0]
    if 'default' in v: return v['default']
    if t == 'string': return {'date': 'YYYY-MM-DD', 'uri': 'https://example.com', 'date-time': '<ISO-8601 timestamp>'}.get(v.get('format'), '<%s>' % name)
    if t == 'integer': return 0
    if t == 'number': return 0.5
    if t == 'boolean': return True
    return None

def endpoint_block(m, p, op, num):
    e = EP.get(ekey(m, p), {})
    fl = [CondPageBreak(1.9 * inch), Spacer(1, 8)]
    fl.append(KeepTogether([endpoint_heading(num, m, p, CW), Spacer(1, 4), para(fmt(desc_of(m, p, op)), note)]))
    for n in e.get('notes', []): fl += [Spacer(1, 3), para(fmt(n), note)]
    ps = op.get('parameters', [])
    if ps:
        rows = [[para(h, th) for h in ('Name', 'In', 'Type', 'Req', 'Notes')]]
        for x in ps:
            sc = x.get('schema', {}); nm = x['name']; d = override(m, p, nm)
            if d is None: d = clean(x.get('description', ''), '%s param %s' % (ekey(m, p), nm)) or PN.get(nm, '')
            rows.append([para(esc(nm), path), para(x['in'], cell), para(tname(sc), cell), para('Yes' if x.get('required') else '', cell),
                         para(fmt(' '.join(([d] if d else []) + sch_notes(sc))), cell)])
        fl += [para('Parameters', lab), grid(rows, [1.25 * inch, 0.5 * inch, 0.95 * inch, 0.35 * inch, CW - 3.05 * inch])]
    rb = op.get('requestBody')
    if rb:
        ct, c = next(iter(rb['content'].items())); sc = c.get('schema', {})
        fl.append(para('Request body <font color="#5B6470" name="Courier" size="7.5">%s</font>' % ct, lab))
        rows = [[para(h, th) for h in ('Field', 'Type', 'Req', 'Notes')]]
        for nm, ty, nt, rq in body_rows(m, p, sc): rows.append([para(esc(nm), path), para(ty, cell), para(rq, cell), para(fmt(nt), cell)])
        fl += [grid(rows, [2.0 * inch, 1.05 * inch, 0.35 * inch, CW - 3.4 * inch]), para('Example', lab)]
        if e.get('example'): ex = e['example']
        elif ct == 'application/json': ex = json.dumps(example(sc, drop=tuple(e.get('example_drop', []))), indent=2)
        else: ex = '\n'.join('%s=<%s>' % (k, k) for k in sc.get('properties', {}))
        fl.append(code_block(ex))
    first = True
    for code in op.get('responses', {}):
        r = e.get('responses', {}).get(code)
        if r is None:
            WARN.append('no content response text for %s %s' % (ekey(m, p), code))
            r = {'text': clean(op['responses'][code].get('description', ''), 'response %s of %s' % (code, ekey(m, p))) or FALLBACK}
        text, shape = r['text'], r.get('shape')
        items = ([para('Responses', lab)] if first else []) + [para('%s  %s' % (chip(code), fmt(text)), note)]
        if shape:
            cb = code_block(shape)
            if len(shape.split('\n')) <= 14: items += [Spacer(1, 3), cb]
            else: fl.append(KeepTogether(items)); items = []; fl += [Spacer(1, 3), cb]
        if items: fl.append(KeepTogether(items))
        fl.append(Spacer(1, 5)); first = False
    return fl

def brand(c, x, y, size=13, height=None):
    if LOGO:
        from reportlab.lib.utils import ImageReader
        iw, ih = ImageReader(LOGO).getSize(); hh = height or size * 1.9
        c.drawImage(LOGO, x, y, width=hh * iw / ih, height=hh, mask='auto'); return
    c.setFillColor(NAVY); c.setFont('Helvetica-Bold', size); c.drawString(x, y, META['company'])
SUBTITLE = 'Detailed Reference' if DETAILED else 'Product Overview'
TAGLINE = ('Requests, parameters and response structures from the OpenAPI %s specification, v%s' if DETAILED
           else 'Endpoint guide generated from the OpenAPI %s specification, v%s') % (SPEC.get('openapi', '3'), SPEC['info']['version'])
def cover(c, doc):
    c.saveState()
    brand(c, M, H - 1.0 * inch - 1.05 * inch, height=1.05 * inch)
    c.setFillColor(RED); c.rect(M, H * 0.60, 0.9 * inch, 4, fill=1, stroke=0)
    c.setFillColor(NAVY); c.setFont('Helvetica-Bold', 36); c.drawString(M, H * 0.60 - 52, META['product'])
    c.setFillColor(INK); c.setFont('Helvetica', 20); c.drawString(M, H * 0.60 - 82, SUBTITLE)
    c.setFillColor(MUTE); c.setFont('Helvetica', 10.5); c.drawString(M, H * 0.60 - 112, TAGLINE)
    c.setFillColor(HDR); c.rect(0, 0, W, 0.55 * inch, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont('Helvetica', 9); c.drawString(M, 0.22 * inch, META['site'])
    c.restoreState()
def page(c, doc):
    c.saveState(); brand(c, M, H - 0.5 * inch, 10)
    c.setFillColor(MUTE); c.setFont('Helvetica', 8); c.setStrokeColor(RULE); c.line(M, H - 0.6 * inch, W - M, H - 0.6 * inch)
    c.drawString(M, 0.5 * inch, META['site']); c.drawRightString(W - M, 0.5 * inch, 'Page %d' % (doc.page - 1)); c.restoreState()
def page_end(c, doc): draw_running_header(c, doc, SUBTITLE)
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
doc = BaseDocTemplate(args.out, pagesize=letter, leftMargin=M, rightMargin=M, topMargin=0.95 * inch, bottomMargin=0.8 * inch,
                      title='%s %s' % (META['product'], SUBTITLE), author=META['company'], subject='API reference generated from an OpenAPI spec')
fr = Frame(M, 0.8 * inch, CW, H - 1.75 * inch, id='f', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
cfr = Frame(M, 1.3 * inch, CW, H * 0.26, id='c', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
doc.addPageTemplates([PageTemplate('cover', [cfr], onPage=cover), PageTemplate('body', [fr], onPage=page, onPageEnd=page_end)])

story = []
what = ('The detailed edition of the %s guide: for all %d operations, the parameters, request body fields, example payloads and response structures, grouped across %d functional areas.' if DETAILED
        else 'A guided tour of the %s: how to authenticate, how the core workflow runs, and a reference of all %d operations across %d functional areas.') % (META['product'], len(eps), len(GROUPS))
story += [callout_box('What is in this document', what, CW), NextPageTemplate('body'), PageBreak()]

story += [SectionMark('Overview'), para('Overview', h1), para(fmt(OV['intro']), lead), Spacer(1, 8)]
stats = [('%d' % len(eps), 'operations'), ('%d' % len(GROUPS), 'resource areas'), ('%d' % len(SPEC['paths']), 'unique paths')] + [tuple(x) for x in OV.get('stats_extra', [])]
story += [stat_table(stats, CW), para('Servers', h2)]
rows = [[para('Base URL', th), para('Purpose', th)]]
for s in SPEC.get('servers', []):
    purpose = OV.get('servers', {}).get(s['url']) or clean(s.get('description', ''), 'server ' + s['url']) or ''
    rows.append([para('<font name="Courier" size="8">%s</font>' % esc(s['url']), cell), para(fmt(purpose), cell)])
story += [grid(rows, [3.0 * inch, CW - 3.0 * inch])]
if OV.get('authentication'): story += [para('Authentication', h2), para(fmt(OV['authentication']))]
if OV.get('families'):
    fam = [[para('Prefix', th), para('Service', th), para('Handles', th)]]
    for a, b, c_ in OV['families']: fam.append([para('<font name="Courier" size="8">%s</font>' % esc(a), cell), para(fmt(b), cell), para(fmt(c_), cell)])
    story += [para('Service families', h2), grid(fam, [1.3 * inch, 1.2 * inch, CW - 2.5 * inch])]
conv = [x for x in OV.get('conventions', []) if DETAILED or x.get('overview')]
if conv:
    story.append(para('Conventions', h2))
    for i, x in enumerate(conv):
        if i: story.append(Spacer(1, 4))
        story.append(para(fmt(x['text'])))
if DETAILED and OV.get('status_codes'):
    sc = [[para('Code', th), para('Meaning in this API', th)]] + [[para(esc(a), cell), para(fmt(b), cell)] for a, b in OV['status_codes']]
    story.append(KeepTogether([para('Status codes in use', h2), grid(sc, [0.9 * inch, CW - 0.9 * inch])]))

WF = C.get('workflow')
if WF:
    story += [CondPageBreak(3.5 * inch) if DETAILED else PageBreak(), SectionMark('Core workflow'), para(esc(WF['title']), h1), para(fmt(WF['lead']), lead), Spacer(1, 8)]
    if DETAILED:
        rows = [[para(h, th) for h in ('Step', 'Method', 'Endpoint', 'What it does', 'Returns', 'Used by')]]
        for n, m, p, d, rt, ub in WF['steps']: rows.append([para('<b>%s</b>' % n, cell), badge(m), para(esc(p), path), para(fmt(d), cell), para(fmt(rt), cell), para(fmt(ub), cell)])
        story.append(grid(rows, [0.38 * inch, 0.55 * inch, 1.75 * inch, 1.65 * inch, 0.85 * inch, CW - 5.18 * inch]))
    else:
        rows = [[para(h, th) for h in ('Step', 'Method', 'Endpoint', 'What it does')]]
        for n, m, p, d, rt, ub in WF['steps']: rows.append([para('<b>%s</b>' % n, cell), badge(m), para(esc(p), path), para(fmt(d), cell)])
        story.append(grid(rows, [0.45 * inch, 0.6 * inch, 2.55 * inch, CW - 3.6 * inch]))
    for sct in WF.get('sections', []):
        if DETAILED or sct.get('overview'): story += [para(esc(sct['heading']), h2), para(fmt(sct['text']))]

story += [CondPageBreak(3 * inch) if DETAILED else Spacer(1, 14), SectionMark('Endpoint reference'), para('Endpoint reference', h1),
          para('Methods: ' + '  '.join('<font color="%s"><b>%s</b></font>' % (c_, m) for m, c_ in MC.items()) + ('. ' + fmt(C['reference_note']) if DETAILED and C.get('reference_note') else ''), small)]
COLS = [0.42 * inch, 0.62 * inch, 2.5 * inch, CW - 3.54 * inch]
for gi, g in enumerate(GROUPS, 1):
    items = grouped[g['name']]
    if DETAILED: story.append(CondPageBreak(3.2 * inch))
    head = [Spacer(1, 10 if DETAILED else 7), SectionMark('Endpoint reference  ›  %02d  %s' % (gi, g['name'])), section_heading(gi, g['name'], len(items), CW)]
    if g.get('blurb'): head += [Spacer(1, 4 if DETAILED else 3), para(fmt(g['blurb']), small)]
    head.append(Spacer(1, 6 if DETAILED else 4))
    rows = [[para(h, th) for h in ('#', 'Method', 'Path', 'Description')]]
    for ei, (m, p, op) in enumerate(items, 1): rows.append([para('%d.%d' % (gi, ei), cell), badge(m), para(esc(p), path), para(fmt(desc_of(m, p, op)), cell)])
    if DETAILED:
        story += head + [grid(rows, COLS), Spacer(1, 6)]
        for ei, (m, p, op) in enumerate(items, 1): story += endpoint_block(m, p, op, '%d.%d' % (gi, ei))
    else:
        story.append(KeepTogether(head + [grid(rows[:min(len(rows), 4)], COLS)]))
        if len(rows) > 4: story.append(grid(rows[4:], COLS, header=False))
doc.build(story)
print('built %s (%s, %d operations, %d sections)' % (args.out, args.mode, len(eps), len(GROUPS)))
for w in dict.fromkeys(WARN): print('WARNING:', w)
if WARN and args.strict: sys.exit(2)
