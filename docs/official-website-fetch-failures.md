# Handling official websites whose job details cannot be fetched directly

**Problem.** Some official Indian recruiting-board pages (PGIMER Chandigarh is
the example in this question — `https://pgimer.edu.in/PGIMER_PORTAL/PGIMERPORTAL/Vacancies/JSP/VACANCIE_VIEW.jsp?countt=0`)
refuse, return nothing parseable, or only render notices through JavaScript
when the GitHub Actions runner fetches them. Common causes:

- The site is on a shared JSP / Struts framework that 403s datacenter IPs
  mid-TLS-handshake (typical for several `*.punjab.gov.in` hosts).
- The notice list is rendered by JavaScript and the static HTML has no
  notice links.
- The site blocks GitHub Actions entirely (a `WAF / 403 / 5xx` challenge).
- The page itself is reachable but the linked notice PDFs go via a CDN that
  drops connections to the same runner.

**The repository already has a three-layer solution** (no Python code change
needed in most cases). The page-source rule is part of the shared per-source
pipeline, so it applies automatically to **every** official website link —
existing or added later — with **no extra configuration**.

The fix is **almost always configuration, not code**. Below is the full
reference: every layer, the exact code paths in `scripts/update_jobs.py` that
back them, and the diff you apply to add PGIMER Chandigarh (and any other
unreachable board) to the monitor.

---

## Layer 1 — Read-only text mirror fallback (`proxyFallback: true`)

When a source's official site refuses the runner's direct connection
(`URLError`, `HTTPError 403/408/425/429`, 5xx), the monitor retries the fetch
through a public read-only text mirror and keeps every published link on the
**official URL** (mirrors are transport only — never a source of truth, and
their hosts are never published on the homepage).

The flag is honoured on **every** fetch path:

| Fetch path | File / function |
| --- | --- |
| Configured source listing (`automation/sources.json`) | `run()` → `fetch_url(proxy_fallback=…)` |
| Per-notice detail / PDF enrichment | `enrich_candidate()` → `fetch_url(proxy_fallback=…)` |
| Discovery feed (`automation/discovery-feeds.json`) | `process_discovery_feeds()` → `fetch_url(proxy_fallback=…)` |
| Official-website verification of discovery headlines (`automation/official-organizations.json`) | same as above |
| Offline-form portal listing + per-vacancy page | `gather_offline_forms_pool()` / `offline_page_documents()` |
| Discovery-article official-website auto-registration | `register_official_website_from_article()` |
| Registry link fetch (`data/notification-source-links.json`) | `additional_link_sources()` → `run()` |

Hard rule: a 404/410 is **never** mirrored (a mirror would serve the same
emptiness); only connection-level refusals are. This is enforced by
`_should_try_mirror()` and tested in `tests/test_update_jobs.py`
(`test_fetch_url_mirror_fallback_preserves_official_url`,
`test_fetch_url_does_not_mirror_hard_404s`).

### 1.a Add the flag to PGIMER Chandigarh (and similar boards)

Edit `automation/sources.json`. PGIMER already exists at line 407 — flip it
on and add the mirror flag, the same way DESGPC, PSSSB-home, PMIDC,
Punjab-Health, CHDSW, PILBS, Punjab-Sports, BFUHS, PRSC, and IBPS do:

```jsonc
{
  "id": "pgimer",
  "enabled": true,                       // was: false
  "proxyFallback": true,                 // <-- add this line
  "name": "PGIMER Chandigarh",
  "department": "Post Graduate Institute of Medical Education and Research (PGIMER), Chandigarh",
  "url": "https://pgimer.edu.in/PGIMER_PORTAL/PGIMERPORTAL/Vacancies/JSP/VACANCIE_VIEW.jsp?countt=0",
  "type": "central",
  "categorySlug": "central",
  "location": "Chandigarh",
  "noticeTypes": [
    "recruitment", "admission", "result", "answer-key", "corrigendum", "admit-card"
  ],
  "includeKeywords": [
    "senior resident", "junior resident", "faculty", "assistant professor",
    "walk-in interview", "walk in interview", "project", "recruitment"
  ],
  "bootstrapCount": 1,
  "maxNewPerRun": 8,
  "maxRefreshPerRun": 12,
  "maxCatchUpPerRun": 12,
  "timeout": 45,                         // JSP pages are slow
  "detailTimeout": 45
}
```

