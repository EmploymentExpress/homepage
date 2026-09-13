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
- **❌ NEVER use generic root homepages:** Never set `pdfLink` or `applyLink` to generic root URLs (e.g., `https://sssb.punjab.gov.in`, `https://pspcl.in`, `https://ppsc.gov.in`, `https://ssc.gov.in`). A portal's own document front door counts as generic too — `https://ors.gov.in/index.html` is `ors.gov.in`'s root homepage even though it carries a file name. `is_generic_homepage()` / `GENERIC_HOME_PATHS` in `scripts/update_jobs.py` treat `/index`, `/index.html`, `/index.php`, `/home` (and `.htm`/`.php` variants) as generic; the refresh merge (`_is_better_notice_link`) never swaps a stored link for one, and the sanitize pass blanks one it finds in the published store. Always extract or provide the direct notification or portal page URL.
- **❌ NEVER attach an administrative document as the "official notification":** a telephone / contact / address **directory**, holiday list, duty roster,
  office order, staff or employee list, newsletter, gallery, annual report or RTI file is **site housekeeping, not a notice** — it may never become a
  `pdfLink`/`applyLink`, and it may never be the subject of a job/admission post. Open the file name and check what the document *is*, not just that it is
  an official `.pdf`. `NON_NOTICE_DOCUMENT_TERMS` / `is_non_notice_document()` in `scripts/update_jobs.py` enforce this in the detail-page PDF picker, the
  raw page-source scan, the refresh merge and the published-data sanitize pass (which blanks such a link and falls back to the notice page);
  `tests/test_update_jobs.py` guards it.
  **Real incident (fixed 2026-09-12):** a CUPB Bathinda "job details" post was published whose only attachment was
  `Telephone directory (Hindi & English) as on 09.10.2025.pdf`, scraped from the university's site chrome while its listing page read
  "Will be Updated Shortly." — i.e. a **job post that was actually a telephone directory**. Two CUPB admission cards had the same file. A notice exists
  only when the board's own page carries the advertisement: an empty or informational page yields **nothing**, never a fallback document.

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

**Verified Job-Updates Reliability Rule (R1–R13)** — added Sep 2026 after three real incidents
(PGIMER's 200 error-stub starvation, AIIMS Bathinda's transient 500s, and 33 sources failing 47
runs because a single dead mirror was the only one ever tried). The same section of
`data/seen-notices.json` also carries the new `mirrorHealth`, `detailFetchHealth` and
`silentDead` keys. Do not remove these safeguards:

4. **A 200 answer is not a successful scan (R1).** A listing that answers HTTP 200 with a known
   error stub ("Could not complete the request. Some error occured…") or with no notice anchors
   at all is a **failure**: `fetch_source_listing()` retries it through a read-only mirror when
   the source opts in, otherwise records it in `sourceHealth`. PGIMER stayed "healthy" with zero
   published notices for a week before this rule existed.
5. **Mirror rotation with memory (R2).** `SOURCE_MIRRORS` holds four read-only mirrors
   (allorigins, r.jina.ai, codetabs, corsproxy). Per-mirror health persists in
   `mirrorHealth` across runs: a mirror that fails twice is skipped for 24 hours instead of
   being retried on every fetch. One dead mirror must never starve every failing source.
6. **Transient 5xx retry (R3) and opt-in SSL fallback (R4).** Server errors and 429s earn one
   extra direct attempt with backoff (AIIMS Bathinda answers one request with 500 and the next
   with the real page). Sources with broken certificate chains may set `"sslFallback": true`
   (read-only fetch of public pages; every published link still comes from that page source).
7. **Endpoint health budget (R5).** Detail/document hosts that fail
   `DETAIL_FETCH_FAILURE_THRESHOLD` times in a row are probed at most once per 24 hours
   (`detailFetchHealth`) — the listing page stays the heartbeat, so a blocked PDF servlet
   (PGIMER `AbstractFilePath` serves 500 to non-browsers) no longer burns its timeout on
   every notice in every run.
