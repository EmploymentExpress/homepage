"""Guard tests for the job-details headline rule (see AGENTS.md).

The rule: every published job-details heading is generated from the official
notification as

    <Department name> <Post name(s)> Recruitment | Apply Online/Offline

with 2-4 different posts listed by name, "Various Post" when the notice names
more than 4, and the single post name when only one is named. Non-recruitment
notices are headed "<Department name> <Notice type>" (e.g. "SBI Admit Card")
with no apply-mode suffix. Interview call letters are admit-card notices and
must reach the Admit Card column.
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
    NOTICE_SUFFIXES,
    apply_mode_suffix,
    headline_posts,
    headline_suffix,
    notice_type,
    short_department,
    short_job_headline,
    smart_title_case,
)

AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
AUTO_JOBS = json.loads((ROOT / "data" / "auto-jobs.json").read_text(encoding="utf-8"))

PGIMER = "Postgraduate Institute of Medical Education and Research (PGIMER), Chandigarh"


class DepartmentTests(unittest.TestCase):
    def test_department_short_form_prefers_official_acronym(self):
        self.assertEqual(
            short_department("Punjab State Legal Services Authority (PULSA)"), "PULSA"
        )
        self.assertEqual(
            short_department("Postgraduate Institute of Medical Education and Research (PGIMER), Chandigarh"),
            "PGIMER Chandigarh",
        )
        self.assertEqual(
            short_department("Central University of Punjab (CUPB), Bathinda"), "CUPB Bathinda"
        )

    def test_department_keeps_state_visible_when_acronym_hides_it(self):
        self.assertEqual(
            short_department("Haryana Women and Child Development Department (WCD), Panchkula"),
            "Haryana WCD",
        )
        self.assertTrue(
            short_department("Local Audit Department, Chandigarh Administration")
            .endswith("Chandigarh")
        )

    def test_department_name_is_title_case_not_all_caps(self):
        cases = [
            ("Punjab Police Constable", "Punjab Police", "Punjab Police"),
            ("Join Indian Army Rally", "Indian Army", "Indian Army"),
            ("Ministry of Defence ASC", "Ministry of Defence", "Ministry of Defence"),
            ("Local Audit Department", "Local Audit Department", "Local Audit Dept."),
            ("Department of Industries", "Department of Industries", "Industries Dept."),
            ("Sainik School Recruitment", "Sainik School", "Sainik School"),
        ]
        for title, dept, expected in cases:
            with self.subTest(dept=dept):
                self.assertEqual(short_department(dept, title), expected)

    def test_department_short_form_is_length_capped(self):
        short = short_department(
            "Chandigarh Institute for Transformation, Planning & Evaluation Organization, "
            "Chandigarh Administration"
        )
        self.assertLessEqual(len(short), 34)

    def test_smart_title_case_keeps_acronyms_capitalised(self):
        # ALL-CAPS tokens (acronyms) keep their capitals; lowercase words are capitalised.
        self.assertEqual(smart_title_case("DEO, mts, pharmacist"), "DEO, Mts, Pharmacist")
        self.assertEqual(smart_title_case("PGIMER chandigarh"), "PGIMER Chandigarh")
        self.assertEqual(smart_title_case("ministry of defence"), "Ministry of Defence")
        self.assertEqual(smart_title_case("class 6th"), "Class 6th")


class PostNameRuleTests(unittest.TestCase):
    def test_single_post_is_named(self):
        self.assertEqual(
            short_job_headline(
                "PGIMER Chandigarh — Recruitment of Nursing Officer 2026", PGIMER,
                "recruitment", "52 Posts", "Online"),
            "PGIMER Chandigarh Nursing Officer Recruitment | Apply Online",
        )

    def test_two_to_four_posts_are_all_listed(self):
        self.assertEqual(
            short_job_headline(
                "PGIMER Chandigarh — Recruitment of DEO, MTS and Pharmacist 2026", PGIMER,
                "recruitment", "120 Posts", "Online"),
            "PGIMER Chandigarh DEO, MTS, Pharmacist Recruitment | Apply Online",
        )
        self.assertEqual(
            short_job_headline(
                "High Court of Punjab and Haryana (PHHC) — Driver, Frash, Safai Sewak & Mali Recruitment 2026",
                "High Court of Punjab and Haryana (PHHC)", "recruitment", "223 Posts",
                "Online / As Notified"),
            "PHHC Driver, Frash, Safai Sewak, Mali Recruitment | Apply Online",
        )

    def test_more_than_four_posts_collapse_to_various_post(self):
        self.assertEqual(
            short_job_headline(
                "PGIMER Chandigarh — Recruitment of MTS, DEO, Pharmacist, Stenographer and Driver 2026",
                PGIMER, "recruitment", "300 Posts", "Offline"),
            "PGIMER Chandigarh Various Post Recruitment | Apply Offline",
        )

    def test_various_posts_notice_uses_various_post(self):
        self.assertEqual(
            short_job_headline(
                "PGIMER Chandigarh — Recruitment for various posts 2026", PGIMER,
                "recruitment", "Various Posts", "Online"),
            "PGIMER Chandigarh Various Post Recruitment | Apply Online",
        )
        self.assertEqual(
            headline_posts("PGIMER Chandigarh — MTS, DEO and various other posts", PGIMER),
            ["Various Post"],
        )

    def test_no_post_named_is_department_only(self):
        self.assertEqual(
            short_job_headline(
                "PGIMER Chandigarh — Recruitment 2026", PGIMER,
                "recruitment", "See Notification", "Online"),
            "PGIMER Chandigarh Recruitment | Apply Online",
        )

    def test_vacancy_count_is_never_in_the_headline(self):
        headline = short_job_headline(
            "PSSSB Clerk, Typist & Data Entry Operator 2026",
            "Punjab Subordinate Services Selection Board (PSSSB)",
            "recruitment", "450 Posts", "Online",
        )
        self.assertEqual(headline, "PSSSB Clerk, Typist, Data Entry Operator Recruitment | Apply Online")
        self.assertNotIn("450", headline)


class ApplyModeTests(unittest.TestCase):
    def test_apply_mode_wording(self):
        self.assertEqual(apply_mode_suffix("Online"), "Apply Online")
        self.assertEqual(apply_mode_suffix("Online / As Notified"), "Apply Online")
        self.assertEqual(apply_mode_suffix("Offline"), "Apply Offline")
        self.assertEqual(apply_mode_suffix("Offline (Form Download)"), "Apply Offline")
        self.assertEqual(apply_mode_suffix(""), "Apply Online")

    def test_by_post_notice_is_offline(self):
        self.assertEqual(
            short_job_headline(
                "PGIMER Chandigarh — Nursing Officer recruitment, apply by post", PGIMER,
                "recruitment", "20 Posts", ""),
            "PGIMER Chandigarh Nursing Officer Recruitment | Apply Offline",
        )

    def test_recruitment_ending_carries_the_apply_mode(self):
        self.assertEqual(
            headline_suffix("Recruitment", "", "Offline"), "Recruitment | Apply Offline")
        self.assertEqual(
            headline_suffix("Recruitment", "", "Online"), "Recruitment | Apply Online")
        self.assertEqual(headline_suffix("Recruitment"), "Recruitment | Apply Online")


class NonRecruitmentHeadlineTests(unittest.TestCase):
    def test_call_letter_is_department_plus_admit_card(self):
        self.assertEqual(
            short_job_headline(
                "State Bank of India (SBI) — CALL LETTER LINK DOWNLOAD PRELIMINARY EXAMINATION CALL LETTER",
                "State Bank of India (SBI)", "admit-card", "15 Posts", "Online / As Notified"),
            "SBI Admit Card",
        )

    def test_interview_call_letter_is_admit_card(self):
        self.assertEqual(
            short_job_headline(
                "Punjab Agricultural University (PAU), Ludhiana — Interview call letter for Lab Helper",
                "Punjab Agricultural University (PAU), Ludhiana", "admit-card", "", ""),
            "PAU Ludhiana Admit Card",
        )

    def test_result_is_department_plus_type(self):
        self.assertEqual(
            short_job_headline(
                "Punjab State Legal Services Authority (PULSA) — View, Public notice "
                "regarding result for the post of Process Server (selection of candidate "
                "from the Ex-servicemen category) PDF 383 KB - opens in a new window View",
                "Punjab State Legal Services Authority (PULSA)", "result", "22 Posts",
                "Online / As Notified"),
            "PULSA Result",
        )

    def test_non_recruitment_headlines_have_no_apply_mode(self):
        for title, alert_type in [
            ("Board — Final result of Clerk exam", "result"),
            ("Board — Answer key and objections", "answer-key"),
            ("Board — Corrigendum to Advt No. 03/2026", "corrigendum"),
            ("Board — Interview call letter download", "admit-card"),
        ]:
            with self.subTest(title=title):
                headline = short_job_headline(title, "Punjab Test Board", alert_type, "", "")
                self.assertNotIn("Apply Online", headline)
                self.assertNotIn("Apply Offline", headline)

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
            "Waiting list for the post of Driver": "Waiting List",
            "Result of written test for Clerk": "Result",
            "Walk-in interview for Senior Resident": "Walk-in Interview",
            "Admission open for B.Sc Nursing course": "Admission",
            "Public notice regarding document verification": "Notice",
            "Recruitment of 90 Assistant posts": "Recruitment",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(notice_type(title), expected)

    def test_every_notice_type_has_headline_wording(self):
        for label, suffix in NOTICE_SUFFIXES.items():
            with self.subTest(label=label):
                self.assertTrue(suffix.strip())
        self.assertEqual(
            headline_suffix("Postponed", "Postponement of interview for Lab Helper"),
            "Interview Postponed",
        )
        self.assertEqual(headline_suffix("Cancelled", "Exam cancelled"), "Exam Cancelled")
        self.assertEqual(headline_suffix("Answer Key", "Exam answer key"), "Exam Answer Key")


class HeadlineQualityTests(unittest.TestCase):
    def test_every_auto_job_gets_a_usable_headline(self):
        endings = set(NOTICE_SUFFIXES.values()) | {
            "Recruitment | Apply Online", "Recruitment | Apply Offline",
            "Exam Cancelled", "Interview Postponed", "Exam Answer Key",
        }
        for job in AUTO_JOBS.get("jobs", []):
            headline = short_job_headline(
                job.get("title", ""), job.get("department", ""), job.get("alertType", ""),
                job.get("vacancies", ""), job.get("applyMode", ""),
            )
            with self.subTest(title=job.get("title", "")[:60]):
                self.assertTrue(headline, "headline must never be empty")
                self.assertTrue(
                    any(headline.endswith(ending) for ending in endings),
                    f"headline must end with an approved notice ending: {headline}",
                )
                # Portal noise must never survive into a heading.
                self.assertNotRegex(headline, r"(?i)\bPDF \d|opens in a new window|click here|^view\b")
                # A heading is never only the notice ending.
                self.assertGreater(len(headline.split()), 1)

    def test_headline_has_no_length_cap(self):
        headline = short_job_headline(
            "Ministry of Defence Army ASC Centre Fireman, Librarian, Fire Engine Driver and "
            "Sub Officer recruitment 2026",
            "Ministry of Defence", "recruitment", "66 Posts", "Offline",
        )
        self.assertGreater(len(headline), 72)
        self.assertTrue(headline.endswith("Recruitment | Apply Offline"))

    def test_curated_titles_still_parse(self):
        pattern = re.compile(r'title:\s*"((?:[^"\\]|\\.)*)"')
        titles = [t.replace('\\"', '"') for t in pattern.findall(INDEX)]
        self.assertTrue(titles, "curated job titles must be readable from index.html")
        for title in titles:
            with self.subTest(title=title[:50]):
                self.assertGreaterEqual(len(title.split()), 2)


class IndexHeadlineWiringTests(unittest.TestCase):
    """index.html renders the headline but keeps the full title as data."""

    def test_index_defines_the_shared_headline_helpers(self):
        for helper in ("function shortJobHeadline(", "function jobDisplayHeadline(",
                       "function shortDepartment(", "function noticeType(", "function headlineSuffix(",
                       "function headlinePosts(", "function applyModeSuffix(", "function smartTitleCase("):
            with self.subTest(helper=helper):
                self.assertIn(helper, INDEX)

    def test_index_headline_vocabulary_matches_the_python_implementation(self):
        for suffix in NOTICE_SUFFIXES.values():
            with self.subTest(suffix=suffix):
                self.assertIn(suffix, INDEX)
        self.assertIn("SHORT_DEPARTMENT_MAX = 34", INDEX)
        self.assertIn("Recruitment | ${applyModeSuffix(applyMode, title)}", INDEX)
        self.assertGreaterEqual(INDEX.count("escapeHtml(jobDisplayHeadline(job))"), 3)
        # Every rendered heading keeps the full official title as a tooltip.
        self.assertGreaterEqual(INDEX.count('title="${escapeHtml(job.title)}"'), 3)

    def test_admit_card_alert_type_is_allowed_and_routed_to_the_admit_column(self):
        """Interview call letters must reach the Admit Card column, not become recruitment."""
        self.assertRegex(
            INDEX,
            r"allowedAlertTypes\s*=\s*\[[^\]]*'admit-card'[^\]]*\]",
        )
        self.assertIn("'admit-card': isNewNotice ? ['NEW ADMIT CARD', 'bg-emerald-600'] : ['ADMIT CARD', 'bg-emerald-600']", INDEX)
        self.assertIn("automaticAlerts.filter(alert => alert.alertType === 'admit-card')", INDEX)
        # ALERT_TYPE_DEFAULTS must keep the admit-card wording too.
        self.assertRegex(INDEX, r"ALERT_TYPE_DEFAULTS\s*=\s*\{[^}]*'admit-card':\s*'Admit Card'")

    def test_full_title_is_still_used_for_details_search_and_schema(self):
        self.assertIn("document.getElementById('modalTitle').innerText = job.title;", INDEX)
        self.assertIn('"title": job.title || "Government Recruitment Notification"', INDEX)
        self.assertIn("navigator.share({ title: job.title", INDEX)

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
                  "vacancies": "15 Posts", "applyMode": "Online / As Notified"},
                 {"title": "PGIMER Chandigarh — Recruitment of DEO, MTS and Pharmacist 2026",
                  "department": PGIMER, "alertType": "recruitment",
                  "vacancies": "120 Posts", "applyMode": "Online"},
                 {"title": "PGIMER Chandigarh — Recruitment of MTS, DEO, Pharmacist, Steno, Driver 2026",
                  "department": PGIMER, "alertType": "recruitment",
                  "vacancies": "300 Posts", "applyMode": "Offline"}]
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
                "const cases=JSON.parse(fs.readFileSync(process.argv[3]));\n"
                "const jobDisplayHeadline=new Function(code+'\\nreturn jobDisplayHeadline;')();\n"
                "process.stdout.write(JSON.stringify(cases.map(jobDisplayHeadline)));\n",
                encoding="utf-8",
            )
            rendered = subprocess.run(
                [sys.executable and "node", str(root / "run.js"), str(root / "mirror.js"), str(root / "cases.json")],
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
        self.assertIn("Clerk", vacancy)
        self.assertNotIn("example.gov.in", vacancy)


class AgentsRuleTests(unittest.TestCase):
    def test_agents_documents_the_headline_rule(self):
        self.assertIn("Job-details headline rule", AGENTS)
        self.assertIn("Recruitment | Apply Online", AGENTS)
        self.assertIn("Recruitment | Apply Offline", AGENTS)
        self.assertIn("Various Post", AGENTS)
        self.assertIn("Interview call letters are admit-card notices", AGENTS)
        self.assertIn("scripts/short_headlines.py", AGENTS)
        self.assertIn("No vacancy count in the headline", AGENTS)

    def test_rule_vocabulary_matches_the_implementation(self):
        for suffix in NOTICE_SUFFIXES.values():
            with self.subTest(suffix=suffix):
                self.assertIn(suffix, AGENTS)


if __name__ == "__main__":
    unittest.main()
