# Discovery repair — 22 September 2026

## Changes

- Added IndGovtJobs as a discovery-only RSS source, with mirror fallback, an 80-headline limit and eight verification attempts per run. A first-run batch is explicitly enabled. The homepage returned navigation only; the RSS endpoint returned current entries, including “Indian Navy Sports Quota Recruitment 2026”. Neither article text nor aggregator PDFs may become published job data.
- Fixed filtering after the 40-link cutoff, lost transport settings, SpeedJob-style HTML article rows, and the premature consumption of failed/unmatched headlines.
- Added bounded fair retries and a one-time migration of legacy discovery fingerprints. Official fingerprints are not cleared. Expired/archive material is not republished during replay.
- Added explicit aliases/official-source registrations for NTPC, CPRI, BMHRC, Assam Rifles, Indian Army, ITBP, CSIR-NGRI and UIIC. Registrations are verification targets, not evidence that every source is reachable.
- Re-enabled direct SSC, UPSC and NVS scans with mirror fallback. Their external availability remains a blocker; no notices were fabricated to fill the gap.
- Added cookie/privacy/application-guide rejection to notification/apply selection and refresh. Advertisement-number suffixes such as `CRPD/SCO/2026-27/15 Posts` no longer become “15 Posts”.
- Added unresolved-lead diagnostics and an `if: always()` workflow summary step.
- Corrected three stored records and regenerated only their share pages/thumbnails. No homepage layout changes.

## Official verification for published corrections

### SBI — https://sbi.bank.in/web/careers/Current-openings

Read the official listing and its link list. For **CRPD/SCO/2026-27/15**, copied the “DOWNLOAD ADVERTISEMENT / English” and “APPLY ONLINE (Online Registration extended till 28.09.2026)” anchors. Read the linked advertisement's pages 1 and 3: Trade Finance Officer (IBG), original deadline 19 September, 14 JMGS-I plus 21 MMGS-II posts. Stored the listing as the extension evidence and preserved the original deadline. The published notification had incorrectly pointed to `CookiePolicy_v1.4.pdf`, and the apply button to `howtoapply.pdf`.

For **CRPD/SCO/2026-27/20**, copied “DOWNLOAD ADVERTISEMENT / English” and “APPLY ONLINE (16.09.2026 to 06.10.2026)”. Read pages 2 and 4 of the linked advertisement: Dean, Faculty and Marketing Executive, one post each (three total), with post-specific postgraduate qualifications/experience. Corrected the same notification/apply-link failure and the advertisement-number-as-vacancy-count error.

### DAV — https://davrecruit.davcmc.in/index.html

Read the homepage's “APPLY NOW” (`/CBT/`) and “CBT POSTS” (`/dav-posts.html`) anchors and the linked CBT-posts page. Replaced the informational “3 Phases Of DAV Recruitment Process” title/department and the how-to-apply link. The record explicitly warns that posts differ by school/zone. No vacancy count, deadline or detailed eligibility was invented.

### CSIR-NGRI — https://www.ngri.res.in/openings-at-ngri.php

Verified the listing exposes “Recruitment of Technician - 1/Group - II (1): Advertisement No.01/2026 Dated 05.09.2026”, with “English”, “Hindi” and “Online Application” anchors. Added the source/aliases for the monitor to verify and enrich; did not manually publish the discovery article's details.

## Remaining verification limits

- SSC and NVS requests failed during this check. NTPC returned 403; CPRI could not be fetched; ITBP returned an error; UIIC returned an empty body. IBPS also could not be read, so its reported RRB XV deadline extension remains unverified and was not copied from an aggregator.
- CPRI/NTPC/NGRI/UIIC targets were copied from the corresponding discovery articles' “Official Website” anchors; ITBP's portal was copied from the article's “CLICK HERE TO APPLY ONLINE” anchor. BMHRC, Assam Rifles and Indian Army targets already existed in the official-source registry. These are monitor registrations only; no article-provided advertisement link was published.
- Historical UIIC share-page data was not used to reconstruct a current job. Its conflicting deadline needs fresh official evidence.
- Code tests and live page reads do not establish that a scheduled GitHub runner can reach every external site. No full multi-source publishing run was executed locally. No production deployment is implied; changes remain on this session's branch until merged.

## Validation

`python -m unittest discover -s tests -v` (using the virtualenv with `automation/requirements.txt`). Regression coverage includes RSS ingestion, real feed-loader settings, navigation cutoff, HTML table rows, first-run bootstrap, legacy migration, retry/fairness/deduplication, unavailable/unmatched officials, failed enrichment, archive/expired suppression, aggregator rejection, bad documents, vacancy-count extraction and health-summary wiring. Existing layout guards remain unchanged.

## Retry requested by user — 22 September 2026

Repeated the external page reads and then ran a **read-only** probe through the actual `fetch_source_listing()` transport, with mirror fallback enabled. The probe did not run publication, alter fingerprints, or overwrite production source-health data.

- **IndGovtJobs RSS:** readable through the page-retrieval tool, with current article entries. The sandbox's Python transport (including mirrors) still failed with TLS/SSL EOF. Readability through the page tool does not prove runner connectivity.
- **BMHRC:** its configured `/content/Hindi/2532_1_Advertisement.aspx` page became readable through the page tool. It lists principal, senior-resident and faculty notices; no matching Group B/C notice was found there. Followed the actual “Vacancy” and “Apply Online” anchors: the vacancy page lists rolling medical/faculty notices, while `/content/4996_1_ApplyOnline.aspx` returns an ASP.NET “There is no row at position 0” error. No Group B/C job was published from these unrelated notices.
- **SSC, IBPS, CPRI, NVS, ITBP, Assam Rifles, Indian Army:** page reads still failed.
- **NTPC:** still returns a 403 Forbidden page.
- **UPSC:** still redirects to a homepage with no usable notice content in the retrieved response.
- **UIIC:** still returns an empty body.
- **Actual automation transport:** read-only checks for IndGovtJobs RSS, IBPS, SSC and BMHRC all ended in `mirror fetch failed: TLS/SSL connection has been closed (EOF)`. These local transport failures were not written into the scheduled runner's persistent health state.

No additional vacancy, deadline, or application-link changes were justified by this retry. A run on the GitHub Actions runner remains necessary to establish deployment-environment reachability after the branch changes are merged.