Also register PGIMER in `automation/official-organizations.json` so
discovery-article headlines (LinkingSky, Punjab Job Alert, HaryanaJobs) that
name it are verified against its own listing first, then against its raw
page source:

```jsonc
{
  "id": "pgimer",
  "name": "PGIMER Chandigarh",
  "department": "Post Graduate Institute of Medical Education and Research (PGIMER), Chandigarh",
  "url": "https://pgimer.edu.in/PGIMER_PORTAL/PGIMERPORTAL/Vacancies/JSP/VACANCIE_VIEW.jsp?countt=0",
  "proxyFallback": true,                 // mirrors are also used for the headline verification
  "aliases": [
    "pgimer", "post graduate institute of medical education and research",
    "pgimer chandigarh", "pgimer chd"
  ]
}
```

That is the entire configuration change for the page-source + mirror pipeline
to start working on PGIMER.

---

## Layer 2 — Page-source rule (mandatory, runs on every workflow run)

Even when the visible listing parser returns nothing, the monitor re-reads
the **raw page source** of every official site on every run. It re-scans
`<noscript>` fallback blocks, `<iframe>`/`<embed>` PDF embeds, `<area>` image
maps, `data-href` / `data-url` / `data-src` hooks, JavaScript config blocks
and bare `http(s)://…` URLs in scripts/JSON. Only links that classify as a
supported notice (recruitment / admission / result / answer-key / admit-card /
corrigendum) for the source are published, and they keep the official URL.

The rule lives in `scripts/update_jobs.py`:

```python
# scripts/update_jobs.py

# Attribute names that may carry a notice URL even when the visible listing
# parser misses them: <noscript> fallback blocks, <iframe>/<embed>/<object>
# embeds, image maps (<area>), JavaScript-generated links and data-* hooks.
PAGE_SOURCE_URL_ATTRS = (
    "href", "src", "data-href", "data-url", "data-link", "data-src",
)
# Document extensions that can carry an official notice/notification.
PAGE_SOURCE_DOC_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf", ".odt",
)
# Static assets that can never be a notice (skipped in the raw scan).
PAGE_SOURCE_ASSET_EXTENSIONS = (
    ".css", ".js", ".mjs", ".json", ".xml", ".map", ".png", ".jpg", ".jpeg",
    ".gif", ".svg", ".webp", ".ico", ".avif", ".woff", ".woff2", ".ttf",
    ".eot", ".mp4", ".mp3", ".zip", ".rar", ".7z", ".tar", ".gz",
)

def page_source_fallback_candidates(
    download: Download,
    discovered: list[Candidate],
    known: set[str],
    source: dict[str, Any],
) -> list[Candidate]:
    """Page-source rule: candidates the raw page source adds beyond the listing."""
    if parse_feed(decode_document(download), download.url):
        return []                                    # feeds are already fully parsed
    listed_urls = {canonical_url(candidate.url) for candidate in discovered}
    extras: list[Candidate] = []
    for candidate in page_source_candidates(download, source):
        if fingerprint(candidate) in known:
            continue
        if canonical_url(candidate.url) in listed_urls:
            continue
        extras.append(candidate)
    return deduplicate_candidates(extras)
```

It is called from the shared per-source loop in `run()`:

```python
# scripts/update_jobs.py — inside the per-source loop in run()

if not unseen:
    # Page-source rule (mandatory, runs on every workflow run for every
    # official website link — existing or newly added, no extra config):
    # after checking the official website, if no new job notification
    # was found in the listing, check the page source of the official
    # website and publish only links found there.
    page_source_extras = page_source_fallback_candidates(
        download, discovered, known, source
    )
    if page_source_extras:
        print(
            f"  Listing showed no new notification; raw page source of the "
            f"official website exposes {len(page_source_extras)} additional "
            f"notice link(s)"
        )
        discovered = deduplicate_candidates([*discovered, *page_source_extras])
        unseen = [
            candidate
            for candidate in discovered
            if fingerprint(candidate) not in known
        ]
```

**This rule applies automatically to every official website link** —
existing or added later, with **no extra configuration**:

- every source in `automation/sources.json` (set `"enabled": true` and the
  monitor handles the rest),
- every approved organisation in `automation/official-organizations.json`
  (when a discovery headline names it, the monitor verifies against the
  official listing first and falls back to the official page source),
