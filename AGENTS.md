# AGENTS.md — Instructions for AI Agents & Automation

> **Read this file before making any change to this repository.**
> These rules apply to every AI agent (Codex, Claude, Cursor, Gemini, Copilot, Arena agents, etc.)
> and to human contributors alike.

## 🔒 The #1 rule: the homepage layout is FROZEN

The section layout of `index.html` (the **Classic 4-Column Mega Grid**, restored in PR #17) is
deliberate and **protected**. When you are asked to "update" anything — jobs, dates, links,
admit cards, results, text, counts — you must change **only the specific details you were asked
to change** and nothing else.

**NEVER do any of the following unless the user EXPLICITLY asks for a layout change
(e.g. "reorder sections", "move X above Y", "change to a 2-column grid"):**

- ❌ Reorder, add, remove, or rename sections
- ❌ Change grid classes (`grid-cols-*`), wrappers, or the 4-column mega grid structure
- ❌ Change element `id`s or `class`es — JS rendering and nav anchors depend on them
- ❌ Restyle headers/cards (colors, badges, icons) or move sections into/out of the grid
- ❌ "Improve", "modernize", or "clean up" the HTML structure on your own initiative

**✅ You MAY change (when instructed):**

- Job/notice entries inside the JS datasets in `index.html` (`jobs`, `admitCards`, `results`,
  admissions, etc.) — add/edit/remove the entries you were told about, leave the rest untouched
- Generated data files: `data/auto-jobs.json`, `data/seen-notices.json`,
  `data/notification-source-links.json`, `data/offline-redirects.json`
- Monitor sources & logic: `automation/*.json`, `scripts/update_jobs.py` (data-only behaviour)
- The offline-form registry: `automation/offline-forms.json` — add offline-apply vacancies
  here (each entry points to the external offline-form page for that job). The external URL is
  masked on the site: links render as `redirect.html?f=<token>` and the real URL lives only in
  the generated `data/offline-redirects.json`. Never display the external portal's name or URL
  on the homepage.
- Specific text a user asks you to fix (titles, dates, links, counts) — in place, no reflow

## 📐 Canonical section order (do not reorder)

Inside `<main>` of `index.html`:

1. Quick Notice Banners / Highlight Grid
2. **Main 4-Column Mega Grid** (`#answer-keys` wrapper, `grid-cols-1 md:grid-cols-2 lg:grid-cols-4`):
   - Column 1: Latest Punjab Jobs (`#punjab-jobs`, blue)
   - Column 2: All India & NVS / Central (`#central-jobs`, purple)
   - Column 3: Admit Card 2026 (`#admit-cards`, emerald)
   - Column 4: Results & Answer Key (`#results`, rose)
3. **Last Date Reminders** (`#last-date-reminders`, red section)
4. Admission & Courses (`#admission-courses`)
5. Qualification Quick Finder Pills
6. Master Table: Latest Govt Job Vacancies 2026
7. Quick Resources & State Syllabus Widget

Newly discovered official notices are rendered **in place inside their respective section**
(Latest Punjab Jobs / All India & NVS / Results & Answer Key / Admission & Courses / the
Master Table) with a **"Just In"** tag that stays for **48 hours** after publication and is
removed automatically once that window elapses.

## 🛡 How the layout is enforced

- **`tests/test_layout_order.py`** asserts the exact section order, the 4-column grid classes,
  and unique anchor IDs. The GitHub Actions workflow runs the full test suite on every run, so a
  layout-changing edit **fails CI**. If this test fails after your edit, you changed the layout —
  revert it unless the user explicitly requested a layout change (in which case update the test
  in the same commit and say so in the PR).
- **`scripts/update_jobs.py`** snapshots `index.html` and `assets/` before every monitoring run
  and restores them afterwards (`PROTECTED_LAYOUT_PATHS`), so automation can only ever write to
  `data/*.json`. Never widen those paths to let the monitor edit the page.
- Guard comments at the top of `<main>` in `index.html` repeat these rules inline.

## 🧪 Before you finish

```bash
python -m unittest discover -s tests -v   # must pass, including layout-order tests
```

Keep diffs minimal: the changed lines in your PR should be recognisable as exactly the content
you were asked to update. If a diff touches section structure, stop and reconsider.
