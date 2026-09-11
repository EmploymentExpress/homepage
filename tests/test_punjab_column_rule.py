"""R14 Punjab column rule: AIIMS Bathinda, every Chandigarh organisation & CUPB.

AGENTS.md ("Punjab column rule") requires every notice from AIIMS Bathinda, from
any recruiting organisation of Chandigarh — even a UT/central institute or a
national body's Chandigarh-specific notice — and from the Central University of
Punjab (CUPB), Bathinda, to publish in Column 1, Latest Punjab Jobs
(`type: "punjab"`, `categorySlug: "punjab-jobs"`), never in the All India & NVS /
Central column, and never carrying the ``alsoInPunjab`` cross-listing flag
(their home column is Punjab). CUPB is a Punjab campus university, so its
vacancies belong next to AIIMS Bathinda's, not in the all-India column.

``EnforcePunjabColumnRuleTests`` runs the real enforcement function from
``scripts/update_jobs.py``; ``StoreClassificationTests`` asserts the published
store and the monitoring sources already comply, so a regression fails CI.
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "scripts" / "update_jobs.py"
AUTO_JOBS = ROOT / "data" / "auto-jobs.json"
SOURCES = ROOT / "automation" / "sources.json"
REGISTRY = ROOT / "data" / "notification-source-links.json"

SPEC = importlib.util.spec_from_file_location("update_jobs", MODULE_PATH)
monitor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = monitor
SPEC.loader.exec_module(monitor)


class EnforcePunjabColumnRuleTests(unittest.TestCase):
    """The enforcement function from scripts/update_jobs.py, for real."""

    def test_aiims_bathinda_and_chandigarh_organisations_match(self):
        cases = [
            "All India Institute of Medical Sciences (AIIMS), Bathinda — Recruitment Types",
            "AIIMS Bathinda (Faculty)",
            "Recruitment of Junior Resident at AIIMS Bathinda",
            "Postgraduate Institute of Medical Education and Research (PGIMER), Chandigarh",
            "PGIMER Chandigarh Nursing Officer Recruitment",
            "High Court of Punjab and Haryana at Chandigarh",
            "Railway Recruitment Board (RRB), Chandigarh",
            "Department of Social Welfare, Chandigarh Administration",
            "Chandigarh Administration Public Notices",
            "https://aiimsbathinda.edu.in/Recruitment.aspx?type=1",
            "https://pgimer.edu.in/PGIMER_PORTAL/PGIMERPORTAL/home.jsp",
            # R14 extension: Central University of Punjab is a Punjab campus
            # university, so every one of its notices is a Punjab-column
            # notice — by name, by acronym and by its own domain.
            "Central University of Punjab (CUPB), Bathinda",
            "Central University of Punjab Recruitment",
            "CUPB Bathinda — Laboratory Attendant Recruitment",
            "Advertisement No. CUPB/26-27/012 dated 02.09.2026",
            "https://cup.edu.in/",
            "https://cup.edu.in/non-teaching_jobs.php",
            "https://cup.edu.in/sites/default/files/Contract%20NT_09_2026.pdf",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertTrue(monitor.is_punjab_column_organisation(text))

    def test_genuine_all_india_organisations_do_not_match(self):
        cases = [
            "State Bank of India (SBI)",
            "Institute of Banking Personnel Selection (IBPS)",
            "Indian Institute of Technology (BHU), Varanasi",
            "Punjab Police Recruitment 2026",
            "https://sbi.co.in/web/careers",
            # A short acronym must be anchored to word boundaries, or
            # "cupboard" would be read as CUPB.
            "Cupboard and stationery supplier tender notice",
            "Recruitment of Cup Bearer",
            "",
            None,
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertFalse(monitor.is_punjab_column_organisation(text))

    def test_central_record_is_moved_to_the_punjab_column(self):
        job = {
            "id": 123,
            "title": "AIIMS Bathinda — Senior Resident/Junior Resident Recruitment",
            "department": "All India Institute of Medical Sciences (AIIMS), Bathinda",
            "sourceName": "AIIMS Bathinda (Faculty)",
            "sourceUrl": "https://aiimsbathinda.edu.in/Recruitment.aspx?type=1",
            "type": "central",
            "categorySlug": "central",
        }
        self.assertTrue(monitor.enforce_punjab_column_rule([job]))
        self.assertEqual(job["type"], "punjab")
        self.assertEqual(job["categorySlug"], "punjab-jobs")

    def test_pgimer_record_is_moved_to_the_punjab_column(self):
        job = {
            "id": 456,
            "title": "PGIMER Chandigarh — Recruitment of Nursing Officer",
            "department": "Postgraduate Institute of Medical Education and Research (PGIMER), Chandigarh",
            "type": "central",
            "categorySlug": "central",
            "alsoInPunjab": True,
        }
        self.assertTrue(monitor.enforce_punjab_column_rule([job]))
        self.assertEqual(job["type"], "punjab")
        self.assertEqual(job["categorySlug"], "punjab-jobs")
        # A Punjab-column notice is home-listed, not cross-listed.
        self.assertNotIn("alsoInPunjab", job)

    def test_a_national_body_chandigarh_specific_notice_moves(self):
        job = {
            "id": 789,
            "title": "UCO Bank — List of Provisionally Shortlisted Candidates (Chandigarh UT)",
            "department": "UCO Bank",
            "type": "central",
            "categorySlug": "central",
            "noticeUrl": (
                "https://uco.bank.in/documents/20120/653076/"
                "Candidate+Provisionally+Selected+under+IBPS-CRP-CSA-XV"
                "+for+Chandigarh+UT.pdf/df4bc94d"
            ),
        }
        self.assertTrue(monitor.enforce_punjab_column_rule([job]))
        self.assertEqual(job["type"], "punjab")
        self.assertEqual(job["categorySlug"], "punjab-jobs")

    def test_the_rule_is_actually_wired_into_the_monitor_run(self):
        """The enforcement function must be *called*, not merely defined.

        For a long time `enforce_punjab_column_rule()` was never invoked from
        the pipeline, so R14 only held because every affected source happened
        to be configured as `punjab`. A notice arriving from a discovery feed
        would have landed in the Central column silently.
        """
        source = MODULE_PATH.read_text(encoding="utf-8")
        calls = source.count("enforce_punjab_column_rule(jobs)")
        self.assertGreaterEqual(
            calls, 1, "enforce_punjab_column_rule() is defined but never called")

    def test_cupb_record_is_moved_to_the_punjab_column(self):
        """R14 extension: CUPB is a Punjab campus university, not all-India."""
        job = {
            "id": 555,
            "title": ("Central University of Punjab (CUPB), Bathinda — "
                      "Laboratory Attendant (Computer Science & Technology) Recruitment"),
            "department": "Central University of Punjab (CUPB), Bathinda",
            "sourceName": "Central University of Punjab Recruitment",
            "sourceUrl": "https://cup.edu.in/",
            "noticeUrl": "https://cup.edu.in/sites/default/files/Contract%20NT_09_2026.pdf",
            "type": "central",
            "categorySlug": "central",
            "alsoInPunjab": True,
        }
        self.assertTrue(monitor.enforce_punjab_column_rule([job]))
        self.assertEqual(job["type"], "punjab")
        self.assertEqual(job["categorySlug"], "punjab-jobs")
        # A Punjab-column notice is home-listed, not cross-listed.
        self.assertNotIn("alsoInPunjab", job)

    def test_genuine_central_records_are_left_alone(self):
        jobs = [
            {
                "id": 1,
                "title": "State Bank of India — Apprentices Recruitment",
                "department": "State Bank of India (SBI)",
                "type": "central",
                "categorySlug": "central",
            },
            {
                "id": 2,
                "title": "Indian Institute of Technology (BHU) — Junior Assistant Recruitment",
                "department": "Indian Institute of Technology (BHU), Varanasi",
                "type": "central",
                "categorySlug": "central",
            },
        ]
        self.assertFalse(monitor.enforce_punjab_column_rule(jobs))
        self.assertTrue(all(job["type"] == "central" for job in jobs))

    def test_already_punjab_records_report_no_change(self):
        job = {
            "id": 1,
            "title": "AIIMS Bathinda — Non-Faculty Recruitment",
            "department": "All India Institute of Medical Sciences (AIIMS), Bathinda",
            "type": "punjab",
            "categorySlug": "punjab-jobs",
        }
        self.assertFalse(monitor.enforce_punjab_column_rule([job]))


class StoreClassificationTests(unittest.TestCase):
    """The published store and the monitoring sources comply with R14."""

    @classmethod
    def setUpClass(cls):
        cls.store = json.loads(AUTO_JOBS.read_text(encoding="utf8"))
        cls.sources = json.loads(SOURCES.read_text(encoding="utf8"))
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf8"))

    def matched_store_jobs(self):
        return [
            job
            for job in self.store["jobs"]
            if monitor.is_punjab_column_organisation(
                job.get("title"),
                job.get("department"),
                job.get("sourceName"),
                job.get("sourceUrl"),
                job.get("noticeUrl"),
                job.get("pdfLink"),
            )
        ]

    def test_store_has_aiims_bathinda_or_chandigarh_records(self):
        self.assertTrue(self.matched_store_jobs(), "expected the published store to hold AIIMS Bathinda / Chandigarh notices")

    def test_every_matching_store_record_publishes_in_the_punjab_column(self):
        for job in self.matched_store_jobs():
            with self.subTest(job=job["id"]):
                self.assertEqual(job["type"], "punjab")
                self.assertEqual(job["categorySlug"], "punjab-jobs")
                self.assertNotEqual(
                    job.get("alsoInPunjab"),
                    True,
                    "a Punjab-column notice must not carry the all-India cross-listing flag",
                )

    def test_registered_sources_use_punjab_column_values(self):
        checked = 0
        for source in self.sources.get("sources", []):
            if not monitor.is_punjab_column_organisation(
                source.get("department"), source.get("name"), source.get("url")
            ):
                continue
            with self.subTest(source=source.get("id")):
                self.assertEqual(source.get("type"), "punjab")
                self.assertEqual(source.get("categorySlug"), "punjab-jobs")
            checked += 1
        self.assertGreaterEqual(checked, 5, "expected the AIIMS Bathinda / Chandigarh sources to stay registered")

    def test_registered_official_links_use_punjab_column_values(self):
        for entry in self.registry.get("links", []):
            if isinstance(entry, str):
                continue
            if not monitor.is_punjab_column_organisation(
                entry.get("url"), entry.get("department"), entry.get("name")
            ):
                continue
            with self.subTest(url=entry.get("url")):
                self.assertEqual(entry.get("type"), "punjab")
                self.assertEqual(entry.get("categorySlug"), "punjab-jobs")


if __name__ == "__main__":
    unittest.main()
