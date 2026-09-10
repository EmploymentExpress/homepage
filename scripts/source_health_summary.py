#!/usr/bin/env python3
"""Source health summary for the Update job alerts workflow (R11/R12).

Reads data/seen-notices.json (per-source and per-feed health recorded by
scripts/update_jobs.py) and data/auto-jobs.json (published jobs) and appends a
compact markdown report to $GITHUB_STEP_SUMMARY, so a failing or silent-dead
source is visible at a glance on the Actions run page instead of being buried
inside a 30-minute log. Also prints the same report to stdout for local runs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "seen-notices.json"
OUTPUT_PATH = ROOT / "data" / "auto-jobs.json"

PLACEHOLDER_FIELDS = (
    "lastDate",
    "vacancies",
    "feeGen",
    "feeSC",
    "examDate",
)
PLACEHOLDER_MARKERS = ("see ", "as notified", "newly published")


def _load(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _is_placeholder(value) -> bool:
    text = str(value or "").strip().lower()
    return not text or any(text.startswith(marker) for marker in PLACEHOLDER_MARKERS)


def build_report(state: dict, output: dict) -> str:
    health = state.get("sourceHealth", {}) or {}
    sources = state.get("sources", {}) or {}
    jobs = output.get("jobs", []) or []
    lines: list[str] = []

    lines.append("## 📡 Monitor source health")
    lines.append("")

    failing = sorted(
        ((sid, entry) for sid, entry in health.items() if int(entry.get("consecutiveFailures") or 0) > 0),
        key=lambda item: -int(item[1].get("consecutiveFailures") or 0),
    )
    healthy = [sid for sid, entry in health.items() if not int(entry.get("consecutiveFailures") or 0)]
    silent_dead = sorted(
        sid for sid, entry in health.items() if entry.get("silentDead")
    )

    lines.append(
        f"**{len(healthy)} healthy · {len(failing)} failing · "
        f"{len(silent_dead)} silent-dead · {len(jobs)} automatic alerts stored**"
    )
    lines.append("")

    if failing:
        lines.append("### ❌ Failing sources (consecutive failed runs)")
        lines.append("")
        lines.append("| Source | Failed runs | Last error |")
        lines.append("| --- | --- | --- |")
        for sid, entry in failing[:20]:
            error = str(entry.get("lastError") or "").replace("|", "/")[:90]
            lines.append(f"| `{sid}` | {int(entry.get('consecutiveFailures') or 0)} | {error} |")
        if len(failing) > 20:
            lines.append(f"| … | {len(failing) - 20} more | |")
        lines.append("")

    if silent_dead:
        lines.append("### 🤐 Silent-dead sources")
        lines.append("")
        lines.append(
            "Initialized days ago but never produced a notice — they answer like a "
            "healthy source while publishing nothing (R12):"
        )
        lines.append("")
        for sid in silent_dead:
            lines.append(f"- `{sid}`")
        lines.append("")

    # Discovery feeds and official sources that have never even initialized.
    never_initialized = sorted(
        sid
        for sid, entry in sources.items()
        if isinstance(entry, dict) and not entry.get("initializedAt")
    )
    if never_initialized:
        lines.append("### ⏳ Not yet initialized")
        lines.append("")
        lines.append(", ".join(f"`{sid}`" for sid in never_initialized[:25]))
        lines.append("")

    placeholder_counts = {
        field: sum(1 for job in jobs if _is_placeholder(job.get(field)))
        for field in PLACEHOLDER_FIELDS
    }
    lines.append("### 📋 Placeholder details still to be filled (R10 backlog)")
    lines.append("")
    lines.append("| Field | Jobs still on a placeholder |")
    lines.append("| --- | --- |")
    for field, count in placeholder_counts.items():
        lines.append(f"| {field} | {count} / {len(jobs)} |")
    lines.append("")

    mirror_health = state.get("mirrorHealth", {}) or {}
    if mirror_health:
        lines.append("### 🪞 Read-only mirror rotation (R2)")
        lines.append("")
        lines.append("| Mirror | Consecutive failures | Last success |")
        lines.append("| --- | --- | --- |")
        for template, stats in sorted(
            mirror_health.items(), key=lambda item: -int(item[1].get("consecutiveFailures") or 0)
        ):
            lines.append(
                f"| `{template.replace('|', '/')}` "
                f"| {int(stats.get('consecutiveFailures') or 0)} "
                f"| {str(stats.get('lastSuccessAt') or '—')[:19]} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    state = _load(STATE_PATH, {})
    output = _load(OUTPUT_PATH, {})
    report = build_report(state, output)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(report)
    print(report, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
