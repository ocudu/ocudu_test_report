#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2026 OpenInfra Foundation Europe. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Render a comparison HTML page from diff.json output.

Reads a diff.json file (produced by diff_runs.py) and generates a
self-contained HTML page showing regressions, fixes, new tests, and
removed tests in a dashboard-style layout matching the existing report theme.

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

# Section definitions: (title, diff_key, css_class)
_SECTIONS = [
    ("Regressions", "regressions", "section-regression"),
    ("Fixes", "fixes", "section-fix"),
    ("New Failures", "new_failures", "section-new-failure"),
    ("New Passes", "new_passes", "section-new-pass"),
    ("New Skips", "new_skips", "section-new-skip"),
    ("Removed Tests", "removed", "section-removed"),
]

# Card definitions: (label, summary_key, css_class, filter_target)
_CARDS = [
    ("Regressions", "regressions", "regression", "section-regression"),
    ("New Failures", "new_failures", "new-failure", "section-new-failure"),
    ("Removed", "removed", "removed-stat", "section-removed"),
    ("Fixes", "fixes", "fix", "section-fix"),
    ("New Passes", "new_passes", "new-pass", "section-new-pass"),
    ("Unchanged", "unchanged", "unchanged", ""),
]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _read_asset(name: str) -> str:
    """Read a file from the scripts directory."""
    return (_SCRIPTS_DIR / name).read_text(encoding="utf-8")


def _status_icon(status: str | None) -> str:
    """Return a status icon character."""
    if status is None:
        return "—"
    return {"passed": "✓", "failed": "✗", "error": "✗", "skipped": "⊘"}.get(status, "?")


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


# ---------------------------------------------------------------------------
# Rendering functions
# ---------------------------------------------------------------------------


def _render_meta(diff: dict) -> str:
    """Render run metadata as a two-column dashboard card."""
    base = diff.get("base", {})
    head = diff.get("head", {})
    summary = diff.get("summary", {})

    def _run_col(data: dict, label: str, total_key: str, css_mod: str) -> str:
        pid = data.get("pipeline_id", "unknown")
        sha = data.get("commit_sha", "")[:8]
        date = data.get("generated_at", "")[:10]
        total = summary.get(total_key, 0)
        return (
            f'<div class="cmp-meta-run {css_mod}">'
            f'<div class="cmp-meta-badge">{label}</div>'
            f'<div class="cmp-meta-pipeline">Pipeline {html.escape(str(pid))}</div>'
            f'<div class="cmp-meta-details">'
            f'<span class="cmp-meta-sha">{html.escape(sha)}</span>'
            f'<span class="cmp-meta-date">{html.escape(date)}</span>'
            f'<span class="cmp-meta-tests">{total} tests</span>'
            f"</div></div>"
        )

    return (
        f'<div class="cmp-meta">'
        f'{_run_col(base, "BASE", "total_base", "cmp-meta-base")}'
        f'<div class="cmp-meta-divider"><div class="cmp-meta-arrow">→</div></div>'
        f'{_run_col(head, "HEAD", "total_head", "cmp-meta-head")}'
        f"</div>"
    )


def _render_summary_cards(summary: dict) -> str:
    """Render summary cards as clickable filter buttons plus search box."""
    parts = []
    for label, key, css_class, filter_target in _CARDS:
        count = summary.get(key, 0)
        active = " active" if count > 0 and css_class != "unchanged" else ""
        data_attr = f' data-filter="{filter_target}"' if filter_target else ""
        clickable = " clickable" if filter_target else ""
        parts.append(
            f'<button class="cmp-card {css_class}{active}{clickable}"{data_attr}>'
            f'<div class="cmp-card-value">{count}</div>'
            f'<div class="cmp-card-label">{label}</div>'
            f"</button>"
        )

    return (
        f'<div class="cmp-cards">{"".join(parts)}</div>'
        f'<div class="cmp-search-wrap">'
        f'<input type="text" class="cmp-search" placeholder="Filter tests..." id="cmp-search">'
        f"</div>"
    )


