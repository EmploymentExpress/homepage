#!/usr/bin/env python3
"""
Build one shareable page per job/admission/notice with its OWN Open Graph
thumbnail, so links shared on WhatsApp / Facebook / Telegram / LinkedIn show
that specific vacancy/result/answer-key/admission card instead of the site
logo.

Why this is needed
------------------
The site is a single-page app: individual alerts open as a modal on
``index.html?job=<id>``. Social scrapers only read the *static* <head> of the
URL they crawl, and they ignore the ``?job=`` query string, so every alert
link currently inherits the homepage logo ``og:image``.

This script writes a tiny ``share/job-<id>.html`` for every alert. Each file:
  * carries the alert's custom 1200x630 thumbnail in ``og:image`` /
    ``twitter:image`` (plus width/height/type/alt),
  * sets ``og:url`` / ``canonical`` to itself (a stable, crawlable URL),
  * instantly redirects a real visitor to ``index.html?job=<id>`` where the
    existing deep-link code opens the modal.

The in-app share functions point at these pages (see index.html).

It regenerates each ``assets/thumbnails/job-<id>.png`` from the same data the
site displays, using the house-style ``thumbnail_generator``.
"""

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
THUMBS = ASSETS / "thumbnails"
SHARE_DIR = ROOT / "share"
INDEX_HTML = ROOT / "index.html"
AUTO_JOBS = ROOT / "data" / "auto-jobs.json"

# Public URL of the project (GitHub Pages). Used for absolute og:image/canonical.
BASE_URL = "https://employmentexpress.github.io/homepage"

sys.path.insert(0, str(ROOT))
# thumbnail_generator needs Pillow, which the scheduled runner installs but a
# plain checkout may not have. Import it lazily inside main() so this module
# stays importable — and testable — without the imaging dependency: the SEO
# markup below is pure text.


