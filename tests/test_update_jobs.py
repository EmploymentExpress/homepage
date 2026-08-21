import importlib.util
import json
import re
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

    def test_psssb_official_site_is_monitored(self):
        config = json.loads(
            (Path(__file__).resolve().parents[1] / "automation" / "sources.json").read_text(
                encoding="utf-8"
            )
        )
        psssb = [
            source for source in config["sources"] if "sssb.punjab.gov.in" in source["url"]
        ]
        self.assertTrue(psssb, "PSSSB must be configured as an automation source")
        home = [
            source
            for source in psssb
            if monitor.canonical_url(source["url"]) == "https://sssb.punjab.gov.in/"
        ]
        self.assertEqual(len(home), 1)
        self.assertTrue(home[0]["enabled"])
        self.assertEqual(
            home[0]["department"], "Punjab Subordinate Services Selection Board (PSSSB)"
        )
        self.assertFalse(monitor.is_discovery_host(home[0]["url"]))
        self.assertEqual(len({source["id"] for source in config["sources"]}), len(config["sources"]))

    def test_agents_rules_require_official_page_source_verification(self):
        raw = (Path(__file__).resolve().parents[1] / "AGENTS.md").read_text(encoding="utf-8")
        # Compare on a single line so re-wrapping the rule text cannot break the guard.
        agents = " ".join(raw.split())
        self.assertIn("Source-of-truth rule", agents)
        for phrase in (
            "and its page source",
            "copied verbatim from an anchor",
            "Never publish a URL you did not see in the official page source",
            "If the official site is unreachable",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, agents)
        # The same rule is repeated inline where the curated entries are edited.
        index = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")
        self.assertIn("SOURCE OF TRUTH", index)

    def test_curated_links_never_point_at_aggregator_hosts(self):
        """Every published link must come from an official source, never a job blog."""
        index = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")
        aggregator_hosts = monitor.DISCOVERY_HOSTS | {
            "freejobalert.com",
            "sarkariresult.com",
            "mysarkarinaukri.com",
            "dailyjobalert.in",
            "testbook.com",
            "adda247.com",
            "pw.live",
        }
        links = re.findall(
            r"(?:pdfLink|applyLink|extensionNoticeUrl|offlineFormLink): \"([^\"]+)\"", index
        )
        self.assertGreater(len(links), 10, "Curated entries should expose official links")
        for link in links:
            url = monitor.canonical_url(link)
            with self.subTest(link=link):
                self.assertTrue(url, "Published links must be usable http(s) URLs")
                self.assertNotIn(monitor.host_name(url), aggregator_hosts)
                self.assertFalse(monitor.is_discovery_host(url))

    def test_curated_psssb_reopen_entry_follows_title_and_link_rules(self):
        html = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")
        entry = re.search(
            r"\{\s*id: 16,.*?applyLabel: \"[^\"]*\"\s*\}", html, re.S
        )
        self.assertIsNotNone(entry, "Curated PSSSB Craft Instructor entry is missing")
        block = entry.group(0)

        def field(name):
            match = re.search(rf"{name}: \"((?:[^\"\\]|\\.)*)\"", block)
            self.assertIsNotNone(match, f"{name} missing from the curated entry")
            return match.group(1)

        title = field("title")
        department = field("department")
        # AGENTS.md naming rule: the visible title names the full recruiting
        # board and the actual post, so re-rendering it never rewrites it.
        self.assertEqual(monitor.official_job_title(title, department), title)
        self.assertFalse(monitor.is_junk_job_title(title))
        self.assertTrue(monitor.title_mentions_department(title, department))
        self.assertIn("Craft Instructor", title)
        self.assertRegex(title, r"(?i)re-?opened")
        # AGENTS.md link rule: never a generic root homepage.
        for name in ("pdfLink", "applyLink", "extensionNoticeUrl"):
            url = monitor.canonical_url(field(name))
            self.assertTrue(url, f"{name} must be a usable http(s) URL")
            self.assertNotIn(
                url, {"https://sssb.punjab.gov.in/", "http://sssb.punjab.gov.in/"}
            )
            self.assertFalse(monitor.is_discovery_host(url))

    def test_psssb_source_catches_reopened_application_notices(self):
        source = next(
            item
            for item in json.loads(
                (Path(__file__).resolve().parents[1] / "automation" / "sources.json").read_text(
                    encoding="utf-8"
                )
            )["sources"]
            if item["id"] == "psssb-home"
        )
        # A re-opening notice that also names the advertisement is a recruitment notice.
        advertisement_notice = monitor.Candidate(
            title="Public Notice regarding re-opening of online applications for Advertisement No. 03/2026",
            url="https://sssb.punjab.gov.in/uploads/public-notice-reopen-03-2026.pdf",
        )
        self.assertEqual(monitor.classify_notice(advertisement_notice, source), "recruitment")
        # Real headline copied from the board's live "What's New" list: it names no
        # recruitment term at all, so only the source keywords can catch it.
        window_notice = monitor.Candidate(
            title="Reopening of Advt 03 of 2026",
            url="https://sssb.punjab.gov.in/wp-content/uploads/2026/08/reopening-advt-03-2026.pdf",
        )
        self.assertEqual(monitor.classify_notice(window_notice, source), "corrigendum")

    def test_published_title_always_names_recruiting_department(self):
        self.assertEqual(
            monitor.official_job_title(
                "Application for Clerk",
                "Punjab State Legal Services Authority (PULSA)",
            ),
            "Punjab State Legal Services Authority (PULSA) — Clerk Recruitment",
        )
        self.assertEqual(
            monitor.official_job_title(
                "PSSSB Clerk, Typist & Data Entry Operator Recruitment 2026",
                "Punjab Subordinate Services Selection Board (PSSSB)",
            ),
            "Punjab Subordinate Services Selection Board (PSSSB) — Clerk, Typist & Data Entry Operator Recruitment 2026",
        )
        for junk in ("Other Links", "Close menu", "work Recruitments", "MDU Date Sheet"):
            with self.subTest(junk=junk):
                self.assertEqual(
                    monitor.official_job_title(junk, "Example Government Department"),
                    "",
                )

    def test_job_from_candidate_prefixes_official_department(self):
        candidate = monitor.Candidate(
            "Application for 40 Clerk posts",
            "https://example.gov.in/clerk-notice.pdf",
        )
        source = {
            "name": "Example Board",
            "department": "Example Government Recruitment Board",
            "url": "https://example.gov.in/recruitment",
            "type": "central",
            "enrichDetails": False,
        }
        job = monitor.job_from_candidate(
            candidate, source, datetime(2026, 8, 19, tzinfo=timezone.utc)
        )
        self.assertEqual(
            job["title"],
            "Example Government Recruitment Board — 40 Clerk posts Recruitment",
        )
        self.assertEqual(job["department"], "Example Government Recruitment Board")

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
    # Offline application forms (offline-form portals)
    # ------------------------------------------------------------------
    def test_offline_forms_registry_loads_and_masks_links(self):
        forms = monitor.load_offline_forms()
        self.assertGreater(len(forms), 0)
        for entry in forms:
            self.assertTrue(monitor.is_offline_form_url(entry["url"]))
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

    def test_offline_page_documents_extracts_form_and_notification_pdfs(self):
        page = monitor.Download(
            "https://onlineforms.in/indian-army-cdm-recruitment/",
            "text/html",
            b"""
            <html><body>
              <h1>Indian Army CDM Recruitment 2026 Apply for Driver, Cook, MTS &amp; Steno</h1>
              <a href="https://onlineforms.in/ids-jaipur-recruitment/">IDS Jaipur Recruitment</a>
              <table>
                <tr><td>College of Defence Management Official Notice &amp; Link</td></tr>
                <tr><td>Download Application Form</td>
                    <td><a href="https://onlineforms.in/wp-content/uploads/2023/08/OnlineForms.in-College-of-Defence-Management-Application-Form-21082023.pdf">Download</a></td></tr>
                <tr><td>Best Books for Exam Preparation</td>
                    <td><a href="https://amzn.to/4vxBB7U">Recommended Books</a></td></tr>
                <tr><td>Official Notification</td>
                    <td><a href="https://onlineforms.in/wp-content/uploads/2023/09/College-of-Defence-Management-Notification-May-2026_compressed.pdf">Notification</a></td></tr>
                <tr><td>Official Website</td><td><a href="https://indianarmy.nic.in/">Click Here</a></td></tr>
                <tr><td>Govt. Job Updates on Telegram App</td>
                    <td><a href="https://telegram.me/online_forms/">Join Channel</a></td></tr>
              </table>
              <a href="https://onlineforms.in/sainik-school-jhansi-recruitment/">Sainik School Jhansi Recruitment 2026 Apply Link</a>
            </body></html>
            """,
        )
        documents = monitor.offline_page_documents(page.url, page)
        self.assertIn("OnlineForms.in-College-of-Defence-Management-Application-Form", documents["form"])
        self.assertIn("College-of-Defence-Management-Notification", documents["notification"])
        self.assertTrue(monitor.is_pdf_url(documents["form"]))
        self.assertTrue(monitor.is_pdf_url(documents["notification"]))

    def test_offline_page_documents_extracts_department_and_application_dates(self):
        page = monitor.Download(
            "https://onlineforms.in/example-board-recruitment/",
            "text/html",
            b"""
            <html><head><title>Example Board Clerk Recruitment 2026</title></head><body>
              <p>Example Government Recruitment Board invites applications to fill Clerk vacancies.</p>
              <table>
                <tr><td>Department/ Organization</td><td>Example Government Recruitment Board</td></tr>
                <tr><td>Advertisement No.</td><td>04/2026</td></tr>
                <tr><td>Application Form Begin</td><td>12 August 2026</td></tr>
                <tr><td>Application Form Submission Last Date</td><td>30 September 2026</td></tr>
              </table>
            </body></html>
            """,
        )
        documents = monitor.offline_page_documents(page.url, page)
        self.assertEqual(documents["department"], "Example Government Recruitment Board")
        self.assertEqual(documents["startDate"], "12-08-2026")
        self.assertEqual(documents["lastDate"], "30-09-2026")

    def test_offline_page_documents_prefers_official_website_notification(self):
        page = monitor.Download(
            "https://onlineforms.in/defence-services-staff-college-recruitment/",
            "text/html",
            b"""
            <html><body>
              <table>
                <tr><td>DSSC Wellington Official Notice &amp; Link</td></tr>
                <tr><td>Download Application Form</td>
                    <td><a href="https://drive.google.com/file/d/1JWX1It9WZ6LsTHj7V9eH-wqrNWUnGaCI/view">Download</a></td></tr>
                <tr><td>Official Notification</td>
                    <td><a href="https://ids.nic.in/KnowledgeBankDetails?type=Direct%20Recruitment">Notification</a></td></tr>
                <tr><td>Official Website</td><td><a href="https://ids.nic.in/">Click Here</a></td></tr>
              </table>
            </body></html>
            """,
        )
        documents = monitor.offline_page_documents(page.url, page)
        self.assertEqual(documents["form"], "https://drive.google.com/file/d/1JWX1It9WZ6LsTHj7V9eH-wqrNWUnGaCI/view")
        self.assertEqual(documents["notification"], "https://ids.nic.in/KnowledgeBankDetails?type=Direct+Recruitment")

    def test_offline_job_from_entry_uses_direct_pdf_links(self):
        entry = {
            "title": "Indian Army CDM Recruitment 2026 Offline Application Form",
            "url": "https://onlineforms.in/indian-army-cdm-recruitment/",
            "department": "College of Defence Management (CDM)",
            "type": "central",
            "categorySlug": "central",
            "location": "All India",
        }
        documents = {
            "form": "https://onlineforms.in/wp-content/uploads/2023/08/OnlineForms.in-College-of-Defence-Management-Application-Form-21082023.pdf",
            "notification": "https://onlineforms.in/wp-content/uploads/2023/09/College-of-Defence-Management-Notification-May-2026_compressed.pdf",
        }
        redirect: dict[str, str] = {}
        now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
        job = monitor.offline_job_from_entry(entry, now, redirect, documents)
        form_token = monitor.redirect_token(documents["form"])
        notification_token = monitor.redirect_token(documents["notification"])
        self.assertEqual(job["offlineFormLink"], f"redirect.html?f={form_token}")
        self.assertEqual(job["applyLink"], f"redirect.html?f={form_token}")
        self.assertEqual(job["pdfLink"], f"redirect.html?f={notification_token}")
        self.assertEqual(redirect[form_token], documents["form"])
        self.assertEqual(redirect[notification_token], documents["notification"])
        for field in ("offlineFormLink", "applyLink", "pdfLink"):
            self.assertNotIn("onlineforms", job[field].lower())

    def test_offline_forms_processing_upgrades_published_alerts_to_pdfs(self):
        article = "https://onlineforms.in/indian-army-cdm-recruitment/"
        form_pdf = "https://onlineforms.in/wp-content/uploads/2023/08/OnlineForms.in-College-of-Defence-Management-Application-Form-21082023.pdf"
        notification_pdf = "https://onlineforms.in/wp-content/uploads/2023/09/College-of-Defence-Management-Notification-May-2026_compressed.pdf"
        article_token = monitor.redirect_token(article)
        page_html = f"""
            <html><body>
              <table>
                <tr><td>Download Application Form</td><td><a href="{form_pdf}">Download</a></td></tr>
                <tr><td>Official Notification</td><td><a href="{notification_pdf}">Notification</a></td></tr>
              </table>
            </body></html>
        """
        jobs = [{
            "id": 123,
            "title": "Indian Army CDM Recruitment 2026 Apply for Driver, Cook, MTS & Steno",
            "department": "Official Offline Recruitment Notices",
            "applyMode": "Offline",
            "applyLabel": "Download Offline Application Form",
            "offlineFormLink": f"redirect.html?f={article_token}",
            "applyLink": f"redirect.html?f={article_token}",
            "pdfLink": f"redirect.html?f={article_token}",
            "sourceUrl": article,
        }]
        config = {"sources": [{
            "id": "x", "role": "offline-forms", "enabled": True,
            "url": "https://onlineforms.in/latest-offline-forms/", "timeout": 5,
        }]}

        def fake_fetch(url, timeout=25, retries=2):
            if url == article:
                return monitor.Download(article, "text/html", page_html.encode("utf-8"))
            raise RuntimeError("no network")

        now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
        state: dict[str, object] = {"sources": {}}
        with tempfile.TemporaryDirectory() as folder:
            redirect_path = Path(folder) / "offline-redirects.json"
            redirect_path.write_text(json.dumps({
                "version": 1,
                "redirects": {article_token: article},
            }), encoding="utf-8")
            with patch.object(monitor, "DEFAULT_OFFLINE_REDIRECTS", redirect_path), \
                 patch.object(monitor, "fetch_url", side_effect=fake_fetch):
                monitor.process_offline_forms(config, jobs, state, now)
            payload = json.loads(redirect_path.read_text(encoding="utf-8"))
            redirects = payload["redirects"]
            target = jobs[0]
            form_token = monitor.redirect_token(form_pdf)
            notification_token = monitor.redirect_token(notification_pdf)
            self.assertEqual(target["offlineFormLink"], f"redirect.html?f={form_token}")
            self.assertEqual(target["applyLink"], f"redirect.html?f={form_token}")
            self.assertEqual(target["pdfLink"], f"redirect.html?f={notification_token}")
            self.assertEqual(redirects[form_token], form_pdf)
            self.assertEqual(redirects[notification_token], notification_pdf)
            self.assertEqual(state["offlinePageDocuments"][article], {
                "form": form_pdf,
                "notification": notification_pdf,
                "website": "",
                "applyMode": "",
                "department": "",
                "startDate": "",
                "lastDate": "",
                "pageTitle": "",
            })

    def test_offline_listing_junk_titles_are_filtered_and_purged(self):
        config = {"sources": [{
            "id": "x", "role": "offline-forms", "enabled": True,
            "url": "https://onlineforms.in/latest-offline-forms/", "timeout": 5,
        }]}
        listing = monitor.Download(
            "https://onlineforms.in/latest-offline-forms/",
            "text/html",
            b"""
            <html><body>
              <a href="https://onlineforms.in/indian-army-cdm-recruitment/">Indian Army CDM Recruitment 2026 Apply for Driver, Cook, MTS &amp; Steno</a>
              <a href="https://onlineforms.in/">Skip to content</a>
              <a href="https://onlineforms.in/latest-online-forms/">Online Form</a>
              <a href="https://onlineforms.in/latest-admit-card/">Admit Card</a>
              <a href="https://onlineforms.in/latest-answer-key/">Answer Key</a>
              <a href="https://onlineforms.in/admission/">Admission</a>
            </body></html>
            """,
        )
        with patch.object(monitor, "fetch_url", return_value=listing):
            pool = monitor.gather_offline_forms_pool(config)
        pool_urls = {entry["url"] for entry in pool}
        pool_titles = {entry["title"].lower() for entry in pool}
        self.assertIn("https://onlineforms.in/indian-army-cdm-recruitment/", pool_urls)
        for junk in ("Skip to content", "Online Form", "Admit Card", "Answer Key", "Admission"):
            self.assertNotIn(junk.lower(), pool_titles)

        now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
        jobs = [
            {"id": 1, "title": "Skip to content", "applyMode": "Offline", "offlineFormLink": "redirect.html?f=000000000000"},
            {"id": 2, "title": "Admit Card", "applyMode": "Offline", "offlineFormLink": "redirect.html?f=000000000001"},
            {"id": 3, "title": "Indian Army CDM Recruitment 2026 Apply for Driver, Cook, MTS & Steno", "applyMode": "Offline", "offlineFormLink": "redirect.html?f=000000000002", "sourceUrl": "https://onlineforms.in/indian-army-cdm-recruitment/"},
        ]
        with tempfile.TemporaryDirectory() as folder:
            redirect_path = Path(folder) / "offline-redirects.json"
            with patch.object(monitor, "DEFAULT_OFFLINE_REDIRECTS", redirect_path), \
                 patch.object(monitor, "fetch_url", side_effect=RuntimeError("no network")):
                monitor.process_offline_forms(config, jobs, {"sources": {}}, now)
        remaining_ids = [job["id"] for job in jobs]
        self.assertNotIn(1, remaining_ids)  # "Skip to content" purged
        self.assertNotIn(2, remaining_ids)  # "Admit Card" purged
        self.assertIn(3, remaining_ids)  # real vacancy kept (registry alerts may also be added)

    def test_offline_page_documents_detects_apply_mode(self):
        offline_page = monitor.Download(
            "https://onlineforms.in/some-offline-job/",
            "text/html",
            b"<html><body><p>The candidates who want to get this opportunity can apply through offline mode.</p></body></html>",
        )
        online_page = monitor.Download(
            "https://onlineforms.in/some-online-job/",
            "text/html",
            b"<html><body><p>The candidates who want to get this opportunity can apply through online mode.</p></body></html>",
        )
        dual_page = monitor.Download(
            "https://onlineforms.in/some-dual-job/",
            "text/html",
            b"<html><body><p>Candidates can apply through online mode or offline mode.</p></body></html>",
        )
        unknown_page = monitor.Download(
            "https://onlineforms.in/some-job/",
            "text/html",
            b"<html><body><p>Applications are invited for the posts.</p></body></html>",
        )
        self.assertEqual(
            monitor.offline_page_documents(offline_page.url, offline_page)["applyMode"],
            "offline",
        )
        self.assertEqual(
            monitor.offline_page_documents(online_page.url, online_page)["applyMode"],
            "online",
        )
        self.assertEqual(
            monitor.offline_page_documents(dual_page.url, dual_page)["applyMode"],
            "offline",
        )
        self.assertEqual(
            monitor.offline_page_documents(unknown_page.url, unknown_page)["applyMode"],
            "",
        )

    def test_offline_page_documents_extracts_official_website_link(self):
        page = monitor.Download(
            "https://onlineforms.in/some-offline-job/",
            "text/html",
            b"""
            <html><body>
              <p>can apply through offline mode.</p>
              <table>
                <tr><td>Official Notification</td><td><a href="https://onlineforms.in/notice.pdf">Notification</a></td></tr>
                <tr><td>Official Website</td><td><a href="https://indianarmy.nic.in/">Click Here</a></td></tr>
              </table>
            </body></html>
            """,
        )
        documents = monitor.offline_page_documents(page.url, page)
        self.assertEqual(documents["website"], "https://indianarmy.nic.in/")
        self.assertEqual(documents["applyMode"], "offline")

    def test_offline_pool_uses_portal_listing_title_for_registry_entry(self):
        config = {"sources": [{
            "id": "x", "role": "offline-forms", "enabled": True,
            "url": "https://onlineforms.in/latest-offline-forms/", "timeout": 5,
            "department": "Official Offline Recruitment Notices",
            "type": "central", "categorySlug": "central", "location": "All India",
        }]}
        listing = monitor.Download(
            "https://onlineforms.in/latest-offline-forms/",
            "text/html",
            b'<html><body><a href="https://onlineforms.in/air-force-non-combatant-recruitment/">Air Force Non-Combatant Recruitment 2026 Offline Form</a></body></html>',
        )
        with patch.object(monitor, "fetch_url", return_value=listing):
            pool = monitor.gather_offline_forms_pool(config)
        entry = next(
            entry for entry in pool
            if entry["url"] == "https://onlineforms.in/air-force-non-combatant-recruitment/"
        )
        self.assertEqual(entry["title"], "Air Force Non-Combatant Recruitment 2026 Offline Form")
        self.assertEqual(entry["department"], "Indian Air Force (IAF)")

    def test_offline_listing_title_strips_branding_and_trailing_last_date(self):
        self.assertEqual(
            monitor._offline_listing_title(
                "Army ASC Centre South MTS, Cook, Cleaner, Fireman, Tradesman & Various Post 04.09.2026"
            ),
            "Army ASC Centre South MTS, Cook, Cleaner, Fireman, Tradesman & Various Post",
        )
        self.assertEqual(
            monitor._offline_listing_title("UPSC EPFO APFC Last Date : 11.09.2026"),
            "UPSC EPFO APFC",
        )
        self.assertEqual(
            monitor._offline_listing_title(
                "www.onlineforms.in Haryana Anganwadi Recruitment 2026"
            ),
            "Haryana Anganwadi Recruitment 2026",
        )

    def test_speedjob_urls_are_treated_as_offline_form_portal(self):
        self.assertTrue(
            monitor.is_offline_form_url(
                "https://www.speedjob.in/army-asc-centre-south-recruitment-2026/"
            )
        )
        self.assertTrue(monitor.is_offline_form_url("https://speedjob.in/latest-job/"))
        self.assertFalse(monitor.is_offline_form_url("https://indianarmy.nic.in/"))

    def test_offline_form_portal_urls_are_masked_behind_redirect_tokens(self):
        redirect: dict[str, str] = {}
        target = (
            "https://www.speedjob.in/wp-content/uploads/2026/08/"
            "ASC-Centre-South-Group-C-Recruitment-Application-Form-226.pdf"
        )
        masked = monitor.mask_offline_url(target, redirect)
        self.assertTrue(masked.startswith("redirect.html?f="))
        token = masked.split("=", 1)[1]
        self.assertEqual(redirect[token], target)

    def test_offline_forms_processing_skips_online_apply_vacancies(self):
        config = {"sources": [{
            "id": "x", "role": "offline-forms", "enabled": True,
            "url": "https://onlineforms.in/latest-offline-forms/", "timeout": 5,
        }]}
        listing = monitor.Download(
            "https://onlineforms.in/latest-offline-forms/",
            "text/html",
            b"""
            <html><body>
              <a href="https://onlineforms.in/some-offline-job-recruitment/">Some Offline Job Recruitment 2026 Apply Offline 30.09.2026</a>
              <a href="https://onlineforms.in/some-online-job-recruitment/">Some Online Job Recruitment 2026 Apply Online 30.09.2026</a>
            </body></html>
            """,
        )
        offline_article = monitor.Download(
            "https://onlineforms.in/some-offline-job-recruitment/",
            "text/html",
            b"<html><body><p>can apply through offline mode.</p></body></html>",
        )
        online_article = monitor.Download(
            "https://onlineforms.in/some-online-job-recruitment/",
            "text/html",
            b"<html><body><p>can apply through online mode.</p></body></html>",
        )

        def fake_fetch(url, timeout=25, retries=2):
            if url == "https://onlineforms.in/latest-offline-forms/":
                return listing
            if url == "https://onlineforms.in/some-offline-job-recruitment/":
                return offline_article
            if url == "https://onlineforms.in/some-online-job-recruitment/":
                return online_article
            raise RuntimeError("no network")

        jobs: list[dict[str, object]] = []
        now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            redirect_path = Path(folder) / "offline-redirects.json"
            with patch.object(monitor, "DEFAULT_OFFLINE_REDIRECTS", redirect_path), \
                 patch.object(monitor, "fetch_url", side_effect=fake_fetch):
                monitor.process_offline_forms(config, jobs, {"sources": {}}, now)
        titles = [job["title"] for job in jobs]
        self.assertIn("Some Offline Job Recruitment 2026 Apply Offline", titles)
        self.assertNotIn("Some Online Job Recruitment 2026 Apply Online", titles)
        for job in jobs:
            self.assertEqual(job["applyMode"], "Offline")

    def test_offline_forms_processing_drops_mislabeled_online_jobs(self):
        config = {"sources": [{
            "id": "x", "role": "offline-forms", "enabled": True,
            "url": "https://onlineforms.in/latest-offline-forms/", "timeout": 5,
        }]}
        online_article = monitor.Download(
            "https://onlineforms.in/some-online-job-recruitment/",
            "text/html",
            b"<html><body><p>can apply through online mode.</p></body></html>",
        )
        jobs = [{
            "id": 1,
            "title": "Some Online Job Recruitment 2026 Apply Online",
            "applyMode": "Offline",
            "offlineFormLink": "redirect.html?f=aaaaaaaaaaaa",
            "pdfLink": "redirect.html?f=aaaaaaaaaaaa",
            "applyLink": "redirect.html?f=aaaaaaaaaaaa",
            "sourceUrl": "https://onlineforms.in/some-online-job-recruitment/",
        }]
        now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)

        def fake_fetch(url, timeout=25, retries=2):
            if url == "https://onlineforms.in/some-online-job-recruitment/":
                return online_article
            raise RuntimeError("no network")

        with tempfile.TemporaryDirectory() as folder:
            redirect_path = Path(folder) / "offline-redirects.json"
            with patch.object(monitor, "DEFAULT_OFFLINE_REDIRECTS", redirect_path), \
                 patch.object(monitor, "fetch_url", side_effect=fake_fetch):
                monitor.process_offline_forms(config, jobs, {"sources": {}}, now)
        self.assertNotIn(1, [job["id"] for job in jobs])

    def test_offline_forms_processing_strips_offline_fields_from_online_jobs(self):
        config = {"sources": [{
            "id": "x", "role": "offline-forms", "enabled": True,
            "url": "https://onlineforms.in/latest-offline-forms/", "timeout": 5,
        }]}
        jobs = [{
            "id": 2,
            "title": "SSC Clerk Result 2026",
            "applyMode": "Online",
            "offlineFormLink": "redirect.html?f=bbbbbbbbbbbb",
            "offlineFormName": "Offline Application Form",
            "applyLabel": "Download Offline Application Form",
        }]
        now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            redirect_path = Path(folder) / "offline-redirects.json"
            with patch.object(monitor, "DEFAULT_OFFLINE_REDIRECTS", redirect_path), \
                 patch.object(monitor, "fetch_url", side_effect=RuntimeError("no network")):
                monitor.process_offline_forms(config, jobs, {"sources": {}}, now)
        target = next(job for job in jobs if job["id"] == 2)
        self.assertNotIn("offlineFormLink", target)
        self.assertNotIn("offlineFormName", target)
        self.assertEqual(target["applyLabel"], "Open Official Application")

    def test_offline_vacancy_covered_by_portal(self):
        forms = monitor.load_offline_forms()
        covered = {
            "applyMode": "Offline",
            "title": "Air Force Non-Combatant Recruitment 2026 - apply offline",
            "department": "Indian Air Force",
        }
        self.assertTrue(monitor.offline_vacancy_covered_by_portal(covered, forms))
        online = {"applyMode": "Online", "title": covered["title"], "department": covered["department"]}
        self.assertFalse(monitor.offline_vacancy_covered_by_portal(online, forms))
        uncovered = {
            "applyMode": "Offline",
            "title": "Recruitment of Software Engineers at a private firm",
            "department": "Private Firm",
        }
        self.assertFalse(monitor.offline_vacancy_covered_by_portal(uncovered, forms))

    def test_offline_source_configured_in_sources_json(self):
        config = json.loads(
            (Path(__file__).resolve().parents[1] / "automation" / "sources.json").read_text(
                encoding="utf-8"
            )
        )
        offline = [source for source in config["sources"] if source.get("role") == "offline-forms"]
        self.assertGreaterEqual(len(offline), 1)
        for source in offline:
            self.assertTrue(source["enabled"])
            self.assertTrue(monitor.is_offline_form_url(source["url"]))
        hosts = {monitor.host_name(source["url"]) for source in offline}
        self.assertIn("onlineforms.in", hosts)
        self.assertIn("speedjob.in", hosts)


if __name__ == "__main__":
    unittest.main()