- every user-added link in `data/notification-source-links.json`
  (`additional_link_sources()` turns it into a normal source on the next run).

Guard tests in `tests/test_update_jobs.py` keep this rule enforced:

- `test_every_enabled_official_source_is_covered_by_the_page_source_rule`
- `test_run_checks_page_source_when_listing_shows_no_new_notification`
- `test_page_source_rule_is_documented_in_workflow_and_agent_rules`

When you add a new official website link, you do **not** need to write any
new scanning code or flags — the page-source check is part of the shared
pipeline every source goes through.

---

## Layer 3 — Reachability tracking (`sourceHealth`)

When a source fetch fails, the run records `consecutiveFailures`,
`lastFailureAt` and `lastError` under `sourceHealth` in
`data/seen-notices.json` (one of the four data files the workflow commits),
and prints a loud warning from the second consecutive failure onward. A
healthy run records `lastSuccessAt` once. This is how "the workflow stopped
updating source X" becomes visible in git instead of hiding in job logs.

```python
# scripts/update_jobs.py

def record_source_success(state: dict[str, Any], source_id: str, now: datetime) -> bool:
    health = state.setdefault("sourceHealth", {})
    entry = health.get(source_id)
    if entry is None:
        health[source_id] = {
            "lastSuccessAt": now.isoformat().replace("+00:00", "Z"),
            "consecutiveFailures": 0,
        }
        return True
    failures = int(entry.get("consecutiveFailures") or 0)
    if failures or entry.get("lastSuccessAt") is None:
        entry["lastSuccessAt"] = now.isoformat().replace("+00:00", "Z")
        entry["consecutiveFailures"] = 0
        entry.pop("lastFailureAt", None)
        entry.pop("lastError", None)
        return True
    return False


def record_source_failure(state: dict[str, Any], source_id: str, now: datetime, error: str) -> bool:
    health = state.setdefault("sourceHealth", {})
    entry = health.setdefault(source_id, {"consecutiveFailures": 0})
    entry["consecutiveFailures"] = int(entry.get("consecutiveFailures") or 0) + 1
    entry["lastFailureAt"] = now.isoformat().replace("+00:00", "Z")
    entry["lastError"] = clean_text(error)[:300]
    return True
```

Called from the per-source loop in `run()`:

```python
try:
    download = fetch_url(source_url, ..., proxy_fallback=proxy_fallback)
    discovered = ...
except Exception as exc:
    if record_source_failure(state, source_id, now, str(exc)):
        state_changed = True
    failures_in_a_row = int(
        (state.get("sourceHealth", {}).get(source_id, {}) or {}).get("consecutiveFailures") or 0
    )
    print(
        f"  Source unavailable; keeping existing data "
        f"({failures_in_a_row} consecutive failed run(s)): {exc}",
        file=sys.stderr,
    )
    if failures_in_a_row >= 2:
        print(
            f"  WARNING: {source.get('name', source_id)} has been unreachable for "
            f"{failures_in_a_row} consecutive runs — its alerts are not being updated. "
            f"Recorded in data/seen-notices.json (sourceHealth)."
        )
    continue

successful_sources += 1
if record_source_success(state, source_id, now):
    state_changed = True
```

After a `proxyFallback: true` source is unreachable, the resulting state file
looks like:

```json
{
  "sourceHealth": {
    "pgimer": {
      "consecutiveFailures": 3,
      "lastFailureAt": "2026-08-29T05:00:00Z",
      "lastError": "TLS handshake killed (mid-handshake)"
    }
  }
}
```

`lastError` is truncated to 300 characters. Hard 404/410 are **not** recorded
as failures (the notice is genuinely gone — a mirror would serve the same
emptiness, and we should not invent links). Sites that block non-Indian
visitors entirely (several `*.punjab.gov.in` hosts) defeat mirrors too;
their `sourceHealth` entries make the gap visible and an India-egress runner
would be the real fix.

---

## Layer 4 (zero-code) — User-added link registry

For an ad-hoc source you want monitored on every future run without editing
any source file, append the URL to
`data/notification-source-links.json`. The monitor automatically converts
every valid link in this registry into a source on every run, de-duplicates
links already present in `automation/sources.json`, and remembers
discovered notices for future scans. The page-source rule + the
`proxyFallback` flag both apply to user-added links too.

