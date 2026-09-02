"""Column membership: an all-India notice may be cross-listed in Punjab.

`data/auto-jobs.json` records carry one home column in ``type`` (the authority
that owns the notice). The optional ``alsoInPunjab`` flag lists that same single
record in the "Latest Punjab Jobs" column too, so a verified all-India
recruitment that Punjab candidates can apply to is reachable from both columns
without pretending the recruiting authority is a Punjab department, without a
duplicate record (the pipeline de-duplicates published alerts on title +
notification URL, so a copy would not survive), and without touching the
record's JobPosting address.

``CrossListedColumnRenderTests`` runs the real renderers from index.html in Node
and inspects the markup each column actually receives.
"""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
AUTO_JOBS = ROOT / "data" / "auto-jobs.json"

# The published store's cross-listed alerts, read once for the data-side checks.
STORE = json.loads(AUTO_JOBS.read_text(encoding="utf8"))
FLAGGED = sorted(job["id"] for job in STORE["jobs"] if job.get("alsoInPunjab") is True)

_CARDS = re.compile(r"openJobDetail\((\d+)\)")


class CrossListedColumnRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node executable not available")
        result = subprocess.run(
            ["node", "-e", cls._runner_js()], capture_output=True, text=True, timeout=90
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to render columns via Node: {result.stderr}")
        cls.out = json.loads(result.stdout)
        cls.out["punjabCards"] = cls._cards(cls.out.pop("punjabHtml"))
        cls.out["centralCards"] = cls._cards(cls.out.pop("centralHtml"))

    @staticmethod
    def _cards(html: str) -> list:
        """The ids the column markup actually offers, in render order."""
        return [int(match) for match in _CARDS.findall(html or "")]

    @staticmethod
    def _runner_js() -> str:
        # No regular expressions inside this block: it is embedded in a JS
        # template literal, which would eat backslash escapes.
        return f"""
const fs = require('fs');
const autoJobsData = JSON.parse(fs.readFileSync({json.dumps(str(AUTO_JOBS))}, 'utf8'));
const elements = new Map();
const element = (id) => {{
    if (!elements.has(id)) {{
        elements.set(id, {{ id, innerText: '', innerHTML: '', textContent: '', value: '', href: '',
            style: {{}}, classList: {{ remove: () => {{}}, add: () => {{}}, toggle: () => {{}} }},
            addEventListener: () => {{}}, remove: () => {{}}, appendChild: () => {{}},
            insertAdjacentHTML: () => {{}} }});
    }}
    return elements.get(id);
}};
globalThis.__element = element;
const document = {{
    getElementById: element,
    querySelectorAll: () => [],
    querySelector: () => null,
    createElement: () => ({{ type: '', id: '', textContent: '' }}),
    head: {{ appendChild: () => {{}} }},
    title: 'EMPLOYMENT EXPRESS',
    body: {{ appendChild: () => {{}}, removeChild: () => {{}} }}
}};
const window = {{
    location: {{ origin: 'https://employmentexpress.github.io', pathname: '/homepage/', search: '' }},
    addEventListener: () => {{}}, setInterval: () => {{}},
    history: {{ replaceState: () => {{}}, pushState: () => {{}} }}
}};
let mainScript = '';
for (const tag of fs.readFileSync({json.dumps(str(INDEX))}, 'utf8')
        .match(/<script(?![^>]*\\bsrc=)[^>]*>([\\s\\S]*?)<\\/script>/gi) || []) {{
    const content = tag.replace(/<script[^>]*>/i, '').replace(/<\\/script>/i, '');
    if (content.includes('renderPunjabColumn')) {{ mainScript = content; break; }}
}}
global.fetch = async () => ({{ ok: true, json: async () => autoJobsData }});
const AsyncFunction = Object.getPrototypeOf(async function(){{}}).constructor;
const runner = new AsyncFunction('document', 'window', 'fetch', mainScript + `
  await loadAutomaticJobs();
  jobDatabase = prepareVisibleVacancies(jobDatabase);
  renderPunjabColumn();
  renderCentralColumn();
  updateSectionSummaries();
  const raw = (id) => String(globalThis.__element(id).innerHTML || '');
  const textOf = (id) => String(globalThis.__element(id).textContent || '');
  const flagged = [];
  const unflaggedCentral = [];
  const punjabHome = [];
  const describe = (job) => ({{
      id: job.id, type: job.type, alsoInPunjab: job.alsoInPunjab === true,
      lastDate: String(job.lastDate || ''),
      punjab: jobInColumn(job, 'punjab'), central: jobInColumn(job, 'central')
  }});
  for (const job of jobDatabase) {{
      if (job.alsoInPunjab === true) flagged.push(describe(job));
      else if (job.type === 'central') unflaggedCentral.push(describe(job));
      else if (job.type === 'punjab') punjabHome.push(describe(job));
  }}
  return {{
      punjabHtml: raw('punjab-jobs-list'),
      centralHtml: raw('central-jobs-list'),
      punjabMeta: textOf('punjab-section-meta'),
      centralMeta: textOf('central-section-meta'),
      punjabLastDates: jobDatabase.filter(j => jobInColumn(j, 'punjab')).map(j => String(j.lastDate || '')),
      centralLastDates: jobDatabase.filter(j => jobInColumn(j, 'central')).map(j => String(j.lastDate || '')),
      flagged, unflaggedCentral: unflaggedCentral.slice(0, 8), punjabHome: punjabHome.slice(0, 4)
  }};
`);
runner(document, window, global.fetch).then(r => process.stdout.write(JSON.stringify(r)))
    .catch(err => {{ console.error(err); process.exit(1); }});
"""

    def test_cross_listed_alert_renders_in_both_columns(self):
        self.assertTrue(FLAGGED, "expected at least one alsoInPunjab alert in the store")
        for job_id in FLAGGED:
            self.assertIn(job_id, self.out["punjabCards"], "cross-listed alert missing from Punjab column")
            self.assertIn(job_id, self.out["centralCards"], "cross-listed alert missing from Central column")

    def test_each_record_is_rendered_once_per_column(self):
        for name in ("punjabCards", "centralCards"):
            ids = self.out[name]
            self.assertTrue(ids, f"{name} rendered no cards at all")
            self.assertEqual(len(ids), len(set(ids)), f"{name} rendered a record more than once")

    def test_central_alerts_are_not_absorbed_into_the_punjab_column(self):
        for job in self.out["unflaggedCentral"]:
            self.assertFalse(job["punjab"], f"unflagged central alert {job['id']} leaked into the Punjab column")
            self.assertTrue(job["central"])
        self.assertTrue(self.out["flagged"], "no cross-listed alert reached the page")
        self.assertTrue(all(job["alsoInPunjab"] and job["punjab"] and job["central"] for job in self.out["flagged"]))

    def test_punjab_home_alerts_stay_out_of_the_central_column(self):
        self.assertTrue(self.out["punjabHome"], "the Punjab column rendered no home-Punjab record")
        for job in self.out["punjabHome"]:
            self.assertTrue(job["punjab"])
            self.assertFalse(job["central"], "cross-listing is one-directional; Punjab notices must not flood Central")

    def test_section_summaries_are_built_from_the_same_filtered_sets(self):
        # Each column header publishes its nearest last date, derived from the same
        # filtered set the cards come from, so a cross-listed deadline has to be
        # visible to the Punjab summary as well instead of only to Central.
        for label, meta, dates in (("Punjab", self.out["punjabMeta"], self.out["punjabLastDates"]),
                                   ("Central", self.out["centralMeta"], self.out["centralLastDates"])):
            text = str(meta)
            if text.startswith("Nearest last date:"):
                self.assertIn(text.split(":", 1)[1].strip(), dates,
                              f"{label} summary quotes a date outside the column's own records")
            else:
                self.assertEqual(text, "No open dated applications")
        for job in self.out["flagged"]:
            self.assertIn(job["lastDate"], self.out["punjabLastDates"])


class ColumnMembershipContractTests(unittest.TestCase):
    """Every column partition must go through the one shared predicate."""

    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf8")
        cls.script = "\n".join(
            tag for tag in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", cls.html)
            if "renderPunjabColumn" in tag
        )

    def test_no_column_partition_bypasses_the_predicate(self):
        offenders = re.findall(r"jobDatabase\s*\.\s*filter\(\s*job\s*=>\s*job\.type\s*===\s*'(?:punjab|central)'",
                               self.script)
        self.assertEqual(
            offenders, [],
            "a column filter was re-added on job.type alone; use jobInColumn(job, column) so "
            "cross-listed alerts keep appearing in both columns",
        )

    def test_predicate_is_used_by_both_columns_and_both_summaries(self):
        for column in ("'punjab'", "'central'"):
            self.assertEqual(
                len(re.findall(r"jobInColumn\(job, " + re.escape(column) + r"\)", self.script)), 2,
                f"expected one column render and one section summary for {column}",
            )

    def test_normalizer_carries_the_flag_from_the_published_store(self):
        self.assertTrue(
            "alsoInPunjab: raw.alsoInPunjab === true" in self.script,
            "normalizeAutomaticJob() does not carry alsoInPunjab, so the flag in "
            "data/auto-jobs.json would never reach the rendered columns",
        )

    def test_punjab_listing_is_searchable(self):
        # The Punjab column is also a discovery surface: typing "punjab" has to
        # find a notice that is listed there, even though its own text says
        # "All India".
        self.assertRegex(self.script, r"job\.alsoInPunjab \? 'punjab' : '',")

    def test_cross_listed_records_keep_one_home_column_and_real_links(self):
        for job in STORE["jobs"]:
            if not job.get("alsoInPunjab"):
                self.assertNotIn("alsoInPunjab", job, "omit the field instead of storing false")
                continue
            self.assertEqual(job["type"], "central", "a cross-listed record's home column must be Central")
            self.assertTrue(str(job.get("pdfLink", "")).startswith("https://"), "cross-listing needs a real notice")
            self.assertNotIn("Punjab", str(job.get("department", "")),
                            "the authority must stay the real one; only the column listing is shared")


if __name__ == "__main__":
    unittest.main()
