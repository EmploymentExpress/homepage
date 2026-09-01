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
import subprocess
import sys
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
from scripts.thumbnail_generator import (  # noqa: E402
    parse_job_for_thumbnail,
    generate_job_thumbnail,
)


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


def share_page_html(job):
    jid = job["id"]
    title = str(job.get("title") or "EMPLOYMENT EXPRESS Alert").strip()
    desc = describe(job)
    thumb = f"{BASE_URL}/assets/thumbnails/job-{jid}.png"
    page_url = f"{BASE_URL}/share/job-{jid}.html"
    target = f"../index.html?job={jid}"
    t = esc(title)
    d = esc(desc)
    return f"""<!doctype html>
<html lang="en-IN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{t} | EMPLOYMENT EXPRESS</title>
    <meta name="description" content="{d}">
    <meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
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

    <!-- Real visitor -> open the alert in the app. Scrapers stay on this page. -->
    <meta http-equiv="refresh" content="0; url={target}">
    <script>window.location.replace({json.dumps(target)});</script>
</head>
<body style="margin:0;font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif;background:#f1f5f9;color:#0f172a;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:24px;">
    <div style="max-width:420px;width:100%;background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:28px;text-align:center;box-shadow:0 10px 30px rgba(2,6,23,.08);">
        <div style="width:56px;height:56px;margin:0 auto 14px;border-radius:50%;background:#1d4ed8;color:#fff;font-weight:800;font-size:20px;display:flex;align-items:center;justify-content:center;">EE</div>
        <h1 style="font-size:16px;line-height:1.4;margin:0 0 8px;">{t}</h1>
        <p style="font-size:13px;color:#64748b;margin:0 0 18px;">Opening the alert on EMPLOYMENT EXPRESS&hellip;</p>
        <a href="{target}" style="display:inline-block;background:#dc2626;color:#fff;text-decoration:none;font-weight:700;font-size:14px;padding:12px 22px;border-radius:10px;">View Alert &rarr;</a>
    </div>
</body>
</html>
"""


def main():
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