Plain URL:

```json
{
  "version": 1,
  "links": [
    "https://pgimer.edu.in/PGIMER_PORTAL/PGIMERPORTAL/Vacancies/JSP/VACANCIE_VIEW.jsp?countt=0"
  ]
}
```

…or with metadata when the page needs filtering or a non-default category:

```json
{
  "url": "https://pgimer.edu.in/PGIMER_PORTAL/PGIMERPORTAL/Vacancies/JSP/VACANCIE_VIEW.jsp?countt=0",
  "name": "PGIMER Chandigarh",
  "department": "Post Graduate Institute of Medical Education and Research (PGIMER), Chandigarh",
  "type": "central",
  "categorySlug": "central",
  "location": "Chandigarh",
  "noticeTypes": ["recruitment", "admission", "result", "answer-key", "corrigendum", "admit-card"],
  "includeKeywords": [
    "senior resident", "junior resident", "faculty", "walk-in interview"
  ],
  "proxyFallback": true,
  "timeout": 45,
  "detailTimeout": 45
}
```

The registry loader is `additional_link_sources()` in
`scripts/update_jobs.py`. It:

1. resolves a bare domain (e.g. `ibps.in`) to its real authority name
   (`Institute of Banking Personnel Selection (IBPS)`) so a website
   address never leaks into the published `department`,
2. carries `proxyFallback`, `timeout`, `detailTimeout` through to the
   generated source,
3. generates a stable id (`custom-<sha256[:12]>`) and adds the source to
   the same per-source pipeline that runs `fetch_url → source_candidates →
   page_source_fallback_candidates → job_from_candidate`.

---

## Layer 5 (zero-code) — Auto-registration of "Official Website" links

Every discovery article (LinkingSky / Punjab Job Alert / HaryanaJobs) and
every offline-form portal vacancy page (onlineforms.in / speedjob.in)
publishes an **"Official Website"** row next to its notification/apply rows.
On every run the monitor reads that row and, when it holds a genuine
official website, **registers it automatically** as an official website link
for the automation workflow:

1. `official_website_links()` reads the label from the row/section context
   (the anchor text itself is generic — "Visit Now", "Click Here"), for
   both table-row and inline layouts.
2. `looks_like_official_website()` accepts the URL only when it is a real
   official domain (`.gov.in`, `.nic.in`, `.gov`, `.mil.in`, `.ac.in`,
   `.edu.in`, `.edu`, `.res.in`, `.org.in`, `.co.in`, `.in`, `.org`) and
   rejects PDFs, discovery/offline-portal hosts, job blogs and
   aggregators (`NON_OFFICIAL_WEBSITE_HOSTS`), social/Telegram/WhatsApp
   links and shorteners.
3. `register_official_website_link()` appends it to
   `data/notification-source-links.json` with
   `addedBy: "discovery-official-website"` and an `addedAt` timestamp.
   Registration is idempotent and is skipped on `--dry-run`.
4. `additional_link_sources()` turns that stored link into a normal monitor
   source on the next run, so the official listing — and, when it shows
   nothing new, its **raw page source** — is checked automatically.

This is the relevant code:

