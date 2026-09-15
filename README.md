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

`metadata.csv` and `pdfs/` here are placeholders. Replace them with the real export;
the app reads these columns from the CSV:

`id, title, primary_companies, primary_company_ticker, released_at, source_label,
source_descriptor, summary, page_count`

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
