#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 OpenInfra Foundation Europe. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Render a comparison HTML page from diff.json output.

Reads a diff.json file (produced by diff_runs.py) and generates a
self-contained HTML page showing regressions, fixes, new tests, and
removed tests in a user-friendly format matching the existing report style.

Usage:
    python render_comparison.py diff.json -o comparison.html
    python render_comparison.py diff.json --favicon https://example.com/icon.png
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
_FAVICON_DEFAULT = "http://www.google.com/s2/favicons?domain=ocudu.org"


def _read_asset(name: str) -> str:
    """Read a file from the scripts directory."""
    return (_SCRIPTS_DIR / name).read_text(encoding="utf-8")


def _status_icon(status: str | None) -> str:
    """Return a status icon character."""
    if status is None:
        return "—"
    icons = {"passed": "✓", "failed": "✗", "error": "✗", "skipped": "⊘"}
    return icons.get(status, "?")


def _status_class(status: str | None) -> str:
    """Return CSS class for a status."""
    if status is None:
        return "removed"
    if status in ("failed", "error"):
        return "failed"
    return status


def _fmt_duration(seconds: float | None) -> str:
    """Format a duration value."""
    if seconds is None:
        return "—"
    if seconds < 0.01:
        return "<0.01s"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"


def _render_summary_cards(summary: dict) -> str:
    """Render the summary statistics as card elements."""
    cards = [
        ("Regressions", summary.get("regressions", 0), "regression"),
        ("Fixes", summary.get("fixes", 0), "fix"),
        ("New Failures", summary.get("new_failures", 0), "new-failure"),
        ("New Passes", summary.get("new_passes", 0), "new-pass"),
        ("Removed", summary.get("removed", 0), "removed-stat"),
        ("Unchanged", summary.get("unchanged", 0), "unchanged"),
    ]
    html_parts = []
    for label, count, css_class in cards:
        html_parts.append(
            f'<div class="cmp-card {css_class}">'
            f'<div class="cmp-card-value">{count}</div>'
            f'<div class="cmp-card-label">{label}</div>'
            f"</div>"
        )
    return '<div class="cmp-cards">' + "".join(html_parts) + "</div>"


def _render_entry_row(entry: dict) -> str:
    """Render a single diff entry as a table row."""
    key = html.escape(entry.get("key", ""))
    status_base = entry.get("status_base")
    status_head = entry.get("status_head")
    dur_base = entry.get("duration_base")
    dur_head = entry.get("duration_head")
    labels = entry.get("labels", [])

    icon_base = _status_icon(status_base)
    icon_head = _status_icon(status_head)
    class_base = _status_class(status_base)
    class_head = _status_class(status_head)

    labels_html = ""
    if labels:
        chips = "".join(
            f'<span class="cmp-label">{html.escape(l)}</span>' for l in labels[:3]
        )
        if len(labels) > 3:
            chips += f'<span class="cmp-label cmp-label-more">+{len(labels) - 3}</span>'
        labels_html = f'<div class="cmp-labels">{chips}</div>'

    return (
        f'<tr class="cmp-row">'
        f'<td class="cmp-key" title="{key}">{key}</td>'
        f'<td class="cmp-status {class_base}">{icon_base} {status_base or "—"}</td>'
        f'<td class="cmp-arrow">→</td>'
        f'<td class="cmp-status {class_head}">{icon_head} {status_head or "—"}</td>'
        f'<td class="cmp-dur">{_fmt_duration(dur_base)}</td>'
        f'<td class="cmp-dur">{_fmt_duration(dur_head)}</td>'
        f'<td class="cmp-labels-cell">{labels_html}</td>'
        f"</tr>"
    )


def _render_section(title: str, entries: list[dict], css_class: str) -> str:
    """Render a collapsible section with a table of entries."""
    if not entries:
        return ""

    count = len(entries)
    rows = "\n".join(_render_entry_row(e) for e in entries)

    return (
        f'<details class="cmp-section {css_class}" open>'
        f'<summary class="cmp-section-header">'
        f'<span class="cmp-section-title">{html.escape(title)}</span>'
        f'<span class="cmp-section-count">{count}</span>'
        f"</summary>"
        f'<table class="cmp-table">'
        f"<thead><tr>"
        f'<th class="cmp-th-key">Test</th>'
        f'<th class="cmp-th-status">Base</th>'
        f"<th></th>"
        f'<th class="cmp-th-status">Head</th>'
        f'<th class="cmp-th-dur">Base Time</th>'
        f'<th class="cmp-th-dur">Head Time</th>'
        f'<th class="cmp-th-labels">Labels</th>'
        f"</tr></thead>"
        f"<tbody>{rows}</tbody>"
        f"</table>"
        f"</details>"
    )