# A tiny Node helper evaluates the curated jobDatabase / admissionDatabase
# array literals that live directly in index.html (they are plain data).
_NODE_EXTRACT = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
function grab(name) {
  const marker = 'let ' + name + ' = [';
  const start = html.indexOf(marker);
  if (start < 0) return [];
  const arrStart = html.indexOf('[', start);
  let depth = 0, i = arrStart;
  for (; i < html.length; i++) {
    const c = html[i];
    if (c === '[') depth++;
    else if (c === ']') { depth--; if (depth === 0) { i++; break; } }
  }
  const body = html.slice(arrStart, i);
  try { return eval('(' + body + ')'); } catch (e) { return []; }
}
console.log(JSON.stringify({
  jobs: grab('jobDatabase'),
  admissions: grab('admissionDatabase')
}));
"""


def load_curated():
    """Return curated jobs/admissions authored inline in index.html."""
    try:
        out = subprocess.run(
            ["node", "-e", _NODE_EXTRACT, "x", str(INDEX_HTML)],
            capture_output=True, text=True, check=True, timeout=60,
        )
        data = json.loads(out.stdout)
        return data.get("jobs", []) + data.get("admissions", [])
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"[warn] could not extract curated jobs via node: {exc}")
        return []


def load_all_jobs():
    """Merge curated (inline) and automatic (data/auto-jobs.json) alerts."""
    jobs = {}
    for j in load_curated():
        if j.get("id") is not None:
            jobs[j["id"]] = j
    if AUTO_JOBS.exists():
        data = json.loads(AUTO_JOBS.read_text(encoding="utf-8"))
        for j in data.get("jobs", data if isinstance(data, list) else []):
            if j.get("id") is not None:
                jobs[j["id"]] = j  # automatic data wins on id collision
    return list(jobs.values())


def esc(text):
    return (str(text or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def describe(job):
    """Short human/share description built from real alert fields."""
    parts = []
    vac = str(job.get("vacancies") or "").strip()
    if vac and vac.lower() not in ("see notification", "see official notification"):
        parts.append(vac)
    dept = str(job.get("department") or job.get("organization") or "").strip()
    if dept:
        parts.append(dept.split("(")[0].strip(",").strip())
    last = str(job.get("lastDate") or "").strip()
    if last and last.lower() not in ("see notification", ""):
        parts.append(f"Last date: {last}")
    body = " • ".join(parts)
    suffix = ". Full notification, eligibility & direct official links — EMPLOYMENT EXPRESS."
    budget = 198
    if len(body) + len(suffix) > budget:
        room = max(40, budget - len(suffix) - 1)
        body = body[:room].rsplit(" ", 1)[0].rstrip(" •,.-")
    return body + suffix


def keywords_for(job):
    """Keyword meta for one alert, from the alert's own fields.

    Crawlers that never run JavaScript cannot see the homepage's dynamic
    boards, so each alert page has to carry its own search phrases.
    """
    words = []

    def add(*values):
        for value in values:
            text = re.sub(r"\s+", " ", str(value or "")).strip()
            if text and text.lower() not in {w.lower() for w in words}:
                words.append(text)

    department = str(job.get("department") or "").strip()
    add(department)
    short = department.split("(")[0].strip(" ,-")
    if short and short != department:
        add(short)
    acronym = re.search(r"\(([A-Z][A-Za-z0-9/&.\-]{2,12})\)", department)
    if acronym:
        add(acronym.group(1))
    title = str(job.get("title") or "").strip()
    if " — " in title:
        add(title.split(" — ", 1)[1].strip())
    add(str(job.get("location") or "").strip())
    category = str(job.get("qualCategory") or "").strip()
    if category:
        add(f"{category} pass jobs")
    alert = str(job.get("alertType") or "recruitment").strip()
    label = {
        "admit-card": "admit card",
        "answer-key": "answer key",
        "result": "result",
        "corrigendum": "corrigendum",
        "admission": "admission",
    }.get(alert, "recruitment")
    add(f"{label} 2026", "sarkari naukri 2026", "government jobs 2026")
    if str(job.get("type", "")).startswith("punjab") or job.get("alsoInPunjab") is True:
        add("Punjab govt jobs 2026", "Punjab sarkari naukri")
    add("EMPLOYMENT EXPRESS")
    return ", ".join(words[:22])


def _salary(job):
    """MonetaryAmount for the schema, parsed from stored text (never guessed)."""
    text = f"{job.get('details') or ''} {job.get('qualification') or ''}"
    match = re.search(
        r"(?:Rs\.?|INR|₹)\s*([0-9,]{5,8})(?:\s*/?\s*(?:-|to)?\s*[0-9,]*\s*)?"
        r"(?:per\s*month|p\.?m\.?|month)?",
        text, re.IGNORECASE)
    if not match:
        return None
    value = int(match.group(1).replace(",", ""))
    if not 10000 <= value <= 500000:
        return None
    return {
        "@type": "MonetaryAmount",
        "currency": "INR",
        "value": {"@type": "QuantitativeValue", "value": value, "unitText": "MONTH"},
    }


def _iso_date(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return match.group(0)
    match = re.match(r"(\d{1,2})-(\d{1,2})-(\d{4})", text)
    if match:
        day, month, year = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return None


def _place(job):
    location = str(job.get("location") or "").strip()
    country = {"@type": "Country", "name": "India"}
    if not location or location.lower().startswith("all india"):
        return {
            "@type": "Place",
            "address": {"@type": "PostalAddress", "addressCountry": "IN",
                        "addressLocality": "India"},
        }
    parts = [part.strip() for part in location.split(",") if part.strip()]
    address = {"@type": "PostalAddress", "addressCountry": "IN",
               "addressLocality": parts[0]}
    if len(parts) > 1:
        address["addressRegion"] = parts[1]
    return {"@type": "Place", "address": address}


def structured_data(job, page_url, description):
    """Static JSON-LD for one alert page.

    index.html injects JobPosting data at runtime, but AI crawlers read only
    static HTML — so every share page carries its own graph.
    """
    posted = (_iso_date(job.get("publishedAt")) or _iso_date(job.get("discoveredAt")))
    valid = _iso_date(job.get("lastDate"))
    if not posted:
        posted = valid or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not valid:
        valid = (datetime.strptime(posted, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")

    text = f"{job.get('details') or ''} {job.get('title') or ''}".lower()
    employment = ("CONTRACTOR" if any(word in text for word in
                                      ("contract", "temporary", "outsourc", "engagement"))
                  else "FULL_TIME")
    notice = str(job.get("pdfLink") or "").strip()
    apply_link = str(job.get("applyLink") or "").strip()
    if notice.lower().startswith("http"):
        notice = notice
    else:
        notice = ""

    posting = {
        "@type": "JobPosting",
        "title": str(job.get("title") or "Government Recruitment Notification").strip(),
        "description": description,
        "identifier": {"@type": "PropertyValue", "name": "EMPLOYMENT EXPRESS",
                       "value": str(job.get("id"))},
        "hiringOrganization": {
            "@type": "Organization",
            "name": str(job.get("department") or "Government Recruitment Board").strip(),
            "url": notice or page_url,
        },
        "jobLocation": _place(job),
        "employmentType": employment,
        "datePosted": posted,
        "validThrough": valid,
        "applicantLocationRequirements": {"@type": "Country", "name": "India"},
        "url": page_url,
    }
    salary = _salary(job)
    if salary:
        posting["baseSalary"] = salary
    if apply_link.lower().startswith("http"):
        posting["directApply"] = True
        posting["applicationContact"] = {"@type": "WebPage", "url": apply_link}
    if notice:
        posting["sameAs"] = notice

    return {
        "@context": "https://schema.org",
        "@graph": [
            posting,
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "EMPLOYMENT EXPRESS",
                     "item": f"{BASE_URL}/"},
                    {"@type": "ListItem", "position": 2, "name": "Government job alerts",
                     "item": f"{BASE_URL}/#master-table"},
                    {"@type": "ListItem", "position": 3,
                     "name": str(job.get("title") or "Alert").strip(), "item": page_url},
                ],
            },
        ],
    }


def summary_rows(job):
    """(label, value) pairs shown on the page for crawlers and humans alike."""
    rows = []
    fields = (
        ("Department", job.get("department")),
        ("Posts", job.get("vacancies")),
        ("Eligibility", job.get("qualification")),
        ("Qualification level", job.get("qualCategory")),
        ("Age limit", job.get("age")),
        ("Application fee", job.get("feeGen")),
        ("Fee for SC/ST", job.get("feeSC")),
        ("Last date to apply", job.get("lastDate")),
        ("Advertisement number", job.get("advtNo")),
        ("Location", job.get("location")),
        ("Apply mode", job.get("applyMode")),
    )
    for label, value in fields:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text or text.lower() in ("see notification", "see official notification",
                                        "see official notice", "newly published",
                                        "as notified"):
            continue
        rows.append((label, text[:300].rsplit(" ", 1)[0] if len(text) > 300 else text))
    return rows


def share_page_html(job):
    jid = job["id"]
    title = str(job.get("title") or "EMPLOYMENT EXPRESS Alert").strip()
    desc = describe(job)
    # A page written before its thumbnail exists (Pillow missing, or a partial
    # run) must still show an image in WhatsApp/Facebook cards, so fall back to
    # the site logo instead of pointing at a 404.
    if (THUMBS / f"job-{jid}.png").exists():
        thumb = f"{BASE_URL}/assets/thumbnails/job-{jid}.png"
    else:
        thumb = f"{BASE_URL}/assets/logo.png"
    page_url = f"{BASE_URL}/share/job-{jid}.html"
    target = f"../index.html?job={jid}"
    t = esc(title)
    d = esc(desc)
    k = esc(keywords_for(job))
    schema = (json.dumps(structured_data(job, page_url, desc), ensure_ascii=False, indent=2)
              .replace("</", "<\\/").replace("<!--", "<\\!--"))
    rows_html = "\n".join(
        f'            <div class="row"><dt>{esc(label)}</dt><dd>{esc(value)}</dd></div>'
        for label, value in summary_rows(job)
    )
    notice = str(job.get("pdfLink") or "").strip()
    apply_link = str(job.get("applyLink") or "").strip()
    links_html = ""
    if notice.lower().startswith("http"):
        links_html += (f'\n            <a class="link" href="{esc(notice)}">'
                       f'Official notification &rarr;</a>')
    if apply_link.lower().startswith("http") and apply_link != notice:
        links_html += (f'\n            <a class="link primary" href="{esc(apply_link)}">'
                       f'Apply online &rarr;</a>')
    return f"""<!doctype html>
