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

    def test_prsc_official_site_is_monitored(self):
        """PRSC (Punjab Remote Sensing Centre) recruitment page must be an
        enabled automation source, and the page-source rule applies to it."""
        config = json.loads(
            (Path(__file__).resolve().parents[1] / "automation" / "sources.json").read_text(
                encoding="utf-8"
            )
        )
        prsc = [
            source
            for source in config["sources"]
            if "prsc.punjab.gov.in" in source["url"]
        ]
        self.assertTrue(prsc, "PRSC must be configured as an automation source")
        self.assertEqual(
            [monitor.canonical_url(source["url"]) for source in prsc],
            ["https://prsc.punjab.gov.in/Recruitment.aspx"],
        )
        self.assertTrue(prsc[0]["enabled"])
        self.assertEqual(
            prsc[0]["department"], "Punjab Remote Sensing Centre (PRSC), Ludhiana"
        )
        self.assertEqual(prsc[0]["type"], "punjab")
        self.assertFalse(monitor.is_discovery_host(prsc[0]["url"]))
        self.assertEqual(len({source["id"] for source in config["sources"]}), len(config["sources"]))
        # PRSC is also an approved official organisation for discovery headlines.
        orgs = json.loads(
            (Path(__file__).resolve().parents[1] / "automation" / "official-organizations.json").read_text(
                encoding="utf-8"
            )
        )
        org_ids = {org["id"] for org in orgs.get("organizations", [])}
        self.assertIn("prsc", org_ids)

    def test_chandigarh_administration_public_notices_are_monitored(self):
        """The direct Chandigarh Public Notice listing is an enabled source."""
        config = json.loads(
            (Path(__file__).resolve().parents[1] / "automation" / "sources.json").read_text(
                encoding="utf-8"
            )
        )
        source = next(
            item
            for item in config["sources"]
            if item["id"] == "chandigarh-administration-public-notices"
        )
        self.assertTrue(source["enabled"])
        self.assertEqual(
            monitor.canonical_url(source["url"]),
            "https://chandigarh.gov.in/public-notice",
        )
        self.assertEqual(source["department"], "Chandigarh Administration")
        self.assertEqual(source["location"], "Chandigarh")
        self.assertFalse(monitor.is_discovery_host(source["url"]))

        org_config = json.loads(
            (Path(__file__).resolve().parents[1] / "automation" / "official-organizations.json").read_text(
                encoding="utf-8"
            )
        )
        chandigarh = next(
            org
            for org in org_config["organizations"]
            if org["id"] == "chandigarh-administration"
        )
        self.assertEqual(chandigarh["url"], source["url"])
        self.assertIn("chandigarh administration", chandigarh["aliases"])

    def test_chandigarh_linked_subject_rows_keep_title_department_and_date(self):
        """Chandigarh puts its full notice subject inside the PDF anchor."""
        markup = """
        <table><tbody>
          <tr><td>1</td>
              <td><a href="/cadmin/uploads/industry.pdf">Terms of Reference (ToR) for engagement of human resources under Policy Implementation Unit in the Department of Industries U.T. Chandigarh</a></td>
              <td>Industries</td><td>21/08/2026</td><td>pdf</td></tr>
          <tr><td>2</td>
              <td><a href="/cadmin/uploads/health.pdf">Ayushman Bharat Digital Mission (ABDM), Health Department U.T. Chandigarh is inviting applications for various posts</a></td>
              <td>Health</td><td>21/08/2026</td><td>pdf</td></tr>
        </tbody></table>
        """
        source = {
            "noticeTypes": ["recruitment", "result", "corrigendum"],
            "includeKeywords": [
                "engagement of human resources",
                "inviting applications",
            ],
            "defaultNoticeType": "recruitment",
        }
        candidates, _ = monitor.parse_html(markup, "https://chandigarh.gov.in/public-notice")
        notices = [candidate for candidate in candidates if monitor.looks_like_notice(candidate, source)]
        self.assertEqual(len(notices), 2)
        self.assertIn("Department of Industries", notices[0].title)
        self.assertIn("Ayushman Bharat Digital Mission", notices[1].title)
        self.assertEqual([notice.notice_date for notice in notices], ["21-08-2026", "21-08-2026"])
        self.assertEqual(
            notices[0].url,
            "https://chandigarh.gov.in/cadmin/uploads/industry.pdf",
        )

    def test_discovery_feeds_include_haryanajobs(self):
        """HaryanaJobs must be configured as a discovery headline scanner and
        never be treated as a publishable source."""
        feeds = monitor.load_discovery_feeds()
        ids = {feed["id"] for feed in feeds}
        self.assertIn("haryanajobs", ids)
        haryanajobs = next(feed for feed in feeds if feed["id"] == "haryanajobs")
        self.assertEqual(
            monitor.canonical_url(haryanajobs["url"]), "https://haryanajobs.in/"
        )
        self.assertTrue(monitor.is_discovery_host(haryanajobs["url"]))
        self.assertGreaterEqual(haryanajobs["maxNewPerRun"], 1)
        self.assertGreaterEqual(haryanajobs["maxHeadlines"], 1)

    def test_discovery_feeds_include_offline_form_portals(self):
        """onlineforms.in and speedjob.in are registered discovery feeds, are
        still recognised as offline-form portals, and can never be published."""
        feeds = monitor.load_discovery_feeds()
        by_id = {feed["id"]: feed for feed in feeds}
        self.assertIn("onlineforms-latest", by_id)
        self.assertIn("speedjob-latest", by_id)
        self.assertEqual(
            monitor.canonical_url(by_id["onlineforms-latest"]["url"]),
            "https://onlineforms.in/latest-offline-forms/",
        )
        self.assertEqual(
            monitor.canonical_url(by_id["speedjob-latest"]["url"]),
            "https://www.speedjob.in/latest-job/",
        )
        for feed_id in ("onlineforms-latest", "speedjob-latest"):
            feed = by_id[feed_id]
            with self.subTest(feed=feed_id):
                self.assertTrue(monitor.is_offline_form_url(feed["url"]))
                self.assertGreaterEqual(feed["maxNewPerRun"], 1)
                self.assertGreaterEqual(feed["maxHeadlines"], 1)

    def test_every_discovery_feed_has_an_effective_new_per_run_limit(self):
        """Each feed must use the key the monitor reads (maxNewPerRun)."""
        registry = json.loads(
            (Path(__file__).resolve().parents[1] / "automation" / "discovery-feeds.json")
            .read_text(encoding="utf-8")
        )
        for entry in registry["feeds"]:
            with self.subTest(feed=entry["id"]):
                self.assertNotIn("maxNewPerFeed", entry)
                self.assertGreaterEqual(int(entry["maxNewPerRun"]), 1)

    def test_offline_portal_branding_never_survives_a_headline(self):
        for value in (
            "OnlineForms.in CSIR NAL Multi-Tasking Staff Recruitment 2026",
            "Speed Job | Army ASC Centre South MTS Recruitment 2026",
        ):
            with self.subTest(value=value):
                cleaned = monitor.strip_discovery_branding(value).lower()
                for term in ("onlineforms", "speedjob", "speed job", "online forms"):
                    self.assertNotIn(term, cleaned)

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

    def test_catch_up_publishes_seen_but_unpublished_active_notice(self):
        page = b"""
        <a href='/clerk.pdf'>Advertisement No. 8/2026 for recruitment of 40 Clerk posts. Last date 30 September 2026</a>
        <a href='/driver.pdf'>Advertisement No. 9/2026 for recruitment of 12 Driver posts. Last date 15 October 2026</a>
        """
        source = {
            "id": "example",
            "name": "Example",
            "department": "Example Government Recruitment Board",
            "url": "https://example.gov.in/jobs",
            "type": "central",
            "enrichDetails": False,
            "bootstrapCount": 1,
            "maxNewPerRun": 5,
            "maxCatchUpPerRun": 5,
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
                return_value=monitor.Download("https://example.gov.in/jobs", "text/html", page),
            ):
                monitor.run(config, output, state)
            first = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(first["jobs"]), 1)

            with patch.object(
                monitor,
                "fetch_url",
                return_value=monitor.Download("https://example.gov.in/jobs", "text/html", page),
            ):
                monitor.run(config, output, state)
            second = json.loads(output.read_text(encoding="utf-8"))
            titles = " ".join(job["title"] for job in second["jobs"])
            self.assertEqual(len(second["jobs"]), 2)
            self.assertIn("Clerk", titles)
            self.assertIn("Driver", titles)

    def test_placeholder_and_homepage_helpers(self):
        self.assertTrue(monitor.is_generic_homepage("https://sahitya-akademi.gov.in/"))
        self.assertTrue(monitor.is_generic_homepage("https://www.sssb.punjab.gov.in"))
        self.assertFalse(monitor.is_generic_homepage("https://sssb.punjab.gov.in/wp-content/uploads/notice.pdf"))
        self.assertTrue(monitor.is_placeholder_detail("See Notification"))
        self.assertTrue(monitor.is_placeholder_detail("Newly Published"))
        self.assertTrue(monitor.is_placeholder_detail("Published 18-08-2026"))
        self.assertFalse(monitor.is_placeholder_detail("30-09-2026"))
        self.assertFalse(monitor.is_placeholder_detail("125 Posts"))

    def test_last_date_reads_upto_and_on_or_before(self):
        self.assertEqual(
            monitor.find_labelled_date(
                "Applications must reach the Registrar upto 01.11.2025 by 5PM.",
                monitor.LAST_DATE_LABELS,
            ),
            "01-11-2025",
        )
        self.assertEqual(
            monitor.find_labelled_date(
                "Completed forms should arrive on or before 04 September 2026.",
                monitor.LAST_DATE_LABELS,
            ),
            "04-09-2026",
        )

    def test_advertisement_number_rejects_table_headings(self):
        self.assertEqual(
            monitor.infer_advertisement_number("Advt No Date Title ENDS ON 16/03/2026"),
            "See Official Notice",
        )
        self.assertEqual(
            monitor.infer_advertisement_number("Advertisement No. 03/2026 for Craft Instructor"),
            "03/2026",
        )

    def test_apply_online_portal_label_is_junk(self):
        self.assertTrue(monitor.is_junk_job_title("Apply Online (Recruitment Portal)"))
        self.assertTrue(
            monitor.is_junk_job_title(
                "Directorate of Education, Shiromani Gurdwara Parbandhak Committee (SGPC), Patiala — Apply Online (Recruitment Portal)"
            )
        )
        self.assertEqual(
            monitor.official_job_title(
                "Apply Online (Recruitment Portal)",
                "Directorate of Education, Shiromani Gurdwara Parbandhak Committee (SGPC), Patiala",
            ),
            "",
        )

    def test_clean_title_keeps_new_delhi_and_strips_new_badge(self):
        self.assertEqual(
            monitor.clean_title("Sahitya Akademi, New Delhi — Clerk Recruitment"),
            "Sahitya Akademi, New Delhi — Clerk Recruitment",
        )
        self.assertEqual(
            monitor.official_job_title(
                "Sahitya Akademi, New Delhi — Delhi Sahitya Akademi MTS, Driver, Clerk, T.A & Various Post",
                "Sahitya Akademi, New Delhi",
            ),
            "Sahitya Akademi, New Delhi — Delhi Sahitya Akademi MTS, Driver, Clerk, T.A & Various Post",
        )
        self.assertEqual(
            monitor.clean_title("NEW Advertisement No. 04/2026 for recruitment of clerks"),
            "Advertisement No. 04/2026 for recruitment of clerks",
        )

    def test_job_from_candidate_never_publishes_root_homepage_links(self):
        candidate = monitor.Candidate(
            "Advertisement for recruitment of 10 Clerk posts",
            "https://example.gov.in/",
        )
        source = {
            "name": "Example Board",
            "department": "Example Government Recruitment Board",
            "url": "https://example.gov.in/",
            "type": "central",
            "enrichDetails": False,
        }
        job = monitor.job_from_candidate(
            candidate, source, datetime(2026, 8, 21, tzinfo=timezone.utc)
        )
        self.assertEqual(job["pdfLink"], "")
        self.assertEqual(job["applyLink"], "")
        self.assertEqual(job["noticeUrl"], "https://example.gov.in/")

    def test_apply_extensions_strips_internal_fields_from_recruitment_jobs(self):
        jobs = [
            {
                "id": 1,
                "title": "Recruitment of 10 Clerk posts",
                "department": "Example Board",
                "alertType": "recruitment",
                "advtNo": "1/2026",
                "lastDate": "20-09-2026",
                "isExtension": False,
                "extensionDate": "",
            }
        ]
        self.assertFalse(monitor.apply_extensions(jobs))
        self.assertNotIn("isExtension", jobs[0])
        self.assertNotIn("extensionDate", jobs[0])

    def test_merge_job_details_fills_placeholders_and_keeps_identity(self):
        existing = {
            "id": 42,
            "title": "Example Government Recruitment Board — Clerk Recruitment",
            "department": "Example Government Recruitment Board",
            "vacancies": "See Notification",
            "lastDate": "See Notification",
            "startDate": "Newly Published",
            "advtNo": "See Official Notice",
            "age": "See Official Notification",
            "qualification": "See Official Notification",
            "pdfLink": "https://example.gov.in/",
            "applyLink": "https://example.gov.in/",
            "sourceUrl": "https://example.gov.in/jobs",
            "discoveredAt": "2026-08-18T10:00:00Z",
            "publishedAt": "",
            "alertType": "recruitment",
        }
        fresh = {
            "id": 99,
            "title": "Example Government Recruitment Board — Clerk Recruitment",
            "department": "Example Government Recruitment Board",
            "vacancies": "40 Posts",
            "lastDate": "30-09-2026",
            "startDate": "12-08-2026",
            "advtNo": "8/2026",
            "age": "18 to 37 Years",
            "qualification": "Graduate",
            "qualCategory": "Graduate",
            "pdfLink": "https://example.gov.in/files/clerk-8.pdf",
            "applyLink": "https://example.gov.in/apply/clerk-8",
            "noticeUrl": "https://example.gov.in/files/clerk-8.pdf",
            "publishedAt": "2026-08-12T09:00:00Z",
            "discoveredAt": "2026-08-21T12:00:00Z",
        }
        self.assertTrue(monitor.merge_job_details(existing, fresh))
        self.assertEqual(existing["id"], 42)
        self.assertEqual(existing["discoveredAt"], "2026-08-18T10:00:00Z")
        self.assertEqual(existing["vacancies"], "40 Posts")
        self.assertEqual(existing["lastDate"], "30-09-2026")
        self.assertEqual(existing["startDate"], "12-08-2026")
        self.assertEqual(existing["advtNo"], "8/2026")
        self.assertEqual(existing["age"], "18 to 37 Years")
        self.assertEqual(existing["pdfLink"], "https://example.gov.in/files/clerk-8.pdf")
        self.assertEqual(existing["applyLink"], "https://example.gov.in/apply/clerk-8")
        self.assertEqual(existing["noticeUrl"], "https://example.gov.in/files/clerk-8.pdf")
        self.assertEqual(existing["publishedAt"], "2026-08-12T09:00:00Z")

    def test_merge_job_details_does_not_revert_extended_last_date(self):
        existing = {
            "lastDate": "30-09-2026",
            "originalLastDate": "20-09-2026",
            "lastDateExtended": True,
            "pdfLink": "https://example.gov.in/advt.pdf",
            "applyLink": "https://example.gov.in/apply",
        }
        fresh = {
            "lastDate": "20-09-2026",
            "pdfLink": "https://example.gov.in/advt.pdf",
            "applyLink": "https://example.gov.in/apply",
        }
        self.assertFalse(monitor.merge_job_details(existing, fresh))
        self.assertEqual(existing["lastDate"], "30-09-2026")

    def test_backfill_reads_last_date_from_stored_details(self):
        jobs = [{
            "title": "Guru Ravidas Ayurved University (GRAU), Hoshiarpur — Professor posts",
            "details": "Applications must reach the Registrar, GRAU upto 01.11.2025 by 5PM.",
            "lastDate": "See Notification",
            "vacancies": "See Notification",
            "advtNo": "DATE",
            "pdfLink": "https://graupunjab.org/",
            "applyLink": "https://graupunjab.org/",
        }]
        self.assertTrue(monitor.backfill_extracted_fields(jobs))
        self.assertEqual(jobs[0]["lastDate"], "01-11-2025")
        self.assertEqual(jobs[0]["pdfLink"], "")
        self.assertEqual(jobs[0]["applyLink"], "")

    def test_seen_notice_is_refreshed_instead_of_left_stale(self):
        listing = b"""
        <a href='/clerk.pdf'>Advertisement No. 8/2026 for recruitment of 40 Clerk posts.
        Last date of online registration: 30 September 2026. Age limit: 18 to 37 Years.</a>
        """
        source = {
            "id": "example",
            "name": "Example",
            "department": "Example Government Recruitment Board",
            "url": "https://example.gov.in/jobs",
            "type": "central",
            "categorySlug": "central",
            "enrichDetails": False,
            "bootstrapCount": 1,
            "maxNewPerRun": 5,
            "maxRefreshPerRun": 5,
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / "sources.json"
            output = root / "auto-jobs.json"
            state = root / "seen.json"
            config.write_text(json.dumps({"sources": [source]}), encoding="utf-8")

            stale = {
                "version": 1,
                "updatedAt": "2026-08-18T00:00:00Z",
                "jobs": [{
                    "id": 1,
                    "title": "Example Government Recruitment Board — Clerk posts Recruitment",
                    "department": "Example Government Recruitment Board",
                    "vacancies": "See Notification",
                    "qualification": "See Official Notification",
                    "qualCategory": "Graduate",
                    "lastDate": "See Notification",
                    "startDate": "Newly Published",
                    "examDate": "See Official Notification",
                    "location": "All India",
                    "applyMode": "Online / As Notified",
                    "alertType": "recruitment",
                    "badge": "JOB NOTICE",
                    "badgeColor": "bg-blue-600",
                    "type": "central",
                    "categorySlug": "central",
                    "advtNo": "See Official Notice",
                    "age": "See Official Notification",
                    "details": "Open the official notice.",
                    "howToApply": [],
                    "pdfLink": "https://example.gov.in/clerk.pdf",
                    "applyLink": "https://example.gov.in/jobs",
                    "applyLabel": "Open Official Application",
                    "sourceName": "Example",
                    "sourceUrl": "https://example.gov.in/jobs",
                    "noticeUrl": "https://example.gov.in/clerk.pdf",
                    "publishedAt": "",
                    "discoveredAt": "2026-08-18T00:00:00Z",
                    "automated": True,
                }],
            }
            output.write_text(json.dumps(stale), encoding="utf-8")
            fingerprint = monitor.fingerprint(
                monitor.Candidate(
                    "Advertisement No. 8/2026 for recruitment of 40 Clerk posts. "
                    "Last date of online registration: 30 September 2026. Age limit: 18 to 37 Years.",
                    "https://example.gov.in/clerk.pdf",
                )
            )
            # Also mark the cleaned title variant used by parse_html.
            parsed, _ = monitor.parse_html(listing.decode(), "https://example.gov.in/jobs")
            fingerprints = list(dict.fromkeys(
                [fingerprint] + [monitor.fingerprint(item) for item in parsed]
            ))
            state.write_text(json.dumps({
                "version": 1,
                "sources": {
                    "example": {
                        "initializedAt": "2026-08-18T00:00:00Z",
                        "fingerprints": fingerprints,
                    }
                },
            }), encoding="utf-8")

            with patch.object(
                monitor,
                "fetch_url",
                return_value=monitor.Download("https://example.gov.in/jobs", "text/html", listing),
            ):
                monitor.run(config, output, state)

            updated = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(updated["jobs"]), 1)
            job = updated["jobs"][0]
            self.assertEqual(job["id"], 1)
            self.assertEqual(job["discoveredAt"], "2026-08-18T00:00:00Z")
            self.assertEqual(job["lastDate"], "30-09-2026")
            self.assertEqual(job["vacancies"], "40 Posts")
            self.assertEqual(job["advtNo"], "8/2026")
            self.assertEqual(job["age"], "18 to 37 Years")
            self.assertNotIn("isExtension", job)
            self.assertNotIn("extensionDate", job)

    def test_offline_page_ignores_portal_homepage_as_official_website_or_form(self):
        page = monitor.Download(
            "https://onlineforms.in/example-board-recruitment/",
            "text/html",
            b"""
            <html><body>
              <table>
                <tr><td>Download Application Form</td>
                    <td><a href="https://sahitya-akademi.gov.in/">Download</a></td></tr>
                <tr><td>Official Notification</td>
                    <td><a href="https://onlineforms.in/wp-content/uploads/2026/08/notice.pdf">Notification</a></td></tr>
                <tr><td>Official Website</td>
                    <td><a href="https://onlineforms.in/">Click Here</a></td></tr>
              </table>
            </body></html>
            """,
        )
        documents = monitor.offline_page_documents(page.url, page)
        self.assertEqual(documents["form"], "")
        self.assertEqual(documents["website"], "")
        self.assertIn("notice.pdf", documents["notification"])

    def test_stale_homepage_form_cache_is_refreshed(self):
        self.assertTrue(
            monitor._offline_documents_need_refresh({"form": "https://sahitya-akademi.gov.in/"})
        )
        cleaned = monitor._sanitize_offline_documents({
            "form": "https://sahitya-akademi.gov.in/",
            "notification": "https://example.gov.in/notice.pdf",
            "website": "https://onlineforms.in/",
        })
        self.assertEqual(cleaned["form"], "")
        self.assertEqual(cleaned["website"], "")
        self.assertEqual(cleaned["notification"], "https://example.gov.in/notice.pdf")

    # ------------------------------------------------------------------
    # Page-source rule: after checking the official website, if no new job
    # notification is found, check the raw page source of the official
    # website on every workflow run.
    # ------------------------------------------------------------------
    def _page_source_source(self):
        return {
            "id": "example-board",
            "name": "Example Board",
            "department": "Example Government Recruitment Board",
            "url": "https://example.gov.in/notices",
            "type": "central",
            "categorySlug": "central",
            "location": "All India",
            "noticeTypes": ["recruitment", "result", "corrigendum"],
            "includeKeywords": ["advt", "advt."],
        }

    def test_page_source_scan_finds_notices_the_listing_parser_misses(self):
        """The raw page source exposes notices hidden from the visible listing:
        <noscript> fallback links, <iframe> PDF embeds, <area> maps and bare
        URLs inside scripts. The normal listing parser sees none of them."""
        markup = """<html><head><title>Official Notices</title></head><body>
        <nav>Home | Careers | Contact</nav>
        <noscript>
          <a href="/files/advt-2026-04.pdf"></a>
        </noscript>
        <iframe src="/uploads/recruitment-notification-2026.pdf"></iframe>
        <map name="m"><area href="/vacancy-notice-2026.pdf" shape="rect" coords="0,0,10,10"></map>
        <script>var n = { url: "https://example.gov.in/recruitment/advt-05-2026.html" };</script>
        <a href="https://example.gov.in/recruitment/advt-06-2026.pdf">Recruitment Advertisement No 06/2026</a>
        </body></html>"""
        download = monitor.Download(
            url="https://example.gov.in/notices",
            content_type="text/html",
            data=markup.encode("utf-8"),
        )
        source = self._page_source_source()
        listing, _ = monitor.parse_html(markup, "https://example.gov.in/notices")
        listed_urls = {monitor.canonical_url(candidate.url) for candidate in listing}
        raw = monitor.page_source_candidates(download, source)
        raw_urls = {monitor.canonical_url(candidate.url) for candidate in raw}
        for hidden in (
            "https://example.gov.in/files/advt-2026-04.pdf",  # noscript, no label
            "https://example.gov.in/uploads/recruitment-notification-2026.pdf",  # iframe
            "https://example.gov.in/vacancy-notice-2026.pdf",  # area
            "https://example.gov.in/recruitment/advt-05-2026.html",  # script config
        ):
            with self.subTest(url=hidden):
                self.assertNotIn(hidden, listed_urls, "listing parser must miss it")
                self.assertIn(hidden, raw_urls, "raw page source must find it")
        # A visible anchor stays a single candidate (same URL, same title).
        self.assertIn("https://example.gov.in/recruitment/advt-06-2026.pdf", raw_urls)

    def test_page_source_scan_skips_assets_and_aggregator_hosts(self):
        """Static assets, same-page anchors and aggregator links never become
        page-source candidates."""
        markup = """<html><body>
        <a href="/style.css">Styles</a>
        <a href="/script.js">Script</a>
        <img src="/banner.png" alt="banner">
        <a href="#recruitment">Same page</a>
        <a href="https://linkingsky.com/government-exams/government-jobs-in-punjab.html">Aggregator</a>
        <a href="https://onlineforms.in/wp-content/uploads/2026/08/notice.pdf">Portal</a>
        <a href="https://example.gov.in/recruitment/advt-06-2026.pdf">Recruitment Advertisement No 06/2026</a>
        </body></html>"""
        download = monitor.Download(
            url="https://example.gov.in/notices",
            content_type="text/html",
            data=markup.encode("utf-8"),
        )
        raw = monitor.page_source_candidates(download, self._page_source_source())
        urls = {monitor.canonical_url(candidate.url) for candidate in raw}
        self.assertEqual(
            urls, {"https://example.gov.in/recruitment/advt-06-2026.pdf"}
        )

    def test_page_source_fallback_only_fires_when_listing_found_nothing(self):
        """The fallback returns raw-source candidates only when they are not
        already listed, not already seen, and the page is HTML (not a feed)."""
        markup = """<html><body>
        <noscript><a href="/files/advt-2026-07.pdf"></a></noscript>
        <a href="https://example.gov.in/recruitment/advt-07-2026.pdf">Recruitment Advertisement No 07/2026</a>
        </body></html>"""
        download = monitor.Download(
            url="https://example.gov.in/notices",
            content_type="text/html",
            data=markup.encode("utf-8"),
        )
        source = self._page_source_source()
        hidden = monitor.Candidate(
            "advt-2026-07", "https://example.gov.in/files/advt-2026-07.pdf"
        )
        visible = monitor.Candidate(
            "Recruitment Advertisement No 07/2026",
            "https://example.gov.in/recruitment/advt-07-2026.pdf",
        )
        # Nothing known, nothing listed -> the raw source surfaces the hidden
        # notice as well as the visible anchor (both are new to the monitor).
        extras = monitor.page_source_fallback_candidates(download, [], set(), source)
        self.assertEqual(
            [monitor.canonical_url(candidate.url) for candidate in extras],
            [
                "https://example.gov.in/files/advt-2026-07.pdf",
                "https://example.gov.in/recruitment/advt-07-2026.pdf",
            ],
        )
        # Already listed -> only the hidden notice is extra, not duplicated.
        extras = monitor.page_source_fallback_candidates(
            download, [visible], set(), source
        )
        self.assertEqual(
            [monitor.canonical_url(candidate.url) for candidate in extras],
            ["https://example.gov.in/files/advt-2026-07.pdf"],
        )
        # Already seen -> nothing is republished.
        extras = monitor.page_source_fallback_candidates(
            download,
            [],
            {monitor.fingerprint(hidden), monitor.fingerprint(visible)},
            source,
        )
        self.assertEqual(extras, [])
        # Feeds are fully parsed by the listing step; the raw scan is skipped.
        feed = monitor.Download(
            url="https://example.gov.in/feed.xml",
            content_type="application/rss+xml",
            data=b'<rss version="2.0"><channel><title>t</title><item>'
            b"<title>Recruitment</title><link>https://example.gov.in/advt.pdf</link>"
            b"</item></channel></rss>",
        )
        self.assertEqual(monitor.page_source_fallback_candidates(feed, [], set(), source), [])

    def test_every_enabled_official_source_is_covered_by_the_page_source_rule(self):
        """The page-source rule lives in the shared per-source pipeline, so it
        applies automatically to every official website link — the configured
        sources, the approved organisations and user-added notification links —
        existing or added later, with no extra configuration."""
        config = json.loads(
            (Path(__file__).resolve().parents[1] / "automation" / "sources.json").read_text(
                encoding="utf-8"
            )
        )
        enabled = [source for source in config["sources"] if source.get("enabled", True)]
        self.assertGreaterEqual(len(enabled), 10)
        for source in enabled:
            with self.subTest(source=source.get("id")):
                url = monitor.canonical_url(source.get("url", ""))
                self.assertTrue(url, "every enabled source needs an official URL")
                self.assertFalse(monitor.is_discovery_host(url))
        # The fallback is a shared function: a brand-new source gets it with
        # zero per-source configuration.
        source = self._page_source_source()
        markup = "<html><body><noscript><a href='/files/advt-2026-09.pdf'></a></noscript></body></html>"
        download = monitor.Download(
            url="https://example.gov.in/notices",
            content_type="text/html",
            data=markup.encode("utf-8"),
        )
        extras = monitor.page_source_fallback_candidates(download, [], set(), source)
        self.assertEqual(len(extras), 1)
        self.assertEqual(
            monitor.canonical_url(extras[0].url),
            "https://example.gov.in/files/advt-2026-09.pdf",
        )

    def test_run_checks_page_source_when_listing_shows_no_new_notification(self):
        """Integration of the rule: on a later workflow run the official page's
        visible listing has no new notification, so run() re-reads the raw page
        source and publishes the notice it finds there."""
        page = (
            b"<html><body>\n"
            b"<noscript><a href=\"/advt-02-2026.pdf\"></a></noscript>\n"
            b"<a href=\"/advt-01-2026.pdf\">Advertisement No. 1/2026 for recruitment of 10 Clerk posts</a>\n"
            b"</body></html>"
        )
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
            "includeKeywords": ["advt", "advt."],
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / "sources.json"
            output = root / "auto-jobs.json"
            state = root / "seen.json"
            config.write_text(json.dumps({"sources": [source]}), encoding="utf-8")
            download = monitor.Download("https://example.gov.in/jobs", "text/html", page)
            with patch.object(monitor, "fetch_url", return_value=download):
                monitor.run(config, output, state)
            first = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(first["jobs"]), 1, "bootstrap publishes only the visible notice")

            # Second run: the listing has no new notification (the visible
            # notice is already known) -> the raw page source must be checked
            # and the hidden noscript notice published.
            with patch.object(monitor, "fetch_url", return_value=download):
                monitor.run(config, output, state)
            second = json.loads(output.read_text(encoding="utf-8"))
            pdfs = {monitor.canonical_url(job["pdfLink"]) for job in second["jobs"]}
            self.assertIn("https://example.gov.in/advt-01-2026.pdf", pdfs)
            self.assertIn(
                "https://example.gov.in/advt-02-2026.pdf",
                pdfs,
                "page-source fallback must publish the notice found in the raw source",
            )

    def test_page_source_rule_is_documented_in_workflow_and_agent_rules(self):
        """The page-source rule is part of the workflow automation: the monitor
        script the scheduled workflow runs enforces it, and AGENTS.md documents
        it so future runs and future contributors keep it."""
        workflow = (
            Path(__file__).resolve().parents[1] / ".github" / "workflows" / "update-job-alerts.yml"
        ).read_text(encoding="utf-8")
        # The scheduled workflow drives the monitor that enforces the rule.
        self.assertIn("python scripts/update_jobs.py", workflow)
        agents = " ".join(
            (Path(__file__).resolve().parents[1] / "AGENTS.md").read_text(encoding="utf-8").split()
        )
        self.assertIn("Workflow automation page-source rule", agents)
        self.assertIn("If no new job notification is found", agents)
        self.assertIn("check the raw page source of that official website", agents)
        self.assertIn("applies automatically to every official website link", agents)
        # The monitor code enforces it (not just the docs).
        script = (Path(__file__).resolve().parents[1] / "scripts" / "update_jobs.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("page_source_fallback_candidates", script)


if __name__ == "__main__":
    unittest.main()
