import argparse
import html
import os
import re
import sqlite3
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
import pandas as pd


def parse_args():
    p = argparse.ArgumentParser(description='Expert Insights: search an export and read its transcripts.')
    p.add_argument('--csv', help='metadata.csv to load (default: next to the app; env EI_CSV)')
    p.add_argument('--pdfs', help='folder holding <id>.pdf transcripts (default: pdfs/ next to metadata.csv; env EI_PDF_DIR)')
    p.add_argument('--index', help='full-text index from index_transcripts.py (default: transcripts.sqlite next to metadata.csv; env EI_INDEX)')
    p.add_argument('--port', type=int, help='port to serve on (default 5000; env EI_PORT)')
    p.add_argument('--no-browser', action='store_true', help='do not open a browser tab')
    args, _unknown = p.parse_known_args()   # a macOS .app launch can add arguments of its own
    return args


ARGS = parse_args()

# Default locations. Frozen (the macOS .app): the .app sits inside the export folder,
#   <export>/ExpertInsights.app/Contents/MacOS/ExpertInsights  ->  parents[3] == <export>
if getattr(sys, 'frozen', False):
    DATA_DIR = Path(sys.executable).parents[3]
    BUNDLE_DIR = Path(sys._MEIPASS)
    CSV_FILE = DATA_DIR / 'metadata.csv'
    PDF_DIR = DATA_DIR / 'pdfs'
else:
    BUNDLE_DIR = Path(__file__).parent
    CSV_FILE = BUNDLE_DIR / 'metadata.csv'
    PDF_DIR = BUNDLE_DIR / 'pdfs'

# Overrides: command line first, then environment, then the defaults above.
CSV_FILE = Path(ARGS.csv or os.environ.get('EI_CSV') or CSV_FILE).expanduser()
PDF_DIR = Path(ARGS.pdfs or os.environ.get('EI_PDF_DIR') or PDF_DIR).expanduser()


def default_index():
    """transcripts.sqlite next to the CSV, else next to the app (where index_transcripts.py writes it)."""
    candidates = [CSV_FILE.parent / 'transcripts.sqlite']
    if not getattr(sys, 'frozen', False):
        candidates.append(BUNDLE_DIR / 'transcripts.sqlite')
    return next((c for c in candidates if c.exists()), candidates[0])


INDEX_FILE = Path(ARGS.index or os.environ.get('EI_INDEX') or default_index()).expanduser()
PORT = ARGS.port or int(os.environ.get('EI_PORT', 5000))

app = Flask(
    __name__,
    template_folder=str(BUNDLE_DIR / 'templates'),
    static_folder=str(BUNDLE_DIR / 'static'),
)

df = pd.read_csv(CSV_FILE, dtype=str).fillna('')
# format='ISO8601': exports mix "2026-09-05T17:30:00" and "2026-09-05T12:00:00+00:00"; without an
# explicit format pandas infers one from the first row and blanks every row in the other style.
df['released_at'] = pd.to_datetime(df['released_at'], utc=True, errors='coerce', format='ISO8601')
df = df.sort_values('released_at', ascending=False).reset_index(drop=True)

print(f"Loaded {len(df):,} records from {CSV_FILE}")
if PDF_DIR.is_dir():
    print(f"PDF folder: {PDF_DIR} ({sum(1 for p in PDF_DIR.iterdir() if p.suffix.lower() == '.pdf'):,} PDFs)")
else:
    print(f"PDF folder not found: {PDF_DIR}  (pass --pdfs or set EI_PDF_DIR)")

SORT_FIELDS = {'released_at', 'title'}


# ---- transcript full-text index (optional; built by index_transcripts.py) ----

def open_index():
    if not INDEX_FILE.exists():
        print("Transcript index: none (search covers title, company, expert type and summary; "
              "run index_transcripts.py to search inside the transcripts)")
        return None
    try:
        conn = sqlite3.connect(f"file:{INDEX_FILE}?mode=ro", uri=True, check_same_thread=False)
        n = conn.execute("SELECT count(*) FROM files").fetchone()[0]
        print(f"Transcript index: {n:,} transcripts ({INDEX_FILE})")
        return conn
    except sqlite3.Error as e:
        print(f"Transcript index unusable ({INDEX_FILE}): {e}")
        return None


INDEX = open_index()
INDEX_LOCK = threading.Lock()
TOKEN_RE = re.compile(r'[^\W_]+')


def fts_query(query):
    """Free text -> FTS5 query: every word is required and matches as a prefix ("pric"* finds pricing)."""
    tokens = TOKEN_RE.findall(query)
    return ' '.join(f'"{t}"*' for t in tokens) if tokens else None


def index_matches(query):
    """ids of transcripts whose text contains every word of the query."""
    q = fts_query(query)
    if INDEX is None or not q:
        return set()
    try:
        with INDEX_LOCK:
            rows = INDEX.execute('SELECT id FROM transcripts WHERE transcripts MATCH ?', (q,)).fetchall()
    except sqlite3.OperationalError as e:
        print(f"Transcript index query failed for {query!r}: {e}")
        return set()
    return {r[0] for r in rows}


