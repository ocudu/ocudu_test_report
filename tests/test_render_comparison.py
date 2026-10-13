# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
# SPDX-FileCopyrightText: Copyright (C) 2026 OpenInfra Foundation Europe. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Tests for scripts/render_comparison.py — comparison HTML renderer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import render_comparison  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_diff(**kwargs) -> dict:
    """Build a minimal diff structure."""
    return {
        "schema_version": 1,
        "base": kwargs.get("base", {"pipeline_id": "100", "commit_sha": "aaa111", "generated_at": "2026-08-13T08:00:00+00:00"}),
        "head": kwargs.get("head", {"pipeline_id": "200", "commit_sha": "bbb222", "generated_at": "2026-08-13T09:00:00+00:00"}),
        "summary": kwargs.get("summary", {"total_base": 100, "total_head": 102, "regressions": 1, "fixes": 1, "new_failures": 1, "new_passes": 1, "new_skips": 0, "removed": 1, "unchanged": 97}),
        "regressions": kwargs.get("regressions", [{"key": "mod.test_reg", "status_base": "passed", "status_head": "failed", "duration_base": 5.0, "duration_head": 12.0, "labels": ["MVP-FUNC-1"]}]),
        "fixes": kwargs.get("fixes", [{"key": "mod.test_fix", "status_base": "failed", "status_head": "passed", "duration_base": 10.0, "duration_head": 3.0, "labels": []}]),
        "new_failures": kwargs.get("new_failures", [{"key": "new.test_fail", "status_base": None, "status_head": "failed", "duration_base": None, "duration_head": 8.0, "labels": ["MVP-NEW"]}]),
        "new_passes": kwargs.get("new_passes", [{"key": "new.test_pass", "status_base": None, "status_head": "passed", "duration_base": None, "duration_head": 1.0, "labels": []}]),
        "new_skips": kwargs.get("new_skips", []),
        "removed": kwargs.get("removed", [{"key": "old.test_gone", "status_base": "passed", "status_head": None, "duration_base": 2.0, "duration_head": None, "labels": ["MVP-OLD"]}]),
    }


# ---------------------------------------------------------------------------
# _status_icon
# ---------------------------------------------------------------------------


class TestStatusIcon:
    def test_passed(self):
        assert render_comparison._status_icon("passed") == "✓"

    def test_failed(self):
        assert render_comparison._status_icon("failed") == "✗"

    def test_error(self):
        assert render_comparison._status_icon("error") == "✗"

    def test_skipped(self):
        assert render_comparison._status_icon("skipped") == "⊘"

    def test_none(self):
        assert render_comparison._status_icon(None) == "—"

    def test_unknown(self):
        assert render_comparison._status_icon("unknown") == "?"


# ---------------------------------------------------------------------------
# _status_class
# ---------------------------------------------------------------------------


class TestStatusClass:
    def test_passed(self):
        assert render_comparison._status_class("passed") == "passed"

    def test_failed(self):
        assert render_comparison._status_class("failed") == "failed"

    def test_error(self):
        assert render_comparison._status_class("error") == "failed"

    def test_skipped(self):
        assert render_comparison._status_class("skipped") == "skipped"

    def test_none(self):
        assert render_comparison._status_class(None) == "removed"


# ---------------------------------------------------------------------------
# _fmt_duration
# ---------------------------------------------------------------------------


class TestFmtDuration:
    def test_none(self):
        assert render_comparison._fmt_duration(None) == "—"

    def test_very_small(self):
        assert render_comparison._fmt_duration(0.001) == "<0.01s"

    def test_seconds(self):
        assert render_comparison._fmt_duration(5.123) == "5.12s"

    def test_minutes(self):
        result = render_comparison._fmt_duration(125.5)
        assert "2m" in result
        assert "5.5s" in result

    def test_zero(self):
        assert render_comparison._fmt_duration(0.0) == "<0.01s"


# ---------------------------------------------------------------------------
# _render_summary_cards
# ---------------------------------------------------------------------------


class TestRenderSummaryCards:
    def test_all_cards_present(self):
        summary = {"regressions": 3, "fixes": 2, "new_failures": 1, "new_passes": 5, "removed": 1, "unchanged": 100}
        html = render_comparison._render_summary_cards(summary)

        assert "cmp-hero" in html
        assert ">3<" in html  # regressions count
        assert ">2<" in html  # fixes count
        assert "Regressions" in html
        assert "Fixes" in html
        assert "Unchanged" in html

    def test_zero_values(self):
        summary = {"regressions": 0, "fixes": 0, "new_failures": 0, "new_passes": 0, "removed": 0, "unchanged": 500}
        html = render_comparison._render_summary_cards(summary)
        assert ">0<" in html
        assert ">500<" in html


# ---------------------------------------------------------------------------
# _render_entry_row
# ---------------------------------------------------------------------------


