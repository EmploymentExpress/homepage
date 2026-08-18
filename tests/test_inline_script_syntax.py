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

# Inline scripts that are not plain JavaScript.
NON_JS_MARKERS = ("@context",)


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

    @unittest.skipUnless(shutil.which("node"), "node executable not available")
    def test_inline_scripts_parse_with_node(self):
        for index, script in enumerate(self.scripts):
            if any(marker in script for marker in NON_JS_MARKERS):
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
