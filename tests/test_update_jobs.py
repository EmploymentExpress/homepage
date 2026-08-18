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
    def test_layout_guard_restores_changes_and_removes_new_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "index.html").write_text("original layout", encoding="utf-8")
            (root / "assets" / "logo.png").write_bytes(b"original logo")
            snapshot = monitor.capture_protected_layout(root)

            (root / "index.html").write_text("changed by automation", encoding="utf-8")
            (root / "assets" / "new-layout.css").write_text("body {}", encoding="utf-8")
            self.assertNotEqual(monitor.capture_protected_layout(root), snapshot)

            monitor.restore_protected_layout(snapshot, root)
            self.assertEqual(monitor.capture_protected_layout(root), snapshot)
            self.assertEqual((root / "index.html").read_text(encoding="utf-8"), "original layout")
            self.assertFalse((root / "assets" / "new-layout.css").exists())

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

    def test_notice_table_row_becomes_one_alert_with_its_own_date(self):
        """AIIMS Bathinda style table: one row = one notice, many file links."""
        markup = """
        <table><thead><tr><th>#</th><th>Date</th><th>Title</th><th>Related Links</th></tr></thead>
        <tbody>
          <tr>
            <td>1</td><td>26-Dec-2025</td>
            <td>Recruitment of Tutor/ Clinical Instructor Posts on Direct Recruitment Basis at AIIMS Bathinda</td>
            <td>1) <a href="/images/Reqruitment/20251226050655.pdf">Advertisement</a>
                2) <a href="/images/Reqruitment/20251226050716.pdf">Application Form</a>
                3) <a href="https://forms.gle/qqxvTEvCN72yNk4m6">Google Form Link</a>
                4) <a href="https://www.onlinesbi.sbi/sbicollect/icollecthome.htm?corpID=2322756">Application Fee Link</a></td>
          </tr>
        </tbody></table>
        """
        source = {
            "id": "aiims-bathinda-non-faculty",
            "name": "AIIMS Bathinda (Non-Faculty)",
            "department": "All India Institute of Medical Sciences (AIIMS), Bathinda",
            "url": "https://aiimsbathinda.edu.in/Recruitment.aspx?type=2",
            "type": "central",
            "categorySlug": "central",
            "location": "Bathinda, Punjab",
            "enrichDetails": False,
            "excludeKeywords": ["google form", "application fee"],
        }
        candidates, _ = monitor.parse_html(
            markup, "https://aiimsbathinda.edu.in/Recruitment.aspx?type=2"
        )
        notices = [c for c in candidates if monitor.looks_like_notice(c, source)]
        # The row publishes once, under its descriptive title, not once per link.
        self.assertEqual(len(notices), 1)
        self.assertEqual(
            notices[0].title,
            "Recruitment of Tutor/ Clinical Instructor Posts on Direct Recruitment Basis at AIIMS Bathinda",
        )
        self.assertTrue(notices[0].url.endswith("20251226050655.pdf"))
        self.assertEqual(notices[0].notice_date, "26-12-2025")

        job = monitor.job_from_candidate(
            notices[0], source, datetime(2026, 8, 18, tzinfo=timezone.utc)
        )
        self.assertEqual(job["startDate"], "Published 26-12-2025")
        self.assertEqual(job["alertType"], "recruitment")
        self.assertEqual(job["sourceUrl"], "https://aiimsbathinda.edu.in/Recruitment.aspx?type=2")
        # Helper links (payment gateway, blank form) never become the notice link.
        self.assertNotIn("onlinesbi", job["pdfLink"])
        self.assertNotIn("forms.gle", job["pdfLink"])

    def test_configured_aiims_bathinda_sources_are_the_two_listing_pages(self):
        config = json.loads(
            (Path(__file__).resolve().parents[1] / "automation" / "sources.json").read_text(
                encoding="utf-8"
            )
        )
        bathinda = [
            source for source in config["sources"] if "aiimsbathinda.edu.in" in source["url"]
        ]
        self.assertEqual(
            sorted(source["url"] for source in bathinda),
            [
                "https://aiimsbathinda.edu.in/Recruitment.aspx?type=2",
                "https://aiimsbathinda.edu.in/Recruitment.aspx?type=4",
            ],
        )

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


    def test_discovery_matches_official_org_and_never_publishes_aggregator(self):
        headline = monitor.Candidate(
            "HSSC Clerk Recruitment 2026 – 450 posts last date",
            "https://haryanajobs.in/hssc-clerk-2026",
        )
        orgs = monitor.approved_official_organizations(
            [{"id": "psssb", "name": "PSSSB", "url": "https://sssb.punjab.gov.in/Advertisements.html"}]
        )
        matched = monitor.match_official_organization(headline.title, orgs)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["id"], "hssc")
        self.assertFalse(monitor.is_discovery_host(matched["url"]))

        unmatched = monitor.match_official_organization(
            "Private bank walk-in for sales executives", orgs
        )
        self.assertIsNone(unmatched)

        official = monitor.Candidate(
            "Advertisement for recruitment of 450 Clerk posts",
            "https://www.hssc.gov.in/files/clerk-2026.pdf",
        )
        matches = monitor.official_notices_for_headline(headline.title, [official])
        self.assertEqual(matches[0].url, official.url)

        source = {
            "name": "HSSC",
            "department": "Haryana Staff Selection Commission (HSSC)",
            "url": "https://www.hssc.gov.in/",
            "type": "central",
            "categorySlug": "central",
            "location": "Haryana",
            "enrichDetails": False,
        }
        job = monitor.job_from_candidate(
            official, source, datetime(2026, 8, 18, tzinfo=timezone.utc)
        )
        for field in ("pdfLink", "applyLink", "sourceUrl"):
            self.assertFalse(monitor.is_discovery_host(job[field]))
            self.assertNotIn("haryanajobs", job[field].lower())
            self.assertNotIn("rozgarnews", job[field].lower())
        self.assertNotIn("haryanajobs", job["title"].lower())
        self.assertNotIn("rozgarnews", job["details"].lower())

        with self.assertRaises(ValueError):
            monitor.job_from_candidate(
                headline,
                {"name": "HaryanaJobs", "url": "https://haryanajobs.in/", "enrichDetails": False},
                datetime(2026, 8, 18, tzinfo=timezone.utc),
            )

    def test_detect_extension_reads_only_explicit_extension_notices(self):
        extension_examples = {
            "The last date for online application has been extended up to 30 September 2026": "30-09-2026",
            "Corrigendum: last date of registration is extended till 30-09-2026": "30-09-2026",
            "The closing date stands extended up to 25.10.2026 for all candidates": "25-10-2026",
        }
        for text, expected_date in extension_examples.items():
            with self.subTest(text=text):
                is_extension, new_date = monitor.detect_extension(text)
                self.assertTrue(is_extension)
                self.assertEqual(new_date, expected_date)

        # An extension phrase with no readable date must not invent one.
        is_extension, new_date = monitor.detect_extension("Extension of last date")
        self.assertTrue(is_extension)
        self.assertEqual(new_date, "")

        # Non-extension corrigenda must not be flagged.
        for text in (
            "Corrigendum regarding revised vacancies and age relaxation",
            "Addendum regarding category-wise distribution of posts",
        ):
            with self.subTest(text=text):
                self.assertFalse(monitor.detect_extension(text)[0])

    def test_apply_extensions_marks_original_and_preserves_first_date(self):
        jobs = [
            {
                "id": 1,
                "title": "Recruitment of 450 Clerk posts",
                "department": "Example Board",
                "alertType": "recruitment",
                "advtNo": "4/2026",
                "lastDate": "20-09-2026",
                "pdfLink": "https://example.gov.in/advt-4.pdf",
            },
            {
                "id": 2,
                "title": "Corrigendum to Advertisement No. 4/2026 for recruitment of Clerks",
                "department": "Example Board",
                "alertType": "corrigendum",
                "advtNo": "4/2026",
                "lastDate": "See Notification",
                "isExtension": True,
                "extensionDate": "30-09-2026",
                "pdfLink": "https://example.gov.in/corr-4.pdf",
                "applyLink": "",
            },
            {
                "id": 3,
                "title": "Corrigendum regarding age relaxation",
                "department": "Example Board",
                "alertType": "corrigendum",
                "advtNo": "See Official Notice",
                "lastDate": "See Notification",
                "isExtension": False,
                "extensionDate": "",
            },
        ]
        self.assertTrue(monitor.apply_extensions(jobs))
        original = next(job for job in jobs if job["id"] == 1)
        self.assertTrue(original["lastDateExtended"])
        self.assertEqual(original["originalLastDate"], "20-09-2026")
        self.assertEqual(original["lastDate"], "30-09-2026")
        self.assertEqual(original["extendedLastDate"], "30-09-2026")
        self.assertEqual(original["extensionNoticeUrl"], "https://example.gov.in/corr-4.pdf")
        # Internal fields are stripped from every corrigendum.
        for job in jobs:
            self.assertNotIn("isExtension", job)
            self.assertNotIn("extensionDate", job)
        # Non-extension corrigendum leaves other jobs untouched.
        self.assertFalse(any(job.get("lastDateExtended") for job in jobs if job["id"] == 3))

    def test_apply_extensions_does_not_apply_without_readable_date(self):
        jobs = [
            {
                "id": 1,
                "title": "Recruitment of 40 Driver posts",
                "department": "Example Board",
                "alertType": "recruitment",
                "advtNo": "2/2026",
                "lastDate": "20-09-2026",
            },
            {
                "id": 2,
                "title": "Corrigendum to Advertisement No. 2/2026 for recruitment of Drivers",
                "department": "Example Board",
                "alertType": "corrigendum",
                "advtNo": "2/2026",
                "lastDate": "See Notification",
                "isExtension": True,
                "extensionDate": "",
            },
        ]
        self.assertFalse(monitor.apply_extensions(jobs))
        original = next(job for job in jobs if job["id"] == 1)
        self.assertNotIn("lastDateExtended", original)
        self.assertEqual(original["lastDate"], "20-09-2026")


    # ------------------------------------------------------------------
    # Offline application forms (onlineforms.in)
    # ------------------------------------------------------------------
    def test_offline_forms_registry_loads_and_masks_links(self):
        forms = monitor.load_offline_forms()
        self.assertGreater(len(forms), 0)
        for entry in forms:
            self.assertTrue(monitor.is_onlineforms_url(entry["url"]))
        link = monitor.offline_form_link(forms[0]["url"])
        self.assertTrue(link.startswith("redirect.html?f="))
        self.assertNotIn("onlineforms", link)
        self.assertTrue(link.endswith(monitor.redirect_token(forms[0]["url"])))

    def test_offline_form_title_match_finds_specific_form(self):
        forms = monitor.load_offline_forms()
        matched = monitor.match_offline_form(
            "Indian Air Force Agniveervayu Non-Combatant Recruitment 2026 - apply offline",
            "Indian Air Force",
            forms,
        )
        self.assertIsNotNone(matched)
        self.assertIn("air-force-non-combatant", matched["url"])

        unmatched = monitor.match_offline_form(
            "Recruitment of Software Engineers at a private firm", "Private Firm", forms
        )
        self.assertIsNone(unmatched)

    def test_offline_forms_processing_publishes_and_masks_links(self):
        forms = monitor.load_offline_forms()
        config = {
            "sources": [{
                "id": "onlineforms-offline-forms",
                "role": "offline-forms",
                "enabled": True,
                "name": "Offline Forms",
                "url": "https://onlineforms.in/latest-offline-forms/",
                "type": "central",
                "categorySlug": "central",
                "location": "All India",
                "timeout": 5,
            }]
        }
        now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
        jobs = []
        with tempfile.TemporaryDirectory() as folder:
            redirect_path = Path(folder) / "offline-redirects.json"
            with patch.object(monitor, "DEFAULT_OFFLINE_REDIRECTS", redirect_path), \
                 patch.object(monitor, "fetch_url", side_effect=RuntimeError("no network")):
                added, changed = monitor.process_offline_forms(config, jobs, {"sources": {}}, now)
            self.assertGreater(added, 0)
            self.assertTrue(changed)
            payload = json.loads(redirect_path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["redirects"]), len(forms))
            for job in jobs:
                self.assertEqual(job["applyMode"], "Offline")
                self.assertEqual(job["applyLabel"], "Download Offline Application Form")
                for field in ("offlineFormLink", "pdfLink", "applyLink"):
                    self.assertTrue(job[field].startswith("redirect.html?f="))
                    self.assertNotIn("onlineforms", job[field].lower())

    def test_offline_form_link_attached_to_existing_offline_job(self):
        forms = monitor.load_offline_forms()
        existing = {
            "id": 999,
            "title": "Air Force Non-Combatant Recruitment 2026 - apply offline",
            "department": "Indian Air Force",
            "applyMode": "Offline",
            "pdfLink": "https://example.gov.in/notice.pdf",
            "applyLink": "https://example.gov.in/apply",
        }
        config = {"sources": [{
            "id": "x", "role": "offline-forms", "enabled": True,
            "url": "https://onlineforms.in/latest-offline-forms/", "timeout": 5,
        }]}
        now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
        jobs = [dict(existing)]
        with tempfile.TemporaryDirectory() as folder:
            redirect_path = Path(folder) / "offline-redirects.json"
            with patch.object(monitor, "DEFAULT_OFFLINE_REDIRECTS", redirect_path), \
                 patch.object(monitor, "fetch_url", side_effect=RuntimeError("no network")):
                monitor.process_offline_forms(config, jobs, {"sources": {}}, now)
        target = next(job for job in jobs if job["id"] == 999)
        self.assertTrue(target["offlineFormLink"].startswith("redirect.html?f="))
        self.assertNotIn("onlineforms", target["offlineFormLink"])
        self.assertEqual(target["applyLabel"], "Download Offline Application Form")

    def test_offline_source_configured_in_sources_json(self):
        config = json.loads(
            (Path(__file__).resolve().parents[1] / "automation" / "sources.json").read_text(
                encoding="utf-8"
            )
        )
        offline = [source for source in config["sources"] if source.get("role") == "offline-forms"]
        self.assertEqual(len(offline), 1)
        self.assertTrue(offline[0]["enabled"])
        self.assertIn("onlineforms.in", offline[0]["url"])


if __name__ == "__main__":
    unittest.main()
