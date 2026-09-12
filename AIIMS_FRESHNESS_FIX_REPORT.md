# AIIMS Bathinda 2025 result shown as a new Punjab job — verification & fix

Reported: *"Check aiims bathinda post that was 2025 result, it is posted in punjab jobs as new job
mind that error."*

## What was found

The monitor publishes `type: "punjab"` / `categorySlug: "punjab-jobs"` alerts from four AIIMS
Bathinda sources (`Recruitment.aspx?type=1` Faculty, `?type=2` Non-Faculty, `?type=3` SR/JR,
`?type=4` Project Posts). Those tables **keep every attachment of every advertisement the institute
has published since 2021** — a row's date is the advertisement date, but its attachment list keeps
growing for years (a 29-Jul-2024 row already carries final-result notices dated 07-Sep-2026).

The monitor treated each unseen attachment link as a new notice and dated it with the scan time, so
history was published as news, roughly 8 links per source per run:

| Check | Result before the fix |
| --- | --- |
| AIIMS Bathinda records in `data/auto-jobs.json` | 164 of 202 |
| Dated 2021–2025 (historical) | 100 |
| `result` alerts (Results column) | 157 |
| `recruitment` + `corrigendum` alerts (job database → **Punjab jobs column**) | 6 + 1 |
| Document older than the 60-day window still in the store | 152 |

The record that matches the report:

```
id          212281947900405
title       All India Institute of Medical Sciences (AIIMS), Bathinda — Non-Faculty
notice      https://aiimsbathinda.edu.in/images/Reqruitment/20250826034810.pdf   (26 Aug 2025)
details     8) Eligibility Notification for the posts of Personal Assistant and Stenographer
alertType   recruitment        badge  NEW JOB ALERT      type  punjab / punjab-jobs
publishedAt (empty)            discoveredAt 2026-09-12T01:53:42Z
```

A 2025 **result-stage document** (an eligibility notification) was classified as `recruitment` —
the broad recruitment filler terms `"posts of"` / `"notification for"` matched its label — given an
empty `publishedAt`, badged `NEW JOB ALERT` and rendered in the Punjab jobs column as a new job.

## What was changed

1. **The notice's own date is used.** `document_date_from_url()` reads the date an official document
   carries in its file name (`.../Reqruitment/20250826034810.pdf` = 26 Aug 2025, `20241114045844.pdf`
   = 14 Nov 2024). That stamp, otherwise the listing row's date, becomes `publishedAt`, so the
   72-hour NEW badge, the 48-hour "Just In" tag and the breaking marquee follow the document's real
   date instead of the scan time.
2. **A freshness window exists.** `maxNoticeAgeDays` (default **60**, top-level in
   `automation/sources.json`, per-source override) + `is_archive_notice()` gate the publish path,
   the catch-up pass and `sanitize_published_jobs()`. Skipped archive links still keep their
   fingerprints, so they are never re-examined. An old advertisement whose verified deadline is
   still open keeps publishing, and an alert with no readable document date is never archive.
3. **A stage document is a result, never a vacancy.** `RESULT_TERMS` now carries the stage labels
   (`eligibility notification`, `eligibility notice`, alongside `final result`,
   `provisional result`, `shortlisted candidates`, …) ahead of the recruitment filler terms, so an
   eligibility/result notification can never land in the Punjab jobs column — even when it is
   recent. A row whose label really is an advertisement still classifies as recruitment.

## Cleanup and result

* `data/auto-jobs.json`: **202 → 50 records**; 152 archived AIIMS notices removed; the store now has
  0 records older than the window, 0 archived records and 0 stale NEW badges; no AIIMS record with
  `alertType` recruitment/corrigendum remains.
* 152 orphan `share/job-*.html` pages and their thumbnails deleted; a repository-wide scan finds no
  file still referencing a removed id; `sitemap.xml` and `llms.txt` regenerated.
* `AGENTS.md` gained mandatory rule **R15 — "Freshness window: a listing's history is never news"**.
* Guards: `ArchivedNoticeFreshnessTests` (6 tests) and the stage-label assertions in
  `JobMonitorTests.test_shortlisted_eligible_and_score_card_go_to_result_column`.
* Suite: 262 tests; the only failures are the four pre-existing ones unrelated to this change
  (balangir registry `type`, CUPB `alertType`, orphan id `208298934260796`, missing `PIL` in this
  sandbox).

Pull request: https://github.com/EmploymentExpress/homepage/pull/72