def _render_entry_row(entry: dict) -> str:
    """Render a single diff entry as a table row with status pills."""
    key = html.escape(entry.get("key", ""))
    status_base = entry.get("status_base")
    status_head = entry.get("status_head")
    dur_base = entry.get("duration_base")
    dur_head = entry.get("duration_head")
    labels = entry.get("labels", [])

    # Status pills
    def _pill(status):
        if status:
            return f'<span class="cmp-pill {_status_class(status)}">{status}</span>'
        return '<span class="cmp-pill removed">absent</span>'

    # Duration delta chip
    delta_html = ""
    if dur_base is not None and dur_head is not None:
        delta = dur_head - dur_base
        if abs(delta) >= 0.1:
            sign = "+" if delta > 0 else ""
            cls = "dur-slower" if delta > 0 else "dur-faster"
            delta_html = f'<span class="cmp-dur-delta {cls}">{sign}{delta:.1f}s</span>'

    # Label chips (max 3 shown)
    labels_html = ""
    if labels:
        chips = "".join(f'<span class="cmp-label">{html.escape(l)}</span>' for l in labels[:3])
        if len(labels) > 3:
            chips += f'<span class="cmp-label cmp-label-more">+{len(labels) - 3}</span>'
        labels_html = f'<div class="cmp-labels">{chips}</div>'

    return (
        f'<tr class="cmp-row">'
        f'<td class="cmp-key" title="{key}">{key}</td>'
        f'<td class="cmp-status-cell">{_pill(status_base)}</td>'
        f'<td class="cmp-arrow-cell"><span class="cmp-arrow-icon">→</span></td>'
        f'<td class="cmp-status-cell">{_pill(status_head)}</td>'
        f'<td class="cmp-dur">{_fmt_duration(dur_head)}{delta_html}</td>'
        f'<td class="cmp-labels-cell">{labels_html}</td>'
        f"</tr>"
    )


def _render_section(title: str, entries: list[dict], css_class: str) -> str:
    """Render a collapsible section with a data table."""
    if not entries:
        return ""

    rows = "\n".join(_render_entry_row(e) for e in entries)
    return (
        f'<details class="cmp-section {css_class}" open>'
        f'<summary class="cmp-section-header">'
        f'<span class="cmp-section-title">{html.escape(title)}</span>'
        f'<span class="cmp-section-count">{len(entries)}</span>'
        f"</summary>"
        f'<table class="cmp-table"><thead><tr>'
        f'<th class="cmp-th-key">Test Case</th>'
        f'<th class="cmp-th-status">Before</th><th></th>'
        f'<th class="cmp-th-status">After</th>'
        f'<th class="cmp-th-dur">Duration</th>'
        f'<th class="cmp-th-labels">Labels</th>'
        f"</tr></thead><tbody>{rows}</tbody></table>"
        f"</details>"
    )


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------


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

    sections_html = "\n".join(
        _render_section(title, diff.get(key, []), css_class) for title, key, css_class in _SECTIONS
    )

    # Empty state
    total_changes = sum(len(diff.get(s[1], [])) for s in _SECTIONS)
    if total_changes == 0:
        sections_html = (
            '<div class="cmp-empty">'
            '<div class="cmp-empty-icon">✓</div>'
            "<p>No differences found between these runs.</p>"
            f'<p>{summary.get("unchanged", 0)} tests unchanged.</p>'
            "</div>"
        )

    css = _read_asset("style.css")
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
{_COMPARISON_CSS}
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
{_COMPARISON_JS}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Inline JS
# ---------------------------------------------------------------------------

_COMPARISON_JS = """<script>
(function() {
  // Search: filter table rows by test name
  var input = document.getElementById('cmp-search');
  if (input) {
    input.addEventListener('input', function() {
      var q = this.value.toLowerCase();
      document.querySelectorAll('.cmp-row').forEach(function(row) {
        var key = row.querySelector('.cmp-key');
        row.style.display = (key && key.textContent.toLowerCase().includes(q)) ? '' : 'none';
      });
    });
  }

  // Card filter: click a card to show only its section
  var cards = document.querySelectorAll('.cmp-card[data-filter]');
  var sections = document.querySelectorAll('.cmp-section');
  var activeFilter = null;

  cards.forEach(function(card) {
    card.addEventListener('click', function() {
      var target = this.dataset.filter;
      if (activeFilter === target) {
        activeFilter = null;
        cards.forEach(function(c) { c.classList.remove('selected'); });
        sections.forEach(function(s) { s.style.display = ''; });
      } else {
        activeFilter = target;
        cards.forEach(function(c) { c.classList.remove('selected'); });
        this.classList.add('selected');
        sections.forEach(function(s) {
          s.style.display = s.classList.contains(target) ? '' : 'none';
        });
      }
    });
  });
})();
</script>"""


# ---------------------------------------------------------------------------
# Inline CSS
# ---------------------------------------------------------------------------