8. **Extract what the notice says, never guess (R6–R10).** Official page source is the only
   truth; detail-page link labels ("Click here for Notice/apply", "Corrigendum") drive
   `pdfLink`/`applyLink` even when the file endpoint blocks bots; anything unverifiable stays
   **"See Official Notification"**. Fees, fee mode and exam dates are now parsed from notice
   text on clear labelled matches only (`infer_fee`, `infer_fee_mode`, `infer_exam_date`) and
   backfilled into already-published jobs (`backfill_extracted_fields`, refresh scoring) — a
   placeholder is always preferable to a guess.
9. **Visibility for feeds and silent sources (R11/R12).** Discovery feeds record
   `sourceHealth` like every official source. A source or feed initialized more than
   `SILENT_DEAD_AFTER_DAYS` ago that still has zero fingerprints is flagged `silentDead`.
   `scripts/source_health_summary.py` (a workflow step with `if: always()`) prints failing,
   silent-dead, never-initialized sources, the placeholder backlog and mirror health into the
   Actions run summary (`$GITHUB_STEP_SUMMARY`).
10. **Category coverage per organisation (R13).** When an organisation groups notices by
    category (AIIMS Bathinda: Faculty / Non-Faculty / SR-JR / Project), monitor **every**
    category page — an open walk-in that reaches the site through no source is a coverage bug
    (observed: the 14-Sep-2026 SR walk-in interview was invisible while only
    `aiimsexams.ac.in` was monitored).
    **A homepage that only links to its category pages is the same bug.** Central University
    of Punjab (`cup.edu.in`) is the cautionary case: its "Recruitment" tab links to
    `teaching_jobs.php`, `non-teaching_jobs.php` and `other-jobs.php` — never to an
    advertisement — so a new advert never created a new fingerprint on the monitored root
    page. The source looked healthy (14 stable fingerprints, no failures) while publishing
    nothing for weeks. Monitoring the root alone is not enough; add one source per category
    page (see `cup-teaching` / `cup-non-teaching` / `cup-project`) and give each a
    `bootstrapCount` above 1 so the live advert is not buried on the first scan.

## 🗓 Freshness window: a listing's history is never news (R15, Mandatory)

Official listing pages keep their complete history. AIIMS Bathinda's category tables
(`Recruitment.aspx?type=1` Faculty, `?type=2` Non-Faculty, `?type=3` SR/JR, `?type=4` Project
Posts) still carry **every attachment of every advertisement they have published since 2021** —
each row keeps its advertisement, application forms, eligibility lists, corrigenda and results
forever. A link the monitor has not seen before is therefore **not** the same thing as a new
notice: draining that history a few links per run published years-old results as
`NEW RESULT` / `NEW JOB ALERT` in the Punjab column (a **2025 AIIMS Bathinda result was reported
as a new Punjab job**, and the flood also pushed genuine alerts out of the 200-record store).

Every notice is now dated by the notice itself, and history is never published:

1. **The document's own date — `document_date_from_url()`.** An official file name carries the
   date the authority uploaded it (`/images/Reqruitment/20241114045844.pdf` = 14 Nov 2024,
   `20250829033442.pdf` = 29 Aug 2025). That stamp — otherwise the listing row's own date — is
   written to `publishedAt`, so the 72-hour NEW badge, the 48-hour **"Just In"** tag and the
   breaking marquee follow the document's real date instead of the scan time. Only a plausible,
   non-future calendar date is accepted; an alert with no readable stamp keeps the previous
   behaviour (`discoveredAt`).
2. **The freshness window — `maxNoticeAgeDays` + `is_archive_notice()`.** A notice whose own
   document is older than the window (**default 60 days**, top-level key in
   `automation/sources.json`, may be overridden per source) is archive material: `run()` skips it
   and still records its fingerprint, so the same archived link is never re-examined — and never
   republished as new — on the following runs; `publish_unpublished_seen_notices()` skips it;
   and `sanitize_published_jobs()` removes it from the store. **An old advertisement whose
   verified deadline is still open stays published** — the window must never delete a live
   vacancy — and an alert with no readable document date is never treated as archive.
3. **A stage document is a result, never a job.** The same tables point straight at a paper trail
   — "8) Eligibility Notification for the posts of …", "Final Result Notification" — whose only
   description is the attachment label. Such a link belongs in the Results column: `RESULT_TERMS`
   carries the stage labels ("eligibility notification", "final result", "provisional result",
   "shortlisted candidates", …) ahead of the broad recruitment filler terms ("posts of",
   "notification for"), so a result can never be re-read as a fresh vacancy in the Punjab column.
   A row whose label really is an advertisement ("Advertisement for recruitment of … posts")
   still classifies as recruitment.
