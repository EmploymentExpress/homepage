"""Network-free tests for the AI health monitor and its repair boundaries."""
from __future__ import annotations

import json
import tempfile
from contextlib import redirect_stderr
from io import StringIO
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import ai_health_monitor as health
from scripts import update_jobs as updater


NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def stamp(value: datetime) -> str:
    return health.iso_timestamp(value)


def mirror_config() -> dict:
    return {
        "version": 1,
        "mirrors": [
            {"id": f"mirror-{index}", "template": template, "enabled": True}
            for index, template in enumerate(updater.DEFAULT_SOURCE_MIRRORS)
        ],
    }


def source_config(*sources: dict) -> dict:
    return {"version": 1, "sources": list(sources)}


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit=-1):
        return self.payload[:limit]


class AIHealthMonitorTests(unittest.TestCase):
    def test_classifies_deterministic_and_novel_failures(self):
        cases = {
            "<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed>": "ssl_certificate_error",
            "mirror fetch failed: HTTP Error 401: Unauthorized": "mirror_auth_or_access",
            "mirror fetch failed: <urlopen error CERTIFICATE_VERIFY_FAILED>": "mirror_tls_error",
            "HTTP Error 404: Not Found": "source_gone",
            "HTTP Error 503: Service Unavailable": "source_server_error",
            "official listing answered HTTP 200 with no notice links (direct and mirror)": "listing_empty_or_changed",
            "request timed out": "transient_network_error",
            "custom parser state drifted": "novel",
        }
        for error, expected in cases.items():
            with self.subTest(error=error):
                self.assertEqual(health.classify_source_failure({"lastError": error, "consecutiveFailures": 4}), expected)

    def test_ssl_fix_is_scoped_to_repeated_https_certificate_errors(self):
        source = {"id": "secure-board", "enabled": True, "url": "https://board.gov.in/jobs"}
        state = {"sourceHealth": {"secure-board": {
            "consecutiveFailures": 2,
            "lastFailureAt": stamp(NOW),
            "lastError": "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
        }}}
        sources, _, _, _, fixes, _ = health.analyze_health(source_config(source), mirror_config(), state, NOW)
        self.assertTrue(sources["sources"][0]["sslFallback"])
        self.assertEqual([fix["kind"] for fix in fixes], ["enable_scoped_ssl_fallback"])

        one_failure = {"sourceHealth": {"secure-board": dict(state["sourceHealth"]["secure-board"], consecutiveFailures=1)}}
        unchanged, _, _, _, fixes, _ = health.analyze_health(source_config(source), mirror_config(), one_failure, NOW)
        self.assertNotIn("sslFallback", unchanged["sources"][0])
        self.assertFalse(fixes)

    def test_ssl_fix_never_overrides_explicit_opt_out_or_http_source(self):
        error = {"consecutiveFailures": 4, "lastError": "certificate verify failed: unable to get local issuer certificate"}
        state = {"sourceHealth": {"opt-out": error, "plain-http": error}}
        sources, _, _, _, fixes, _ = health.analyze_health(
            source_config(
                {"id": "opt-out", "enabled": True, "url": "https://board.gov.in", "sslFallback": False},
                {"id": "plain-http", "enabled": True, "url": "http://board.gov.in"},
            ),
            mirror_config(), state, NOW,
        )
        self.assertFalse(sources["sources"][0]["sslFallback"])
        self.assertNotIn("sslFallback", sources["sources"][1])
        self.assertFalse(fixes)

    def test_direct_repeated_404_is_quarantined_but_mirror_404_is_not(self):
        state = {"sourceHealth": {
            "gone": {"consecutiveFailures": 5, "lastFailureAt": stamp(NOW), "lastError": "HTTP Error 404: Not Found"},
            "mirror-problem": {"consecutiveFailures": 20, "lastFailureAt": stamp(NOW), "lastError": "mirror fetch failed: HTTP Error 404: Not Found"},
            "not-yet": {"consecutiveFailures": 4, "lastFailureAt": stamp(NOW), "lastError": "HTTP Error 410: Gone"},
        }}
        sources, _, _, _, fixes, _ = health.analyze_health(
            source_config(
                {"id": "gone", "enabled": True, "url": "https://gone.gov.in/jobs"},
                {"id": "mirror-problem", "enabled": True, "url": "https://board.gov.in/jobs"},
                {"id": "not-yet", "enabled": True, "url": "https://board.gov.in/archive"},
            ),
            mirror_config(), state, NOW,
        )
        by_id = {item["id"]: item for item in sources["sources"]}
        self.assertFalse(by_id["gone"]["enabled"])
        self.assertEqual(by_id["gone"]["_aiHealth"]["phase"], "disabled")
        self.assertTrue(by_id["mirror-problem"]["enabled"])
        self.assertTrue(by_id["not-yet"]["enabled"])
        self.assertEqual([fix["target"] for fix in fixes], ["gone"])

    def test_quarantined_source_reenables_for_probe_without_reusing_stale_404(self):
        source = {
            "id": "gone", "enabled": False, "url": "https://gone.gov.in/jobs",
            "_aiHealth": {
                "managedBy": health.AGENT_MARKER, "phase": "disabled",
                "disabledAt": stamp(NOW - timedelta(days=8)),
                "disabledUntil": stamp(NOW - timedelta(days=1)),
            },
        }
        old_health = {"consecutiveFailures": 5, "lastFailureAt": stamp(NOW - timedelta(days=8)), "lastError": "HTTP Error 404: Not Found"}
        sources, _, _, _, fixes, _ = health.analyze_health(source_config(source), mirror_config(), {"sourceHealth": {"gone": old_health}}, NOW)
        reenabled = sources["sources"][0]
        self.assertTrue(reenabled["enabled"])
        self.assertEqual(reenabled["_aiHealth"]["phase"], "recheck")
        self.assertIn("recheck_dead_source", [fix["kind"] for fix in fixes])

        # The old failure counter is only a baseline. It needs five fresh
        # failures after re-enabling before a second quarantine is justified.
        old_since = reenabled["_aiHealth"]["recheckSince"]
        one_new_failure = dict(old_health, consecutiveFailures=6, lastFailureAt=stamp(NOW + timedelta(hours=1)))
        intermediate, _, _, _, intermediate_fixes, _ = health.analyze_health(
            source_config(reenabled), mirror_config(), {"sourceHealth": {"gone": one_new_failure}}, NOW + timedelta(hours=2)
        )
        self.assertTrue(intermediate["sources"][0]["enabled"])
        self.assertNotIn("quarantine_dead_source", [fix["kind"] for fix in intermediate_fixes])

        new_health = dict(old_health, consecutiveFailures=10, lastFailureAt=stamp(NOW + timedelta(hours=3)))
        next_sources, _, _, _, next_fixes, _ = health.analyze_health(
            source_config(reenabled), mirror_config(), {"sourceHealth": {"gone": new_health}}, NOW + timedelta(hours=2)
        )
        self.assertFalse(next_sources["sources"][0]["enabled"])
        self.assertIn("quarantine_dead_source", [fix["kind"] for fix in next_fixes])
        self.assertIsNotNone(old_since)

    def test_auto_registered_source_receives_scoped_ssl_fix_and_is_used_by_updater(self):
        link = {"url": "https://custom.gov.in/jobs?utm_source=monitor", "name": "Custom Board"}
        links = {"version": 1, "links": [link]}
        # Derive the exact ID using the updater from a temporary registry.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "links.json"
            path.write_text(json.dumps(links), encoding="utf-8")
            source_id = updater.additional_link_sources(path)[0]["id"]
        state = {"sourceHealth": {source_id: {
            "consecutiveFailures": 2, "lastError": "CERTIFICATE_VERIFY_FAILED: certificate verify failed",
        }}}
        _, _, planned_links, _, fixes, _ = health.analyze_health(
            source_config(), mirror_config(), state, NOW, links
        )
        self.assertTrue(planned_links["links"][0]["sslFallback"])
        self.assertIn("enable_scoped_ssl_fallback", [fix["kind"] for fix in fixes])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "links.json"
            path.write_text(json.dumps(planned_links), encoding="utf-8")
            generated = updater.additional_link_sources(path)[0]
        self.assertEqual(generated["id"], source_id)
        self.assertTrue(generated["sslFallback"])

    def test_auto_registered_dead_source_is_disabled_for_updater_and_rechecked(self):
        links = {"version": 1, "links": [{"url": "https://custom.gov.in/jobs", "name": "Custom Board"}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "links.json"
            path.write_text(json.dumps(links), encoding="utf-8")
            source_id = updater.additional_link_sources(path)[0]["id"]
        state = {"sourceHealth": {source_id: {
            "consecutiveFailures": 6, "lastFailureAt": stamp(NOW), "lastError": "HTTP Error 410: Gone",
        }}}
        _, _, planned_links, _, fixes, _ = health.analyze_health(
            source_config(), mirror_config(), state, NOW, links
        )
        configured = planned_links["links"][0]
        self.assertFalse(configured["enabled"])
        self.assertEqual(configured["_aiHealth"]["phase"], "disabled")
        self.assertIn("quarantine_dead_source", [fix["kind"] for fix in fixes])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "links.json"
            path.write_text(json.dumps(planned_links), encoding="utf-8")
            generated = updater.additional_link_sources(path)[0]
        self.assertFalse(generated["enabled"])
        self.assertIn("_aiHealth", generated)

    def test_successful_source_probe_clears_quarantine_metadata(self):
        source = {
            "id": "board", "enabled": True, "url": "https://board.gov.in/jobs",
            "_aiHealth": {"managedBy": health.AGENT_MARKER, "phase": "recheck", "recheckSince": stamp(NOW - timedelta(hours=1))},
        }
        state = {"sourceHealth": {"board": {"consecutiveFailures": 0, "lastSuccessAt": stamp(NOW)}}}
        sources, _, _, _, fixes, _ = health.analyze_health(source_config(source), mirror_config(), state, NOW)
        self.assertTrue(sources["sources"][0]["enabled"])
        self.assertNotIn("_aiHealth", sources["sources"][0])
        self.assertIn("source_recovered", [fix["kind"] for fix in fixes])

    def test_mirror_cooldown_removes_deadest_but_keeps_minimum_active_pool(self):
        mirrors = mirror_config()
        templates = updater.DEFAULT_SOURCE_MIRRORS
        state = {"mirrorHealth": {
            template: {
                "consecutiveFailures": 100 + index,
                "lastFailureAt": stamp(NOW),
                "lastSuccessAt": stamp(NOW - timedelta(days=1)),
            }
            for index, template in enumerate(templates[:4])
        }}
        _, planned, _, _, fixes, _ = health.analyze_health(source_config(), mirrors, state, NOW)
        # The health monitor no longer sets enabled=False; instead it marks
        # mirrors with _aiHealth.phase="disabled" and a disabledUntil date.
        def _in_cooldown(entry):
            meta = entry.get("_aiHealth", {})
            return meta.get("phase") == "disabled" and "disabledUntil" in meta

        cooling = [entry for entry in planned["mirrors"] if _in_cooldown(entry)]
        not_cooling = [entry for entry in planned["mirrors"] if not _in_cooldown(entry)]
        # Mirrors stay enabled=True even during cooldown; the runtime rotation
        # deprioritises them.  The monitor still tracks MIN_ACTIVE_MIRRORS via
        # _aiHealth metadata rather than the enabled flag.
        self.assertEqual(len(not_cooling), health.MIN_ACTIVE_MIRRORS)
        self.assertEqual(len(cooling), len(templates) - health.MIN_ACTIVE_MIRRORS)
        self.assertEqual(len([fix for fix in fixes if fix["kind"] == "cooldown_dead_mirror"]), len(cooling))
        self.assertIn(templates[3], [entry["template"] for entry in cooling])

    def test_mirror_requires_repeated_recent_failures(self):
        template = updater.DEFAULT_SOURCE_MIRRORS[0]
        state = {"mirrorHealth": {template: {
            "consecutiveFailures": health.MIRROR_FAILURE_THRESHOLD - 1,
            "lastFailureAt": stamp(NOW),
            "lastSuccessAt": stamp(NOW - timedelta(days=2)),
        }}}
        _, planned, _, _, fixes, _ = health.analyze_health(source_config(), mirror_config(), state, NOW)
        self.assertTrue(planned["mirrors"][0]["enabled"])
        self.assertFalse(fixes)

        state["mirrorHealth"][template]["consecutiveFailures"] = health.MIRROR_FAILURE_THRESHOLD
        state["mirrorHealth"][template]["lastSuccessAt"] = stamp(NOW + timedelta(hours=1))
        _, planned, _, _, fixes, _ = health.analyze_health(source_config(), mirror_config(), state, NOW)
        self.assertTrue(planned["mirrors"][0]["enabled"])
        self.assertFalse(fixes)

    def test_expired_mirror_cooldown_rechecks_instead_of_immediately_disabling(self):
        mirrors = mirror_config()
        entry = mirrors["mirrors"][0]
        entry.update({
            "enabled": False,
            "disabledUntil": stamp(NOW - timedelta(hours=1)),
            "_aiHealth": {
                "managedBy": health.AGENT_MARKER, "phase": "disabled",
                "disabledUntil": stamp(NOW - timedelta(hours=1)),
            },
        })
        stats = {"consecutiveFailures": 50, "lastFailureAt": stamp(NOW - timedelta(hours=2))}
        state = {"mirrorHealth": {entry["template"]: stats}}
        _, first, _, _, fixes, _ = health.analyze_health(source_config(), mirrors, state, NOW)
        self.assertTrue(first["mirrors"][0]["enabled"])
        self.assertEqual(first["mirrors"][0]["_aiHealth"]["phase"], "recheck")
        self.assertIn("recheck_mirror", [fix["kind"] for fix in fixes])

        _, second, _, _, second_fixes, _ = health.analyze_health(
            source_config(), first, state, NOW + timedelta(days=1)
        )
        self.assertTrue(second["mirrors"][0]["enabled"])
        self.assertNotIn("cooldown_dead_mirror", [fix["kind"] for fix in second_fixes])

        # A cooldown should require new failures since the probe baseline, not
        # just reuse the old failure counter that caused the first cooldown.
        fresh_failures = {"mirrorHealth": {entry["template"]: {
            "consecutiveFailures": 50 + health.MIRROR_FAILURE_THRESHOLD,
            "lastFailureAt": stamp(NOW + timedelta(days=2)),
        }}}
        _, third, _, _, third_fixes, _ = health.analyze_health(
            source_config(), second, fresh_failures, NOW + timedelta(days=3)
        )
        # The health monitor no longer sets enabled=False; cooldown is tracked
        # via _aiHealth.phase="disabled" and disabledUntil.
        third_meta = third["mirrors"][0].get("_aiHealth", {})
        self.assertEqual(third_meta.get("phase"), "disabled")
        self.assertIn("disabledUntil", third_meta)
        self.assertIn("cooldown_dead_mirror", [fix["kind"] for fix in third_fixes])

    def test_updater_consumes_mirror_cooldown_config(self):
        mirrors = mirror_config()
        mirrors["mirrors"][0]["enabled"] = False
        mirrors["mirrors"][0]["disabledUntil"] = stamp(NOW + timedelta(days=1))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mirrors.json"
            path.write_text(json.dumps(mirrors), encoding="utf-8")
            loaded = updater.load_source_mirrors(path, now=NOW)
            self.assertNotIn(updater.DEFAULT_SOURCE_MIRRORS[0], loaded)
            self.assertEqual(loaded, updater.DEFAULT_SOURCE_MIRRORS[1:])

    def test_llm_is_optional_and_filters_unknown_ids(self):
        self.assertEqual(health.request_gemini_analysis([], "secret")["status"], "skipped")
        self.assertEqual(health.request_gemini_analysis([{"source_id": "s"}], "")["status"], "skipped")
        result_payload = {
            "candidates": [{"content": {"parts": [{"text": json.dumps({"items": [
                {"source_id": "board", "likely_cause": "New anti-bot page", "safe_next_step": "Inspect the public listing", "confidence": 0.75},
                {"source_id": "unrelated", "likely_cause": "bad", "safe_next_step": "bad", "confidence": 1},
            ]})}]}}]
        }
        request_seen = {}

        def fake_urlopen(request, timeout):
            request_seen["request"] = request
            request_seen["timeout"] = timeout
            return FakeResponse(result_payload)

        with patch.object(health.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = health.request_gemini_analysis(
                [{"source_id": "board", "host": "board.gov.in", "failure_count": 3, "error": "parser shape changed"}],
                "fake-secret", model="gemini-test",
            )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["source_id"], "board")
        request = request_seen["request"]
        self.assertNotIn("fake-secret", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "fake-secret")
        self.assertEqual(request_seen["timeout"], 20)

    def test_llm_suggestions_are_report_only_even_when_apply_is_enabled(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sources_path = root / "sources.json"
            mirrors_path = root / "mirrors.json"
            state_path = root / "state.json"
            links_path = root / "links.json"
            report_dir = root / "report"
            sources_doc = source_config({"id": "board", "enabled": True, "url": "https://board.gov.in/jobs"})
            mirrors_doc = mirror_config()
            state = {"sourceHealth": {"board": {"consecutiveFailures": 2, "lastError": "unusual parser response 7f44"}}}
            original_sources = json.dumps(sources_doc, indent=2)
            sources_path.write_text(original_sources, encoding="utf-8")
            mirrors_path.write_text(json.dumps(mirrors_doc, indent=2), encoding="utf-8")
            state_path.write_text(json.dumps(state), encoding="utf-8")
            links_path.write_text(json.dumps({"version": 1, "links": []}), encoding="utf-8")
            suggestion = {"status": "complete", "model": "test", "items": [{
                "source_id": "board", "likely_cause": "Markup changed", "safe_next_step": "Review the page", "confidence": 0.6,
            }]}
            with patch.object(health, "request_gemini_analysis", return_value=suggestion):
                report = health.run_monitor(
                    state_path, sources_path, mirrors_path, report_dir, apply=True,
                    llm_api_key="not-used-by-mock", links_path=links_path, now=NOW,
                )
            self.assertEqual(report["llm"]["items"][0]["likely_cause"], "Markup changed")
            self.assertEqual(sources_path.read_text(encoding="utf-8"), original_sources)
            self.assertEqual(json.loads(state_path.read_text(encoding="utf-8")), state)
            self.assertTrue((report_dir / "report.md").exists())

    def test_dry_run_does_not_write_config_and_apply_never_changes_health_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sources_path, mirrors_path, state_path = root / "sources.json", root / "mirrors.json", root / "state.json"
            links_path = root / "links.json"
            report_dir = root / "report"
            sources_doc = source_config({"id": "board", "enabled": True, "url": "https://board.gov.in/jobs"})
            mirrors_doc = mirror_config()
            state = {"sourceHealth": {"board": {"consecutiveFailures": 2, "lastError": "CERTIFICATE_VERIFY_FAILED"}}}
            for path, payload in ((sources_path, sources_doc), (mirrors_path, mirrors_doc), (state_path, state)):
                path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            links_path.write_text(json.dumps({"version": 1, "links": []}, indent=2), encoding="utf-8")
            original_sources = sources_path.read_text(encoding="utf-8")
            original_mirrors = mirrors_path.read_text(encoding="utf-8")
            original_state = state_path.read_text(encoding="utf-8")

            dry = health.run_monitor(state_path, sources_path, mirrors_path, report_dir, links_path=links_path, now=NOW, enable_llm=False)
            self.assertEqual(dry["fixes"][0]["status"], "proposed")
            self.assertEqual(sources_path.read_text(encoding="utf-8"), original_sources)
            self.assertEqual(mirrors_path.read_text(encoding="utf-8"), original_mirrors)

            applied = health.run_monitor(state_path, sources_path, mirrors_path, report_dir, apply=True, links_path=links_path, now=NOW, enable_llm=False)
            self.assertEqual(applied["fixes"][0]["status"], "applied")
            self.assertTrue(json.loads(sources_path.read_text(encoding="utf-8"))["sources"][0]["sslFallback"])
            self.assertEqual(state_path.read_text(encoding="utf-8"), original_state)

    def test_reports_and_llm_input_redact_query_secrets_and_bearer_tokens(self):
        text = "https://board.gov.in/jobs?api_key=very-secret&token=another-secret Bearer abc.def"
        sanitized = health.sanitize_text(text)
        self.assertNotIn("very-secret", sanitized)
        self.assertNotIn("another-secret", sanitized)
        self.assertNotIn("abc.def", sanitized)
        self.assertIn("board.gov.in/jobs", sanitized)
        self.assertNotIn("<img", health._md("<img src=x onerror=alert(1)>").lower())

    def test_cli_refuses_redirected_inputs_or_outputs_when_applying(self):
        with tempfile.TemporaryDirectory() as folder:
            alternate = Path(folder) / "sources.json"
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                health.main(["--apply", "--sources", str(alternate), "--no-llm"])
        self.assertEqual(error.exception.code, 2)

    def test_workflow_is_scheduled_tests_monitor_and_limits_committed_files(self):
        workflow = (updater.ROOT / ".github" / "workflows" / "ai-health-monitor.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "43 2 * * *"', workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("test_ai_health_monitor.py", workflow)
        self.assertIn("python scripts/ai_health_monitor.py", workflow)
        self.assertIn("automation/sources.json", workflow)
        self.assertIn("automation/mirrors.json", workflow)
        self.assertIn("data/notification-source-links.json", workflow)
        self.assertNotIn("data/seen-notices.json", workflow)

    def test_current_mirror_registry_matches_updater_allowlist(self):
        config = json.loads((updater.ROOT / "automation" / "mirrors.json").read_text(encoding="utf-8"))
        templates = tuple(entry["template"] for entry in config["mirrors"] if entry.get("enabled", True))
        self.assertEqual(templates, updater.SOURCE_MIRRORS)
        self.assertEqual(set(templates), set(updater.DEFAULT_SOURCE_MIRRORS))


if __name__ == "__main__":
    unittest.main()
