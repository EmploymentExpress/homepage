"""Guard: every inline <script> in index.html must be syntactically valid JavaScript.

Regression from PR #17/#18: a corrupted duplicate block inside
updateSectionSummaries() left an unterminated string literal, so the browser
rejected the entire inline script and no job data (curated or automatic) ever
rendered — while every layout/parser test still passed. The homepage was broken
for hours because nothing checked the inline JS.

This test:
1. extracts every inline <script> block (external CDN scripts and the
   application/ld+json block are skipped), and
2. runs `node --check` on each when Node is available (GitHub Actions runners
   ship Node, so CI really does parse the scripts).

If you edit index.html's inline JavaScript, keep this green. If you
deliberately change the script structure, update this test in the same commit.
"""

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"

# Corrupted fragment that broke the main script (PR #17/#18). If it ever
# reappears, the inline script will not parse and the whole page stops
# rendering. Kept deliberately long so it cannot match legitimate code such as
# `jobDatabase.filter(job => ...)` (whose "database" also contains "ase.filter").
KNOWN_CORRUPTION_FRAGMENTS = (
    "'No open dated ase.filter(job => job.type === 'punjab')],",
)

# Inline scripts that are not plain JavaScript: JSON-LD blocks begin with "{"
# after whitespace. Do not key on "@context" alone — the main inline script
# legitimately contains the string "@context": "https://schema.org" inside
# injectJobPostingSchema(), and keying on that would skip the very script this
# test exists to guard.
def _is_json_ld(script: str) -> bool:
    return script.lstrip().startswith("{")


class InlineScriptSyntaxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.scripts = re.findall(
            r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
            cls.html,
            flags=re.DOTALL | re.IGNORECASE,
        )

    def test_index_contains_inline_scripts(self):
        self.assertGreater(len(self.scripts), 0, "No inline scripts found in index.html")

    def test_known_corruption_fragment_absent(self):
        for fragment in KNOWN_CORRUPTION_FRAGMENTS:
            self.assertNotIn(
                fragment,
                self.html,
                f"Known JS-corrupting fragment {fragment!r} found in index.html; "
                "the inline script cannot parse (see PR #18).",
            )

    def test_vacancy_sections_use_newest_first_order(self):
        self.assertIn("function sortNewestPublishedFirst(items)", self.html)
        self.assertGreaterEqual(
            self.html.count("sortNewestPublishedFirst("),
            5,
            "Punjab, Central, Admission and master-table renderers must keep newest notices first",
        )
        self.assertNotIn("sortByLastDateDesc(", self.html)

    def test_frontend_rejects_generic_titles_and_departments(self):
        self.assertIn("function jobTitleWithDepartment(title, department)", self.html)
        for bad_label in ("other links", "close menu", "work recruitments"):
            self.assertIn(f"'{bad_label}'", self.html)
        self.assertIn("'official recruitment notice'", self.html)

    def test_frontend_never_uses_website_link_as_department_or_headline(self):
        # The inline headline generator must strip website links.
        self.assertIn("function isWebsiteDomain(value)", self.html)
        self.assertIn("function stripWebsiteDomains(value)", self.html)
        self.assertIn("department = stripWebsiteDomains(department);", self.html)
        self.assertIn("const rawTitle = stripWebsiteDomains(headlineClean(title));", self.html)

    @unittest.skipUnless(shutil.which("node"), "node executable not available")
    def test_strip_website_domains_in_frontend(self):
        # Extract the helper functions and exercise them under node.
        big = max(self.scripts, key=len)
        snippet = "\n".join(line for line in big.splitlines() if not line.strip().startswith("//"))
        harness = """
        %s
        const cases = [
          ["sbi.gov.in announced result for PO posts", true],
          ["https://iitbhu.ac.in latest vacancy", true],
          ["State Bank of India (SBI) — Result", false],
          ["Craft Instructor 2026 Re-Opened (Advt No. 03/2026)", false],
        ];
        for (const [text, shouldStrip] of cases) {
          const out = stripWebsiteDomains(text);
          if (/\\b(?:https?:\\/\\/)?(?:www\\.)?[a-z0-9-]+(?:\\.[a-z0-9-]+)+\\b/i.test(out)) {
            throw new Error("domain leaked into: " + out);
          }
        }
        if (isWebsiteDomain("sbi.gov.in") !== true) throw new Error("sbi domain not detected");
        if (isWebsiteDomain("State Bank of India (SBI)") !== false) throw new Error("false domain");
        if (!stripWebsiteDomains("Craft Instructor (Advt No. 03/2026)").includes("(Advt No. 03/2026)"))
          throw new Error("bracketed advt number was stripped");
        """
        # Provide the function bodies: pull from WEBSITE_DOMAIN_RE through stripWebsiteDomains.
        start = snippet.index("const WEBSITE_DOMAIN_RE")
        end = snippet.index("function escapeRegExp")
        helpers = snippet[start:end]
        script = helpers + "\nfunction headlineClean(v){return String(v==null?'':v).replace(/\\s+/g,' ').trim();}\n" + (harness % "")
        result = subprocess.run(["node", "--check"], input=script.encode("utf-8"),
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        run = subprocess.run(["node", "-e", script], capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr.decode("utf-8", "replace"))

    def test_extended_deadlines_are_excluded_from_last_date_reminders(self):
        self.assertIn(".filter(job => job.lastDateExtended !== true)", self.html)

    def test_extended_deadline_tag_is_in_relevant_vacancy_columns(self):
        self.assertIn("Last Date Extended", self.html)
        self.assertIn("renderJobSectionCard(job,", self.html)
        self.assertIn("job.originalLastDate", self.html)
        self.assertIn("job.extensionNoticeUrl", self.html)

    def test_extended_deadline_tag_is_in_job_details_modal_only_when_extended(self):
        self.assertIn("modalExtendedBadge", self.html)
        self.assertIn("modalLastDateExtendedTag", self.html)
        self.assertIn("modalEndDateExtendedTag", self.html)
        self.assertIn("modalExtensionNoticeBanner", self.html)
        self.assertIn("const isExtended = Boolean(job && job.lastDateExtended === true);", self.html)

    def test_headline_department_name_is_always_in_capital_letter(self):
        self.assertIn("return headlineClean(short).toUpperCase();", self.html)

    @unittest.skipUnless(shutil.which("node"), "node executable not available")
    def test_inline_scripts_parse_with_node(self):
        for index, script in enumerate(self.scripts):
            if _is_json_ld(script):
                continue
            with self.subTest(inline_script=index):
                result = subprocess.run(
                    ["node", "--check"],
                    input=script.encode("utf-8"),
                    capture_output=True,
                    timeout=30,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    msg=(
                        f"inline script #{index} failed `node --check`:\n"
                        f"{result.stderr.decode('utf-8', 'replace')}"
                    ),
                )


if __name__ == "__main__":
    unittest.main()