4. **Do not weaken this.** `tests/test_update_jobs.py::ArchivedNoticeFreshnessTests` guards the
   stamp reader, the publish gate, the still-open-advertisement exception, the store cleanup and
   the config key, and `JobMonitorTests::test_shortlisted_eligible_and_score_card_go_to_result_column`
   guards the stage-label rule. The window is what keeps a monitor that reads whole archives
   honest; removing it restores the 2025-result-as-new-job bug.

## 🔄 Refresh safety: a refresh may verify and complete, never downgrade (R16, Mandatory)

The refresh pass re-reads a notice the monitor already published and merges the fresh details
onto the stored alert (`merge_job_details` in `scripts/update_jobs.py`). A refresh is allowed to
**fill placeholders and supersede with the board's own newer wording** — it is never allowed to
replace a verified value with something weaker. **Real incident (broke the scheduled runs
2026-09-12/13):** re-reading AIIMS Bathinda's Non-Faculty table merged the page's *column
heading* ("Non-Faculty") over a verified result title, filled a vacancy placeholder from a table
header ("2024 Posts") and a notice-number placeholder from a page stamp ("TICE"), and swapped the
verified apply portal for `ors.gov.in/index.html`. On CUPB, a per-post row attached to the same
PDF as its umbrella alert was merged into the *umbrella* (the same-source fallback target),
re-titled it, and the retention pass's (title, notice-URL) de-duplication then dropped the live
umbrella recruitment. The rules that prevent both:

1. **No title/department downgrade.** `merge_job_details` refuses to replace a verified,
   specific title (or full authority name) with a shorter page label
   (`_is_less_specific_title`): a refreshed title with at most two content words, or with fewer
   content words and no overlap, is refused. Replacing a *generic* stored title with the
   notice's specific wording still works.
2. **Last dates move forward only.** A later official last date supersedes the stored one; an
   earlier date is never written back (a deadline change arrives as an extension corrigendum via
   `apply_extensions`). This is what the merge contract always said — the code now does it.
3. **Placeholders only from real values.** An advertisement number without a digit is page
   chrome, not a number (the merge and `infer_advertisement_number` both refuse it), and a
   four-digit year is a table header, not a vacancy count
   (`infer_vacancies` refuses `1900–2099` as the count).
4. **A weak stored link justifies no candidate.** When the stored link is weak (the listing page
   itself or a homepage), `_is_better_notice_link` still requires the replacement to be its own
   strong link — a discovery host, a generic homepage or an administrative document never
   "improves" anything.
5. **Shared URLs target the title-matching alert only.** `find_existing_job_for_candidate`
   prefers, among several stored alerts sharing a candidate's URL, the alert whose stored title
   the candidate matches; `refresh_published_source_jobs` then **skips** the candidate entirely
   when its URL is shared by several alerts and none of them carries its title (an umbrella alert
   and its per-post alerts attach the same PDF). A row whose identity is ambiguous is left
   alone, never merged.
6. **Do not weaken this.** `JobMonitorTests` in `tests/test_update_jobs.py`
   (`test_merge_never_downgrades_a_verified_title_to_a_page_label`,
   `test_generic_homepage_recognizes_index_html_variants`,
   `test_weak_link_is_never_swapped_for_a_portal_homepage`,
   `test_merge_never_pulls_a_last_date_backwards`,
   `test_infer_vacancies_rejects_a_year_as_the_count`,
   `test_infer_advertisement_number_rejects_a_word_without_digits`,
   `test_existing_job_lookup_prefers_the_title_match_among_shared_urls`,
   `test_refresh_never_stamps_a_per_post_row_onto_the_umbrella_alert`) and
   `NonNoticeDocumentGuardTests` (store-wide: no CUPB card ever carries an administrative
   document or a generic homepage link, no alert carries the RTI document) guard every item
   above. The full incident write-up is `docs/MONITOR_REFRESH_INCIDENT_2026-09-13.md`.

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

## 📰 Job-details headline rule (Mandatory)

Every job-details **heading** published on the site (grid cards, Last Date Reminders, the master
vacancy table, admission cards, the admit-card and result lists) is generated from the official
notification — never the raw portal link text and never a full sentence.

