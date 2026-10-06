# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
# SPDX-FileCopyrightText: Copyright (C) 2026 OpenInfra Foundation Europe. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Tests for scripts/diff_runs.py — the test run comparison engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import diff_runs  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _results(tests_by_suite: dict[str, list[dict]], **kwargs) -> dict:
    """Build a minimal results.json structure from {suite_name: [test_entries]}."""
    suites = []
    for name, tests in tests_by_suite.items():
        suites.append({"name": name, "tests": tests})
    return {
        "schema_version": 1,
        "pipeline_id": kwargs.get("pipeline_id", ""),
        "commit_sha": kwargs.get("commit_sha", ""),
        "generated_at": kwargs.get("generated_at", ""),
        "suites": suites,
    }


def _test(key: str, status: str = "passed", duration: float = 1.0, labels: list | None = None) -> dict:
    """Build a single test entry."""
    return {
        "key": key,
        "status": status,
        "duration_s": duration,
        "labels": labels or [],
    }


# ---------------------------------------------------------------------------
# _flatten_results
# ---------------------------------------------------------------------------


class TestFlattenResults:
    def test_single_suite(self):
        results = _results({"E2E": [_test("a.test_1"), _test("a.test_2")]})
        flat = diff_runs._flatten_results(results)
        assert len(flat) == 2
        assert "a.test_1" in flat
        assert "a.test_2" in flat

    def test_multiple_suites(self):
        results = _results({
            "Unit": [_test("a.test_1")],
            "E2E": [_test("b.test_2")],
        })
        flat = diff_runs._flatten_results(results)
        assert len(flat) == 2

    def test_empty_suites(self):
        results = _results({})
        flat = diff_runs._flatten_results(results)
        assert flat == {}

    def test_duplicate_key_last_wins(self):
        """If same key appears in two suites, last one wins."""
        results = _results({
            "Unit": [_test("a.test_1", status="passed")],
            "E2E": [_test("a.test_1", status="failed")],
        })
        flat = diff_runs._flatten_results(results)
        assert flat["a.test_1"]["status"] == "failed"

    def test_missing_suites_key(self):
        flat = diff_runs._flatten_results({})
        assert flat == {}


# ---------------------------------------------------------------------------
# _classify
# ---------------------------------------------------------------------------


class TestClassify:
    def test_pass_to_fail_is_regression(self):
        assert diff_runs._classify("passed", "failed") == diff_runs.DiffClass.REGRESSION

    def test_pass_to_error_is_regression(self):
        assert diff_runs._classify("passed", "error") == diff_runs.DiffClass.REGRESSION

    def test_skip_to_fail_is_regression(self):
        assert diff_runs._classify("skipped", "failed") == diff_runs.DiffClass.REGRESSION

    def test_fail_to_pass_is_fix(self):
        assert diff_runs._classify("failed", "passed") == diff_runs.DiffClass.FIX

    def test_error_to_pass_is_fix(self):
        assert diff_runs._classify("error", "passed") == diff_runs.DiffClass.FIX

    def test_same_status_is_unchanged(self):
        assert diff_runs._classify("passed", "passed") == diff_runs.DiffClass.UNCHANGED
        assert diff_runs._classify("failed", "failed") == diff_runs.DiffClass.UNCHANGED
        assert diff_runs._classify("skipped", "skipped") == diff_runs.DiffClass.UNCHANGED

    def test_none_to_failed_is_new_failure(self):
        assert diff_runs._classify(None, "failed") == diff_runs.DiffClass.NEW_FAILURE

    def test_none_to_error_is_new_failure(self):
        assert diff_runs._classify(None, "error") == diff_runs.DiffClass.NEW_FAILURE

    def test_none_to_passed_is_new_pass(self):
        assert diff_runs._classify(None, "passed") == diff_runs.DiffClass.NEW_PASS

    def test_none_to_skipped_is_new_skip(self):
        assert diff_runs._classify(None, "skipped") == diff_runs.DiffClass.NEW_SKIP

    def test_status_to_none_is_removed(self):
        assert diff_runs._classify("passed", None) == diff_runs.DiffClass.REMOVED
        assert diff_runs._classify("failed", None) == diff_runs.DiffClass.REMOVED

    def test_pass_to_skip_is_unchanged(self):
        """pass->skip is an ambiguous transition, classified as unchanged."""
        assert diff_runs._classify("passed", "skipped") == diff_runs.DiffClass.UNCHANGED

    def test_fail_to_skip_is_unchanged(self):
        """fail->skip is ambiguous (test disabled, not fixed), classified as unchanged."""
        assert diff_runs._classify("failed", "skipped") == diff_runs.DiffClass.UNCHANGED


# ---------------------------------------------------------------------------
# diff_runs
# ---------------------------------------------------------------------------


