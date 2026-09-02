"""Guard tests for the short job-details headline rule (see AGENTS.md).

The rule: every published job-details heading is generated from the official
notification as

    <Department short name> <Total posts> <Post name(s)> <What the notice is about>

capped at 72 characters, with the notice type taken from a fixed vocabulary.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
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
        self.assertEqual(
            short_department("Central University of Punjab (CUPB), Bathinda"), "CUPB"
        )

    def test_department_keeps_state_visible_when_acronym_hides_it(self):
        self.assertEqual(
            short_department("Haryana Women and Child Development Department (WCD), Panchkula"),
            "HARYANA WCD",
        )
        self.assertTrue(
            short_department("Local Audit Department, Chandigarh Administration")
            .endswith("CHANDIGARH")
        )

    def test_department_name_is_always_in_capital_letters(self):
        cases = [
            ("Punjab Police Constable", "Punjab Police", "PUNJAB POLICE"),
            ("Join Indian Army Rally", "Indian Army", "INDIAN ARMY"),
            ("Ministry of Defence ASC", "Ministry of Defence", "MINISTRY OF DEFENCE"),
            ("Local Audit Department", "Local Audit Department", "LOCAL AUDIT DEPT."),
            ("Department of Industries", "Department of Industries", "INDUSTRIES DEPT."),
            ("Sainik School Recruitment", "Sainik School", "SAINIK SCHOOL"),
        ]
        for title, dept, expected in cases:
            with self.subTest(dept=dept):
                short = short_department(dept, title)
                self.assertEqual(short, expected)
                self.assertEqual(short, short.upper())

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


class IndexHeadlineWiringTests(unittest.TestCase):
    """index.html renders the short heading but keeps the full title as data."""

    def test_index_defines_the_shared_headline_helpers(self):
        for helper in ("function shortJobHeadline(", "function jobDisplayHeadline(",
                       "function shortDepartment(", "function noticeType(",
                       "function headlineSuffix(", "function vacancyCount("):
            with self.subTest(helper=helper):
                self.assertIn(helper, INDEX)

    def test_index_headline_vocabulary_matches_the_python_implementation(self):
        for suffix in NOTICE_SUFFIXES.values():
            with self.subTest(suffix=suffix):
                self.assertIn(suffix, INDEX)
        self.assertIn("SHORT_HEADLINE_MAX = 72", INDEX)

    def test_index_headline_mirror_output_matches_the_python_implementation(self):
        """AGENTS.md: both implementations must produce identical output.

        Runs index.html's `shortJobHeadline` in node over every published alert
        (and over the admit-card-with-a-generic-title case that once drifted),
        so the two copies of the rule cannot diverge silently again.
        """
        if not shutil.which("node"):
            self.skipTest("node executable not available")
        start = INDEX.index("// Short job-details headline generator (JS mirror")
        end = INDEX.index("function normalizeAutomaticJob(", start)
        cases = [{"title": "State Bank of India (SBI) — NOTIFICATION FOR ONLINE WRITTEN TEST: "
                           "TENTATIVE DATE OF ONLINE WRITTEN TEST: 23.11.2024 FOR ASSISTANT MANAGER (SYSTEM)",
                  "department": "State Bank of India (SBI)", "alertType": "admit-card",
                  "vacancies": "15 Posts", "applyMode": "Online / As Notified"}]
        cases += [
            {
                "title": job.get("title", ""),
                "department": job.get("department", ""),
                "alertType": job.get("alertType", ""),
                "vacancies": job.get("vacancies", ""),
                "applyMode": job.get("applyMode", ""),
            }
            for job in AUTO_JOBS.get("jobs", [])
        ]
        self.assertTrue(cases)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mirror.js").write_text(INDEX[start:end], encoding="utf-8")
            (root / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
            (root / "run.js").write_text(
                "const fs=require('fs');\n"
                "const code=fs.readFileSync(process.argv[2],'utf8');\n"
                "const cases=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));\n"
                "const jobDisplayHeadline=new Function(code+'\\nreturn jobDisplayHeadline;')();\n"
                "process.stdout.write(JSON.stringify(cases.map(jobDisplayHeadline)));\n",
                encoding="utf-8",
            )
            rendered = subprocess.run(
                ["node", str(root / "run.js"), str(root / "mirror.js"), str(root / "cases.json")],
                capture_output=True, text=True, timeout=120, check=False,
            )
            self.assertEqual(rendered.returncode, 0, f"node failed: {rendered.stderr[-800:]}")
            js_headlines = json.loads(rendered.stdout)
        self.assertEqual(len(js_headlines), len(cases))
        for case, headline in zip(cases, js_headlines):
            expected = short_job_headline(
                case["title"], case["department"], case["alertType"],
                case["vacancies"], case["applyMode"],
            )
            with self.subTest(title=case["title"][:60]):
                self.assertEqual(headline, expected)

    def test_index_admit_card_alert_type_default_is_present(self):
        """A stored admit-card alert must never be headed as an application form."""
        self.assertRegex(INDEX, r"ALERT_TYPE_DEFAULTS\s*=\s*\{[^}]*'admit-card':\s*'Admit Card'")

    def test_card_table_and_reminder_headings_use_the_short_headline(self):
        self.assertGreaterEqual(INDEX.count("escapeHtml(jobDisplayHeadline(job))"), 3)
        # Every rendered heading keeps the full official title as a tooltip.
        self.assertGreaterEqual(INDEX.count('title="${escapeHtml(job.title)}"'), 3)

    def test_full_title_is_still_used_for_details_search_and_schema(self):
        self.assertIn("document.getElementById('modalTitle').innerText = job.title;", INDEX)
        self.assertIn('"title": job.title || "Government Recruitment Notification"', INDEX)
        self.assertIn("navigator.share({ title: job.title", INDEX)


class WebsiteDomainRuleTests(unittest.TestCase):
    """A website link must never be a department name or headline text."""

    def test_detects_bare_domains(self):
        from short_headlines import is_website_domain
        for value in ("sbi.gov.in", "https://iitbhu.ac.in", "www.hau.ac.in/",
                      "iitbhu.aci.in", "http://bceceboard.bihar.gov.in/rec"):
            with self.subTest(value=value):
                self.assertTrue(is_website_domain(value))
        # Real authority names / text must NOT be treated as domains.
        for value in ("State Bank of India (SBI)", "Dr. B.R. Ambedkar University",
                      "Sahitya Akademi, New Delhi", "Punjab Subordinate Services Board"):
            with self.subTest(value=value):
                self.assertFalse(is_website_domain(value))

    def test_strips_domain_from_department(self):
        from short_headlines import strip_website_domains
        self.assertEqual(
            strip_website_domains("sbi.gov.in announced result"),
            "announced result",
        )
        # Bracketed year tails must survive.
        self.assertIn("(Advt No. 03/2026)",
                      strip_website_domains("Recruitment 2026 Re-Opened (Advt No. 03/2026)"))

    def test_department_never_a_domain(self):
        # A bare-domain department falls back to the title's authority segment.
        self.assertNotIn("iitbhu.ac.in", short_department("iitbhu.ac.in — alerts shortlisted"))
        self.assertTrue(short_department("Punjab Subordinate Services Selection Board (PSSSB)"))

    def test_headline_never_contains_a_domain(self):
        headline = short_job_headline(
            "sbi.gov.in announced result for PO posts", "sbi.gov.in", "result")
        self.assertNotIn("sbi.gov.in", headline)
        self.assertNotIn("iitbhu", short_job_headline(
            "iitbhu.ac.in alerts shortlisted candidates skill test", "iitbhu.ac.in", "result"))
        # Normal vacancies still build a proper headline.
        vacancy = short_job_headline(
            "Recruitment of 450 Clerk posts 2026", "Example Recruitment Board",
            "recruitment", "450 Posts")
        self.assertIn("450", vacancy)
        self.assertNotIn("example.gov.in", vacancy)


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
