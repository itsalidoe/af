import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
import pandas as pd

# Locate the data folder (metadata.csv + pdfs/) and the bundled templates/static.
# Frozen (PyInstaller .app): the .app is expected to sit inside the export folder,
#   <export>/ExpertInsights.app/Contents/MacOS/ExpertInsights  ->  parents[3] == <export>
if getattr(sys, 'frozen', False):
    DATA_DIR = Path(sys.executable).parents[3]
    BUNDLE_DIR = Path(sys._MEIPASS)
    PDF_DIR = DATA_DIR / 'pdfs'
    CSV_FILE = DATA_DIR / 'metadata.csv'
else:
    BUNDLE_DIR = Path(__file__).parent
    CSV_FILE = Path(__file__).parent / 'metadata.csv'
    PDF_DIR = Path(__file__).parent.parent / 'expert_insights_export' / 'pdfs'

app = Flask(
    __name__,
    template_folder=str(BUNDLE_DIR / 'templates'),
    static_folder=str(BUNDLE_DIR / 'static'),
)

df = pd.read_csv(CSV_FILE, dtype=str).fillna('')
df['released_at'] = pd.to_datetime(df['released_at'], utc=True, errors='coerce', format='ISO8601')
df = df.sort_values('released_at', ascending=False).reset_index(drop=True)

print(f"Loaded {len(df):,} records.")

SORT_FIELDS = {'released_at', 'title'}


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
            results = df[mask]
        else:
            results = df

        sorted_results = results.sort_values(by=sort_by, ascending=sort_order == 'asc', na_position='last')
        start = (page - 1) * per_page
        page_df = sorted_results.iloc[start:start + per_page]

        return jsonify({
            'interviews': serialize(page_df.to_dict('records')),
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


PORT = 5000


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
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, port=PORT)
