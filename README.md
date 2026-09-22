# Expert Insights

A small local viewer for an "expert insights" export: a searchable, sortable list of
expert-interview records (`metadata.csv`) with a PDF pane that shows the matching
transcript from `pdfs/<id>.pdf`.

The macOS build (`ExpertInsights-mac.zip`) is a PyInstaller bundle of this Flask app.
The source in `expert_insights_export/` was recovered from that bundle (the Python
bytecode of the recovered `app.py` matches the bundled script exactly) so the app can
be run and modified on any platform.

## Layout

```
expert_insights_export/
  app.py              Flask app (search, sort, pagination, PDF serving)
  templates/index.html
  static/script.js
  static/style.css
  metadata.csv        SYNTHETIC sample data (36 records) so the app runs out of the box
  pdfs/<id>.pdf       one placeholder PDF per sample record
  requirements.txt
```

`metadata.csv` and `pdfs/` here are placeholders. Replace them with the real export
(the real files are deliberately not committed to this repository); the app reads
these columns from the CSV and ignores any others:

`id, title, primary_companies, primary_company_ticker, released_at, source_label,
source_descriptor, summary, page_count`

## Date parsing fix

The bundled macOS build calls `pd.to_datetime(..., utc=True, errors='coerce')` without a
format. A real export mixes `2026-09-05T17:30:00` and `2026-09-05T12:00:00+00:00` in
`released_at`; pandas infers the format from the first row and silently turns every
row in the other style into a blank date (794 of 4,732 rows in the September 2026
export, all of them the newest records, which then sort to the end). `app.py` here
passes `format='ISO8601'`, which parses both styles. Rebuild the macOS binary from this
source to pick up the fix.

## Run from source

```
cd expert_insights_export
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The app frees port 5000 if something else holds it, starts on
http://localhost:5000 and opens a browser tab after two seconds.

## Where the macOS build looks for its data

When frozen, the app resolves the data folder as three levels above the executable,
i.e. it expects the `.app` to sit inside the export folder:

```
expert_insights_export/
  ExpertInsights.app/Contents/MacOS/ExpertInsights
  metadata.csv
  pdfs/
```

A bare `ExpertInsights` executable run from, say, `~/Downloads` resolves the data
folder to `/` and fails at startup because `/metadata.csv` does not exist.

## Static preview

`preview/build_preview.py` produces a single-file, server-less copy of the UI: the CSV
rows are embedded gzip-compressed, the search/sort/paging logic of `app.py` is
re-implemented in the page, and every `pdfs/<id>.pdf` that exists is rendered to page
images with MuPDF (lossless WebP) so no browser PDF engine is involved. Records without
a PDF show a notice instead.

```
pip install -r preview/requirements.txt
python3 preview/build_preview.py expert_insights_export preview/expert-insights-preview.html \
    --note "Data: one sentence for the banner"
```

The output is a build product and is not committed. A 4,732-record export with one
12-page PDF becomes a 5MB page; hosted artifacts are capped at 16MB, so with a full PDF
set embed a subset. `preview/make_sample_data.py <export dir>` regenerates the synthetic
sample dataset.
