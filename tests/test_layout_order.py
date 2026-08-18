"""Layout guard: the homepage section layout is frozen (Classic 4-Column Mega Grid, PR #17).

AI agents and automation may update CONTENT (job entries, dates, links, datasets in
data/*.json) but must not reorder, restructure, or restyle sections. These tests pin the
canonical section order, the 4-column mega grid, and the anchor IDs that the navigation
and rendering JS depend on.

If one of these tests fails after your change, you altered the layout. Revert the
structural change unless the user EXPLICITLY requested a layout change — in that case
update the expected order here in the same commit and note it in the PR description.
See AGENTS.md for the full rules.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"

# (description, marker) — must appear in this exact order.
CANONICAL_ORDER = [
    ("SEO H1", 'class="sr-only"'),
    ("Quick Notice Banners", "<!-- Quick Notice Banners / Highlight Grid -->"),
    ("Data freshness summary", "<!-- Data freshness and deadline summary -->"),
    ("Flash cards", 'id="flash-cards-section"'),
    ("Last Date reminders", 'id="last-date-reminders"'),
    ("Mega grid wrapper", "<!-- Main 4-Column Mega Grid (Classic EMPLOYMENT EXPRESS Layout) -->"),
    ("Column 1: Punjab Jobs", 'id="punjab-jobs"'),
    ("Column 2: Central Jobs", 'id="central-jobs"'),
    ("Column 3: Admit Cards", 'id="admit-cards"'),
    ("Column 4: Results", 'id="results"'),
    ("Admission & Courses", 'id="admission-courses"'),
    ("Qualification pills", "<!-- Qualification Quick Finder Pills -->"),
    ("Master table", "<!-- Master Table: Latest Govt Job Vacancies 2026 -->"),
    ("Quick Resources", "<!-- Quick Resources & State Syllabus Widget Section -->"),
]

# Anchor IDs the nav bar, footer links and rendering JS rely on — exactly once each.
REQUIRED_UNIQUE_IDS = [
    "answer-keys",
    "punjab-jobs",
    "punjab-jobs-list",
    "central-jobs",
    "central-jobs-list",
    "admit-cards",
    "admit-cards-list",
    "results",
    "results-list",
    "admission-courses",
    "admission-list",
    "last-date-reminders",
    "last-date-list",
    "flash-cards-section",
]

# The classic mega grid: four cards side-by-side on desktop.
MEGA_GRID_CLASSES = 'class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 scroll-mt-28"'


class LayoutOrderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")

    def test_index_exists(self):
        self.assertTrue(INDEX.exists(), "index.html is missing")

    def test_canonical_section_order(self):
        positions = []
        for name, marker in CANONICAL_ORDER:
            pos = self.html.find(marker)
            self.assertNotEqual(pos, -1, f"Layout marker not found: {name} ({marker!r})")
            positions.append(pos)
        self.assertEqual(
            positions,
            sorted(positions),
            f"Section order changed! Expected canonical order {[n for n, _ in CANONICAL_ORDER]}",
        )

    def test_mega_grid_is_four_columns(self):
        self.assertIn(
            MEGA_GRID_CLASSES,
            self.html,
            "The Main 4-Column Mega Grid wrapper classes were changed (expected "
            f"{MEGA_GRID_CLASSES!r}). Layout is frozen — see AGENTS.md.",
        )

    def test_anchor_ids_unique(self):
        for element_id in REQUIRED_UNIQUE_IDS:
            count = self.html.count(f'id="{element_id}"')
            self.assertEqual(
                count,
                1,
                f'Anchor id="{element_id}" found {count} times (expected exactly 1); '
                "nav links and JS rendering depend on unique IDs.",
            )

    def test_divs_balanced(self):
        opens, closes = self.html.count("<div"), self.html.count("</div>")
        self.assertEqual(opens, closes, f"Unbalanced <div> tags: {opens} open vs {closes} close")


if __name__ == "__main__":
    unittest.main()