def _render_meta(diff: dict) -> str:
    """Render the run metadata comparison header."""
    base = diff.get("base", {})
    head = diff.get("head", {})
    summary = diff.get("summary", {})

    base_id = base.get("pipeline_id", "unknown")
    head_id = head.get("pipeline_id", "unknown")
    base_sha = base.get("commit_sha", "")[:8]
    head_sha = head.get("commit_sha", "")[:8]
    base_date = base.get("generated_at", "")[:10]
    head_date = head.get("generated_at", "")[:10]

    return (
        f'<div class="cmp-meta">'
        f'<div class="cmp-meta-run">'
        f'<div class="cmp-meta-label">Base Run</div>'
        f'<div class="cmp-meta-id">Pipeline {html.escape(str(base_id))}</div>'
        f'<div class="cmp-meta-detail">{html.escape(base_sha)} · {html.escape(base_date)}</div>'
        f'<div class="cmp-meta-detail">{summary.get("total_base", 0)} tests</div>'
        f"</div>"
        f'<div class="cmp-meta-arrow">→</div>'
        f'<div class="cmp-meta-run">'
        f'<div class="cmp-meta-label">Head Run</div>'
        f'<div class="cmp-meta-id">Pipeline {html.escape(str(head_id))}</div>'
        f'<div class="cmp-meta-detail">{html.escape(head_sha)} · {html.escape(head_date)}</div>'
        f'<div class="cmp-meta-detail">{summary.get("total_head", 0)} tests</div>'
        f"</div>"
        f"</div>"
    )


def render_comparison_html(diff: dict, favicon: str = _FAVICON_DEFAULT) -> str:
    """Render a complete comparison HTML page from a diff dict.

    Args:
        diff: Parsed diff.json structure (from build_diff_output).
        favicon: URL for the page favicon.

    Returns:
        Complete self-contained HTML string.
    """
    summary = diff.get("summary", {})

    meta_html = _render_meta(diff)
    cards_html = _render_summary_cards(summary)

    sections = [
        ("Regressions", diff.get("regressions", []), "section-regression"),
        ("Fixes", diff.get("fixes", []), "section-fix"),
        ("New Failures", diff.get("new_failures", []), "section-new-failure"),
        ("New Passes", diff.get("new_passes", []), "section-new-pass"),
        ("New Skips", diff.get("new_skips", []), "section-new-skip"),
        ("Removed Tests", diff.get("removed", []), "section-removed"),
    ]

    sections_html = "\n".join(
        _render_section(title, entries, css_class)
        for title, entries, css_class in sections
    )

    # If nothing changed, show a message
    total_changes = sum(len(diff.get(k, [])) for k in [
        "regressions", "fixes", "new_failures", "new_passes", "new_skips", "removed"
    ])
    if total_changes == 0:
        sections_html = (
            '<div class="cmp-empty">'
            "<p>No differences found between these runs.</p>"
            f'<p>{summary.get("unchanged", 0)} tests unchanged.</p>'
            "</div>"
        )

    css = _read_asset("style.css")
    comparison_css = _COMPARISON_CSS

    favicon_tag = f"<link rel='icon' href='{html.escape(favicon)}'>" if favicon else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Run Comparison</title>
{favicon_tag}
<style>
{css}
{comparison_css}
</style>
</head>
<body>
<div class="report-header">
  <div class="header-logo"></div>
  <div class="header-title">
    <h1>Run Comparison</h1>
    <div class="header-link">Comparing two test runs</div>
  </div>
</div>
{meta_html}
{cards_html}
{sections_html}
</body>
</html>"""


_COMPARISON_CSS = """
/* ── Comparison page styles ──────────────────────────────── */

.cmp-meta {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-bottom: 24px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px 28px;
  box-shadow: var(--shadow);
}

.cmp-meta-run {
  flex: 1;
}

.cmp-meta-arrow {
  font-size: 1.5em;
  color: var(--text-muted);
  font-weight: 700;
}

.cmp-meta-label {
  font-size: 0.7em;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: 4px;
}

.cmp-meta-id {
  font-size: 1.1em;
  font-weight: 700;
  color: var(--text);
}

.cmp-meta-detail {
  font-size: 0.85em;
  color: var(--text-sub);
  margin-top: 2px;
}

/* ── Summary cards ───────────────────────────────────────── */

.cmp-cards {
  display: flex;
  gap: 12px;
  margin-bottom: 28px;
  flex-wrap: wrap;
}

.cmp-card {
  flex: 1;
  min-width: 120px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 16px 12px;
  text-align: center;
}

.cmp-card-value {
  font-size: 2em;
  font-weight: 700;
  color: var(--text-muted);
}

.cmp-card-label {
  font-size: 0.75em;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-top: 4px;
}

