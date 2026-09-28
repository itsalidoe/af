#!/usr/bin/env python3
"""Build or update the transcript full-text index that app.py's search box uses.

    python index_transcripts.py --pdfs /Users/you/Downloads/pdfs
    python index_transcripts.py --pdfs /Users/you/Downloads/pdfs --index /somewhere/transcripts.sqlite --workers 8

Every <id>.pdf in the folder is read with MuPDF and its text stored in an SQLite FTS5 table
(transcripts.sqlite next to this script unless --index says otherwise). Re-running is
incremental: unchanged files are skipped, changed ones re-read, deleted ones dropped.
"""
import argparse
import os
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    id         TEXT PRIMARY KEY,
    path       TEXT NOT NULL,
    size       INTEGER NOT NULL,
    mtime      REAL NOT NULL,
    pages      INTEGER NOT NULL,
    chars      INTEGER NOT NULL,
    indexed_at REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS transcripts USING fts5(
    id UNINDEXED,
    text,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


def extract(path):
    """Read one PDF in a worker process; returns (path, pages, text, error)."""
    import pymupdf
    try:
        with pymupdf.open(path) as doc:
            pages = [page.get_text() for page in doc]
        return path, len(pages), '\n'.join(pages), None
    except Exception as e:                      # one bad file must not stop the run
        return path, 0, '', f'{type(e).__name__}: {e}'


def main():
    ap = argparse.ArgumentParser(description='Index the text of every transcript PDF for app.py search.')
    ap.add_argument('--pdfs', required=True, help='folder of <id>.pdf files')
    ap.add_argument('--index', default=str(Path(__file__).with_name('transcripts.sqlite')),
                    help='SQLite file to write (default: transcripts.sqlite next to this script)')
    ap.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 1),
                    help='parallel PDF readers (default: CPU count minus one)')
    args = ap.parse_args()

    pdf_dir = Path(args.pdfs).expanduser()
    if not pdf_dir.is_dir():
        sys.exit(f'not a folder: {pdf_dir}')
    files = sorted(p for p in pdf_dir.iterdir() if p.suffix.lower() == '.pdf')
    print(f'{len(files):,} PDFs in {pdf_dir}')

    conn = sqlite3.connect(args.index)
    conn.executescript(SCHEMA)
    known = {row[0]: (row[1], row[2]) for row in conn.execute('SELECT id, size, mtime FROM files')}

    todo = []
    for p in files:
        st = p.stat()
        if known.get(p.stem) != (st.st_size, st.st_mtime):
            todo.append(str(p))
    present = {p.stem for p in files}
    gone = [doc_id for doc_id in known if doc_id not in present]
    if gone:
        conn.executemany('DELETE FROM transcripts WHERE id = ?', [(i,) for i in gone])
        conn.executemany('DELETE FROM files WHERE id = ?', [(i,) for i in gone])
        conn.commit()
    print(f'{len(todo):,} to read, {len(files) - len(todo):,} unchanged, {len(gone):,} removed')

    errors = []
    started = time.time()
    done = 0
    if todo:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for path, pages, text, err in pool.map(extract, todo, chunksize=8):
                done += 1
                doc_id = Path(path).stem
                if err:
                    errors.append((doc_id, err))       # left out of `files`, so the next run retries it
                else:
                    st = Path(path).stat()
                    conn.execute('DELETE FROM transcripts WHERE id = ?', (doc_id,))
                    conn.execute('INSERT INTO transcripts (id, text) VALUES (?, ?)', (doc_id, text))
                    conn.execute('INSERT OR REPLACE INTO files (id, path, size, mtime, pages, chars, indexed_at) '
                                 'VALUES (?, ?, ?, ?, ?, ?, ?)',
                                 (doc_id, path, st.st_size, st.st_mtime, pages, len(text), time.time()))
                if done % 250 == 0 or done == len(todo):
                    conn.commit()
                    rate = done / max(time.time() - started, 1e-6)
                    print(f'  {done:,}/{len(todo):,}  {rate:.0f} files/s, about {(len(todo) - done) / max(rate, 1e-6):.0f}s left')
        conn.execute("INSERT INTO transcripts(transcripts) VALUES('optimize')")
        conn.commit()

    total = conn.execute('SELECT count(*) FROM files').fetchone()[0]
    conn.close()
    print(f'index: {args.index}  ({total:,} transcripts, {Path(args.index).stat().st_size / 1024 / 1024:.1f} MB)')
    if errors:
        print(f'{len(errors)} files could not be read:')
        for doc_id, err in errors[:10]:
            print(f'  {doc_id}: {err}')


if __name__ == '__main__':
    main()
