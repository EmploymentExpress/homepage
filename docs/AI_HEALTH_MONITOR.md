# AI health monitor

`ai-health-monitor.yml` runs daily (and can be dispatched manually). It uses the updater's existing `sourceHealth` and `mirrorHealth` history in `data/seen-notices.json`; it does not crawl sites or publish job data. The engine is `scripts/ai_health_monitor.py`, uses only the Python standard library, and works without an LLM key.

The workflow runs the monitor's network-free tests, applies only deterministic repairs, publishes a Markdown summary, uploads a sanitized JSON/Markdown report, and commits only transport/enablement metadata changes in `automation/sources.json`, `automation/mirrors.json`, or `data/notification-source-links.json` when those files change. Registered source URLs are not changed.

## Deterministic repair rules

| Pattern | Requirement | Repair / recovery |
| --- | --- | --- |
| Broken certificate chain | At least 2 consecutive updater failures, with the latest error explicitly identifying certificate verification; source URL must be HTTPS; `sslFallback` must not already be explicitly set | Set `sslFallback: true` on that source only. This uses the updater's existing per-source unverified-TLS fallback, so it reduces transport security for that host. Explicit `sslFallback: false` is respected. Remove the flag once the official certificate chain is repaired. |
| Dead mirror | At least 25 consecutive mirror failures, with the last failure newer than the last success | Disable that mirror for 48 hours. Keep at least 2 configured mirrors active, then re-enable and probe it after cooldown. Another cooldown requires 25 new failures since that probe. The updater can use only the fixed template allowlist in `automation/mirrors.json`; health data cannot add a mirror host. |
| Dead official source | At least 5 consecutive updater failures, with the latest recorded error a **direct** HTTP 404/410. Errors from a mirror are excluded. | Temporarily set `enabled: false` and record an agent-owned 7-day quarantine. Re-enable for a scheduled probe afterwards. Another quarantine requires 5 new consecutive updater failures since re-enable, ending in a direct 404/410; a successful updater run clears the marker. Manually disabled sources are not changed. |

The monitor defaults to a dry run locally. `--apply` is required to write the three permitted configuration files. It never edits `data/seen-notices.json`, `data/auto-jobs.json`, the homepage, assets, scripts, or workflow files.

```bash
# Report proposed repairs without changing config
python3 scripts/ai_health_monitor.py --report-dir /tmp/ai-health-monitor

# Apply only the deterministic rules above
python3 scripts/ai_health_monitor.py --apply --report-dir /tmp/ai-health-monitor

# Run the monitor's tests (network-free)
python3 -m unittest discover -s tests -p 'test_ai_health_monitor.py' -v
```

## Optional LLM analysis

Novel/unclassified errors can be sent to Gemini for short diagnostic hypotheses and safe manual next steps. The model is **report-only**: its response is treated as untrusted, validated and sanitized, and can never make a code/config change or run a command. Deterministic rules remain the only repair path.

To enable it, create an optional Gemini API key and save it as the repository Actions secret `AI_HEALTH_LLM_API_KEY`. The default model is `gemini-2.5-flash-lite`; override it with the repository variable `AI_HEALTH_LLM_MODEL`. The model call is skipped when there are no novel failures or no secret. Provider free-tier availability, quota, and terms can change; no model call is needed for scheduled deterministic repairs.

Only the source ID, hostname, failure count, and a short redacted error are sent. URL query strings and fragments, bearer credentials, and common token/key fields are removed. The report includes the LLM status even when the provider is unavailable, without failing source monitoring.

## Workflow permissions and artifacts

The workflow needs `contents: write` to commit only its three config files. Repository Actions settings must allow the built-in workflow token to write to the triggering branch, and branch protection must allow or explicitly reject bot commits according to repository policy. Reports are uploaded as a 14-day workflow artifact and appended to the Actions run summary. Manual dispatch is available under **Actions → AI health monitor → Run workflow**.