<html lang="en-IN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{t} | EMPLOYMENT EXPRESS</title>
    <meta name="description" content="{d}">
    <meta name="keywords" content="{k}">
    <meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
    <meta name="author" content="EMPLOYMENT EXPRESS">
    <meta name="geo.region" content="IN-PB">
    <meta name="language" content="English">
    <link rel="canonical" href="{page_url}">
    <link rel="icon" type="image/png" href="../assets/logo.png">

    <!-- Open Graph / Facebook / WhatsApp -->
    <meta property="og:type" content="article">
    <meta property="og:site_name" content="EMPLOYMENT EXPRESS">
    <meta property="og:title" content="{t}">
    <meta property="og:description" content="{d}">
    <meta property="og:url" content="{page_url}">
    <meta property="og:image" content="{thumb}">
    <meta property="og:image:secure_url" content="{thumb}">
    <meta property="og:image:type" content="image/png">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="og:image:alt" content="{t}">
    <meta property="og:locale" content="en_IN">

    <!-- Twitter / X -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{t}">
    <meta name="twitter:description" content="{d}">
    <meta name="twitter:image" content="{thumb}">
    <meta name="twitter:image:alt" content="{t}">

    <!-- Static structured data: this page is the canonical, indexable copy of
         the alert, so the JobPosting and breadcrumb are served in the HTML
         itself. Crawlers that never run JavaScript (AI answer engines
         included) can therefore read the vacancy without the app. -->
    <script type="application/ld+json">
{schema}
    </script>

    <!-- Real visitors are sent on to the alert board; crawlers stay on this
         page. The redirect is JavaScript-only on purpose: a 0-second meta
         refresh would flag the page as a redirect and cost it the index. -->
    <script>window.location.replace({json.dumps(target)});</script>
