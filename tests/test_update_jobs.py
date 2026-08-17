import importlib.util
import json
import tempfile
import unittest
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_jobs.py"
SPEC = importlib.util.spec_from_file_location("update_jobs", MODULE_PATH)
monitor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = monitor
SPEC.loader.exec_module(monitor)


class JobMonitorTests(unittest.TestCase):
    def test_html_parser_classifies_recruitment_and_result(self):
        markup = """
        <html><head><meta name="description" content="Official notices"></head><body>
          <a href="/files/advt-04.pdf"><span>NEW</span> Advertisement No. 04/2026 for recruitment of 450 Clerk posts</a>
          <a href="/files/result.pdf">Final result for Clerk recruitment</a>
          <a href="/recruitment">Recruitment</a>
        </body></html>
        """
        candidates, _ = monitor.parse_html(markup, "https://example.gov.in/notices")
        classified = [
            (candidate, monitor.classify_notice(candidate, {}))
            for candidate in candidates
            if monitor.looks_like_notice(candidate, {})
        ]
        self.assertEqual([notice_type for _, notice_type in classified], ["recruitment", "result"])
        self.assertEqual(classified[0][0].url, "https://example.gov.in/files/advt-04.pdf")

    def test_generic_click_here_link_uses_nearby_notice_text(self):
        markup = """
        <table><tr><td>12-08-2026</td><td>Advertisement No. 8/2026 for recruitment of 40 Patwari posts</td>
        <td><a href="/advt8.pdf">Click here</a></td></tr></table>
        """
        candidates, _ = monitor.parse_html(markup, "https://example.gov.in/jobs")
        matches = [candidate for candidate in candidates if monitor.looks_like_notice(candidate, {})]
        self.assertEqual(len(matches), 1)
        self.assertIn("Advertisement No. 8/2026", matches[0].title)

    def test_supported_notice_types_and_source_limits(self):
        examples = {
            "Online admission form for JNVST Class VI selection test": "admission",
            "Provisional answer key for Clerk written examination": "answer-key",
            "Merit list and final result for Junior Engineer posts": "result",
            "Corrigendum to Advertisement No. 4/2026 for recruitment of Clerks": "corrigendum",
            "Addendum regarding vacancies under Advt No. 7/2026": "corrigendum",
        }
        for title, expected in examples.items():
            with self.subTest(title=title):
                candidate = monitor.Candidate(title, "https://example.gov.in/notice.pdf")
                self.assertEqual(monitor.classify_notice(candidate, {}), expected)

        answer_key = monitor.Candidate(
            "Final answer key for Clerk recruitment", "https://example.gov.in/key.pdf"
        )
        recruitment_only = {"noticeTypes": ["recruitment", "corrigendum"]}
        self.assertIsNone(monitor.classify_notice(answer_key, recruitment_only))
        bare_update = monitor.Candidate(
            "Corrigendum dated 17 August 2026", "https://example.gov.in/corrigendum.pdf"
        )
        self.assertEqual(monitor.classify_notice(bare_update, recruitment_only), "corrigendum")

        old_result = {
            "alertType": "result",
            "badge": "NEW RESULT",
            "badgeColor": "bg-rose-600",
            "discoveredAt": "2026-01-01T00:00:00Z",
        }
        monitor.refresh_badges(
            [old_result], datetime(2026, 8, 17, tzinfo=timezone.utc), new_days=7
        )
        self.assertEqual(old_result["badge"], "RESULT")
        self.assertEqual(old_result["badgeColor"], "bg-rose-600")

    def test_additional_notification_links_become_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            registry = Path(folder) / "links.json"
            registry.write_text(json.dumps({
                "links": [
                    "https://example.gov.in/recruitment/",
                    {"url": "https://example.gov.in/recruitment/", "name": "Duplicate"},
                    {"url": "https://railway.gov.in/jobs", "name": "Railway Jobs", "type": "central"},
                ]
            }), encoding="utf-8")
            sources = monitor.additional_link_sources(registry)
            self.assertEqual(len(sources), 3)
            self.assertEqual(sources[0]["id"], sources[1]["id"])
            self.assertEqual(sources[2]["name"], "Railway Jobs")

    def test_feed_and_detail_inference(self):
        feed = """<?xml version="1.0"?>
        <rss version="2.0"><channel><item>
          <title>Recruitment of 125 Junior Engineer posts - Advertisement No. 7/2026</title>
          <link>https://example.gov.in/jobs/7</link>
          <description>Applications invited from Diploma holders. Age limit: 18 to 37 Years.
          Opening date 12 August 2026. Last date of online registration: 30 September 2026.</description>
          <pubDate>Wed, 12 Aug 2026 09:00:00 +0530</pubDate>
        </item></channel></rss>"""
        candidates = monitor.parse_feed(feed, "https://example.gov.in/feed")
        self.assertEqual(len(candidates), 1)
        source = {
            "name": "Example Board",
            "department": "Example Recruitment Board",
            "url": "https://example.gov.in/jobs",
            "type": "punjab",
            "categorySlug": "punjab-jobs",
            "location": "Punjab",
            "enrichDetails": False,
        }
        job = monitor.job_from_candidate(
            candidates[0], source, datetime(2026, 8, 17, tzinfo=timezone.utc)
        )
        self.assertEqual(job["vacancies"], "125 Posts")
        self.assertEqual(job["lastDate"], "30-09-2026")
        self.assertEqual(job["startDate"], "12-08-2026")
        self.assertEqual(job["advtNo"], "7/2026")
        self.assertEqual(job["age"], "18 to 37 Years")
        self.assertEqual(job["qualCategory"], "Diploma/ITI")
        self.assertEqual(job["alertType"], "recruitment")
        self.assertEqual(job["badge"], "NEW JOB ALERT")
        self.assertTrue(job["automated"])

    def test_first_run_bootstraps_then_only_adds_unseen_notice(self):
        old_page = b"""
        <a href='/a.pdf'>Advertisement No. 1/2026 for recruitment of 10 Clerk posts</a>
        <a href='/b.pdf'>Advertisement No. 2/2025 for recruitment of 20 Driver posts</a>
        """
        new_page = b"""
        <a href='/new.pdf'>Advertisement No. 2/2026 for recruitment of 30 Teacher posts</a>
        <a href='/a.pdf'>Advertisement No. 1/2026 for recruitment of 10 Clerk posts</a>
        <a href='/b.pdf'>Advertisement No. 2/2025 for recruitment of 20 Driver posts</a>
        """
        source = {
            "id": "example",
            "name": "Example",
            "department": "Example Board",
            "url": "https://example.gov.in/jobs",
            "type": "central",
            "categorySlug": "central",
            "enrichDetails": False,
            "bootstrapCount": 1,
            "maxNewPerRun": 5,
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / "sources.json"
            output = root / "auto-jobs.json"
            state = root / "seen.json"
            config.write_text(json.dumps({"sources": [source]}), encoding="utf-8")

            with patch.object(
                monitor,
                "fetch_url",
                return_value=monitor.Download("https://example.gov.in/jobs", "text/html", old_page),
            ):
                monitor.run(config, output, state)
            first = json.loads(output.read_text(encoding="utf-8"))
            first_state = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(len(first["jobs"]), 1)
            self.assertEqual(len(first_state["sources"]["example"]["fingerprints"]), 2)

            with patch.object(
                monitor,
                "fetch_url",
                return_value=monitor.Download("https://example.gov.in/jobs", "text/html", new_page),
            ):
                monitor.run(config, output, state)
            second = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(second["jobs"]), 2)
            self.assertTrue(any("Teacher" in job["title"] for job in second["jobs"]))


if __name__ == "__main__":
    unittest.main()
