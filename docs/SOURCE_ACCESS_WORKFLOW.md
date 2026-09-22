# Recurring official-source access checks

## What runs automatically

Every scheduled or manually dispatched **Update job alerts** run now starts a separate **Read-only official source diagnostics** job. It calls `.github/workflows/source-access.yml` on the same branch/commit as the updater. The diagnostic runs alongside publishing, not as a prerequisite, so one blocked website does not prevent healthy sources from updating.

The reusable workflow also appears in Actions as **Check official source access (read-only)** and can be dispatched on its own. It has only `contents: read`, never commits/pushes, and checks out without persistent Git credentials. There is no pull-request trigger and no inherited repository secrets.

**Deployment:** these changes must be merged into the default branch for its future six-hourly schedule to use them. Saving this branch does not change a running/main-branch workflow.

## Check sequence

For each unique registered target:

1. **Direct GET**, with at most two attempts, verified TLS, 12-second socket timeouts and a 2 MiB response limit. Redirects must remain on the same hostname (the `www` variant is allowed); redirects to another authority/portal are reported for review, not silently trusted.
2. **Playwright Chromium**, for a failed request or a page without notice links. It uses a fresh unauthenticated context, runs JavaScript and waits briefly for rendering. It does not fill forms, submit POST requests, accept downloads, reuse user cookies, solve CAPTCHAs or attempt to evade access restrictions.
3. **Configured read-only mirrors**, only when the source has `proxyFallback: true`. Two transports are tried per run, rotating through the monitor's existing `SOURCE_MIRRORS` list across workflow runs. Mirrors retain the original official URL as the document base. A clean 404/410 does not trigger browser/mirror retries.
4. **Alternative official links**, at most two, copied from recruitment/career/vacancy/notice anchors actually found on the fetched page. Only the same official host is followed. The checker never guesses paths or promotes aggregator links. A working alternative is reported as `alternative-found`; it does not rewrite the registry automatically.

The checker reads enabled sources, approved organisation verification targets, user-added official links and configured discovery feeds, including IndGovtJobs RSS. It deduplicates URLs. Approved verification targets may be checked even if their separate direct-monitor switch is disabled: this diagnostic cannot publish notices.

Visible and raw-page-source notice candidates are examined using the existing parser. A PDF must have PDF magic bytes, not merely a `.pdf` URL or content type. Error pages, empty bodies, access challenges and pages with no supported notices never get a successful-notice verdict.

**Important:** `reachable-notices`, `reachable-feed` and `reachable-pdf` describe access, not a verified current vacancy. The diagnostic does not validate every PDF's dates or post counts. Discovery articles and mirror copies remain leads/transport evidence only. No browser/API observation is fed directly into `data/auto-jobs.json`. The existing publisher retains its official-verification and pending-retry rules; a human can use this diagnostic to repair a source or verify a missing notice safely.

## API inspection and artifacts

The browser observes GET/HEAD XHR/fetch responses on the official host or its subdomains. `api-requests.json` records URL parameter **names** with redacted values, method, status and resource type. It does **not** record request headers, cookies, API bodies, form submissions or authentication details, and does not replay discovered endpoints.

Each run uploads `source-access-<run-id>-<attempt>` for **7 days**, even if the diagnostic step fails, containing:

- `report.md` and `report.json`: source outcomes, transport attempts, errors, observed alternatives and progress/completion status;
- `run.log`: diagnostic console output;
- per-target sanitized `*.html.txt` snapshots (up to 512 KiB), when a page was received;
- `browser.png`: viewport screenshot where browser startup/navigation permits it;
- `api-requests.json`: bounded request metadata (up to 100 entries per browser visit).

HTML snapshots omit scripts and form values, redact token metadata and URL query values, and are saved as text rather than executable HTML. These are diagnostic snapshots, not exact archival source copies. Screenshots show public, unauthenticated pages; access to workflow artifacts should still be controlled appropriately. No user credentials should ever be entered into this browser.