```python
# scripts/update_jobs.py

OFFICIAL_WEBSITE_DOMAIN_SUFFIXES = (
    ".gov.in", ".nic.in", ".gov", ".mil.in", ".ac.in", ".edu.in", ".res.in",
    ".org.in", ".net.in", ".co.in", ".edu", ".org", ".in",
)
# Job blogs / aggregators, social platforms and shorteners: an "Official
# Website" row pointing at one of these is never an official website.
NON_OFFICIAL_WEBSITE_HOSTS = {
    "freejobalert.com", "sarkariresult.com", "sarkariresult.info",
    "mysarkarinaukri.com", "dailyjobalert.in", "punjabjobalert.com",
    "haryanajobs.in", "linkingsky.com", "rozgarnews.com", "testbook.com",
    "adda247.com", "pw.live", "jagranjosh.com", "careerpower.in",
    "oliveboard.in", "gradeup.co", "byjus.com", "indgovtjobs.in",
    "sarkarijobfind.com", "rojgarresult.com", "sarkarialert.com",
    "facebook.com", "twitter.com", "x.com", "instagram.com", "youtube.com",
    "t.me", "telegram.me", "whatsapp.com", "chat.whatsapp.com", "linkedin.com",
    "bit.ly", "tinyurl.com", "goo.gl",
}


def looks_like_official_website(url: str) -> bool:
    normalized = canonical_url(url)
    if not normalized or is_pdf_url(normalized):
        return False
    if is_discovery_host(normalized) or is_offline_form_url(normalized):
        return False
    host = host_name(normalized)
    if not host or host in NON_OFFICIAL_WEBSITE_HOSTS:
        return False
    if any(host == blocked or host.endswith(f".{blocked}") for blocked in NON_OFFICIAL_WEBSITE_HOSTS):
        return False
    return host.endswith(OFFICIAL_WEBSITE_DOMAIN_SUFFIXES)


def register_official_website_link(
    url: str,
    name: str = "",
    department: str = "",
    *,
    path: Path | None = None,
    config_urls: set[str] | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
) -> bool:
    """Add an official website found on a discovery article as a monitor source."""
    path = path or NOTIFICATION_SOURCE_LINKS
    normalized = canonical_url(url)
    if not looks_like_official_website(normalized):
        return False
    if config_urls and normalized in config_urls:
        return False
    registry = read_json(path, {"version": 1, "links": []})
    if not isinstance(registry, dict) or not isinstance(registry.get("links"), list):
        registry = {"version": 1, "links": []}
    known = {
        canonical_url(entry.get("url", "")) if isinstance(entry, dict) else canonical_url(entry)
        for entry in registry["links"]
    }
    if normalized in known:
        return False
    host = host_name(normalized)
    label = strip_discovery_branding(clean_text(name)) or host
    org = strip_discovery_branding(clean_text(department)) or label
    registry["links"].append({
        "url": normalized,
        "name": label,
        "department": org,
        "type": "central",
        "categorySlug": "central",
        "location": "All India",
        "noticeTypes": sorted(DEFAULT_NOTICE_TYPES),
        "addedBy": "discovery-official-website",
        "addedAt": (now or datetime.now(timezone.utc)).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z"),
    })
    print(f"  Registered official website from the notification page: {normalized}")
    if not dry_run:
        write_json(path, registry)
    return True
```

So: a PGIMER vacancy published on `linkingsky.com` with an "Official Website"
row pointing at `pgimer.edu.in` will, on the next run, automatically start
being monitored — without any human editing `sources.json`. The official
listing is checked, and when the visible listing shows nothing new the raw
page source is checked instead.

---

## Code path summary — what runs, when, in what order

For every official website link the monitor does, in order:

```
run() per-source loop
 ├─ fetch_url(url, proxy_fallback=<source.proxyFallback>)
 │    └─ on refusal → _download_via_mirror() → keeps the OFFICIAL url
 │                   only on 403/408/425/429/5xx/timeouts/TLS resets
 │                   never on a 404/410
 ├─ source_candidates(download)   # visible listing (anchor labels)
 │    ├─ parse_feed  (RSS/Atom)
 │    └─ parse_html  (NoticeHTMLParser → table_row_candidates + bare anchors)
 ├─ if discovered == known (no new notice from the visible listing):
 │    └─ page_source_fallback_candidates(download, discovered, known, source)
 │         # raw source: <noscript>, <iframe>, <area>, data-*, script URLs
 ├─ select_bootstrap_candidates() on the very first successful scan
 │    # ranks real, current, same-host notices over nav/portal links
 ├─ job_from_candidate(candidate, source, now)
 │    └─ enrich_candidate()  # may fetch the notice detail page through the
 │                            # same mirror fallback before parsing dates
 ├─ record_source_success() / record_source_failure()
 │    # → data/seen-notices.json "sourceHealth" entry
 └─ every notice row's URL is the OFFICIAL URL, never the mirror
```

For every discovery headline:

```
process_discovery_feeds()
 ├─ for each feed headline:
 │    ├─ match_official_organization()  # only approved boards win
 │    ├─ fetch_url(official_url, proxy_fallback=<org.proxyFallback>)
 │    ├─ if no match in visible listing:
 │    │    └─ page_source_candidates()  # raw source of the OFFICIAL url
 │    ├─ register_official_website_from_article()  # auto-add new boards
 │    └─ job_from_candidate(official_candidate, official, now)
 │         # only ever publishes an OFFICIAL url, never the aggregator's
```

