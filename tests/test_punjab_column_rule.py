"""R14 Punjab column rule: AIIMS Bathinda, every Chandigarh organisation, CUPB,
Punjab state & every Punjab district — as the JOB LOCATION, never an exam centre.

AGENTS.md ("Punjab column rule") requires every notice from AIIMS Bathinda, from
any recruiting organisation of Chandigarh — even a UT/central institute or a
national body's Chandigarh-specific notice — from the Central University of
Punjab (CUPB), Bathinda, and every notice whose job details name **the Punjab
state, Chandigarh, or a district of Punjab as the job location** (all 23
districts, with their common spelling variants, matched on word boundaries) to
publish in Column 1, Latest Punjab Jobs (`type: "punjab"`,
`categorySlug: "punjab-jobs"`), never in the All India & NVS / Central column,
and never carrying the ``alsoInPunjab`` cross-listing flag (their home column is
Punjab). Two exclusions keep the rule honest: a Punjab district / the state /
Chandigarh that appears only as an **examination centre, exam city or test
venue** never moves a notice (the candidate sits the exam there, the job is not
there), banks merely *named* Punjab (PNB, Punjab & Sind, Punjab & Maharashtra)
stay central, and a bare word "Punjab" in the PDF-derived details free text
needs an explicit employer phrase ("Government of Punjab") to count.

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

    def test_punjab_state_name_matches(self):
        # R14 state extension: the state's own name counts like a district —
        # "Punjab Police Recruitment 2026" is a Punjab notice (its source is
        # registered as punjab in automation/sources.json).
        cases = [
            "Punjab Police Recruitment 2026",
            "Punjab State Power Corporation Limited (PSPCL) — Lineman Recruitment",
            "Government of Punjab — Clerk Recruitment",
            "Punjab State Civil Supplies Corporation (PUNSUP) Recruitment",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertTrue(monitor.is_punjab_column_organisation(text))

    def test_punjab_location_value_matches(self):
        self.assertTrue(monitor.is_punjab_column_organisation("Punjab"))

    def test_banks_named_punjab_stay_central(self):
        # These banks are merely NAMED Punjab but are headquartered outside
        # the state, so their all-India notices never move to Punjab.
        cases = [
            "Punjab National Bank (PNB) — Officer Recruitment",
            "Punjab & Sind Bank — Specialist Officers Recruitment",
            "Punjab and Maharashtra Bank — Clerk Recruitment",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertFalse(monitor.is_punjab_column_organisation(text))

    # ------------------------------------------------------------------
    # R14 exam-centre exclusion: a Punjab district / the state / Chandigarh
    # counts only as a JOB LOCATION — never as an examination centre, exam
    # city or test venue named in the notice.
    # ------------------------------------------------------------------

    def test_exam_centre_mentions_do_not_trigger(self):
        cases = [
            "SSC JHT 2026 — Examination Centres: Delhi, Ludhiana, Chandigarh and Pune",
            "The written examination will be held at exam centres in Amritsar and Jalandhar.",
            "Exam City Intimation — Chandigarh region",
            "Test centre: Patiala",
            "Venue: SAS Nagar (Mohali)",
            "CUIET — choice of exam cities includes Bathinda and Delhi",
            "Examination cities: Chandigarh, Delhi, Mumbai",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertFalse(monitor.is_punjab_column_organisation(text))

    def test_exam_centre_notice_stays_in_the_central_column(self):
        # A notice whose ONLY Punjab connection is its exam centres must stay
        # in the All India & Central column.
        job = {
            "id": 9001,
            "title": "SSC — Junior Hindi Translator Recruitment",
            "department": "Staff Selection Commission (SSC)",
            "sourceName": "Staff Selection Commission (SSC)",
            "location": "All India",
            "details": ("The examination will be conducted at examination centres in "
                        "Delhi, Ludhiana and Chandigarh. Applications are submitted online."),
            "type": "central",
            "categorySlug": "central",
        }
        self.assertFalse(monitor.enforce_punjab_column_rule([job]))
        self.assertEqual(job["type"], "central")
        self.assertEqual(job["categorySlug"], "central")

    def test_job_location_survives_alongside_exam_centres(self):
        # The employer's posting names the district, the exam happens
        # elsewhere: the notice still moves to the Punjab column.
        job = {
            "id": 9002,
            "title": "Ex-Servicemen Contributory Health Scheme, Ferozepur (Punjab) — Recruitment",
            "department": "Ex-Servicemen Contributory Health Scheme (ECHS)",
            "location": "All India",
            "details": ("Post based at Ferozepur (Punjab). Examination centres for the "
                        "written test: Delhi and Chandigarh."),
            "type": "central",
            "categorySlug": "central",
        }
        self.assertTrue(monitor.enforce_punjab_column_rule([job]))
        self.assertEqual(job["type"], "punjab")
        self.assertEqual(job["categorySlug"], "punjab-jobs")

    def test_bare_punjab_in_details_free_text_does_not_trigger(self):
        # The live IBPS case: "Punjab" appears only as an exam-language option
        # in the PDF-derived details, not as the job location — the notice
        # stays central and keeps its all-India cross-listing.
        details = ("For Office Assistants and Officer Scale-I the test versions "
                   "offered for Punjab are English, Hindi and Punjabi, and the "
                   "medium is chosen in the online application.")
        self.assertFalse(monitor.is_punjab_column_organisation(details=details))
        job = {
            "id": 9003,
            "title": "Institute of Banking Personnel Selection (IBPS) — Apply Online for Common Recruitment Process",
            "department": "Institute of Banking Personnel Selection (IBPS)",
            "sourceName": "IBPS",
            "location": "All India (state-wise, participating RRBs)",
            "details": details,
            "type": "central",
            "categorySlug": "central",
            "alsoInPunjab": True,
        }
        self.assertFalse(monitor.enforce_punjab_column_rule([job]))
        self.assertEqual(job["type"], "central")
        self.assertTrue(job.get("alsoInPunjab") is True)

    def test_punjab_employer_phrase_in_details_triggers(self):
        details = ("Applications are invited under the Government of Punjab for "
                   "various district posts. Apply before the last date.")
        self.assertTrue(monitor.is_punjab_column_organisation(details=details))

    def test_chandigarh_organisation_exam_city_notice_stays_punjab(self):
        # A Chandigarh organisation's own exam-city notice still publishes in
        # the Punjab column: the organisation identity (department/source
        # name) is matched unmasked, even though the title names an exam city.
        job = {
            "id": 9004,
            "title": "RRB Chandigarh — Exam City Intimation Slip",
            "department": "Railway Recruitment Board (RRB), Chandigarh",
            "sourceName": "Railway Recruitment Board Chandigarh",
            "location": "All India",
            "details": "Exam city intimation for the upcoming computer based test.",
            "type": "central",
            "categorySlug": "central",
        }
        self.assertTrue(monitor.enforce_punjab_column_rule([job]))
        self.assertEqual(job["type"], "punjab")
        self.assertEqual(job["categorySlug"], "punjab-jobs")

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

    # ------------------------------------------------------------------
    # R14 district extension: every district of Punjab, named anywhere in
    # the job details, always publishes in the Punjab column.
    # ------------------------------------------------------------------

    PUNJAB_DISTRICTS = (
        "Amritsar",
        "Barnala",
        "Bathinda",
        "Faridkot",
        "Fatehgarh Sahib",
        "Fazilka",
        "Ferozepur",
        "Gurdaspur",
        "Hoshiarpur",
        "Jalandhar",
        "Kapurthala",
        "Ludhiana",
        "Malerkotla",
        "Mansa",
        "Moga",
        "Pathankot",
        "Patiala",
        "Rupnagar",
        "SAS Nagar",
        "Sangrur",
        "Shahid Bhagat Singh Nagar",
        "Sri Muktsar Sahib",
        "Tarn Taran",
    )

    def test_every_punjab_district_matches(self):
        for district in self.PUNJAB_DISTRICTS:
            with self.subTest(district=district):
                self.assertTrue(
                    monitor.is_punjab_column_organisation(
                        f"Office of the District and Sessions Judge, {district} — Clerk Recruitment"
                    )
                )

    def test_district_spelling_variants_match(self):
        cases = [
            "ECHS Polyclinic Firozpur Recruitment 2026",
            "District Court Ferozepore Recruitment",
            "Bhatinda District Administration Notice",
            "Ropar DC Office Recruitment",
            "Mohali Court Stenographer Recruitment",
            "S.A.S. Nagar Municipal Corporation Recruitment",
            "Nawanshahr District Court Recruitment",
            "Muktsar DC Office Notice",
            "Jullundur Cantonment Board Recruitment",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertTrue(monitor.is_punjab_column_organisation(text))

    def test_district_names_inside_other_words_do_not_match(self):
        # Short district names are matched on word boundaries, so they must
        # never fire inside an unrelated word.
        cases = [
            "Mansarovar Lake Development Authority Recruitment",
            "Mansarovar colony welfare association notice",
            "PSG Medical College recruitment",  # no district name present
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertFalse(monitor.is_punjab_column_organisation(text))

    def test_districts_of_other_states_do_not_match(self):
        cases = [
            "Office of The District and Session Judge, Rewari — Stenographer Recruitment",
            "Panipat Urban Co-operative Bank, Haryana — Clerk Recruitment",
            "Chaudhary Charan Singh Haryana Agricultural University (HAU), Hisar",
            "University, Rohtak — Peon Recruitment",
            "Ex-Servicemen Contributory Health Scheme (ECHS), Meerut",
            "District Court Balangir, Odisha Recruitment",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assertFalse(monitor.is_punjab_column_organisation(text))

    def test_punjab_district_notice_is_moved_to_the_punjab_column(self):
        # The live case that motivated the district rule: an ECHS (central
        # body) vacancy at Ferozepur was published in the central column with
        # location "All India".
        job = {
            "id": 238551255168358,
            "title": ("Ex-Servicemen Contributory Health Scheme, Ferozepur (Punjab) — "
                      "ECHS Ferozepur Recruitment 2026 Application Form"),
            "department": "Ex-Servicemen Contributory Health Scheme, Ferozepur (Punjab)",
            "sourceName": "ECHS Ferozepur Recruitment",
            "location": "All India",
            "details": ("Offline application vacancy for Ex-Servicemen Contributory "
                        "Health Scheme, Ferozepur (Punjab)."),
            "type": "central",
            "categorySlug": "central",
        }
        self.assertTrue(monitor.enforce_punjab_column_rule([job]))
        self.assertEqual(job["type"], "punjab")
        self.assertEqual(job["categorySlug"], "punjab-jobs")
        # Only the home column changes — the location metadata stays truthful
        # (the enforcement never rewrites it).
        self.assertEqual(job["location"], "All India")

    def test_district_named_only_in_location_or_details_still_moves(self):
        # Every job detail is scanned: a district that appears only in the
        # location field, or only inside the details summary text, is enough.
        for field, value in (
            ("location", "Ludhiana, Punjab"),
            ("details", "Applications must reach the Kapurthala polyclinic office."),
        ):
            with self.subTest(field=field):
                job = {
                    "id": 42,
                    "title": "Ex-Servicemen Contributory Health Scheme — Recruitment",
                    "department": "Ex-Servicemen Contributory Health Scheme (ECHS)",
                    "type": "central",
                    "categorySlug": "central",
                    field: value,
                }
                self.assertTrue(monitor.enforce_punjab_column_rule([job]))
                self.assertEqual(job["type"], "punjab")
                self.assertEqual(job["categorySlug"], "punjab-jobs")

    def test_rail_coach_factory_kapurthala_notice_is_moved_to_the_punjab_column(self):
        # RCF is a Ministry of Railways body — but it is located in Kapurthala,
        # a district of Punjab, so its notices belong in the Punjab column.
        job = {
            "id": 77,
            "title": "Rail Coach Factory (RCF), Kapurthala — Act Apprentice Recruitment",
            "department": "Rail Coach Factory (RCF), Kapurthala — Ministry of Railways",
            "type": "central",
            "categorySlug": "central",
        }
        self.assertTrue(monitor.enforce_punjab_column_rule([job]))
        self.assertEqual(job["type"], "punjab")
        self.assertEqual(job["categorySlug"], "punjab-jobs")

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
        # The same fields enforce_punjab_column_rule() scans, with the same
        # exam-centre masking and strict details handling.
        return [
            job
            for job in self.store["jobs"]
            if monitor.is_punjab_column_organisation(
                job.get("title"),
                job.get("location"),
                job.get("sourceUrl"),
                job.get("noticeUrl"),
                job.get("pdfLink"),
                department=job.get("department"),
                source_name=job.get("sourceName"),
                details=job.get("details"),
            )
        ]

    def test_store_has_aiims_bathinda_chandigarh_or_punjab_district_records(self):
        self.assertTrue(
            self.matched_store_jobs(),
            "expected the published store to hold AIIMS Bathinda / Chandigarh / Punjab-district notices",
        )

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
                # The column is `type`; `categorySlug` is the homepage's
                # master-table filter and may deliberately be a custom Punjab
                # category ("psssb", "ppsc", "punjab-police", …) — but a
                # Punjab-column source must never carry the central values.
                self.assertEqual(source.get("type"), "punjab")
                self.assertNotIn(
                    source.get("categorySlug"), ("", None, "central"),
                    "a Punjab-column source must not carry the central category slug",
                )
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
