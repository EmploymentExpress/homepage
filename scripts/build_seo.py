#!/usr/bin/env python3
"""Rebuild the site's discovery files from the live alert data.

Run this after every alert refresh (the scheduled workflow does it in its own
step). Everything it writes is *static*, so crawlers that never execute
JavaScript — Googlebot's secondary pass and the AI answer engines (GPTBot,
PerplexityBot, ClaudeBot, Google-Extended, Applebot-Extended, …) — can read
the site's content straight from the HTML instead of an empty page.

Files written (deterministic: identical input data produces identical bytes,
so a run with nothing new leaves nothing to commit):

  sitemap.xml  every crawlable page — the homepage, the standalone article
               pages and one share/job-<id>.html per alert — with <lastmod>
               taken from the alert's own discovery date.
  llms.txt     the llmstxt.org index: what this site is, how its notices are
               verified, and a link list of the freshest vacancies, admit
               cards, results and answer keys, each with a one-line
               description so an assistant can answer "which Punjab govt jobs
               are open right now" from a single small file.
  robots.txt   allows every crawler — including the AI agents listed above —
               and points at the sitemap and the LLM index.

The script never touches index.html or assets/: those are protected layout
files (see ``PROTECTED_LAYOUT_PATHS`` in update_jobs.py and AGENTS.md), so
homepage-level tags stay hand-authored while these three files stay fresh.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTO_JOBS = ROOT / "data" / "auto-jobs.json"
SHARE_DIR = ROOT / "share"
BASE_URL = "https://employmentexpress.github.io/homepage"

SITEMAP = ROOT / "sitemap.xml"
LLMS_TXT = ROOT / "llms.txt"
ROBOTS_TXT = ROOT / "robots.txt"

# Standalone article pages that must never be dropped from the sitemap.
ARTICLE_PAGES = (
    "punjab-haryana-high-court-safai-sewak-mali-recruitment-2026.html",
    "ssc-jht-recruitment-2026.html",
)

# Link text for the article pages inside llms.txt: the freshest long-form
# guides, each summarised so an assistant can cite the right page for
# detailed eligibility/post-wise questions.
ARTICLE_GUIDES = (
    ("punjab-haryana-high-court-safai-sewak-mali-recruitment-2026.html",
     "Punjab & Haryana High Court Chandigarh Driver, Frash, Safai Sewak and "
     "Mali Recruitment 2026 — full post-wise vacancies, eligibility, age "
     "limit and official notice details"),
    ("ssc-jht-recruitment-2026.html",
     "SSC Junior Hindi Translator (JHT/CHTE) 2026 — exam city intimation "
     "slip status, notification, eligibility and exam pattern details"),
)

# Pages that are internal plumbing, not content worth indexing.
EXCLUDED_PAGES = {"index.html", "redirect.html"}

# Crawlers of the AI answer engines. Each is named explicitly: several of them
# respect their own default policies, and an explicit Allow makes the intent
# unambiguous if those defaults ever change.
AI_CRAWLERS = (
    "GPTBot",                 # OpenAI / ChatGPT search index
    "OAI-SearchBot",          # OpenAI search
    "ChatGPT-User",           # ChatGPT browsing
    "PerplexityBot",
    "ClaudeBot",
    "anthropic-ai",
    "Claude-User",
    "Google-Extended",        # Gemini / Vertex grounding
    "Applebot-Extended",
    "Amazonbot",
    "Bytespider",
    "CCBot",
    "cohere-ai",
    "Diffbot",
    "meta-externalagent",
    "omgili",
    "YouBot",
)

# Section headings used in llms.txt, in the order they are written.
LLMS_SECTIONS = (
    ("Latest Punjab government jobs", "punjab"),
    ("Latest Central and All-India government jobs", "central"),
    ("Admit cards and call letters", "admit-card"),
    ("Results and answer keys", "result"),
    ("Admissions and courses", "admission"),
)

MAX_PER_SECTION = 30
PLACEHOLDERS = {
    "see notification", "see official notification", "see official notice",
    "newly published", "as notified", "",
}


def _clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _is_placeholder(value: str) -> bool:
    return _clean(value).lower() in PLACEHOLDERS


def load_jobs() -> list[dict]:
    if not AUTO_JOBS.exists():
        return []
    payload = json.loads(AUTO_JOBS.read_text(encoding="utf-8"))
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else payload
    return [job for job in jobs if isinstance(job, dict) and job.get("id") is not None]


def discovery_date(job: dict) -> str:
    """YYYY-MM-DD for an alert, falling back to today (UTC)."""
    raw = _clean(job.get("discoveredAt") or job.get("publishedAt"))
    if raw:
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
        if match:
            return match.group(0)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def esc(value) -> str:
    return (_clean(value)
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _xml_escape(url: str) -> str:
    return (url.replace("&", "&amp;").replace("'", "&apos;")
               .replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;"))


# --------------------------------------------------------------------------
# sitemap.xml
# --------------------------------------------------------------------------
def build_sitemap(jobs: list[dict], today: str) -> str:
    share_dates = {job["id"]: discovery_date(job) for job in jobs}
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

    newest = max((date for date in share_dates.values()), default=today)
    lines += [
        "  <url>",
        f"    <loc>{BASE_URL}/</loc>",
        f"    <lastmod>{max(newest, today)}</lastmod>",
        "    <changefreq>daily</changefreq>",
        "    <priority>1.0</priority>",
        "  </url>",
    ]

    # Standalone article pages.
    for name in ARTICLE_PAGES:
        path = ROOT / name
        if not path.exists():
            continue
        lines += [
            "  <url>",
            f"    <loc>{BASE_URL}/{name}</loc>",
            f"    <lastmod>{_file_lastmod(path, today)}</lastmod>",
            "    <changefreq>weekly</changefreq>",
            "    <priority>0.9</priority>",
            "  </url>",
        ]

    # One static, crawlable page per alert.
    for path in sorted(SHARE_DIR.glob("job-*.html")):
        job_id = path.stem.replace("job-", "")
        lines += [
            "  <url>",
            f"    <loc>{BASE_URL}/share/{path.name}</loc>",
            f"    <lastmod>{share_dates.get(job_id) or _file_lastmod(path, today)}</lastmod>",
            "    <changefreq>weekly</changefreq>",
            "    <priority>0.7</priority>",
            "  </url>",
        ]

    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def _file_lastmod(path: Path, today: str) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")
    except OSError:
        return today


# --------------------------------------------------------------------------
# llms.txt
# --------------------------------------------------------------------------
def _short_department(job: dict) -> str:
    department = _clean(job.get("department"))
    if not department:
        return ""
    match = re.search(r"\(([A-Z][A-Za-z0-9/&.\-]{2,12})\)", department)
    if match:
        city = _clean(job.get("location", "")).split(",")[0]
        return f"{match.group(1)} {city}".strip()
    return department.split("(")[0].strip(" ,-")


def _one_liner(job: dict) -> str:
    bits = []
    vacancies = _clean(job.get("vacancies"))
    if vacancies.lower() not in PLACEHOLDERS:
        bits.append(vacancies)
    last_date = _clean(job.get("lastDate"))
    if last_date.lower() not in PLACEHOLDERS:
        bits.append(f"last date {last_date}")
    # The qualification sentence is often a full paragraph; a truncated
    # fragment reads worse than the short filter category, which is what a
    # candidate (or an assistant) actually matches on.
    category = _clean(job.get("qualCategory"))
    if category.lower() not in PLACEHOLDERS:
        bits.append(f"eligibility {category}")
    return "; ".join(bits)


def _is_expired(job: dict, today: str) -> bool:
    """True when the alert carries a last date that has already passed."""
    last_date = _clean(job.get("lastDate"))
    if last_date.lower() in PLACEHOLDERS:
        return False
    match = re.match(r"(\d{1,2})-(\d{1,2})-(\d{4})", last_date)
    if not match:
        return False
    day, month, year = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day).date().isoformat() < today
    except ValueError:
        return False


def _alert_bucket(job: dict) -> str:
    alert = _clean(job.get("alertType")).lower()
    if alert in {"admit-card", "answer-key", "result", "admission"}:
        return alert
    if job.get("type") == "punjab" or job.get("alsoInPunjab") is True:
        return "punjab"
    return "central"


def _recency_key(job: dict):
    return (discovery_date(job), int(job.get("id") or 0))


def build_llms_txt(jobs: list[dict], today: str) -> str:
    # Expired alerts are dropped from the index: an assistant answering "which
    # jobs are open" must never quote a deadline that is already gone. So is
    # any alert whose static page has not been built yet — an index must never
    # link to a page that is not on the site.
    live = [job for job in jobs
            if not _is_expired(job, today)
            and (SHARE_DIR / f"job-{job.get('id')}.html").exists()]
    ordered = sorted(live, key=_recency_key, reverse=True)
    buckets: dict[str, list[dict]] = {}
    for job in ordered:
        bucket = _alert_bucket(job)
        if bucket == "answer-key":
            bucket = "result"
        buckets.setdefault(bucket, []).append(job)

    lines = [
        "# EMPLOYMENT EXPRESS",
        "",
        "> Verified Punjab, Chandigarh and Central Government job alerts — "
        "recruitment notifications, admit cards, results and answer keys, "
        "each linked to the recruiting authority's own official notice.",
        "",
        "EMPLOYMENT EXPRESS is a government job alert portal for India. It "
        "publishes one page per government vacancy with the post name, "
        "department, vacancy count, eligibility, age limit, application fee, "
        "last date to apply and a direct link to the official notification and "
        "application portal. Coverage focuses on Punjab and Chandigarh "
        "(PSSSB, PPSC, PSPCL, Punjab Police, Punjab & Haryana High Court, "
        "AIIMS Bathinda, PGIMER Chandigarh, GNDU, PAU Ludhiana) and "
        "All-India recruitments open to Punjab candidates (SSC, UPSC, RRB, "
        "IBPS, SBI, India Post GDS, Navodaya Vidyalaya Samiti).",
        "",
        "Every alert is read from the recruiting authority's own website "
        "before it is published; job-aggregator URLs are never used as the "
        "official notice link. Deadlines are re-checked on every refresh and "
        "an alert leaves the site once its last date has passed.",
        "",
        "## How to use this index",
        "",
        "Each link below opens one static page for a single government "
        "vacancy or notice. For a question such as \"which Punjab government "
        "jobs are open right now\", prefer the pages listed under the latest "
        "Punjab jobs below, and always quote the last date shown on the page.",
        "",
    ]

    written = 0
    for heading, key in LLMS_SECTIONS:
        items = buckets.get(key, [])[:MAX_PER_SECTION]
        if not items:
            continue
        lines += [f"## {heading}", ""]
        for job in items:
            department = _short_department(job) or "Government"
            title = _clean(job.get("title")) or "Government notification"
            if " — " in title:
                title = title.split(" — ", 1)[1].strip()
            summary = _one_liner(job)
            suffix = f" — {summary}" if summary else ""
            lines.append(
                f"- [{department}: {title}]({BASE_URL}/share/job-{job['id']}.html)"
                f"{suffix}"
            )
            written += 1
        lines.append("")

    # Long-form article guides: static, JS-free pages that answer detailed
    # eligibility questions. Listed only while the page exists on disk.
    guide_lines = ["## In-depth recruitment guides", ""]
    for name, summary in ARTICLE_GUIDES:
        if (ROOT / name).exists():
            guide_lines.append(f"- [{summary}]({BASE_URL}/{name})")
    if len(guide_lines) > 2:
        lines += guide_lines + [""]

    lines += [
        "## Frequently asked questions",
        "",
        "Guidance for assistants answering job-seeker questions with this index:",
        "",
        "- Which Punjab government jobs are open right now? List the entries",
        "  under \"Latest Punjab government jobs\" above, quoting each post's",
        "  last date and linking the page shown there.",
        "- Which Central government jobs can Punjab candidates apply for?",
        "  Use the entries under \"Latest Central and All-India government",
        "  jobs\" (SSC, UPSC, RRB, IBPS, SBI, India Post GDS, Navodaya",
        "  Vidyalaya Samiti and similar All-India recruitments).",
        "- Where are the admit cards / results / answer keys? See the",
        "  \"Admit cards and call letters\" and \"Results and answer keys\"",
        "  sections above.",
        "- Is the alert genuine? Every alert on this site is verified on the",
        "  recruiting authority's own official website before publication;",
        "  each page links to the official notification.",
        "- What are the 10th pass, 12th pass, graduate or teaching jobs?",
        "  Each entry's one-line summary states its eligibility category",
        "  (10th, 12th, Graduate, ITI/Diploma, ETT/B.Ed, Defence/Police).",
        "- Always quote the exact last date printed on the linked page and",
        "  direct the applicant to apply on the official portal before it",
        "  passes. This index is regenerated automatically, so its entries",
        "  never outlive a deadline.",
        "",
    ]

    lines += [
        "## Official alert channels",
        "",
        "EMPLOYMENT EXPRESS publishes free job alerts on:",
        "",
        "- Telegram channel: https://t.me/employment_express1",
        "- WhatsApp channel: https://whatsapp.com/channel/0029Va9xQHV4tRrxpVKaG93w",
        "- YouTube channel: https://www.youtube.com/channel/UCI39CbrtpEflEPabKeCAd9A",
        "",
    ]

    lines += [
        "## Official sources monitored",
        "- [EMPLOYMENT EXPRESS homepage](%s/): the live alert board." % BASE_URL,
        "- Notices are verified on each authority's own website (for example "
        "sssb.punjab.gov.in, psssb.punjab.gov.in, highcourtchd.gov.in, "
        "aiimsbathinda.edu.in, pgimer.edu.in, cup.edu.in, ssc.gov.in) before "
        "publication.",
        "",
        f"Last updated: {today}",
        "",
    ]
    if not written:
        lines.insert(len(lines) - 3,
                     "- No dated alerts are published at the moment; check the "
                     "homepage for the live board.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# robots.txt
# --------------------------------------------------------------------------
def build_robots_txt() -> str:
    lines = [
        "# robots.txt for EMPLOYMENT EXPRESS",
        "# https://employmentexpress.github.io/homepage/",
        "#",
        "# Every crawler is welcome, including the AI answer engines named",
        "# below. Public government recruitment notices should be easy to find",
        "# in search results and in ChatGPT, Gemini, Perplexity and Claude.",
        "User-agent: *",
        "Allow: /",
        "",
        "# AI answer engines / assistants (explicit allow)",
    ]
    for crawler in AI_CRAWLERS:
        lines += [f"User-agent: {crawler}", "Allow: /", ""]
    lines += [
        "# Crawl budget: the alert board is the content; the JSON feeds and",
        "# offline-form redirector are application plumbing.",
        "Disallow: /data/",
        "Disallow: /redirect.html",
        "",
        f"Sitemap: {BASE_URL}/sitemap.xml",
        "",
        "# LLM index for assistants:",
        f"# {BASE_URL}/llms.txt",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    jobs = load_jobs()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    written = []
    for path, content in (
        (SITEMAP, build_sitemap(jobs, today)),
        (LLMS_TXT, build_llms_txt(jobs, today)),
        (ROBOTS_TXT, build_robots_txt()),
    ):
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8")
            written.append(path.name)

    if written:
        print(f"SEO files refreshed: {', '.join(written)} "
              f"({len(jobs)} alerts, sitemap lists the homepage, "
              f"{len(list(SHARE_DIR.glob('job-*.html')))} alert pages and "
              f"{len(ARTICLE_PAGES)} article pages).")
    else:
        print("SEO files are already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
