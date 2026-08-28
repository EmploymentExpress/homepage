# AGENTS.md — Instructions for AI Agents & Automation

> **Read this file before making any change to this repository.**
> These rules apply to every AI agent (Codex, Claude, Cursor, Gemini, Copilot, Arena agents, etc.)
> and to human contributors alike.

## 🔒 The #1 rule: the homepage layout is FROZEN

The section layout of `index.html` (the **Classic 4-Column Mega Grid**, restored in PR #17) is
deliberate and **protected**. When you are asked to "update" anything — jobs, dates, links,
admit cards, results, text, counts — you must change **only the specific details you were asked
to change** and nothing else.

**NEVER do any of the following unless the user EXPLICITLY asks for a layout change
(e.g. "reorder sections", "move X above Y", "change to a 2-column grid"):**

- ❌ Reorder, add, remove, or rename sections
- ❌ Change grid classes (`grid-cols-*`), wrappers, or the 4-column mega grid structure
- ❌ Change element `id`s or `class`es — JS rendering and nav anchors depend on them
- ❌ Restyle headers/cards (colors, badges, icons) or move sections into/out of the grid
- ❌ "Improve", "modernize", or "clean up" the HTML structure on your own initiative

**✅ You MAY change (when instructed):**

- Job/notice entries inside the JS datasets in `index.html` (`jobs`, `admitCards`, `results`,
  admissions, etc.) — add/edit/remove the entries you were told about, leave the rest untouched
- Generated data files: `data/auto-jobs.json`, `data/seen-notices.json`,
  `data/notification-source-links.json`, `data/offline-redirects.json`
- Monitor sources & logic: `automation/*.json`, `scripts/update_jobs.py` (data-only behaviour)
- The offline-form registry: `automation/offline-forms.json` — add offline-apply vacancies
  here (each entry points to the external offline-form page for that job). The external URL is
  masked on the site: links render as `redirect.html?f=<token>` and the real URL lives only in
  the generated `data/offline-redirects.json`. Never display the external portal's name or URL
  on the homepage.
- Specific text a user asks you to fix (titles, dates, links, counts) — in place, no reflow

## 🔗 Official Advertisement & Apply Link Standard (Mandatory)

Whenever job details are updated, curated, or generated via automation:
- **`pdfLink` (Official Notice / PDF):** MUST always point directly to the specific advertisement notification PDF or active notice page for that job.
- **`applyLink` (Apply Online / Portal):** MUST always point directly to the specific online application or registration portal page for that post.
- **❌ NEVER use generic root homepages:** Never set `pdfLink` or `applyLink` to generic root URLs (e.g., `https://sssb.punjab.gov.in`, `https://pspcl.in`, `https://ppsc.gov.in`, `https://ssc.gov.in`). Always extract or provide the direct notification or portal page URL.

## 🔍 Source-of-truth rule: always read the official website **and its page source** (Mandatory)

Job details are never written from memory, from a search snippet, or from a job-alert blog.
Before you add, edit, or re-date **any** job/notice detail — title, department, advertisement
number, vacancy count, dates, `pdfLink`, `applyLink` — you must complete this loop:

1. **Open the official website** of the recruiting board/department: the URL registered for it
   in `automation/sources.json` (or `automation/official-organizations.json`). That registry is
   the list of approved sources; if the organisation is not in it, add it there first.
2. **Read that page's source** — the actual rendered HTML/link list ("What's New", "Latest
   Updates", the vacancy listing), not a summary of it. Every URL you publish must be **copied
   verbatim from an anchor `href` you saw in that page source**.
3. **Update the job details to match the source**: the notice must actually exist there, and the
   post name, advertisement number and dates you publish must match the board's own wording.

**Hard rules that follow from this:**

- ❌ **Never publish a URL you did not see in the official page source.** Aggregators
  (freejobalert, sarkariresult, mysarkarinaukri, dailyjobalert, punjabjobalert, linkingsky,
  testbook, adda247, …) may be used only as a *lead* to learn that a notice exists. Their
  "direct link" URLs are routinely invented — discard any that is absent from the official page
  source. Aggregator hosts must never appear in a published `pdfLink`/`applyLink`.
- ❌ **Never guess a deep link** by pattern-matching another site's URL scheme, and never fall
  back to a root homepage (see the link standard above).
- ⚠️ **If the official site is unreachable**, stop: keep the existing value (or
  `See Notification`), publish nothing new for that field, and say plainly in your reply/PR that
  the source could not be read and what still needs verification. A broken or unverifiable link
  is worse than no link.
- 🔁 **Re-check the page source for changes** before touching dates. Re-openings, corrigenda,
  extensions and cancellations must come from the board's own notice — when the board re-opens a
  window, set `lastDateExtended`, `originalLastDate` and `extensionNoticeUrl` from that notice.
- 🧭 **Fix the registry when the site moves.** Official portals get rebuilt (PSSSB moved from
  `*.html` pages to a WordPress structure). If a configured URL is dead, repoint it in
  `automation/sources.json` in the same pass instead of leaving a source that can never fetch.
- 📝 **Say what you verified.** In the commit/PR message and in your reply, name the page you
  read and the notice/anchor text you copied the link from.

`tests/test_update_jobs.py` enforces the mechanical half of this rule
(`test_curated_links_never_point_at_aggregator_hosts`,
`test_agents_rules_require_official_page_source_verification`). The judgement half — actually
opening the source before you type — is on you.

## 🤖 Workflow automation page-source rule (mandatory, runs on every workflow run)

The scheduled monitor (`.github/workflows/update-job-alerts.yml` →
`scripts/update_jobs.py`) enforces the same source-of-truth rule mechanically:

1. **Check the official website listing** of every enabled source.
2. **If no new job notification is found** in the listing, **check the raw page
   source of that official website** (`page_source_fallback_candidates` in
   `scripts/update_jobs.py`): it re-reads the page's raw HTML — including
   `<noscript>` fallback blocks, `<iframe>`/`<embed>` PDF embeds, `<area>`
   maps, `data-*` hooks and bare URLs in scripts/JSON — and publishes only
   links found there that classify as a supported notice. This runs on **every
   workflow run**, not just the first.

**This rule applies automatically to every official website link** — existing
or added later, with **no extra configuration**:

- every source in `automation/sources.json` (set `"enabled": true` and the
  monitor handles the rest),
- every approved organisation in `automation/official-organizations.json`
  (when a discovery headline names it, the monitor verifies against the
  official listing first and falls back to the official page source),
- every user-added link in `data/notification-source-links.json`
  (`additional_link_sources()` turns it into a normal source).

When you add a new official website link to any of these files, you do **not**
need to write any new scanning code or flags — the page-source check is part
of the shared pipeline every source goes through. Never remove, weaken, or
bypass this fallback; if the official site is unreachable, the monitor keeps
existing data and says so (it never invents links). Keep the rule's guard
tests in `tests/test_update_jobs.py` green when touching this pipeline.

**Discovery feeds (`automation/discovery-feeds.json`).** A feed may be hosted on a headline
aggregator (`linkingsky.com`, `punjabjobalert.com`, `haryanajobs.in`) **or** on an offline-form
portal (`onlineforms.in`, `speedjob.in`). Either way a feed supplies **leads only**: the notice
must still be matched to an approved organisation and verified on the recruiting board's own
listing/page source before anything is published, and the feed host's URLs and branding are never
shown on the homepage. Use the key `maxNewPerRun` (not `maxNewPerFeed`) for per-feed limits — it
is the key `load_discovery_feeds()` reads.

## 📡 Source reachability, mirrors & first-scan quality (mandatory behaviour)

Three safeguards keep an official source from silently going stale — do not remove them:

1. **Reachability tracking (`sourceHealth`).** When a source fetch fails, the run records
   `consecutiveFailures`, `lastFailureAt` and `lastError` under `sourceHealth` in
   `data/seen-notices.json` (one of the four data files the workflow commits), and prints a
   loud warning from the second consecutive failure onward. A healthy run records
   `lastSuccessAt` once. This is how "the workflow stopped updating source X" becomes visible
   in git instead of hiding in job logs.
2. **Mirror fallback (opt-in per source).** A site that refuses datacenter connections
   (TLS handshake dropped mid-handshake, 403 WAF block, 5xx anti-bot challenge) can be
   fetched through the read-only text mirrors in `SOURCE_MIRRORS` when the config sets
   `"proxyFallback": true`. The flag is honoured on **every fetch path**: the official
   listing check (`automation/sources.json`), per-notice detail/PDF enrichment, discovery
   feed fetches (`automation/discovery-feeds.json`), the official-website verification of
   discovery headlines (`automation/official-organizations.json`), the offline-form portal
   listing and its vacancy pages, and discovery-article registration. The fallback fires
   **only** for refusal/connection errors — never for clean 404/410s — and every parsed
   link keeps the **official URL**: mirrors are transport only, never a source of truth,
   and their URLs must never appear in published data. Sites that block **non-Indian**
   visitors entirely (several `*.punjab.gov.in` hosts) defeat mirrors too; their
   `sourceHealth` entries make the gap visible and an India-egress runner would be the
   real fix.
3. **First-scan (`bootstrapCount`) ranking.** The first successful scan marks the whole listing
   as seen and publishes only the top `bootstrapCount` links; `select_bootstrap_candidates()`
   ranks them so **real, current, same-host notices** (readable unexpired last date, direct
   PDF) win over navigation/portal links such as "Apply Online (Recruitment Portal)". Never
   revert to raw page order — that is exactly how a portal link was once published as a
   "vacancy" with placeholder details.

## 🔗 Auto-registration of the "Official Website" link (mandatory, every run)

Notification pages on the discovery feeds print an **"Official Website"** row beside their
notification/apply rows. On every run the monitor reads that row and, when it holds a genuine
official website, **registers it automatically** as an official website link for the automation
workflow:

1. `official_website_links()` reads the label from the row/section context (the anchor text itself
   is generic — "Visit Now", "Click Here"), for both table-row and inline layouts.
2. `looks_like_official_website()` accepts the URL only when it is a real official domain
   (`.gov.in`, `.nic.in`, `.gov`, `.mil.in`, `.ac.in`, `.edu.in`, `.edu`, `.res.in`, `.org.in`,
   `.co.in`, `.in`, `.org`) and rejects PDFs, discovery/offline-portal hosts, job blogs and
   aggregators (`NON_OFFICIAL_WEBSITE_HOSTS`), social/Telegram/WhatsApp links and shorteners.
3. `register_official_website_link()` appends it to **`data/notification-source-links.json`**
   with `addedBy: "discovery-official-website"` and an `addedAt` timestamp. Registration is
   idempotent (never duplicates a link already configured in `automation/sources.json` or already
   stored) and is skipped entirely on `--dry-run`.
4. `additional_link_sources()` turns that stored link into a normal monitor source on the next
   run, so the official listing — and, when it shows nothing new, its **raw page source** — is
   checked automatically. No manual configuration is needed for a newly seen board.

This never changes what may be published: notices still come only from the official website, and
the discovery/portal URL is never published or displayed. Do not weaken the host checks — the
guard tests in `tests/test_update_jobs.py` (`test_official_website_*`,
`test_discovery_article_official_website_is_registered`) must stay green.

## ⏱️ "Just In" Badge, newest-first order & 48-Hour Auto-Removal Rule

Whenever new job details are added or published through automation:
- **"Just In" Batching:** Every newly published or newly discovered job detail must carry a `publishedAt` or `discoveredAt` ISO timestamp.
- **Newest First:** Every vacancy/admission column and the master active-recruitment table sorts by publication/discovery time, newest first. Do not replace freshness order with last-date order.
- **Active Recruitments:** A recruitment/admission with a readable deadline is removed after that deadline passes. Notices whose deadline cannot be verified must say `See Notification`, never use a guessed date.
- **48-Hour Window:** The homepage automatically renders a prominent **"Just In"** tag on newly discovered official notices across all main grid sections and the master vacancy table.
- **Automatic Expiry:** The **"Just In"** badge/tag stays active for exactly **48 hours** after publication/discovery and is automatically removed by the page logic once that 48-hour window elapses.

## 🏛️ Specific recruiting-department title rule

Every published job title must visibly contain the full recruiting department/organisation name and the actual post or vacancy subject. Convert action-only labels such as `Application for Clerk` into a specific title such as `Punjab State Legal Services Authority (PULSA) — Clerk Recruitment`; reject navigation/link labels such as `Other Links`, `Close menu`, or `work Recruitments`. Generic source labels such as `Official Recruitment Notice` are never valid department names.

## 📰 Short job-details headline rule (Mandatory)

Every job-details **heading** published on the site (grid cards, Last Date Reminders, the master
vacancy table, admission cards) must be a **short, scannable headline generated from the official
notification** — never the raw portal link text and never a full sentence.

**Format (fixed word order, no em dash, no year):**

```
<Department short name> <Total posts> <Post name(s)> <What the notice is about>
```

- **Department short name** — always in **capital letters** (uppercase). Use the board's own bracketed acronym when it publishes one
  (`Punjab State Legal Services Authority (PULSA)` → `PULSA`,
  `Punjab Agricultural University (PAU), Ludhiana` → `PAU`), otherwise the leading segment of the
  official name in capital letters, abbreviated and capped at 34 characters (`Local Audit Department, Chandigarh
  Administration` → `LOCAL AUDIT DEPT.`). Keep the state/UT visible when the acronym hides it
  (`HARYANA WCD`, `ABDM CHANDIGARH`). Never invent an acronym the board does not use.
- **Total posts** — the numeric vacancy count when the notice states one (`681`, `4,161`).
  Omit it for `See Notification` / `Various` / single-post notices.
- **Post name(s)** — the actual post(s), taken from the notice's own wording. List at most two,
  comma separated, and append `& Various Post` when more exist
  (`Clerk, Typist & Various Post`). Strip portal noise (`View`, `PDF 383 KB - opens in a new
  window`, `Click Here`, `Apply Online`, `Application Form`, `Notification`), bracketed
  `(Last date … / interview on …)` blurbs, advertisement numbers, years, and trailing
  office/college/department qualifiers.
- **What the notice is about** — detected from the board's own wording, using exactly this
  vocabulary:

  | Notice says | Headline ends with |
  | --- | --- |
  | new vacancy, apply online | `Online Form` |
  | apply offline / by post / walk-in application | `Offline Form` |
  | corrigendum | `Corrigendum Notice` |
  | addendum | `Addendum Notice` |
  | cancellation / withdrawal of vacancy | `Vacancy Cancelled` (exam → `Exam Cancelled`) |
  | postponement / rescheduling | `Exam Postponed` (interview → `Interview Postponed`) |
  | extension / re-opening of last date | `Last Date Extended` |
  | shortlisted / empanelled candidates | `Shortlisted Candidates` |
  | exam date / schedule / exam city | `Exam Date` |
  | admit card / call letter / roll no. | `Admit Card` |
  | answer key / objections | `Answer Key` (exam → `Exam Answer Key`) |
  | merit / selection list | `Merit List` |
  | waiting list | `Waiting List` |
  | result / cut-off | `Result` |
  | posting / appointment orders | `Posting Orders` |
  | walk-in interview | `Walk in Interview` |
  | admission / entrance | `Admission Form` |
  | public notice | `Public Notice` |

**Hard rules:**

- ⏳ **72-character cap.** Shorten by dropping extra posts (`& Various Post`), then brackets —
  never by cutting a word in half or dropping the notice type.
- 🧾 **Headline ≠ data.** Shortening applies to the displayed heading only. The full official
  title, advertisement number, dates and links stay in the job-details modal, the description and
  the `JobPosting` structured data — nothing is deleted from the dataset.
- 🏛️ **The department and the post must both still be visible** (the specific
  recruiting-department title rule above still applies); never publish a bare
  `Result` / `Online Form` heading with no department.
- 🚫 Never guess the notice type. If the official wording gives no cue, use `Online Form` for a
  vacancy notice and the alert type's default otherwise.
- 🛠 **Use the shared implementation, don't re-invent it:** `scripts/short_headlines.py`
  (`short_job_headline(title, department, alert_type, vacancies, apply_mode)`) and its JS mirror in
  `index.html` (`shortJobHeadline()` / `jobDisplayHeadline(job)`, used by the grid cards, the master
  table and Last Date Reminders; both implementations must produce identical output).
  Regenerate the before/after demo with `python scripts/preview_short_headlines.py`
  (writes `docs/short-headline-demo.html` / `.md`). Guard tests live in
  `tests/test_short_headlines.py` and must stay green.

## 📋 Google Jobs & Search Console Schema Standard (Mandatory)

Whenever job structured data, `index.html` schema functions, curated vacancy datasets, or automation scripts are created or modified, all Schema.org `JobPosting` structured data must strictly satisfy **all Google Search Console critical and non-critical requirements**:

1. **`datePosted` (Critical / Required):**
   - Must ALWAYS be present as a valid ISO 8601 string (`YYYY-MM-DD` or `YYYY-MM-DDTHH:mm:ssZ`).
   - Parsed from `job.publishedAt`, `job.startDate`, `job.discoveredAt`, or derived from `job.lastDate`, with a fallback to the current date. Never emit an empty, null, or missing `datePosted`.
2. **`validThrough` (Recommended / Non-critical):**
   - Must ALWAYS be present as a valid ISO 8601 string at the end of the deadline date (`23:59:59`).
   - Parsed from `job.extendedLastDate` or `job.lastDate`. If "See Notification" or unparseable, set to a 30-day validity window from `datePosted`.
3. **`jobLocation.address` (Required / Non-critical subfields):**
   - Must be a `PostalAddress` object with all five fields populated:
     - `streetAddress`: Post/department campus, office, or district complex.
     - `addressLocality`: City or district (e.g. Chandigarh, Ludhiana, Amritsar, SAS Nagar Mohali, Patiala, Jalandhar, Bathinda, New Delhi, etc.).
     - `addressRegion`: State or UT (e.g. Punjab, Chandigarh, Delhi, Haryana, Karnataka, Tamil Nadu).
     - `postalCode`: Valid 6-digit Indian PIN code (e.g. 160001, 141004, 143005, 160017, 110001).
     - `addressCountry`: `"IN"`.
4. **`baseSalary` (Recommended / Non-critical):**
   - Must be structured as a `MonetaryAmount` in currency `"INR"` with a `QuantitativeValue` (`unitText: "MONTH"`).
   - Value must be numeric (single `value` or `minValue`/`maxValue` range), extracted from parsed remuneration / pay scale or mapped to standard 7th CPC entry pay levels (10th/12th: Level 2, Diploma/ITI: Level 4, Graduate/Officer: Level 6-7).
5. **Required Core Fields:**
   - `title`: Specific post title naming the department.
   - `description`: Rich textual description combining details, qualification, vacancies, age criteria, and how-to-apply steps.
   - `hiringOrganization`: `@type: "Organization"` with non-empty `name` and valid `sameAs` / `url`.
   - `identifier`: `@type: "PropertyValue"`, `name: "EMPLOYMENT EXPRESS"`, `value: String(job.id)`.
   - `url`: Direct deep link (`getJobDirectUrl(job)`).
   - `employmentType`: `"FULL_TIME"`, `"CONTRACTOR"`, `"TEMPORARY"`, `"PART_TIME"`, or `"INTERN"`.
6. **Automated Verification:**
   - Every change must pass `tests/test_job_posting_schema.py` and the complete test suite (`python -m unittest discover tests/ -v`).
7. **Resilience & Fallbacks (Always Post the Job Details):**
   - If any specific or optional detail (such as exact salary figures, detailed street address, or explicit application opening/closing dates) is not found in the official notification, **the job details MUST STILL be published on the homepage, table, feeds, and structured data**.
   - Never skip, drop, withhold, or fail to publish a job alert solely due to missing optional details — use safe, standard fallbacks (`See Notification`, official board headquarters address, standard pay scale defaults) so the job is always visible to applicants and search engines.

## 📐 Canonical section order (do not reorder)

Inside `<main>` of `index.html`:

1. Quick Notice Banners / Highlight Grid
2. **Main 4-Column Mega Grid** (`#answer-keys` wrapper, `grid-cols-1 md:grid-cols-2 lg:grid-cols-4`):
   - Column 1: Latest Punjab Jobs (`#punjab-jobs`, blue)
   - Column 2: All India & NVS / Central (`#central-jobs`, purple)
   - Column 3: Admit Card 2026 (`#admit-cards`, emerald)
   - Column 4: Results & Answer Key (`#results`, rose)
3. **Last Date Reminders** (`#last-date-reminders`, red section)
4. Admission & Courses (`#admission-courses`)
5. Qualification Quick Finder Pills
6. Master Table: Latest Govt Job Vacancies 2026
7. Quick Resources & State Syllabus Widget

Newly discovered official notices are rendered **in place inside their respective section**
(Latest Punjab Jobs / All India & NVS / Results & Answer Key / Admission & Courses / the
Master Table) with a **"Just In"** tag that stays for **48 hours** after publication and is
removed automatically once that window elapses.

## 🛡 How the layout is enforced

- **`tests/test_layout_order.py`** asserts the exact section order, the 4-column grid classes,
  and unique anchor IDs. The GitHub Actions workflow runs the full test suite on every run, so a
  layout-changing edit **fails CI**. If this test fails after your edit, you changed the layout —
  revert it unless the user explicitly requested a layout change (in which case update the test
  in the same commit and say so in the PR).
- **`scripts/update_jobs.py`** snapshots `index.html` and `assets/` before every monitoring run
  and restores them afterwards (`PROTECTED_LAYOUT_PATHS`), so automation can only ever write to
  `data/*.json`. Never widen those paths to let the monitor edit the page.
- Guard comments at the top of `<main>` in `index.html` repeat these rules inline.

## 🧪 Before you finish

```bash
python -m unittest discover -s tests -v   # must pass, including layout-order tests
```

Keep diffs minimal: the changed lines in your PR should be recognisable as exactly the content
you were asked to update. If a diff touches section structure, stop and reconsider.