class TestRenderEntryRow:
    def test_basic_row(self):
        entry = {"key": "mod.test_a", "status_base": "passed", "status_head": "failed", "duration_base": 1.0, "duration_head": 2.0, "labels": []}
        html = render_comparison._render_entry_row(entry)

        assert "mod.test_a" in html
        assert "cmp-pill passed" in html
        assert "cmp-pill failed" in html
        assert "cmp-row" in html

    def test_labels_rendered(self):
        entry = {"key": "test", "status_base": "passed", "status_head": "failed", "duration_base": 1.0, "duration_head": 2.0, "labels": ["MVP-FUNC-1", "phy"]}
        html = render_comparison._render_entry_row(entry)

        assert "MVP-FUNC-1" in html
        assert "phy" in html
        assert "cmp-label" in html

    def test_many_labels_truncated(self):
        entry = {"key": "test", "status_base": "passed", "status_head": "failed", "duration_base": 1.0, "duration_head": 2.0, "labels": ["a", "b", "c", "d", "e"]}
        html = render_comparison._render_entry_row(entry)

        assert "+2" in html  # overflow indicator

    def test_none_status(self):
        entry = {"key": "test", "status_base": None, "status_head": "failed", "duration_base": None, "duration_head": 5.0, "labels": []}
        html = render_comparison._render_entry_row(entry)

        assert "absent" in html  # None rendered as 'absent' pill

    def test_html_escaping(self):
        entry = {"key": "mod.<script>alert(1)</script>", "status_base": "passed", "status_head": "failed", "duration_base": 1.0, "duration_head": 2.0, "labels": []}
        html = render_comparison._render_entry_row(entry)

        assert "<script>" not in html
        assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# _render_section
# ---------------------------------------------------------------------------


class TestRenderSection:
    def test_empty_entries_returns_empty(self):
        assert render_comparison._render_section("Title", [], "css") == ""

    def test_section_structure(self):
        entries = [{"key": "t1", "status_base": "passed", "status_head": "failed", "duration_base": 1.0, "duration_head": 2.0, "labels": []}]
        html = render_comparison._render_section("Regressions", entries, "section-regression")

        assert "<details" in html
        assert "Regressions" in html
        assert "section-regression" in html
        assert "<table" in html
        assert "t1" in html

    def test_count_shown(self):
        entries = [
            {"key": f"t{i}", "status_base": "passed", "status_head": "failed", "duration_base": 1.0, "duration_head": 2.0, "labels": []}
            for i in range(5)
        ]
        html = render_comparison._render_section("Title", entries, "css")
        assert ">5<" in html


# ---------------------------------------------------------------------------
# render_comparison_html
# ---------------------------------------------------------------------------


class TestRenderComparisonHtml:
    def test_produces_valid_html(self):
        diff = _minimal_diff()
        html = render_comparison.render_comparison_html(diff)

        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "<title>Run Comparison</title>" in html

    def test_contains_base_and_head_info(self):
        diff = _minimal_diff()
        html = render_comparison.render_comparison_html(diff)

        assert "Pipeline 100" in html
        assert "Pipeline 200" in html
        assert "aaa111" in html
        assert "bbb222" in html

    def test_contains_all_sections(self):
        diff = _minimal_diff()
        html = render_comparison.render_comparison_html(diff)

        assert "Regressions" in html
        assert "Fixes" in html
        assert "New Failures" in html
        assert "New Passes" in html
        assert "Removed Tests" in html

    def test_contains_test_keys(self):
        diff = _minimal_diff()
        html = render_comparison.render_comparison_html(diff)

        assert "mod.test_reg" in html
        assert "mod.test_fix" in html
        assert "new.test_fail" in html

    def test_empty_diff_shows_message(self):
        diff = _minimal_diff(
            regressions=[], fixes=[], new_failures=[],
            new_passes=[], new_skips=[], removed=[],
            summary={"total_base": 100, "total_head": 100, "regressions": 0, "fixes": 0, "new_failures": 0, "new_passes": 0, "new_skips": 0, "removed": 0, "unchanged": 100},
        )
        html = render_comparison.render_comparison_html(diff)

        assert "No differences found" in html
        assert "100 tests unchanged" in html

    def test_includes_css(self):
        diff = _minimal_diff()
        html = render_comparison.render_comparison_html(diff)

        # Should include the base style.css tokens
        assert "--bg:" in html
        assert "slate" in html or "#0f172a" in html
        # Should include comparison-specific styles
        assert ".cmp-hero" in html
        assert ".cmp-section" in html

    def test_favicon_included(self):
        diff = _minimal_diff()
        html = render_comparison.render_comparison_html(diff, favicon="https://example.com/icon.png")

        assert "https://example.com/icon.png" in html

    def test_responsive_css_included(self):
        diff = _minimal_diff()
        html = render_comparison.render_comparison_html(diff)

        assert "@media" in html
        assert "768px" in html


# ---------------------------------------------------------------------------
# CLI (main)
# ---------------------------------------------------------------------------


class TestMain:
    def test_writes_output(self, tmp_path, monkeypatch):
        diff_file = tmp_path / "diff.json"
        diff_file.write_text(json.dumps(_minimal_diff()))
        out_file = tmp_path / "comparison.html"

        monkeypatch.setattr(sys, "argv", ["render_comparison.py", str(diff_file), "-o", str(out_file)])
        render_comparison.main()

        assert out_file.exists()
        content = out_file.read_text()
        assert "<!DOCTYPE html>" in content

    def test_missing_file_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["render_comparison.py", str(tmp_path / "nope.json")])
        with pytest.raises(SystemExit) as exc_info:
            render_comparison.main()
        assert exc_info.value.code == 1