**Recruitment notices (fixed format, no length cap):**

```
<Department name> <Post name(s)> Recruitment | Apply Online
<Department name> Various Post Recruitment | Apply Offline
```

- **Department name** — the board's own bracketed acronym when it publishes one
  (`Postgraduate Institute of Medical Education and Research (PGIMER), Chandigarh` →
  `PGIMER Chandigarh`), otherwise the leading segment of the official name in title case,
  abbreviated and capped at 34 characters (`Local Audit Department, Chandigarh Administration` →
  `Local Audit Dept. Chandigarh`). Keep the state/UT or city visible when the acronym hides it
  (`Haryana WCD`, `PAU Ludhiana`). Title case means acronyms stay capitalised (`DEO`, `MTS`,
  `PGIMER`) and small words stay lowercase (`Ministry of Defence`). Never invent an acronym the
  board does not use.
- **Post name(s)** — taken from the notice's own wording:

  | Posts in the notice | Headline shows | Example |
  | --- | --- | --- |
  | 1 post | that post name | `PGIMER Chandigarh Nursing Officer Recruitment \| Apply Online` |
  | 2–4 different posts | all of them, comma separated | `PGIMER Chandigarh DEO, MTS, Pharmacist Recruitment \| Apply Online` |
  | more than 4 posts | `Various Post` | `PGIMER Chandigarh Various Post Recruitment \| Apply Offline` |
  | no post named | department only | `PGIMER Chandigarh Recruitment \| Apply Online` |

- **Apply mode** — from the stored apply mode and the notice's own wording: offline / by-post /
  by-hand applications end `| Apply Offline`; everything else ends `| Apply Online`.

**Non-recruitment notices** (admit card, result, answer key, corrigendum, admission, exam date,
postponement, cancellation, shortlist, merit/waiting list, posting orders, walk-in interview,
public notice): `<Department name> <Notice type>` — e.g. `SBI Admit Card`,
`PGIMER Chandigarh Result`. No post names, no apply-mode suffix. The notice type is detected from
the board's own wording, using exactly this vocabulary:

  | Notice says | Headline ends with |
  | --- | --- |
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

**Interview call letters are admit-card notices:** anything the board words as a call letter,
admit card, hall ticket or roll no. (interview call letters included) must render in the Admit
Card column — `alertType: "admit-card"` end to end, and the frontend `allowedAlertTypes` list in
`index.html` must keep `"admit-card"` allowed so such notices are never downgraded to
`recruitment`.

**Hard rules:**

- 🧾 **Headline ≠ data.** The headline shortens the displayed heading only. The full official
  title, advertisement number, dates and links stay in the job-details modal, the description and
  the `JobPosting` structured data — nothing is deleted from the dataset.
- 🏛️ **The department must always be visible** (the specific recruiting-department title rule
  above still applies); never publish a bare `Result` heading with no department.
- 🔢 **No vacancy count in the headline** — counts live in the card details, not in the heading.
- 🚫 Never guess the notice type. If the official wording gives no cue, use
  `Recruitment | Apply Online` for a vacancy notice and the alert type's default otherwise.
- 🛠 **Use the shared implementation, don't re-invent it:** `scripts/short_headlines.py`
  (`short_job_headline(title, department, alert_type, vacancies, apply_mode)`) and its JS mirror in
  `index.html` (`shortJobHeadline()` / `jobDisplayHeadline(job)`, used by the grid cards, the
  master table, Last Date Reminders and the results and admit-card lists; both implementations
  must produce identical output). Regenerate the before/after demo with
  `python scripts/preview_short_headlines.py` (writes `docs/short-headline-demo.html` / `.md`).
  Guard tests live in `tests/test_short_headlines.py` and must stay green.

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

## 🔎 Discovery files: sitemap.xml, llms.txt, robots.txt (generated — never hand-edit)

`scripts/build_seo.py` regenerates three files on **every** scheduled run (its own
workflow step runs after the alert and share-page steps). Hand edits are lost at the
next run, so change the generator instead.

- **`sitemap.xml`** — the homepage, the standalone article pages listed in
  `ARTICLE_PAGES`, and one `share/job-<id>.html` per alert. Generated from the
  filesystem plus each alert's own `discoveredAt` date, so new alerts become
  discoverable the same run they are published.