Partial reports are written as sources complete. An interrupted run is marked partial; targets skipped by the time budget are `deferred`, not healthy. Source order rotates across runs to avoid permanently starving later targets.

External failures are summarized as warnings and unresolved report entries rather than causing publication of unverified jobs. Browser installation is best effort: direct/mirror checks still run if Chromium is unavailable, and the browser-stage error is recorded. Setup/test failures remain real workflow failures; no report is not an all-clear.

## Manual run

In GitHub:

1. Open **Actions → Check official source access (read-only)**.
2. Choose **Run workflow** and the branch containing this workflow.
3. Leave `source_ids` empty to check all registered targets, or enter e.g. `ssc,ibps,ntpc,indgovtjobs`.
4. Read the job summary and download the diagnostic artifact.

Unknown IDs fail clearly. This manual workflow never runs the publishing/commit steps. **Update job alerts** is a different workflow and retains its normal publishing behaviour.

Local equivalent:

```bash
python -m pip install -r automation/source-access-requirements.txt
python -m playwright install chromium
python scripts/check_source_access.py --source-ids ssc,ibps,ntpc,indgovtjobs
```

Use `--no-browser` to intentionally skip Chromium. By default, artifacts go into ignored `.cache/source-access/`; use `--output` for another separate diagnostic directory. Published-data and Git directories are rejected as output destinations. No job data, registries, production health counters or fingerprints are updated.

## India-based runner (requires administrator setup)

GitHub-hosted `ubuntu-latest` is the default. **GitHub Actions cannot guarantee India egress or create an Indian network simply by setting a country flag.**

To use an India-based network:

1. Provision an **ephemeral, isolated Linux runner hosted in India** and confirm its actual outbound IP/location. Do not use a personal machine or a server with production credentials/internal-service access.
2. Register it with the repository using labels `self-hosted`, `linux`, `x64`, `india`. Restrict runner access to trusted branches/workflows and keep its OS/browser updated. This workflow is not enabled for untrusted PRs.
3. Preinstall Chromium's OS libraries (administrator action; e.g. `python -m playwright install-deps chromium` in a prepared image), Python/setup-python prerequisites and outbound DNS/HTTPS access. The workflow will install the browser binary but does **not** run sudo on self-hosted machines.
4. Set repository **Settings → Secrets and variables → Actions → Variables**:

   `SOURCE_CHECK_RUNNER_LABELS = ["self-hosted","linux","x64","india"]`

5. Dispatch the read-only workflow and verify artifact results. This setting affects diagnostics only, not the existing publishing runner.

If no matching self-hosted runner is online, the job queues; GitHub does not silently fall back to another region. Remove the variable to return to `ubuntu-latest`.

The code rejects private/local URLs, embedded credentials, private DNS answers and unsafe browser methods. These checks are defence in depth, **not a substitute for network isolation/firewall rules on a self-hosted runner**. Browser pages may load public third-party resources. Never provide private credentials to this workflow or disable TLS verification to make a source appear healthy. Temporary browser/artifact directories are cleaned up at the end of the job; ephemeral runners should also be destroyed after use, including after hard cancellation.

## Limits and validation

Defaults live in `automation/source-access.json`: four workers, 15-minute scan budget, two direct attempts, two mirrors and two observed alternative links per source. The workflow has a 35-minute outer limit to allow setup and artifact upload; individual installation/scan steps are also bounded. Large PDFs or slowly rendering sites can remain unresolved and require manual verification.

Regression tests cover direct/browser/mirror order, retry limits, 404 behaviour, errors/CAPTCHA stubs, raw-page fallback, RSS leads, API redaction, observed-only alternatives, private URL/DNS/method blocking, no data writes, budget deferrals/rotation, partial reports and workflow permissions/artifacts.

During local validation the sandbox still closed outbound TLS connections, including Chromium's download endpoint. The four-source smoke run correctly reported all targets unresolved and left the homepage, data and registries byte-for-byte unchanged. Browser behaviour is covered by mocked tests; a real Chromium/network run on GitHub remains necessary after deployment. No successful live verification is claimed for blocked sources.
