"""Build a self-contained static preview of the Expert Insights app.
Embeds metadata.csv (pre-serialised exactly like the Flask API) and the PDFs (base64),
and re-implements the /api/interviews, /api/search and /pdf/<id> behaviour client-side."""
import base64, csv, json, sys
from datetime import datetime, timezone
from pathlib import Path

EXPORT = Path(sys.argv[1])
OUT = Path(sys.argv[2])

FIELDS = ['id', 'title', 'primary_companies', 'primary_company_ticker', 'released_at',
          'source_label', 'source_descriptor', 'summary', 'page_count']

records = []
for r in csv.DictReader(open(EXPORT / 'metadata.csv', encoding='utf-8')):
    r = {k: (r.get(k) or '') for k in FIELDS}
    ts = None
    if r['released_at']:
        dt = datetime.strptime(r['released_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        ts = dt.isoformat()
        r['released_at'] = dt.strftime('%Y-%m-%d')   # what serialize() returns
    r['_ts'] = ts                                     # sort key (None == NaT)
    records.append(r)

pdfs = {}
for r in records:
    p = EXPORT / 'pdfs' / f"{r['id']}.pdf"
    if p.exists():
        pdfs[r['id']] = base64.b64encode(p.read_bytes()).decode('ascii')

def js(obj):
    return json.dumps(obj, ensure_ascii=True, separators=(',', ':')).replace('</', '<\\/')

html = open(Path(__file__).parent / 'preview_template.html', encoding='utf-8').read()
html = html.replace('__RECORDS__', js(records)).replace('__PDFS__', js(pdfs)).replace('__COUNT__', str(len(records)))
OUT.write_text(html, encoding='utf-8')
print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB), {len(records)} records, {len(pdfs)} pdfs")