For every offline-form portal vacancy:

```
process_offline_forms()
 ├─ offline_page_documents(page_url, proxy_fallback=…)
 │    ├─ direct application form PDF
 │    ├─ official notification document
 │    └─ official website row → register_official_websites_from_documents()
 └─ offline_job_from_entry()
      # the form/notification URLs are masked behind redirect.html,
      # the OFFICIAL website (when present) is published unmasked
```

---

## Hard rules (do not weaken)

- **Never publish a URL you did not see in the official page source.** The
  monitor reads the source for every official link, but if you add a link
  by hand, it must come from an anchor you saw on the board's own page.
- **Aggregator URLs (LinkingSky / freejobalert / sarkariresult / …) must
  never appear in `pdfLink` / `applyLink` / `sourceUrl`.** The discovery
  pipeline verifies the notice on the official board's page before publishing.
- **Never fall back to a generic root homepage** (e.g.
  `https://sssb.punjab.gov.in`) for `pdfLink` / `applyLink`. The
  `is_generic_homepage()` guard strips these from every published job.
- **The page-source rule is part of the shared pipeline** — never remove
  `page_source_fallback_candidates()` from the per-source loop in `run()`.
- **The mirror flag must reach every fetch path** — the
  `ProxyFallbackWiringTests` enforce this for sources, organisations, feeds
  and registry links.
- **`sourceHealth` is a real, committed signal** — it lives in
  `data/seen-notices.json` and surfaces in git when a source goes silent.

Guard tests in `tests/test_update_jobs.py` keep all of this enforced:

```
test_fetch_url_mirror_fallback_preserves_official_url
test_fetch_url_does_not_mirror_hard_404s
test_fetch_url_direct_success_never_touches_mirror
test_source_health_records_failures_then_recovers
test_discovery_feed_fetch_honors_proxy_fallback
test_offline_page_documents_passes_proxy_flag
test_offline_portal_listing_fetch_honors_proxy_fallback
test_config_files_enable_proxy_fallback_for_blocked_sources
test_every_enabled_official_source_is_covered_by_the_page_source_rule
test_run_checks_page_source_when_listing_shows_no_new_notification
test_page_source_rule_is_documented_in_workflow_and_agent_rules
test_discovery_article_official_website_is_registered
test_official_website_links_reads_row_and_inline_labels
test_official_website_row_is_recognised_only_for_official_domains
test_official_website_link_is_registered_as_a_monitor_source
test_official_website_registration_skips_blogs_portals_and_known_sources
test_dry_run_never_writes_the_registered_official_website
test_sources_json_desgpc_opts_into_mirror_fallback
```

---

## How to add a new unreachable official website (copy-paste recipe)

Pick any of these three, in this order of preference:

1. **Edit `automation/sources.json`** — copy an existing object with
   `proxyFallback: true`, change the `id` / `name` / `department` / `url`,
   and set `enabled: true`. The page-source rule, the mirror fallback and
   the `sourceHealth` tracking all apply automatically.

2. **Edit `automation/official-organizations.json`** — so any discovery
   headline naming this board is verified against its own listing first
   (and its raw page source on every run). Mirror-flag the entry when the
   board's site is known to block datacenters.

3. **Append to `data/notification-source-links.json`** — zero code change
   needed. `additional_link_sources()` turns it into a normal source on
   the next run. Carry `proxyFallback: true` here too.

The PGIMER diff (the one in the question) is just option 1 + 2 applied
to the existing entries in `automation/sources.json` (line 407) and
`automation/official-organizations.json`. No Python change is required.

---

## Local verification

```bash
# install deps
python -m pip install -r automation/requirements.txt

# unit tests — must stay green (they enforce all of the above)
python -m unittest discover -s tests -v

# dry-run the monitor; it never writes data files
python scripts/update_jobs.py --dry-run
```

Look for these log lines on a successful first run:

```
Checking PGIMER Chandigarh: https://pgimer.edu.in/.../VACANCIE_VIEW.jsp?countt=0
  Found N supported alert link(s), M unseen, publishing K
  Published: <Department> — <Post> Recruitment
```

And on a later run when the visible listing is unchanged:

```
  Listing showed no new notification; raw page source of the official
  website exposes <N> additional notice link(s)
```
