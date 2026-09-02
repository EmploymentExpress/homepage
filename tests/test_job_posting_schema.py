"""Test JobPosting Schema.org JSON-LD generation.

Verifies that the dynamic JobPosting schema injected on index.html satisfies
all Google Search Console requirements (critical and non-critical fields):
- datePosted (Critical)
- validThrough (Non-critical)
- jobLocation.address.streetAddress (Non-critical)
- jobLocation.address.addressRegion (Non-critical)
- jobLocation.address.postalCode (Non-critical)
- jobLocation.address.addressLocality
- jobLocation.address.addressCountry
- baseSalary (MonetaryAmount in INR) (Non-critical)
- title, description, hiringOrganization, identifier
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


class JobPostingSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        if not shutil.which("node"):
            raise unittest.SkipTest("node executable not available")

        # Execute JavaScript in Node environment simulating browser DOMContentLoaded
        runner_js = f"""
const fs = require('fs');
const autoJobsData = JSON.parse(fs.readFileSync({json.dumps(str(AUTO_JOBS))}, 'utf8'));

// Minimal browser DOM mockup
let injectedSchema = null;
const createMockElement = () => ({{
    innerText: '',
    innerHTML: '',
    textContent: '',
    value: '',
    href: '',
    style: {{}},
    classList: {{ remove: () => {{}}, add: () => {{}}, toggle: () => {{}} }},
    addEventListener: () => {{}},
    remove: () => {{}}
}});

const document = {{
    getElementById: (id) => {{
        if (id === 'dynamic-job-schema') return null;
        return createMockElement();
    }},
    querySelectorAll: () => [],
    querySelector: () => null,
    createElement: (tag) => {{
        const el = createMockElement();
        el.type = '';
        el.id = '';
        return el;
    }},
    head: {{
        appendChild: (el) => {{
            if (el.id === 'dynamic-job-schema') {{
                injectedSchema = JSON.parse(el.textContent);
            }}
        }}
    }},
    title: 'EMPLOYMENT EXPRESS',
    body: {{ appendChild: () => {{}}, removeChild: () => {{}} }}
}};

const window = {{
    location: {{ origin: 'https://employmentexpress.github.io', pathname: '/homepage/', search: '' }},
    addEventListener: () => {{}},
    setInterval: () => {{}},
    history: {{ replaceState: () => {{}}, pushState: () => {{}} }}
}};

// Extract JS script from HTML
const html = fs.readFileSync({json.dumps(str(INDEX))}, 'utf8');
const scriptMatches = html.match(/<script(?![^>]*\\bsrc=)[^>]*>([\\s\\S]*?)<\\/script>/gi);
let mainScript = '';
for (const tag of scriptMatches) {{
    const content = tag.replace(/<script[^>]*>/i, '').replace(/<\\/script>/i, '');
    if (content.includes('injectJobPostingSchema')) {{
        mainScript = content;
        break;
    }}
}}

// Mock fetch for loadAutomaticJobs
global.fetch = async (url) => {{
    return {{
        ok: true,
        json: async () => autoJobsData
    }};
}};

// Run the script
const AsyncFunction = Object.getPrototypeOf(async function(){{}}).constructor;
const runner = new AsyncFunction('document', 'window', 'fetch', mainScript + '; await loadAutomaticJobs(); jobDatabase = prepareVisibleVacancies(jobDatabase); injectJobPostingSchema(); return injectedSchema;');

