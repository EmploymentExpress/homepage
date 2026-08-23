"""Render a BEFORE / AFTER demo of the short job-details headings.

Reads the job details that are actually posted right now:
  * curated entries inside index.html (jobDatabase / admissionDatabase)
  * auto-discovered entries in data/auto-jobs.json

and prints (and writes to docs/short-headline-demo.md) the current long heading
next to the proposed short heading. Data-only: nothing on the page is modified.

Usage:  python scripts/preview_short_headlines.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from short_headlines import short_job_headline  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
AUTO_JOBS = ROOT / "data" / "auto-jobs.json"
OUTPUT = ROOT / "docs" / "short-headline-demo.md"
OUTPUT_HTML = ROOT / "docs" / "short-headline-demo.html"


def _unescape(text: str) -> str:
    return text.replace('\\"', '"').replace("\\\\", "\\")


def curated_entries() -> list[dict]:
    html = INDEX.read_text(encoding="utf-8")
    entries = []
    for block in re.finditer(r"\{\s*\n\s*id:\s*\d+,(.*?)\n\s*\}", html, re.DOTALL):
        body = block.group(1)
        title = re.search(r'title:\s*"((?:[^"\\]|\\.)*)"', body)
        dept = re.search(r'department:\s*"((?:[^"\\]|\\.)*)"', body)
        vac = re.search(r'vacancies:\s*"((?:[^"\\]|\\.)*)"', body)
        mode = re.search(r'applyMode:\s*"((?:[^"\\]|\\.)*)"', body)
        if not title:
            continue
        entries.append({
            "source": "index.html (curated)",
            "title": _unescape(title.group(1)),
            "department": _unescape(dept.group(1)) if dept else "",
            "alertType": "admission" if "ADMISSION" in body else "",
            "vacancies": _unescape(vac.group(1)) if vac else "",
            "applyMode": _unescape(mode.group(1)) if mode else "",
        })
    return entries


def automatic_entries() -> list[dict]:
    data = json.loads(AUTO_JOBS.read_text(encoding="utf-8"))
    return [
        {
            "source": "data/auto-jobs.json (auto)",
            "title": job.get("title", ""),
            "department": job.get("department", ""),
            "alertType": job.get("alertType", ""),
            "vacancies": job.get("vacancies", ""),
            "applyMode": job.get("applyMode", ""),
        }
        for job in data.get("jobs", [])
    ]


def write_html(rows) -> None:
    """Side-by-side HTML preview of the current vs proposed headings."""
    from html import escape

    cards = []
    for i, (source, before, after) in enumerate(rows, 1):
        tag = "Curated" if "curated" in source else "Auto"
        cards.append(f"""
        <tr>
          <td class="num">{i}<span class="tag">{tag}</span></td>
          <td class="before">{escape(before)}<span class="len">{len(before)} chars</span></td>
          <td class="after">{escape(after)}<span class="len">{len(after)} chars</span></td>
        </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Short job-detail headings — before / after demo</title>
<style>
  body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; background:#f8fafc; color:#0f172a; }}
  header {{ background:#0f172a; color:#fff; padding:22px 28px; }}
  header h1 {{ margin:0 0 6px; font-size:20px; }}
  header p {{ margin:0; font-size:13px; color:#cbd5e1; }}
  .rule {{ margin:18px 28px; padding:14px 16px; background:#fff; border:1px solid #e2e8f0; border-radius:10px; font-size:13px; }}
  code {{ background:#f1f5f9; padding:2px 6px; border-radius:4px; }}
  table {{ width:calc(100% - 56px); margin:0 28px 40px; border-collapse:collapse; background:#fff;
           border:1px solid #e2e8f0; border-radius:10px; overflow:hidden; font-size:13px; }}
  th {{ text-align:left; background:#f1f5f9; padding:10px 12px; font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:#475569; }}
  td {{ padding:12px; border-top:1px solid #e2e8f0; vertical-align:top; }}
  td.num {{ width:60px; color:#94a3b8; font-weight:700; }}
  .tag {{ display:block; font-size:9px; font-weight:700; color:#64748b; margin-top:4px; }}
  td.before {{ width:52%; color:#7f1d1d; background:#fef2f2; }}
  td.after {{ font-weight:700; color:#14532d; background:#f0fdf4; }}
  .len {{ display:block; font-size:10px; font-weight:600; color:#94a3b8; margin-top:6px; }}
</style></head><body>
<header>
  <h1>Job details heading — short headline demo</h1>
  <p>Before = heading posted today &nbsp;·&nbsp; After = proposed short heading &nbsp;·&nbsp; {len(rows)} live job details</p>
</header>
<div class="rule">
  <strong>Rule:</strong> <code>&lt;Department short name&gt; — &lt;Post / subject&gt; &lt;What the notice is about&gt;</code>,
  capped at 72 characters. The notice type is detected from the board's own wording:
  Recruitment · Corrigendum · Addendum · Cancelled · Postponed · Date Extended · Shortlisted ·
  Exam Date · Admit Card · Answer Key · Merit List · Waiting List · Result · Posting Orders ·
  Walk-in Interview · Admission · Notice.
</div>
<table>
  <tr><th>#</th><th>Before (current heading)</th><th>After (short heading)</th></tr>
  {''.join(cards)}
</table>
</body></html>
"""
    OUTPUT_HTML.write_text(html, encoding="utf-8")


def main() -> None:
    rows = []
    for entry in curated_entries() + automatic_entries():
        before = entry["title"]
        after = short_job_headline(before, entry["department"], entry["alertType"],
                                   entry.get("vacancies", ""), entry.get("applyMode", ""))
        rows.append((entry["source"], before, after))

    lines = [
        "# Job details heading — SHORT headline demo",
        "",
        "Proposed rule: `<Department short name> <Total posts> <Post name(s)> <What the notice is about>`",
        "(job-portal headline style, e.g. `HAL Design Trainee, Management Trainee Online Form`)",
        "where the notice type is auto-detected from the official wording",
        "(Online/Offline Form, Corrigendum Notice, Addendum Notice, Vacancy Cancelled,",
        "Exam Postponed, Last Date Extended, Shortlisted Candidates, Exam Date, Admit Card,",
        "Answer Key, Merit List, Waiting List, Result, Posting Orders, Walk in Interview,",
        "Admission Form, Public Notice).",
        "",
        f"Headlines are capped at 72 characters. {len(rows)} posted job details below.",
        "",
    ]
    for i, (source, before, after) in enumerate(rows, 1):
        lines += [
            f"### {i}. {source}",
            f"- **BEFORE ({len(before)} chars):** {before}",
            f"- **AFTER ({len(after)} chars):** {after}",
            "",
        ]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    write_html(rows)

    for i, (source, before, after) in enumerate(rows, 1):
        print(f"{i:>2}. [{source}]")
        print(f"    BEFORE: {before}")
        print(f"    AFTER : {after}\n")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
