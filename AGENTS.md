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

## ⏱️ "Just In" Badge, newest-first order & 48-Hour Auto-Removal Rule

Whenever new job details are added or published through automation:
- **"Just In" Batching:** Every newly published or newly discovered job detail must carry a `publishedAt` or `discoveredAt` ISO timestamp.
- **Newest First:** Every vacancy/admission column and the master active-recruitment table sorts by publication/discovery time, newest first. Do not replace freshness order with last-date order.
- **Active Recruitments:** A recruitment/admission with a readable deadline is removed after that deadline passes. Notices whose deadline cannot be verified must say `See Notification`, never use a guessed date.
- **48-Hour Window:** The homepage automatically renders a prominent **"Just In"** tag on newly discovered official notices across all main grid sections and the master vacancy table.
- **Automatic Expiry:** The **"Just In"** badge/tag stays active for exactly **48 hours** after publication/discovery and is automatically removed by the page logic once that 48-hour window elapses.

## 🏛️ Specific recruiting-department title rule

Every published job title must visibly contain the full recruiting department/organisation name and the actual post or vacancy subject. Convert action-only labels such as `Application for Clerk` into a specific title such as `Punjab State Legal Services Authority (PULSA) — Clerk Recruitment`; reject navigation/link labels such as `Other Links`, `Close menu`, or `work Recruitments`. Generic source labels such as `Official Recruitment Notice` are never valid department names.

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