runner(document, window, global.fetch).then(schema => {{
    process.stdout.write(JSON.stringify(schema));
}}).catch(err => {{
    console.error(err);
    process.exit(1);
}});
"""
        result = subprocess.run(
            ["node", "-e", runner_js],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to generate schema via Node: {result.stderr}")

        cls.schema = json.loads(result.stdout)

    def test_schema_structure(self):
        self.assertEqual(self.schema.get("@context"), "https://schema.org")
        self.assertEqual(self.schema.get("@type"), "ItemList")
        self.assertIsInstance(self.schema.get("itemListElement"), list)
        self.assertGreater(len(self.schema["itemListElement"]), 0)

    def test_all_jobs_have_required_and_recommended_fields(self):
        for index, item_wrapper in enumerate(self.schema["itemListElement"]):
            posting = item_wrapper.get("item", {})
            title = posting.get("title", f"Index {index}")

            with self.subTest(job_title=title):
                # 1. Type
                self.assertEqual(posting.get("@type"), "JobPosting")

                # 2. Critical: datePosted
                date_posted = posting.get("datePosted")
                self.assertIsInstance(date_posted, str, f"Missing datePosted for {title}")
                self.assertRegex(
                    date_posted,
                    r"^\d{4}-\d{2}-\d{2}",
                    f"Invalid datePosted format for {title}: {date_posted}",
                )

                # 3. Non-critical: validThrough
                valid_through = posting.get("validThrough")
                self.assertIsInstance(valid_through, str, f"Missing validThrough for {title}")
                self.assertRegex(
                    valid_through,
                    r"^\d{4}-\d{2}-\d{2}",
                    f"Invalid validThrough format for {title}: {valid_through}",
                )

                # 4. Job Location with PostalAddress
                job_loc = posting.get("jobLocation")
                self.assertIsInstance(job_loc, dict, f"Missing jobLocation for {title}")
                self.assertEqual(job_loc.get("@type"), "Place")
                addr = job_loc.get("address")
                self.assertIsInstance(addr, dict, f"Missing jobLocation.address for {title}")
                self.assertEqual(addr.get("@type"), "PostalAddress")

                # Non-critical: streetAddress
                self.assertTrue(addr.get("streetAddress"), f"Missing streetAddress for {title}")
                # Non-critical: addressRegion
                self.assertTrue(addr.get("addressRegion"), f"Missing addressRegion for {title}")
                # Non-critical: postalCode
                self.assertTrue(addr.get("postalCode"), f"Missing postalCode for {title}")
                # Locality & Country
                self.assertTrue(addr.get("addressLocality"), f"Missing addressLocality for {title}")
                self.assertEqual(addr.get("addressCountry"), "IN")

                # 5. Non-critical: baseSalary
                salary = posting.get("baseSalary")
                self.assertIsInstance(salary, dict, f"Missing baseSalary for {title}")
                self.assertEqual(salary.get("@type"), "MonetaryAmount")
                self.assertEqual(salary.get("currency"), "INR")
                val = salary.get("value")
                self.assertIsInstance(val, dict, f"Missing baseSalary.value for {title}")
                self.assertEqual(val.get("@type"), "QuantitativeValue")
                self.assertEqual(val.get("unitText"), "MONTH")
                if "value" in val:
                    self.assertIsInstance(val["value"], (int, float))
                    self.assertGreater(val["value"], 0)
                else:
                    self.assertIn("minValue", val)
                    self.assertIn("maxValue", val)
                    self.assertIsInstance(val["minValue"], (int, float))
                    self.assertIsInstance(val["maxValue"], (int, float))
                    self.assertLessEqual(val["minValue"], val["maxValue"])

                # 6. Basic fields
                self.assertTrue(posting.get("title"))
                self.assertTrue(posting.get("description"))
                self.assertIn("hiringOrganization", posting)
                self.assertTrue(posting["hiringOrganization"].get("name"))
                self.assertIn("identifier", posting)
                self.assertTrue(posting["identifier"].get("value"))


class SchemaLocationMatchTests(unittest.TestCase):
    """getSchemaJobLocation() must match authority names, not word fragments.

    A bare ``loc.includes('nal')`` test (National Aerospace Laboratory) also
    matched the "nal" inside "Re*gal*ional Rural Banks" and "provisio*nal*ly",
    which moved dozens of unrelated alerts to a Bengaluru street address in the
    structured data. The same trap applies to any future fragment match, so the
    rule is checked over the whole published dataset, not just one record.
    """

    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node executable not available")
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.results = json.loads(subprocess.run(
            ["node", "-e", cls._runner_js()], capture_output=True, text=True, timeout=60
        ).stdout)

    @staticmethod
    def _runner_js() -> str:
        return f"""
const fs = require('fs');
const autoJobsData = JSON.parse(fs.readFileSync({json.dumps(str(AUTO_JOBS))}, 'utf8'));
globalThis.__jobs = autoJobsData.jobs;
const createMockElement = () => ({{ innerText: '', innerHTML: '', textContent: '', value: '', href: '',
    style: {{}}, classList: {{ remove: () => {{}}, add: () => {{}}, toggle: () => {{}} }},
    addEventListener: () => {{}}, remove: () => {{}} }});