- **`llms.txt`** — the [llmstxt.org](https://llmstxt.org) index for AI answer
  engines. It describes the site, states that notices are verified on the
  authority's own website, then lists the freshest vacancies / admit cards /
  results, each with a one-line summary. Expired alerts and alerts whose share
  page does not exist yet are deliberately excluded: an assistant must never
  quote a deadline that has passed or link to a page that 404s.
- **`robots.txt`** — allows every crawler, names each AI agent explicitly
  (GPTBot, OAI-SearchBot, PerplexityBot, ClaudeBot, Google-Extended, …) and
  points at the sitemap and the LLM index.

**Why this exists.** The homepage is a single-page app: its alert board only
exists after JavaScript fetches `data/auto-jobs.json`. Crawlers that never run
JavaScript — Googlebot's secondary pass and the AI answer engines — used to
receive an essentially empty page, while 500+ static, canonical alert pages sat
undiscoverable in `share/`. So:

- `scripts/build_share_pages.py` writes **static** `JobPosting` + `BreadcrumbList`
  JSON-LD, per-page `meta keywords` and the alert's details as readable text into
  every share page. That is the content AI crawlers actually read.
- Share pages redirect real visitors to the app with **JavaScript only**. Never
  re-add a `http-equiv="refresh"`: a 0-second meta refresh flags the page as a
  redirect and costs it the index.
- `index.html` and `assets/` are protected layout files
  (`PROTECTED_LAYOUT_PATHS`), so homepage-level tags stay hand-authored while
  these three files stay fresh.

Guards: `tests/test_seo.py` (sitemap lists every share page, robots allows the
AI agents, llms.txt links only to pages that exist, share pages carry valid
static structured data, and `build_seo.main()` never touches a protected file).

## 🗺️ Punjab column rule: AIIMS Bathinda, every Chandigarh organisation, CUPB, Punjab state & every Punjab district (R14, Mandatory)

AIIMS Bathinda notices, every notice from a recruiting organisation **of
Chandigarh**, every notice of the **Central University of Punjab (CUPB),
Bathinda**, and every notice whose **job details name the Punjab state,
Chandigarh, or a district of Punjab as the JOB LOCATION** must ALWAYS be
published in Column 1 — **Latest Punjab Jobs** —
with `type: "punjab"` and `categorySlug: "punjab-jobs"`. They must never appear
in the All India & NVS / Central column, no matter how their source is
registered:

- **AIIMS Bathinda** (Bathinda is in Punjab): Faculty, Non-Faculty, SR/JR
  Resident, Project posts — every category.
- **Central University of Punjab (CUPB), Bathinda** — every notice, teaching,
  non-teaching and project/research posts alike. CUPB is a central university
  **located in Punjab**, exactly like AIIMS Bathinda: being "central" describes
  who funds it, not where the job is. Punjab applicants are the primary
  audience, so CUPB vacancies sit beside AIIMS Bathinda's in the Punjab column
  and their sources are registered as `type: "punjab"` /
  `categorySlug: "punjab-jobs"`. Matching is by full name, by the `CUPB`
  acronym and by the `cup.edu.in` domain — the acronym is matched on word
  boundaries so an unrelated word such as "cupboard" never triggers the rule.
- **Every Chandigarh organisation**, even when the body is a UT/central
  institute or the notification serves a wider region: PGIMER Chandigarh,
  Chandigarh Administration departments (incl. Social Welfare / chdsw), Punjab
  and Haryana High Court at Chandigarh, Railway Recruitment Board (RRB)
  Chandigarh, and any future organisation located in or administered from
  Chandigarh.
- **The rule is per notice, not only per organisation.** A notice from a
  national body that is itself specifically for Chandigarh / the Chandigarh UT
  region (e.g. a UCO Bank result list for Chandigarh UT) also publishes in the
  Punjab column, while the same body's all-India notices stay in the central
  column.
- **Every Punjab district.** A notice whose details name any of Punjab's 23
  districts as the job location is a Punjab-column notice, whatever the
  recruiting body, whoever funds it and however the source is registered — an
  ECHS polyclinic vacancy at Ferozepur or a Rail Coach Factory (Ministry of
  Railways) notice at Kapurthala is a Punjab vacancy. The districts: Amritsar,
  Barnala, Bathinda, Faridkot, Fatehgarh Sahib, Fazilka, Ferozepur, Gurdaspur,
  Hoshiarpur, Jalandhar, Kapurthala, Ludhiana, Malerkotla, Mansa, Moga,
  Pathankot, Patiala, Rupnagar, SAS Nagar (Mohali), Sangrur, Shahid Bhagat
  Singh Nagar (Nawanshahr), Sri Muktsar Sahib, Tarn Taran — with common
  spelling variants (Firozpur, Bhatinda, Ropar, Jullundur) also matched. All
  names are matched on word boundaries (in `PUNJAB_COLUMN_DISTRICTS` /
  `PUNJAB_COLUMN_DISTRICT_PATTERNS`) so a short district name such as "Moga"
  or "Mansa" never fires inside an unrelated word ("Mansarovar"). Every job
  detail is scanned — title, department, source name, `location`, `details`
  and the notice URLs — but only for a job-location mention (see the
  exam-centre exclusion below).
- **Punjab state name.** The state's own name counts exactly like a district:
  "Punjab Police", location "Punjab", "Government of Punjab" → Punjab column.
  Three banks are merely **named** Punjab but are headquartered outside the
  state — Punjab National Bank (New Delhi), Punjab & Sind Bank (New Delhi),
  Punjab & Maharashtra Bank (Mumbai) — their all-India notices stay in the
  central column (`PUNJAB_NAMED_BANKS`).
- **Never an examination centre.** A Punjab district, the state or Chandigarh
  that appears only as an **examination centre / exam city / test venue** does
  NOT put a notice in the Punjab column — the candidate sits the exam there,
  the job is not there. `strip_exam_centre_context()` blanks every sentence
  naming exam centres/cities/venues before matching ("Examination Centres:
  Delhi, Ludhiana, Chandigarh", "Exam City Intimation — Chandigarh",
  "Test centre: Patiala", "Venue: …", "choice of exam cities"). A notice moves
  only on a **job-location** mention — the employer's posting ("Post based at
  Ferozepur (Punjab)", "Office of the DC, Sangrur") — and it still moves when
  the same notice also lists exam centres elsewhere. The recruiting
  organisation's own identity (`department` / `sourceName`, e.g. RRB
  Chandigarh) is matched unmasked, so a Chandigarh organisation's exam-city
  notices still publish in the Punjab column. In the PDF-derived `details`
  free text a bare word "Punjab" does not count either — it is usually exam
  language or a participating-state list (e.g. IBPS "test versions offered for
  Punjab are English, Hindi and Punjabi") — only an explicit employer phrase
  ("Government of Punjab", "State of Punjab", "Punjab Government") does
  (`PUNJAB_STATE_EMPLOYER_PHRASES`).
- **Data side:** register sources for these organisations with `type: "punjab"`
  / `categorySlug: "punjab-jobs"` in `automation/sources.json`,
  `data/notification-source-links.json` and `automation/offline-forms.json`.
  Keep the `location` metadata truthful (e.g. `Bathinda, Punjab`,
  `Ferozepur, Punjab`, `Chandigarh`) — the column rule is about placement,
  not the address.
- **Never** put the `alsoInPunjab` cross-listing flag on these records: their
  home column is Punjab. The flag stays reserved for genuine all-India notices
  that Punjab candidates can also apply to.
- **Enforcement:** `enforce_punjab_column_rule()` in `scripts/update_jobs.py`
  re-classifies matching records into the Punjab column on every monitoring run
  (it self-heals anything that still reaches the store as `central`), and
  `tests/test_punjab_column_rule.py` fails CI if one of these notices is
  published outside the Punjab column.
- **Rationale:** Bathinda is in Punjab, Chandigarh is the region's shared
  capital, and a vacancy posted in a Punjab district serves Punjab applicants
  first — these notices belong in the Punjab column whatever body issues them.

**Keep the enforcement call wired.** `enforce_punjab_column_rule()` is invoked
from the store-refresh block in `main()` (right after
`normalize_stored_departments()`). It was once defined but never called, so R14
held only because the affected sources happened to be configured as `punjab` —
a notice arriving from a discovery feed would have landed in the Central column
silently. `tests/test_punjab_column_rule.py` guards that the call still exists.

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