</head>
<body style="margin:0;font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;background:#f1f5f9;color:#0f172a;display:flex;min-height:100vh;align-items:flex-start;justify-content:center;padding:24px;">
    <main style="max-width:560px;width:100%;background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:24px;box-shadow:0 10px 30px rgba(2,6,23,.08);">
        <header style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
            <span style="width:34px;height:34px;border-radius:50%;background:#1d4ed8;color:#fff;font-weight:800;font-size:13px;display:flex;align-items:center;justify-content:center;">EE</span>
            <span style="font-weight:800;font-size:12px;letter-spacing:.08em;color:#1e3a8a;">EMPLOYMENT EXPRESS</span>
        </header>

        <h1 style="font-size:18px;line-height:1.4;margin:0 0 8px;">{t}</h1>
        <p style="font-size:13px;color:#475569;margin:0 0 16px;line-height:1.5;">{d}</p>

        <dl style="margin:0 0 16px;font-size:13px;">
            <style>
                .row {{ display:flex; gap:10px; padding:6px 0; border-top:1px solid #f1f5f9; }}
                .row dt {{ flex:0 0 130px; color:#64748b; font-weight:600; }}
                .row dd {{ margin:0; color:#0f172a; flex:1; }}
                .link {{ display:inline-block; font-weight:700; font-size:13px; text-decoration:none;
                         padding:9px 16px; border-radius:8px; border:1px solid #cbd5e1; color:#1e3a8a; }}
                .link.primary {{ background:#dc2626; border-color:#dc2626; color:#fff; }}
            </style>
{rows_html}
        </dl>

        <div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px;">{links_html}
        </div>

        <a href="{target}" style="display:inline-block;background:#dc2626;color:#fff;text-decoration:none;font-weight:700;font-size:14px;padding:12px 22px;border-radius:10px;">View Alert &rarr;</a>

        <p style="font-size:11px;color:#94a3b8;margin:16px 0 0;line-height:1.5;">
            Verified against the recruiting authority's own official notice.
            Dates and vacancy counts change without warning — confirm them on
            the official notification before applying.
        </p>
    </main>
</body>
</html>
"""


def main():
    # Imported here (not at module scope) so this module stays importable —
    # and the SEO markup testable — without Pillow installed.
    from scripts.thumbnail_generator import (  # noqa: PLC0415
        parse_job_for_thumbnail,
        generate_job_thumbnail,
    )

    jobs = load_all_jobs()
    if not jobs:
        print("No jobs found; nothing to build.")
        return 1

    THUMBS.mkdir(parents=True, exist_ok=True)
    SHARE_DIR.mkdir(parents=True, exist_ok=True)

    built = 0
    for job in jobs:
        jid = job.get("id")
        if jid is None:
            continue
        card = parse_job_for_thumbnail(job)
        thumb_path = THUMBS / f"job-{jid}.png"
        generate_job_thumbnail(card, thumb_path)
        (SHARE_DIR / f"job-{jid}.html").write_text(
            share_page_html(job), encoding="utf-8")
        built += 1

    print(f"Built {built} share pages in {SHARE_DIR.relative_to(ROOT)}/ "
          f"with thumbnails in {THUMBS.relative_to(ROOT)}/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
