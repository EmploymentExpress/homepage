"""Guard tests for the short job-details headline rule (see AGENTS.md).

The rule: every published job-details heading is generated from the official
notification as

    <Department short name> <Total posts> <Post name(s)> <What the notice is about>

capped at 72 characters, with the notice type taken from a fixed vocabulary.
"""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from short_headlines import (  # noqa: E402
    MAX_HEADLINE_LENGTH,
    NOTICE_SUFFIXES,
    headline_suffix,
    notice_type,
    short_department,
    short_job_headline,
    vacancy_count,
)

AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
AUTO_JOBS = json.loads((ROOT / "data" / "auto-jobs.json").read_text(encoding="utf-8"))


class ShortHeadlineFormatTests(unittest.TestCase):
    def test_department_short_form_prefers_official_acronym(self):
        self.assertEqual(
            short_department("Punjab State Legal Services Authority (PULSA)"), "PULSA"
        )
        self.assertEqual(
            short_department("Punjab Agricultural University (PAU), Ludhiana"), "PAU"
        )

    def test_department_keeps_state_visible_when_acronym_hides_it(self):
        self.assertEqual(
            short_department("Haryana Women and Child Development Department (WCD), Panchkula"),
            "Haryana WCD",
        )
        self.assertTrue(
            short_department("Local Audit Department, Chandigarh Administration")
            .lower()
            .endswith("chandigarh")
        )

    def test_department_short_form_is_length_capped(self):
        short = short_department(
            "Chandigarh Institute for Transformation, Planning & Evaluation Organization, "
            "Chandigarh Administration"
        )
        self.assertLessEqual(len(short), 34)

    def test_vacancy_count_only_for_real_counts(self):
        self.assertEqual(vacancy_count("681 Posts (52 Trades)"), "681")
        self.assertEqual(vacancy_count("4,161 Posts"), "4,161")
        self.assertEqual(vacancy_count("1 Post"), "")
        self.assertEqual(vacancy_count("See Notification"), "")
        self.assertEqual(vacancy_count("Multiple Posts (See Notification)"), "")

    def test_notice_type_is_detected_from_official_wording(self):
        cases = {
            "Corrigendum to Advt No. 03/2026": "Corrigendum",
            "Addendum regarding Clerk posts": "Addendum",
            "Cancellation of vacancy for Steno Typist": "Cancelled",
            "Postponement of interview for the post of Lab Helper": "Postponed",
            "Last date extended for Craft Instructor": "Date Extended",
            "List of shortlisted candidates for Section Officer": "Shortlisted",
            "Exam date notice for Clerk written test": "Exam Date",
            "Admit card released for Constable CBT": "Admit Card",
            "Answer key and objections for Patwari exam": "Answer Key",
            "Final merit list of Process Server": "Merit List",
            "Result for the posts of Process Server": "Result",
            "Posting orders of the candidates": "Posting Orders",
            "Walk-in-Interview for Senior Resident": "Walk-in Interview",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(notice_type(title), expected)

    def test_every_notice_type_has_headline_wording(self):
        for label, _pattern in [(k, v) for k, v in NOTICE_SUFFIXES.items()]:
            self.assertTrue(NOTICE_SUFFIXES[label].strip())
        self.assertEqual(headline_suffix("Recruitment"), "Online Form")
        self.assertEqual(headline_suffix("Recruitment", apply_mode="Offline"), "Offline Form")
        self.assertEqual(
            headline_suffix("Postponed", "Postponement of interview for Lab Helper"),
            "Interview Postponed",
        )

    def test_headline_examples_follow_the_rule(self):
        cases = [
            (
                (
                    "Punjab State Legal Services Authority (PULSA) — View, Public notice "
                    "regarding result for the post of Process Server (selection of candidate "
                    "from the Ex-servicemen category) PDF 383 KB - opens in a new window View",
                    "Punjab State Legal Services Authority (PULSA)",
                    "result",
                    "22 Posts",
                    "Online / As Notified",
                ),
                "PULSA 22 Process Server Result",
            ),
            (
                (
                    "Punjab Agricultural University (PAU), Ludhiana — Postponement of interview "
                    "for the post of Lab Helper - College of Basic Scs. & Humanities",
                    "Punjab Agricultural University (PAU), Ludhiana",
                    "recruitment",
                    "1 Post",
                    "Offline",
                ),
                "PAU Lab Helper Interview Postponed",
            ),
            (
                (
                    "Punjab Subordinate Services Selection Board (PSSSB) — Craft Instructor "
                    "Recruitment 2026 Re-Opened (Advt No. 03/2026)",
                    "Punjab Subordinate Services Selection Board (PSSSB)",
                    "recruitment",
                    "681 Posts (52 Trades)",
                    "Online",
                ),
                "PSSSB 681 Craft Instructor Last Date Extended",
            ),
            (
                (
                    "PSSSB Clerk, Typist & Data Entry Operator 2026",
                    "Punjab Subordinate Services Selection Board (PSSSB)",
                    "recruitment",
                    "450 Posts",
                    "Online",
                ),
                "PSSSB 450 Clerk, Typist & Various Post Online Form",
            ),
        ]
        for args, expected in cases:
            with self.subTest(title=args[0][:60]):
                self.assertEqual(short_job_headline(*args), expected)

    def test_headlines_never_exceed_the_cap_and_keep_department_and_type(self):
        for job in AUTO_JOBS.get("jobs", []):
            headline = short_job_headline(
                job.get("title", ""),
                job.get("department", ""),
                job.get("alertType", ""),
                job.get("vacancies", ""),
                job.get("applyMode", ""),
            )
            with self.subTest(title=job.get("title", "")[:60]):
                self.assertTrue(headline, "headline must never be empty")
                self.assertLessEqual(len(headline), MAX_HEADLINE_LENGTH)
                self.assertTrue(
                    any(headline.endswith(suffix) for suffix in set(NOTICE_SUFFIXES.values())
                        | {"Offline Form", "Exam Cancelled", "Interview Postponed", "Exam Answer Key"}),
                    f"headline must end with an approved notice type: {headline}",
                )
                # Portal noise must never survive into a heading.
                self.assertNotRegex(headline, r"(?i)\bPDF \d|opens in a new window|click here|^view\b")
                # A heading is never only the notice type.
                self.assertGreater(len(headline.split()), 1)

    def test_curated_headings_have_a_department_and_a_post(self):
        pattern = re.compile(r'title:\s*"((?:[^"\\]|\\.)*)"')
        titles = [t.replace('\\"', '"') for t in pattern.findall(INDEX)]
        self.assertTrue(titles, "curated job titles must be readable from index.html")
        for title in titles:
            with self.subTest(title=title[:50]):
                self.assertGreaterEqual(len(title.split()), 2)


class AgentsRuleTests(unittest.TestCase):
    def test_agents_documents_the_short_headline_rule(self):
        self.assertIn("Short job-details headline rule", AGENTS)
        self.assertIn(
            "<Department short name> <Total posts> <Post name(s)> <What the notice is about>",
            AGENTS,
        )
        for wording in [
            "Online Form", "Offline Form", "Corrigendum Notice", "Addendum Notice",
            "Vacancy Cancelled", "Exam Postponed", "Last Date Extended",
            "Shortlisted Candidates", "Exam Date", "Admit Card", "Answer Key",
            "Merit List", "Waiting List", "Result", "Posting Orders",
            "Walk in Interview", "Admission Form", "Public Notice",
        ]:
            with self.subTest(wording=wording):
                self.assertIn(wording, AGENTS)
        self.assertIn("72-character cap", AGENTS)
        self.assertIn("scripts/short_headlines.py", AGENTS)

    def test_rule_vocabulary_matches_the_implementation(self):
        for suffix in NOTICE_SUFFIXES.values():
            with self.subTest(suffix=suffix):
                self.assertIn(suffix, AGENTS)


if __name__ == "__main__":
    unittest.main()