class TestDiffRuns:
    def test_identical_runs(self):
        """Two identical runs produce no diff entries."""
        base = _results({"E2E": [_test("a.t1"), _test("a.t2")]})
        head = _results({"E2E": [_test("a.t1"), _test("a.t2")]})
        entries, summary = diff_runs.diff_runs(base, head)

        assert entries == []
        assert summary.unchanged == 2
        assert summary.regressions == 0

    def test_regression_detected(self):
        base = _results({"E2E": [_test("a.t1", status="passed")]})
        head = _results({"E2E": [_test("a.t1", status="failed")]})
        entries, summary = diff_runs.diff_runs(base, head)

        assert len(entries) == 1
        assert entries[0].diff_class == "regression"
        assert entries[0].status_base == "passed"
        assert entries[0].status_head == "failed"
        assert summary.regressions == 1

    def test_fix_detected(self):
        base = _results({"E2E": [_test("a.t1", status="failed")]})
        head = _results({"E2E": [_test("a.t1", status="passed")]})
        entries, summary = diff_runs.diff_runs(base, head)

        assert len(entries) == 1
        assert entries[0].diff_class == "fix"
        assert summary.fixes == 1

    def test_new_failure(self):
        base = _results({"E2E": []})
        head = _results({"E2E": [_test("a.t1", status="failed")]})
        entries, summary = diff_runs.diff_runs(base, head)

        assert len(entries) == 1
        assert entries[0].diff_class == "new_failure"
        assert entries[0].status_base is None
        assert summary.new_failures == 1

    def test_new_pass(self):
        base = _results({"E2E": []})
        head = _results({"E2E": [_test("a.t1", status="passed")]})
        entries, summary = diff_runs.diff_runs(base, head)

        assert len(entries) == 1
        assert entries[0].diff_class == "new_pass"
        assert summary.new_passes == 1

    def test_removed_test(self):
        base = _results({"E2E": [_test("a.t1", status="passed")]})
        head = _results({"E2E": []})
        entries, summary = diff_runs.diff_runs(base, head)

        assert len(entries) == 1
        assert entries[0].diff_class == "removed"
        assert entries[0].status_head is None
        assert summary.removed == 1

    def test_mixed_changes(self):
        """Multiple change types in a single diff."""
        base = _results({"E2E": [
            _test("a.t1", status="passed"),   # will regress
            _test("a.t2", status="failed"),   # will be fixed
            _test("a.t3", status="passed"),   # unchanged
            _test("a.t4", status="passed"),   # will be removed
        ]})
        head = _results({"E2E": [
            _test("a.t1", status="failed"),
            _test("a.t2", status="passed"),
            _test("a.t3", status="passed"),
            _test("a.t5", status="failed"),   # new failure
        ]})
        entries, summary = diff_runs.diff_runs(base, head)

        assert summary.regressions == 1
        assert summary.fixes == 1
        assert summary.unchanged == 1
        assert summary.removed == 1
        assert summary.new_failures == 1
        # Unchanged tests are NOT in entries
        assert len(entries) == 4

    def test_empty_base(self):
        """All tests in head are new."""
        base = _results({})
        head = _results({"E2E": [_test("a.t1"), _test("a.t2", status="failed")]})
        entries, summary = diff_runs.diff_runs(base, head)

        assert summary.total_base == 0
        assert summary.total_head == 2
        assert summary.new_passes == 1
        assert summary.new_failures == 1

    def test_empty_head(self):
        """All tests in base are removed."""
        base = _results({"E2E": [_test("a.t1"), _test("a.t2")]})
        head = _results({})
        entries, summary = diff_runs.diff_runs(base, head)

        assert summary.total_base == 2
        assert summary.total_head == 0
        assert summary.removed == 2

    def test_both_empty(self):
        base = _results({})
        head = _results({})
        entries, summary = diff_runs.diff_runs(base, head)

        assert entries == []
        assert summary.total_base == 0
        assert summary.total_head == 0

    def test_labels_from_head(self):
        """Labels in diff entries come from the head run."""
        base = _results({"E2E": [_test("a.t1", status="passed", labels=["old-label"])]})
        head = _results({"E2E": [_test("a.t1", status="failed", labels=["MVP-FUNC-1"])]})
        entries, _ = diff_runs.diff_runs(base, head)

        assert entries[0].labels == ["MVP-FUNC-1"]

    def test_duration_preserved(self):
        """Duration values from both runs are preserved in entries."""
        base = _results({"E2E": [_test("a.t1", status="passed", duration=10.5)]})
        head = _results({"E2E": [_test("a.t1", status="failed", duration=25.3)]})
        entries, _ = diff_runs.diff_runs(base, head)

        assert entries[0].duration_base == 10.5
        assert entries[0].duration_head == 25.3

    def test_entries_sorted_by_key(self):
        """Entries within each category are sorted by key for deterministic output."""
        base = _results({"E2E": [
            _test("z.test", status="passed"),
            _test("a.test", status="passed"),
            _test("m.test", status="passed"),
        ]})
        head = _results({"E2E": [
            _test("z.test", status="failed"),
            _test("a.test", status="failed"),
            _test("m.test", status="failed"),
        ]})
        entries, _ = diff_runs.diff_runs(base, head)

        keys = [e.key for e in entries]
        assert keys == sorted(keys)

    def test_cross_suite_matching(self):
        """A test that moves between suites is matched by key, not suite."""
        base = _results({"Unit": [_test("a.t1", status="passed")]})
        head = _results({"E2E": [_test("a.t1", status="failed")]})
        entries, summary = diff_runs.diff_runs(base, head)

        assert summary.regressions == 1
        assert entries[0].key == "a.t1"