_COMPARISON_CSS = """
/* ── Run metadata ────────────────────────────────────────── */
.cmp-meta { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; margin-bottom: 24px; background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px 24px; box-shadow: var(--shadow); }
.cmp-meta-run { display: flex; flex-direction: column; gap: 6px; }
.cmp-meta-divider { display: flex; align-items: center; justify-content: center; padding: 0 24px; }
.cmp-meta-arrow { font-size: 1.4em; color: var(--accent); font-weight: 700; opacity: 0.8; }
.cmp-meta-badge { font-size: 0.65em; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 800; background: var(--bg-raised); border-radius: 4px; padding: 2px 8px; display: inline-block; width: fit-content; color: var(--text-dim); }
.cmp-meta-base .cmp-meta-badge { color: var(--text-muted); }
.cmp-meta-head .cmp-meta-badge { color: var(--accent); background: rgba(56, 189, 248, 0.1); }
.cmp-meta-pipeline { font-size: 1.15em; font-weight: 700; color: var(--text); }
.cmp-meta-details { display: flex; gap: 12px; font-size: 0.82em; color: var(--text-muted); }
.cmp-meta-sha { font-family: "JetBrains Mono", "Fira Code", monospace; color: var(--text-sub); }

/* ── Summary cards ───────────────────────────────────────── */
.cmp-cards { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 24px; }
.cmp-card { background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px 16px; text-align: center; transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s; font-family: inherit; font-size: inherit; outline: none; -webkit-appearance: none; appearance: none; }
.cmp-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
.cmp-card.clickable { cursor: pointer; }
.cmp-card.clickable.selected { outline: 2px solid var(--accent); outline-offset: -2px; background: rgba(56, 189, 248, 0.06); }
.cmp-card-value { font-size: 2.5em; font-weight: 800; color: var(--text-dim); line-height: 1.1; transition: color 0.2s; }
.cmp-card-label { font-size: 0.7em; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); margin-top: 8px; font-weight: 600; }
.cmp-card.regression.active { border-color: var(--red); box-shadow: 0 0 12px rgba(239,68,68,0.15); }
.cmp-card.regression.active .cmp-card-value { color: var(--red); }
.cmp-card.new-failure.active { border-color: var(--red); box-shadow: 0 0 12px rgba(239,68,68,0.1); }
.cmp-card.new-failure.active .cmp-card-value { color: var(--red); }
.cmp-card.fix.active { border-color: var(--green); box-shadow: 0 0 12px rgba(107,203,119,0.15); }
.cmp-card.fix.active .cmp-card-value { color: var(--green); }
.cmp-card.new-pass.active { border-color: var(--green); box-shadow: 0 0 10px rgba(107,203,119,0.1); }
.cmp-card.new-pass.active .cmp-card-value { color: var(--green); }
.cmp-card.removed-stat.active { border-color: var(--orange); }
.cmp-card.removed-stat.active .cmp-card-value { color: var(--orange); }
.cmp-card.unchanged .cmp-card-value { color: var(--text-dim); }

/* ── Search ──────────────────────────────────────────────── */
.cmp-search-wrap { margin-bottom: 20px; }
.cmp-search { width: 100%; max-width: 400px; padding: 10px 16px; background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-md); color: var(--text); font-size: 0.9em; font-family: inherit; outline: none; transition: border-color 0.15s, box-shadow 0.15s; }
.cmp-search:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(56,189,248,0.1); }
.cmp-search::placeholder { color: var(--text-dim); }

/* ── Sections ────────────────────────────────────────────── */
.cmp-section { margin-bottom: 12px; background: var(--bg-surface); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; animation: fadeSlideIn 0.3s ease-out; }
.cmp-section-header { display: flex; align-items: center; gap: 12px; padding: 14px 20px; cursor: pointer; user-select: none; font-weight: 600; transition: background 0.12s; }
.cmp-section-header:hover { background: var(--bg-raised); }
.cmp-section-header::marker { color: var(--text-dim); }
.cmp-section-title { flex: 1; font-size: 0.95em; }
.cmp-section-count { background: var(--bg-raised); border-radius: 12px; padding: 3px 12px; font-size: 0.82em; font-weight: 700; }
.section-regression .cmp-section-header { border-left: 4px solid var(--red); }
.section-regression .cmp-section-count { background: rgba(239,68,68,0.15); color: var(--red); }
.section-fix .cmp-section-header { border-left: 4px solid var(--green); }
.section-fix .cmp-section-count { background: rgba(107,203,119,0.15); color: var(--green); }
.section-new-failure .cmp-section-header { border-left: 4px solid var(--red); }
.section-new-failure .cmp-section-count { background: rgba(239,68,68,0.12); color: var(--red); }
.section-new-pass .cmp-section-header { border-left: 4px solid var(--green); }
.section-new-pass .cmp-section-count { background: rgba(107,203,119,0.12); color: var(--green); }
.section-new-skip .cmp-section-header { border-left: 4px solid var(--orange); }
.section-removed .cmp-section-header { border-left: 4px solid var(--orange); }
.section-removed .cmp-section-count { background: rgba(251,146,60,0.12); color: var(--orange); }

/* ── Table ───────────────────────────────────────────────── */
.cmp-table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
.cmp-table thead { background: var(--bg-sunken); }
.cmp-table th { padding: 10px 12px; text-align: left; font-weight: 600; color: var(--text-muted); font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.05em; }
.cmp-table tbody tr { border-top: 1px solid var(--border-lite); transition: background 0.1s; }
.cmp-table tbody tr:hover { background: var(--bg-raised); }
.section-regression .cmp-table tbody tr:hover { box-shadow: inset 3px 0 0 var(--red); }
.section-fix .cmp-table tbody tr:hover { box-shadow: inset 3px 0 0 var(--green); }
.section-new-failure .cmp-table tbody tr:hover { box-shadow: inset 3px 0 0 var(--red); }
.section-new-pass .cmp-table tbody tr:hover { box-shadow: inset 3px 0 0 var(--green); }
.section-removed .cmp-table tbody tr:hover { box-shadow: inset 3px 0 0 var(--orange); }
.cmp-key { padding: 12px; font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace; font-size: 0.88em; color: var(--text); max-width: 450px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── Status pills ────────────────────────────────────────── */
.cmp-status-cell { padding: 10px 8px; }
.cmp-pill { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.82em; font-weight: 600; text-transform: capitalize; }
.cmp-pill.passed { background: rgba(107,203,119,0.15); color: var(--green); border: 1px solid rgba(107,203,119,0.3); }
.cmp-pill.failed { background: rgba(239,68,68,0.15); color: var(--red); border: 1px solid rgba(239,68,68,0.3); }
.cmp-pill.skipped { background: rgba(251,146,60,0.12); color: var(--orange); border: 1px solid rgba(251,146,60,0.25); }
.cmp-pill.removed { background: var(--bg-raised); color: var(--text-dim); border: 1px solid var(--border); }
.cmp-arrow-cell { padding: 10px 4px; text-align: center; }
.cmp-arrow-icon { color: var(--text-dim); font-size: 1.1em; opacity: 0.6; }

/* ── Duration ────────────────────────────────────────────── */
.cmp-dur { padding: 10px 8px; color: var(--text-muted); font-size: 0.88em; white-space: nowrap; }
.cmp-dur-delta { display: inline-block; margin-left: 6px; font-size: 0.85em; font-weight: 600; padding: 1px 6px; border-radius: 8px; }
.dur-slower { color: var(--red); background: rgba(239,68,68,0.1); }
.dur-faster { color: var(--green); background: rgba(107,203,119,0.1); }

/* ── Labels ──────────────────────────────────────────────── */
.cmp-labels-cell { padding: 10px 8px; }
.cmp-labels { display: flex; gap: 4px; flex-wrap: wrap; }
.cmp-label { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 10px; padding: 2px 9px; font-size: 0.78em; color: var(--accent); white-space: nowrap; font-weight: 500; }
.cmp-label-more { color: var(--text-dim); font-style: italic; }

/* ── Empty state ─────────────────────────────────────────── */
.cmp-empty { text-align: center; padding: 80px 20px; color: var(--text-muted); }
.cmp-empty-icon { font-size: 3em; margin-bottom: 16px; opacity: 0.7; }
.cmp-empty p { margin-bottom: 8px; font-size: 1.1em; }

/* ── Animations ──────────────────────────────────────────── */
@keyframes fadeSlideIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.cmp-section:nth-child(1) { animation-delay: 0s; }
.cmp-section:nth-child(2) { animation-delay: 0.05s; }
.cmp-section:nth-child(3) { animation-delay: 0.1s; }
.cmp-section:nth-child(4) { animation-delay: 0.15s; }
.cmp-section:nth-child(5) { animation-delay: 0.2s; }

/* ── Responsive ──────────────────────────────────────────── */
@media (max-width: 1100px) { .cmp-cards { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 768px) {
  .cmp-meta { grid-template-columns: 1fr; gap: 12px; }
  .cmp-meta-divider { padding: 8px 0; }
  .cmp-meta-arrow { transform: rotate(90deg); }
  .cmp-cards { grid-template-columns: repeat(2, 1fr); }
  .cmp-table { font-size: 0.78em; }
  .cmp-key { max-width: 200px; }
  .cmp-th-dur, .cmp-dur { display: none; }
  .cmp-th-labels, .cmp-labels-cell { display: none; }
}
"""


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    """Entry point: parse arguments, load diff, write HTML."""
    parser = argparse.ArgumentParser(description="Render a comparison HTML page from diff.json")
    parser.add_argument("diff", type=Path, help="Path to diff.json (produced by diff_runs.py)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("comparison.html"),
        help="Output HTML file path (default: comparison.html)",
    )
    parser.add_argument("--favicon", default=_FAVICON_DEFAULT, metavar="URL", help="Favicon URL")
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