const document = {{ getElementById: () => createMockElement(), querySelectorAll: () => [],
    querySelector: () => null, createElement: () => ({{ type: '', id: '', textContent: '' }}),
    head: {{ appendChild: () => {{}} }} }};
const window = {{ location: {{ origin: 'https://employmentexpress.github.io', pathname: '/homepage/', search: '' }},
    addEventListener: () => {{}}, setInterval: () => {{}},
    history: {{ replaceState: () => {{}}, pushState: () => {{}} }} }};
const html = fs.readFileSync({json.dumps(str(INDEX))}, 'utf8');
let mainScript = '';
for (const tag of html.match(/<script(?![^>]*\\bsrc=)[^>]*>([\\s\\S]*?)<\\/script>/gi) || []) {{
    const content = tag.replace(/<script[^>]*>/i, '').replace(/<\\/script>/i, '');
    if (content.includes('getSchemaJobLocation')) {{ mainScript = content; break; }}
}}
const AsyncFunction = Object.getPrototypeOf(async function(){{}}).constructor;
const runner = new AsyncFunction('document', 'window', mainScript + `
  const blob = (j) => ((j.location || '') + ' ' + (j.department || '') + ' ' + (j.title || '')).toLowerCase();
  const cityOf = (j) => ((getSchemaJobLocation(j) || {{}}).address || {{}}).addressLocality || '';
  const stored = (globalThis.__jobs || []).map(j => ({{ id: j.id, blob: blob(j), locality: cityOf(j) }}));
  const cases = [
    {{ label: 'rrb-regional-rural-banks', job: {{ location: 'All India (state-wise, participating RRBs)',
      department: 'Institute of Banking Personnel Selection (IBPS)',
      title: 'Institute of Banking Personnel Selection (IBPS) — Regional Rural Banks Post of Office Assistants (Multipurpose) CRP-RRBs-XV, Online Form',
      type: 'central' }} }},
    {{ label: 'provisional-list', job: {{ location: 'All India', department: 'State Bank of India (SBI)',
      title: 'State Bank of India (SBI) — LIST OF CANDIDATES PROVISIONALLY SELECTED FOR YOUNG PROFESSIONAL',
      type: 'central' }} }},
    {{ label: 'national-aerospace', job: {{ location: 'Bengaluru', department: 'CSIR–National Aerospace Laboratories (CSIR–NAL)',
      title: 'CSIR–National Aerospace Laboratories (CSIR–NAL) — Technical Assistant Recruitment',
      type: 'central' }} }}
  ];
  return {{ stored, cases: cases.map(c => ({{ label: c.label, locality: cityOf(c.job) }})) }};
`);
runner(document, window).then(r => process.stdout.write(JSON.stringify(r)))
  .catch(err => {{ console.error(err); process.exit(1); }});
"""

    def test_regional_or_provisional_text_never_resolves_to_bengaluru(self):
        Bengaluru_clue = re.compile(r"bangalore|bengaluru|\bnal\b|asc centre")
        wrong = [j for j in self.results["stored"]
                 if j["locality"] == "Bengaluru" and not Bengaluru_clue.search(j["blob"])]
        self.assertEqual(
            wrong, [],
            "Bengaluru was inferred from a word fragment instead of an authority name: "
            + ", ".join(str(j["id"]) for j in wrong[:5]),
        )

    def test_bengaluru_authorities_still_resolve_locally(self):
        by_label = {c["label"]: c["locality"] for c in self.results["cases"]}
        self.assertEqual(by_label["national-aerospace"], "Bengaluru")
        self.assertNotEqual(by_label["rrb-regional-rural-banks"], "Bengaluru")
        self.assertNotEqual(by_label["provisional-list"], "Bengaluru")

    def test_location_matching_uses_word_boundaries(self):
        self.assertNotIn(
            "loc.includes('nal')", self.html,
            "fragment matching reintroduced: use /\\bnal\\b/ so words that merely "
            "contain 'nal' (Regional, Provisional, National) are not matched",
        )


if __name__ == "__main__":
    unittest.main()