# ---------------------------------------------------------------------------
# build_diff_output
# ---------------------------------------------------------------------------


class TestBuildDiffOutput:
    def test_output_structure(self):
        base = _results({"E2E": [_test("a.t1", status="passed")]},
                        pipeline_id="100", commit_sha="aaa")
        head = _results({"E2E": [_test("a.t1", status="failed")]},
                        pipeline_id="200", commit_sha="bbb")
        output = diff_runs.build_diff_output(base, head)

        assert output["schema_version"] == 1
        assert output["base"]["pipeline_id"] == "100"
        assert output["base"]["commit_sha"] == "aaa"
        assert output["head"]["pipeline_id"] == "200"
        assert output["head"]["commit_sha"] == "bbb"
        assert "summary" in output
        assert "regressions" in output
        assert "fixes" in output
        assert "new_failures" in output
        assert "new_passes" in output
        assert "new_skips" in output
        assert "removed" in output

    def test_entries_grouped_correctly(self):
        base = _results({"E2E": [
            _test("a.t1", status="passed"),
            _test("a.t2", status="failed"),
        ]})
        head = _results({"E2E": [
            _test("a.t1", status="failed"),
            _test("a.t2", status="passed"),
            _test("a.t3", status="failed"),
        ]})
        output = diff_runs.build_diff_output(base, head)

        assert len(output["regressions"]) == 1
        assert output["regressions"][0]["key"] == "a.t1"
        assert len(output["fixes"]) == 1
        assert output["fixes"][0]["key"] == "a.t2"
        assert len(output["new_failures"]) == 1
        assert output["new_failures"][0]["key"] == "a.t3"

    def test_json_serialisable(self):
        """Output can be serialised to JSON without errors."""
        base = _results({"E2E": [_test("a.t1", status="passed")]})
        head = _results({"E2E": [_test("a.t1", status="failed")]})
        output = diff_runs.build_diff_output(base, head)

        text = json.dumps(output, indent=2)
        assert "regression" in text

    def test_no_diff_class_in_entries(self):
        """Individual entries don't include diff_class (redundant once grouped)."""
        base = _results({"E2E": [_test("a.t1", status="passed")]})
        head = _results({"E2E": [_test("a.t1", status="failed")]})
        output = diff_runs.build_diff_output(base, head)

        for entry in output["regressions"]:
            assert "diff_class" not in entry


# ---------------------------------------------------------------------------
# CLI integration (main)
# ---------------------------------------------------------------------------


class TestMain:
    def test_file_not_found_base(self, tmp_path, monkeypatch):
        """Exits with error when base file doesn't exist."""
        head = tmp_path / "head.json"
        head.write_text(json.dumps(_results({})))

        monkeypatch.setattr(sys, "argv", ["diff_runs.py", str(tmp_path / "nope.json"), str(head)])
        with pytest.raises(SystemExit) as exc_info:
            diff_runs.main()
        assert exc_info.value.code == 1

    def test_file_not_found_head(self, tmp_path, monkeypatch):
        """Exits with error when head file doesn't exist."""
        base = tmp_path / "base.json"
        base.write_text(json.dumps(_results({})))

        monkeypatch.setattr(sys, "argv", ["diff_runs.py", str(base), str(tmp_path / "nope.json")])
        with pytest.raises(SystemExit) as exc_info:
            diff_runs.main()
        assert exc_info.value.code == 1

    def test_writes_output_file(self, tmp_path, monkeypatch):
        """Writes diff to output file when -o is specified."""
        base = tmp_path / "base.json"
        head = tmp_path / "head.json"
        out = tmp_path / "diff.json"

        base.write_text(json.dumps(_results({"E2E": [_test("a.t1", status="passed")]})))
        head.write_text(json.dumps(_results({"E2E": [_test("a.t1", status="failed")]})))

        monkeypatch.setattr(sys, "argv", ["diff_runs.py", str(base), str(head), "-o", str(out)])
        diff_runs.main()

        assert out.exists()
        result = json.loads(out.read_text())
        assert result["summary"]["regressions"] == 1

    def test_stdout_output(self, tmp_path, monkeypatch, capsys):
        """Writes to stdout when no -o is specified."""
        base = tmp_path / "base.json"
        head = tmp_path / "head.json"

        base.write_text(json.dumps(_results({"E2E": [_test("a.t1")]})))
        head.write_text(json.dumps(_results({"E2E": [_test("a.t1")]})))

        monkeypatch.setattr(sys, "argv", ["diff_runs.py", str(base), str(head)])
        diff_runs.main()

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["summary"]["unchanged"] == 1
