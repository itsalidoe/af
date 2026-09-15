"""Generate a small, clearly synthetic dataset so the Expert Insights app can run
without the real export. Writes metadata.csv and one placeholder PDF per record."""
import csv
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(sys.argv[1])
PDF_DIR = OUT / "pdfs"
PDF_DIR.mkdir(parents=True, exist_ok=True)

random.seed(7)

COMPANIES = [
    ("Northwind Robotics", "NWRB", "warehouse automation"),
    ("Cobalt Grid Energy", "CBGE", "battery storage"),
    ("Harbor Lane Health", "HRLH", "outpatient clinics"),
    ("Sableridge Semiconductors", "SBRS", "power chips"),
    ("Meridian Freight Systems", "MRFS", "cross-border trucking"),
    ("Juniper Cloud Analytics", "JNCA", "usage-based data platform"),
    ("Tidewater Foods", "TDWF", "frozen seafood"),
    ("Orion Payments", "ORNP", "merchant acquiring"),
    ("Kestrel Aerospace Parts", "KSAP", "aftermarket components"),
    ("Bluefern Biosciences", "BLFB", "rare disease therapeutics"),
    ("Granite Peak Insurance", "GPKI", "specialty commercial lines"),
    ("Lumen Street Retail", "LMSR", "off-price apparel"),
]

ROLES = [
    "Former VP of Sales", "Former Director of Product", "Former Regional GM",
    "Former Head of Supply Chain", "Industry Consultant", "Former Finance Director",
    "Channel Partner Executive", "Former Plant Manager", "Customer (Procurement Lead)",
    "Former Head of Engineering",
]

TOPICS = [
    "pricing power and contract renewals",
    "competitive positioning versus the two largest rivals",
    "unit economics of the newest product line",
    "customer churn drivers and retention levers",
    "capacity expansion timeline and capex needs",
    "channel strategy and distributor incentives",
    "regulatory exposure and compliance costs",
    "gross margin outlook through next year",
    "management changes and execution risk",
    "demand signals from the largest customer segment",
]


def summary_for(company, sector, role, topic):
    templates = [
        "A {role} discusses {company}'s {topic}, with emphasis on how {sector} demand has shifted over the past four quarters.",
        "Call covering {company}'s {topic}. The expert compares current practice against peers in {sector} and flags what to watch next.",
        "The expert, a {role}, walks through {topic} at {company} and gives a view on realistic scenarios for the next 12 to 18 months.",
    ]
    return random.choice(templates).format(role=role.lower(), company=company, topic=topic, sector=sector)


def esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def wrap(text, width=80):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def make_pdf(path, title, meta_lines, body_paragraphs):
    ops = []
    y = 770
    ops.append(f"BT /F2 15 Tf 50 {y} Td ({esc('SYNTHETIC SAMPLE TRANSCRIPT - placeholder for preview only')}) Tj ET")
    y -= 30
    for line in wrap(title, 62):
        ops.append(f"BT /F2 13 Tf 50 {y} Td ({esc(line)}) Tj ET")
        y -= 18
    y -= 6
    for line in meta_lines:
        ops.append(f"BT /F1 10 Tf 50 {y} Td ({esc(line)}) Tj ET")
        y -= 14
    y -= 10
    for para in body_paragraphs:
        for line in wrap(para, 92):
            ops.append(f"BT /F1 10 Tf 50 {y} Td ({esc(line)}) Tj ET")
            y -= 13
        y -= 8
    stream = "\n".join(ops).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(bytes(out))


rows = []
start = datetime(2024, 3, 1, tzinfo=timezone.utc)
n = 0
for company, ticker, sector in COMPANIES:
    for _ in range(3):
        n += 1
        role = random.choice(ROLES)
        topic = random.choice(TOPICS)
        released = start + timedelta(days=random.randint(0, 900), hours=random.randint(8, 18))
        doc_id = f"sample-{n:03d}"
        title = f"{role} on {company}: {topic}"
        summary = summary_for(company, sector, role, topic)
        page_count = random.randint(6, 28)
        rows.append({
            "id": doc_id,
            "title": title,
            "primary_companies": company,
            "primary_company_ticker": ticker,
            "released_at": released.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_label": "Synthetic sample",
            "source_descriptor": role,
            "summary": summary,
            "page_count": str(page_count),
        })
        make_pdf(
            PDF_DIR / f"{doc_id}.pdf",
            title,
            [f"Company: {company} ({ticker})", f"Released: {released.strftime('%Y-%m-%d')}",
             f"Source: {role}", f"Pages in original: {page_count}"],
            [
                "This is a generated placeholder standing in for the real interview transcript. "
                "The real export ships one PDF per record in the pdfs/ folder, named <id>.pdf.",
                "Summary: " + summary,
                "Q: How would you characterize the last two quarters? A: The expert describes a "
                "gradual normalization after an unusually strong prior year, with pricing holding "
                "better than volumes. Q: What should investors watch? A: Renewal outcomes in the "
                "largest accounts and any change in the discounting posture of the two main rivals.",
            ],
        )

# A couple of edge cases the real data can contain: a blank ticker, and a blank date.
rows[4]["primary_company_ticker"] = ""
rows[9]["released_at"] = ""

fields = ["id", "title", "primary_companies", "primary_company_ticker", "released_at",
          "source_label", "source_descriptor", "summary", "page_count"]
with (OUT / "metadata.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
print(f"wrote {len(rows)} rows to {OUT/'metadata.csv'} and {len(rows)} PDFs to {PDF_DIR}")