def index_snippets(query, ids):
    """Per id, an HTML-escaped excerpt with <mark> around the matched words."""
    q = fts_query(query)
    ids = list(ids)
    if INDEX is None or not q or not ids:
        return {}
    sql = (f"SELECT id, snippet(transcripts, 1, ?, ?, ?, 18) FROM transcripts "
           f"WHERE transcripts MATCH ? AND id IN ({','.join('?' * len(ids))})")
    try:
        with INDEX_LOCK:
            rows = INDEX.execute(sql, ['\x01', '\x02', ' … ', q, *ids]).fetchall()
    except sqlite3.OperationalError as e:
        print(f"Transcript snippet query failed for {query!r}: {e}")
        return {}
    out = {}
    for doc_id, snip in rows:
        text = html.escape(' '.join(snip.split()))
        out[doc_id] = text.replace('\x01', '<mark>').replace('\x02', '</mark>')
    return out


def index_count():
    if INDEX is None:
        return None
    with INDEX_LOCK:
        return INDEX.execute("SELECT count(*) FROM files").fetchone()[0]


def serialize(records):
    out = []
    for r in records:
        d = r.copy()
        ts = d.get('released_at')
        try:
            d['released_at'] = ts.strftime('%Y-%m-%d') if pd.notna(ts) else ''
        except Exception:
            d['released_at'] = ''
        out.append({k: d.get(k, '') for k in (
            'id', 'title', 'primary_companies', 'primary_company_ticker', 'released_at',
            'source_label', 'source_descriptor', 'summary', 'page_count',
        )})
    return out


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status')
def status():
    return jsonify({
        'records': len(df),
        'pdf_dir': str(PDF_DIR),
        'index': str(INDEX_FILE) if INDEX is not None else None,
        'indexed': index_count(),
    })


@app.route('/api/interviews')
def get_interviews():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    sort_by = request.args.get('sort_by', 'released_at')
    sort_order = request.args.get('sort_order', 'desc')
    if sort_by not in SORT_FIELDS:
        sort_by = 'released_at'

    sorted_df = df.sort_values(by=sort_by, ascending=sort_order == 'asc', na_position='last')
    start = (page - 1) * per_page
    page_df = sorted_df.iloc[start:start + per_page]

    return jsonify({
        'interviews': serialize(page_df.to_dict('records')),
        'total': len(df),
        'page': page,
        'per_page': per_page,
    })


@app.route('/api/search')
def search_interviews():
    query = request.args.get('query', '').strip()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    sort_by = request.args.get('sort_by', 'released_at')
    sort_order = request.args.get('sort_order', 'desc')
    if sort_by not in SORT_FIELDS:
        sort_by = 'released_at'

    try:
        if query:
            mask = (
                df['title'].str.contains(query, case=False, na=False, regex=False)
                | df['primary_companies'].str.contains(query, case=False, na=False, regex=False)
                | df['source_descriptor'].str.contains(query, case=False, na=False, regex=False)
                | df['summary'].str.contains(query, case=False, na=False, regex=False)
            )
            in_transcript = index_matches(query)
            if in_transcript:
                mask = mask | df['id'].isin(in_transcript)
            results = df[mask]
        else:
            in_transcript = set()
            results = df

        sorted_results = results.sort_values(by=sort_by, ascending=sort_order == 'asc', na_position='last')
        start = (page - 1) * per_page
        page_df = sorted_results.iloc[start:start + per_page]

        interviews = serialize(page_df.to_dict('records'))
        snippets = index_snippets(query, [r['id'] for r in interviews if r['id'] in in_transcript])
        for r in interviews:
            if r['id'] in snippets:
                r['snippet'] = snippets[r['id']]

        return jsonify({
            'interviews': interviews,
            'total': len(results),
            'page': page,
            'per_page': per_page,
        })
    except Exception as e:
        print(f"Search error for query={query!r}: {e}")
        return jsonify({'error': str(e), 'interviews': [], 'total': 0, 'page': page, 'per_page': per_page}), 500


@app.route('/pdf/<doc_id>')
def serve_pdf(doc_id):
    pdf_path = PDF_DIR / f"{doc_id}.pdf"
    if not pdf_path.exists():
        return 'PDF not found', 404
    return send_file(pdf_path, mimetype='application/pdf')


def free_port(port):
    """Kill whatever process is holding the port."""
    import socket, os, signal, subprocess
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('localhost', port)) != 0:
            return
    print(f"Port {port} in use — killing existing process...")
    try:
        if sys.platform == 'win32':
            subprocess.call(
                f'for /f "tokens=5" %a in (\'netstat -aon ^| findstr :{port}\') do taskkill /F /PID %a',
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            result = subprocess.check_output(['lsof', '-ti', f':{port}'])
            for pid in result.decode().split():
                os.kill(int(pid), signal.SIGKILL)
    except Exception as e:
        print(f"  Warning: {e}")
    import time; time.sleep(1)


def open_browser():
    import time
    time.sleep(2)
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == '__main__':
    free_port(PORT)
    if not ARGS.no_browser:
        threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, port=PORT)