.cmp-card.regression .cmp-card-value { color: var(--red); }
.cmp-card.fix .cmp-card-value { color: var(--green); }
.cmp-card.new-failure .cmp-card-value { color: var(--red); }
.cmp-card.new-pass .cmp-card-value { color: var(--green); }
.cmp-card.removed-stat .cmp-card-value { color: var(--orange); }
.cmp-card.unchanged .cmp-card-value { color: var(--text-dim); }

/* Highlight cards with non-zero values */
.cmp-card.regression:not(:has(.cmp-card-value:empty)) { border-color: var(--red); }
.cmp-card.fix:not(:has(.cmp-card-value:empty)) { border-color: var(--green); }

/* ── Sections ────────────────────────────────────────────── */

.cmp-section {
  margin-bottom: 16px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.cmp-section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  cursor: pointer;
  user-select: none;
  font-weight: 600;
}

.cmp-section-header:hover {
  background: var(--bg-raised);
}

.cmp-section-title {
  flex: 1;
}

.cmp-section-count {
  background: var(--bg-raised);
  border-radius: 12px;
  padding: 2px 10px;
  font-size: 0.85em;
  color: var(--text-muted);
}

.section-regression .cmp-section-header { border-left: 3px solid var(--red); }
.section-fix .cmp-section-header { border-left: 3px solid var(--green); }
.section-new-failure .cmp-section-header { border-left: 3px solid var(--red); }
.section-new-pass .cmp-section-header { border-left: 3px solid var(--green); }
.section-new-skip .cmp-section-header { border-left: 3px solid var(--orange); }
.section-removed .cmp-section-header { border-left: 3px solid var(--orange); }

/* ── Table ───────────────────────────────────────────────── */

.cmp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85em;
}

.cmp-table thead {
  background: var(--bg-sunken);
}

.cmp-table th {
  padding: 8px 12px;
  text-align: left;
  font-weight: 600;
  color: var(--text-muted);
  font-size: 0.85em;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.cmp-table tbody tr {
  border-top: 1px solid var(--border-lite);
}

.cmp-table tbody tr:hover {
  background: var(--bg-raised);
}

.cmp-key {
  padding: 10px 12px;
  font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
  font-size: 0.9em;
  color: var(--text);
  max-width: 500px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cmp-status {
  padding: 10px 8px;
  font-weight: 600;
  white-space: nowrap;
}

.cmp-status.passed { color: var(--green); }
.cmp-status.failed { color: var(--red); }
.cmp-status.skipped { color: var(--orange); }
.cmp-status.removed { color: var(--text-dim); }

.cmp-arrow {
  padding: 10px 4px;
  color: var(--text-dim);
  text-align: center;
}

.cmp-dur {
  padding: 10px 8px;
  color: var(--text-muted);
  font-size: 0.9em;
  white-space: nowrap;
}

.cmp-labels-cell {
  padding: 10px 8px;
}

.cmp-labels {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.cmp-label {
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 0.8em;
  color: var(--text-sub);
  white-space: nowrap;
}

.cmp-label-more {
  color: var(--text-dim);
  font-style: italic;
}

/* ── Empty state ─────────────────────────────────────────── */

.cmp-empty {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
}

.cmp-empty p {
  margin-bottom: 8px;
  font-size: 1.1em;
}

/* ── Responsive ──────────────────────────────────────────── */

@media (max-width: 768px) {
  .cmp-meta { flex-direction: column; gap: 12px; }
  .cmp-meta-arrow { transform: rotate(90deg); }
  .cmp-cards { flex-direction: column; }
  .cmp-table { font-size: 0.78em; }
  .cmp-key { max-width: 200px; }
  .cmp-th-dur, .cmp-dur { display: none; }
  .cmp-th-labels, .cmp-labels-cell { display: none; }
}
"""


def main():
    """Entry point: parse arguments, load diff, write HTML."""
    parser = argparse.ArgumentParser(
        description="Render a comparison HTML page from diff.json"
    )
    parser.add_argument(
        "diff",
        type=Path,
        help="Path to diff.json (produced by diff_runs.py)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("comparison.html"),
        help="Output HTML file path (default: comparison.html)",
    )
    parser.add_argument(
        "--favicon",
        default=_FAVICON_DEFAULT,
        metavar="URL",
        help="Favicon URL",
    )
    args = parser.parse_args()

    if not args.diff.exists():
        print(f"ERROR: Diff file not found: {args.diff}", file=sys.stderr)
        sys.exit(1)

    diff = json.loads(args.diff.read_text(encoding="utf-8"))
    html_output = render_comparison_html(diff, favicon=args.favicon)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_output, encoding="utf-8")
    print(f"comparison.html written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
