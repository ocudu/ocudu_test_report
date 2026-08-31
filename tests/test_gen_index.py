# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OpenInfra Foundation Europe. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Tests for scripts/gen_index.py — the index page navigator generator."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import gen_index  # noqa: E402


# ---------------------------------------------------------------------------
# _safe
# ---------------------------------------------------------------------------


class TestSafe:
    def test_replaces_spaces(self):
        assert gen_index._safe("26.04 (v1.0)") == "26.04_(v1.0)"

    def test_no_spaces_unchanged(self):
        assert gen_index._safe("26.04") == "26.04"


# ---------------------------------------------------------------------------
# _generate — HTML output structure
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_produces_valid_html(self):
        html = gen_index._generate([])
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_latest_tab_present(self):
        html = gen_index._generate([])
        assert 'data-version="latest"' in html
        assert ">Latest<" in html

    def test_historic_versions_added(self):
        html = gen_index._generate(["26.04", "26.03"])
        assert 'data-version="26.04"' in html
        assert 'data-version="26.03"' in html
        assert "historic_26.04/report.html" in html
        assert "historic_26.03/all.html" in html

    def test_fixed_pages_present(self):
        html = gen_index._generate([])
        assert 'data-fixed="features"' in html
        assert 'data-fixed="tifg"' in html
        assert 'data-fixed="wg11"' in html
        assert 'data-fixed="third_party"' in html

    def test_comparison_tab_present(self):
        """The comparison tab is included in the navigator."""
        html = gen_index._generate([])
        assert 'data-fixed="comparison"' in html
        assert ">Comparison<" in html
        assert "comparison.html" in html

    def test_comparison_in_fixed_pages_js(self):
        """FIXED_PAGES JS object includes comparison mapping."""
        html = gen_index._generate([])
        assert "comparison: 'comparison.html'" in html

    def test_run_history_present(self):
        html = gen_index._generate([])
        assert "run-selector-btn" in html
        assert "Run History" in html
        assert "runs.json" in html

    def test_subnav_present(self):
        html = gen_index._generate([])
        assert 'data-sub="report"' in html
        assert 'data-sub="all"' in html
        assert "Test Report" in html
        assert "All Tests" in html

    def test_iframe_present(self):
        html = gen_index._generate([])
        assert '<iframe id="frame"' in html

    def test_hash_navigation_js(self):
        """Hash-based navigation logic is present."""
        html = gen_index._generate([])
        assert "parseHash" in html
        assert "hashchange" in html

    def test_empty_historic_only_latest(self):
        """With no historic versions, only Latest tab appears."""
        html = gen_index._generate([])
        assert 'data-version="latest"' in html
        # No other version tabs
        assert 'data-version="26' not in html


# ---------------------------------------------------------------------------
# _main — CLI
# ---------------------------------------------------------------------------


class TestMain:
    def test_writes_to_file(self, tmp_path, monkeypatch):
        out = tmp_path / "index.html"
        monkeypatch.setattr(sys, "argv", ["gen_index.py", "-o", str(out)])
        gen_index._main()

        assert out.exists()
        content = out.read_text()
        assert "<!DOCTYPE html>" in content

    def test_with_historic(self, tmp_path, monkeypatch):
        out = tmp_path / "index.html"
        monkeypatch.setattr(sys, "argv", ["gen_index.py", "-o", str(out), "--historic", "26.04", "26.03"])
        gen_index._main()

        content = out.read_text()
        assert "26.04" in content
        assert "26.03" in content
