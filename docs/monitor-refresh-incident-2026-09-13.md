# Incident: monitor refresh corrupted live alerts and dropped the CUPB umbrella recruitment (2026-09-13)

**Status:** fixed — monitor guards added (R16), store restored, guard tests reconciled with the
expiry rule. Scheduled `Update job alerts` runs are green again from the commit that restores
this file.

## Symptoms

The scheduled `Update job alerts` workflow failed two consecutive runs (2026-09-12 and
2026-09-13) in the **Test alert parser** step, before the monitor was allowed to touch the data.

Two data-guard tests in `tests/test_update_jobs.py` (`NonNoticeDocumentGuardTests`) failed with
`KeyError: '7859300428388'` and `StopIteration: '208298934260796'` — the records they pin no
longer existed in `data/auto-jobs.json`.

## What actually happened (the 2026-09-12 13:16 UTC run)

The 13:16 UTC run succeeded and committed `data/auto-jobs.json`. The diff against the previous
healthy store (commit `2ee07e5`, 51 records) shows 49 records with exactly this damage:

1. **Dropped: CUPB umbrella recruitment `7859300428388`** — "Central University of Punjab
   (CUPB), Bathinda — Various Post (Contractual Non-Teaching Posts) Recruitment", a **live**
   recruitment with last date **15-09-2026** (after the incident date). This violated the
   "never delete a live vacancy" rule.
2. **Dropped: AIIMS Bathinda Faculty recruitment `208298934260796`** — *by design*: its extended
   last date was 31-08-2026, already past. The expiry rule removed it correctly.
3. **Corrupted: two AIIMS Bathinda (Non-Faculty) records** (`135942653393639`,
   `238706784518752`) — verified fields overwritten by page chrome during a refresh merge:
   title → `… — Non-Faculty` (the table's column heading), `vacancies` → `2024 Posts` (a table
   header), `advtNo` → `TICE` (a fragment of a page stamp), `feeMode` → `Online`,
   `applyLink` → `https://ors.gov.in/index.html` (a generic portal homepage).
4. Benign: `publishedAt` backfills for Chandigarh records (working as intended).

The two failing guard tests pinned records 1 and 2 with **hard presence checks** — a
contract mismatch: the monitor's own expiry rule (AGENTS.md "Active Recruitments") removes
recruitment/admission records once their last date passes, so a test that fails when a record is
legitimately pruned is a time bomb, not a guard. Record 2's expiry was the trigger for this
incident; the CUPB admission cards the other test pinned (last date 13-09-2026) were the same
bomb one day later.

## Root causes (all in `scripts/update_jobs.py`, pre-fix)

- `merge_job_details` overwrote `title`/`department` whenever the fresh value was "not a
  placeholder". A listing page's **column heading** ("Non-Faculty") is not a placeholder, so a
  per-post row re-read wiped the verified result title. Its contract ("a later official last
  date supersedes an earlier one") was also broken in code: an **earlier** date overwrote a
  later one whenever the record had not been extended.
- `backfill_extracted_fields` filled placeholders from the whole page blob:
  `infer_vacancies` read a table header ("2024 Posts"), `infer_advertisement_number` read a page
  stamp fragment ("TICE" — no digit, and `NOTICE` is not in the noise-word list because the
  stamp was cut mid-word).
- `is_generic_homepage` only recognised the bare root (`/`). A portal's `/index.html` is its
  root homepage wearing a file name; `ors.gov.in/index.html` slipped through as a valid
  `applyLink`.
- `_is_better_notice_link` treated *any* non-weak candidate as "better" than a weak stored link
  (the listing page). Combined with the previous item, the generic portal homepage was accepted
  as an improvement.
- **The CUPB drop.** CUPB's umbrella alert and its per-post alerts attach the **same PDF**.
  When the refresh re-read the non-teaching table, the per-post row's candidate matched several
  stored alerts by URL; `find_existing_job_for_candidate` fell back to the first same-source
  match — the **umbrella**. The merge re-titled the umbrella with the per-post row's wording;
  the retention pass then de-duplicates on (title, notice-URL), the pair collided, and the
  older umbrella record was dropped. The only two deletion paths in the monitor
  (`sanitize_published_jobs`, `retain_stored_jobs`) were both checked; the drop was this
  merge-then-dedupe sequence.

## Fix

**`scripts/update_jobs.py`** (see AGENTS.md R16 for the normative rule):

1. `is_generic_homepage` — `/index`, `/index.html`, `/index.php`, `/home` (+ `.htm`/`.php`
   variants) are generic homepages, not just the bare root (`GENERIC_HOME_PATHS`).
2. `_is_better_notice_link` — a weak stored link justifies **no** candidate: the replacement
   must be its own strong link (not the listing page, not a homepage, not an administrative
   document).
3. `merge_job_details` — refuses a title/department **downgrade** to a shorter page label
   (`_is_less_specific_title`); `advtNo` placeholders are only filled from values carrying a
   digit; `lastDate` moves **forward only** (the merge now honours its own contract).
4. `infer_vacancies` — a four-digit year (1900–2099) is a table header, never the vacancy
   count. `infer_advertisement_number` — a captured value without a digit is page chrome, never
   a number.
5. `find_existing_job_for_candidate` — among several stored alerts sharing a candidate URL, the
   alert whose stored title the candidate matches wins.
6. `refresh_published_source_jobs` — a candidate whose URL is shared by several stored alerts
   and matches **none** of their titles is skipped entirely: an ambiguous row is left alone,
   never merged into the wrong alert.

**`data/auto-jobs.json`** — restored from the pre-incident store (`2ee07e5`):

- The CUPB umbrella recruitment `7859300428388` re-inserted at its original position (live:
  last date 15-09-2026).
- The two corrupted AIIMS Bathinda records restored to their verified fields.
- AIIMS Faculty `208298934260796` **not** restored: its extended last date (31-08-2026) had
  passed, and the expiry rule removes it by design.
- Four AIIMS Bathinda result records that had been *published* with the
  `ors.gov.in/index.html` homepage as `applyLink` (before the `/index.html` guard existed) were
  cleaned to an honest empty apply link — the cards keep their verified notice PDF.

After the restore, every monitor store pass (`refresh_badges`, `normalize_stored_departments`,
`enforce_punjab_column_rule`, `reclassify_stored_jobs`, `apply_extensions`,
`strip_internal_job_fields`, `sanitize_published_jobs`, `retain_stored_jobs`) is a no-op on the
50-record store — no churn commit, no silent drop.

**`tests/test_update_jobs.py`**:

- The two guard tests now assert the **store-wide invariants** that matter (no CUPB card ever
  carries an administrative document or a generic-homepage link; no alert carries the RTI
  document) and pin the individual records' fields **while they are in the store** —
  consistent with the expiry rule instead of fighting it.
- Eight regression tests cover every guard added above (in `JobMonitorTests`).

## Lessons

- A test that pins generated data with a hard presence check must account for the monitor's
  *designed* removals (expiry). Pin the invariant, and the record while it exists.
- "Not a placeholder" is not the same as "a verified value". Anything a refresh is allowed to
  write over a stored value needs its own quality bar (specificity, digits, link strength).
- When several alerts legitimately share one notice URL (umbrella + per-post), URL alone is not
  identity. The refresh must match on the alert's own title and refuse ambiguous rows instead of
  guessing.
