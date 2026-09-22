"""Build a self-contained static preview of the Expert Insights app.

    python3 build_preview.py <export dir> <output.html> [--note "banner sentence"]

Loads metadata.csv exactly the way app.py does (pandas, dtype=str, UTC dates), embeds the
records gzip-compressed, renders every pdfs/<id>.pdf that exists to page images, and re-implements the
/api/interviews, /api/search and /pdf/<id> behaviour in the page."""
import base64, gzip, json, sys
from pathlib import Path

import pandas as pd

args = sys.argv[1:]
note = ''
if '--note' in args:
    i = args.index('--note')
    note = args[i + 1]
    del args[i:i + 2]
EXPORT, OUT = Path(args[0]), Path(args[1])

FIELDS = ['id', 'title', 'primary_companies', 'primary_company_ticker', 'released_at',
          'source_label', 'source_descriptor', 'summary', 'page_count']

# Same load as app.py
df = pd.read_csv(EXPORT / 'metadata.csv', dtype=str).fillna('')
df['released_at'] = pd.to_datetime(df['released_at'], utc=True, errors='coerce', format='ISO8601')
df = df.sort_values('released_at', ascending=False).reset_index(drop=True)

records = []
for r in df.to_dict('records'):
    ts = r.get('released_at')
    d = {k: r.get(k, '') for k in FIELDS}
    d['released_at'] = ts.strftime('%Y-%m-%d') if pd.notna(ts) else ''   # what serialize() returns
    d['_ts'] = ts.isoformat() if pd.notna(ts) else None                  # sort key (None == NaT)
    records.append(d)

import io
import pymupdf
from PIL import Image

DPI = 130   # 1105 px wide letter pages: crisp in the 760 px pane, also on high-density screens

def render_pages(pdf_path):
    """Rasterise every page with MuPDF and pack it as a lossless WebP data URI."""
    out = []
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=DPI)
            im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            buf = io.BytesIO()
            im.save(buf, format='WEBP', lossless=True, quality=100)
            out.append('data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode('ascii'))
    return out

pdfs = {}
for r in records:
    p = EXPORT / 'pdfs' / f"{r['id']}.pdf"
    if p.exists():
        pdfs[r['id']] = render_pages(p)

def js(obj):
    return json.dumps(obj, ensure_ascii=True, separators=(',', ':')).replace('</', '<\\/')

data_json = json.dumps(records, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
data_b64 = base64.b64encode(gzip.compress(data_json, compresslevel=9)).decode('ascii')

n, npdf = len(records), len(pdfs)
if not note:
    note = f"Data: {n:,} records from metadata.csv."
if npdf == n:
    pdf_note = f"PDFs: all {npdf:,} included."
elif npdf == 0:
    pdf_note = "PDFs: none were provided, so the document pane shows a notice instead."
else:
    pdf_note = f"PDFs: {npdf:,} of {n:,} included; records that have one carry a PDF badge, the rest show a notice."

html = (Path(__file__).parent / 'preview_template.html').read_text(encoding='utf-8')
for k, v in {
    '__DATA_B64__': data_b64,
    '__PAGES__': js(pdfs),
    '__COUNT__': f"{n:,}",
    '__DATA_NOTE__': note.replace('<', '&lt;'),
    '__PDF_NOTE__': pdf_note.replace('<', '&lt;'),
}.items():
    html = html.replace(k, v)
OUT.write_text(html, encoding='utf-8')
print(f"wrote {OUT} ({OUT.stat().st_size/1024/1024:.2f} MB): {n} records ({len(data_json)/1024/1024:.1f} MB JSON -> {len(data_b64)/1024/1024:.1f} MB gzip+base64), {npdf} pdfs rendered to {sum(len(v) for v in pdfs.values())} page images")
