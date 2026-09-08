# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Tests for data-processing logic in the report scripts.

These test pure functions where silent bugs corrupt report output.
"""

import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import gitlab_fetch  # noqa: E402
import xunit_report  # noqa: E402


# ---------------------------------------------------------------------------
# _safe_name — filesystem name sanitisation
# ---------------------------------------------------------------------------


class TestSafeName:
    def test_simple_name_unchanged(self):
        assert gitlab_fetch._safe_name("E2E_Functional") == "E2E_Functional"

    def test_spaces_replaced(self):
        assert gitlab_fetch._safe_name("E2E Functional") == "E2E_Functional"

    def test_parens_replaced(self):
        assert gitlab_fetch._safe_name("E2E (nightly)") == "E2E__nightly"

    def test_special_chars_replaced(self):
        assert gitlab_fetch._safe_name("suite:test/run") == "suite_test_run"

    def test_leading_trailing_stripped(self):
        assert gitlab_fetch._safe_name("...hello...") == "hello"

    def test_dots_and_dashes_preserved(self):
        assert gitlab_fetch._safe_name("v1.0-release") == "v1.0-release"

    def test_empty_string(self):
        assert gitlab_fetch._safe_name("") == ""

    def test_collision_example(self):
        """Two different inputs can produce the same safe name — this is the known bug."""
        a = gitlab_fetch._safe_name("E2E (nightly)")
        b = gitlab_fetch._safe_name("E2E__nightly")
        assert a == b  # demonstrates the collision


# ---------------------------------------------------------------------------
# _parse_testcase — XML element to TestCase dataclass
# ---------------------------------------------------------------------------


def _xml(text: str) -> ET.Element:
    """Helper to parse an XML string into an element."""
    return ET.fromstring(text)


class TestParseTestcase:
    def test_passed_test(self):
        elem = _xml('<testcase name="test_add" classname="math_test" time="0.5"/>')
        tc = xunit_report._parse_testcase(elem)
        assert tc.name == "test_add"
        assert tc.classname == "math_test"
        assert tc.duration == 0.5
        assert tc.status == xunit_report.Status.PASSED
        assert tc.message == ""

    def test_failed_test(self):
        elem = _xml('''
            <testcase name="test_div" classname="math_test" time="1.2">
                <failure message="division by zero"/>
            </testcase>
        ''')
        tc = xunit_report._parse_testcase(elem)
        assert tc.status == xunit_report.Status.FAILED
        assert tc.message == "division by zero"

    def test_error_test(self):
        elem = _xml('''
            <testcase name="test_crash" classname="core" time="0">
                <error message="segfault"/>
            </testcase>
        ''')
        tc = xunit_report._parse_testcase(elem)
        assert tc.status == xunit_report.Status.ERROR
        assert tc.message == "segfault"

    def test_skipped_test(self):
        elem = _xml('''
            <testcase name="test_skip" classname="core" time="0">
                <skipped message="not implemented"/>
            </testcase>
        ''')
        tc = xunit_report._parse_testcase(elem)
        assert tc.status == xunit_report.Status.SKIPPED

    def test_cmake_labels_parsed(self):
        elem = _xml('''
            <testcase name="test_phy" classname="phy_test" time="0.1">
                <properties>
                    <property name="cmake_labels" value="phy;tsan;MVP-ARCH-1"/>
                </properties>
            </testcase>
        ''')
        tc = xunit_report._parse_testcase(elem)
        assert tc.labels == ["phy", "tsan", "MVP-ARCH-1"]

    def test_empty_labels_ignored(self):
        elem = _xml('''
            <testcase name="t" classname="c" time="0">
                <properties>
                    <property name="cmake_labels" value="a;;b; ;c"/>
                </properties>
            </testcase>
        ''')
        tc = xunit_report._parse_testcase(elem)
        assert tc.labels == ["a", "b", "c"]

    def test_missing_time_defaults_zero(self):
        elem = _xml('<testcase name="t" classname="c"/>')
        tc = xunit_report._parse_testcase(elem)
        assert tc.duration == 0.0

    def test_system_out_captured(self):
        elem = _xml('''
            <testcase name="t" classname="c" time="0">
                <system-out>hello world</system-out>
            </testcase>
        ''')
        tc = xunit_report._parse_testcase(elem)
        assert "hello world" in tc.system_out

    def test_failure_text_as_message(self):
        """When failure has no message attr, use element text."""
        elem = _xml('''
            <testcase name="t" classname="c" time="0">
                <failure>assertion failed at line 42</failure>
            </testcase>
        ''')
        tc = xunit_report._parse_testcase(elem)
        assert tc.status == xunit_report.Status.FAILED
        assert "assertion failed" in tc.message


# ---------------------------------------------------------------------------
# _load_feature_map — YAML to {test_id: [feature_ids]}
# ---------------------------------------------------------------------------


class TestLoadFeatureMap:
    def _write_yaml(self, content: str) -> Path:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
        f.write(content)
        f.close()
        return Path(f.name)

    def test_basic_mapping(self):
        path = self._write_yaml("""
tests:
  - test_id: "5.3"
    ocudu_features: ["MVP-FUNC-1", "MVP-FUNC-2"]
  - test_id: "5.4"
    ocudu_features: ["MVP-FUNC-3"]
""")
        result = xunit_report._load_feature_map(path)
        assert result == {"5.3": ["MVP-FUNC-1", "MVP-FUNC-2"], "5.4": ["MVP-FUNC-3"]}
        path.unlink()

    @pytest.mark.xfail(reason="Known bug: null test_id becomes string 'None'. Fixed in fix/misc-corrections.")
    def test_null_test_id_skipped(self):
        """The bug: null test_id should not create a 'None' string key."""
        path = self._write_yaml("""
tests:
  - test_id: null
    ocudu_features: ["MVP-FUNC-1"]
  - test_id: "5.3"
    ocudu_features: ["MVP-FUNC-2"]
""")
        result = xunit_report._load_feature_map(path)
        assert "None" not in result
        assert result == {"5.3": ["MVP-FUNC-2"]}
        path.unlink()

    def test_empty_features_skipped(self):
        path = self._write_yaml("""
tests:
  - test_id: "5.3"
    ocudu_features: []
""")
        result = xunit_report._load_feature_map(path)
        assert result == {}
        path.unlink()

    def test_missing_features_key_skipped(self):
        path = self._write_yaml("""
tests:
  - test_id: "5.3"
""")
        result = xunit_report._load_feature_map(path)
        assert result == {}
        path.unlink()

    def test_numeric_test_id_converted_to_string(self):
        """YAML may parse '5.3' as a float if unquoted."""
        path = self._write_yaml("""
tests:
  - test_id: 5.3
    ocudu_features: ["MVP-FUNC-1"]
""")
        result = xunit_report._load_feature_map(path)
        assert "5.3" in result
        path.unlink()


# ---------------------------------------------------------------------------
# _group_by_features — the core linking logic
# ---------------------------------------------------------------------------


class TestGroupByFeatures:
    def _make_tc(self, name, labels, status=xunit_report.Status.PASSED):
        return xunit_report.TestCase(
            name=name, classname="test", duration=1.0, status=status, labels=labels
        )

    def _make_suite(self, name, testcases):
        s = xunit_report.Suite(name=name)
        s.testcases = testcases
        return s

    def _make_features(self, ids):
        """Create a features dict from a list of IDs."""
        return {fid: xunit_report.FeatureDef(description=f"Feature {fid}", labels={fid}) for fid in ids}

    def test_test_matches_feature_by_label(self):
        features = self._make_features(["MVP-FUNC-1"])
        tc = self._make_tc("test_a", ["MVP-FUNC-1", "other"])
        suite = self._make_suite("E2E", [tc])

        result = xunit_report._group_by_features([suite], features)

        assert "MVP-FUNC-1" in result
        assert len(result["MVP-FUNC-1"].suites["E2E"][1]) == 1

    def test_unmatched_test_not_in_any_feature(self):
        features = self._make_features(["MVP-FUNC-1"])
        tc = self._make_tc("test_a", ["phy", "tsan"])
        suite = self._make_suite("Unit", [tc])

        result = xunit_report._group_by_features([suite], features)

        assert result["MVP-FUNC-1"].suites == {}

    def test_feature_with_no_tests_still_present(self):
        """All defined features appear even if no test matches them."""
        features = self._make_features(["MVP-FUNC-1", "MVP-FUNC-2"])
        tc = self._make_tc("test_a", ["MVP-FUNC-1"])
        suite = self._make_suite("E2E", [tc])

        result = xunit_report._group_by_features([suite], features)

        assert "MVP-FUNC-2" in result
        assert result["MVP-FUNC-2"].suites == {}

    def test_test_matches_multiple_features(self):
        features = self._make_features(["MVP-FUNC-1", "MVP-FUNC-2"])
        tc = self._make_tc("test_a", ["MVP-FUNC-1", "MVP-FUNC-2"])
        suite = self._make_suite("E2E", [tc])

        result = xunit_report._group_by_features([suite], features)

        assert len(result["MVP-FUNC-1"].suites["E2E"][1]) == 1
        assert len(result["MVP-FUNC-2"].suites["E2E"][1]) == 1

    def test_multiple_suites_grouped_correctly(self):
        features = self._make_features(["MVP-FUNC-1"])
        tc1 = self._make_tc("test_a", ["MVP-FUNC-1"])
        tc2 = self._make_tc("test_b", ["MVP-FUNC-1"])
        suite1 = self._make_suite("E2E", [tc1])
        suite2 = self._make_suite("Unit", [tc2])

        result = xunit_report._group_by_features([suite1, suite2], features)

        assert "E2E" in result["MVP-FUNC-1"].suites
        assert "Unit" in result["MVP-FUNC-1"].suites

    def test_pipe_alias_matching(self):
        """Features with pipe-separated aliases match on any alias."""
        features = {"Display Name": xunit_report.FeatureDef(
            description="Test", labels={"Display Name", "alias1", "alias2"}
        )}
        tc = self._make_tc("test_a", ["alias1"])
        suite = self._make_suite("E2E", [tc])

        result = xunit_report._group_by_features([suite], features)

        assert len(result["Display Name"].suites["E2E"][1]) == 1



# ---------------------------------------------------------------------------
# _truncate_log — log preview splitting
# ---------------------------------------------------------------------------


class TestTruncateLog:
    def test_short_text_not_truncated(self):
        """Text with fewer lines than max_lines is returned as-is."""
        text = "line 1\nline 2\nline 3"
        preview, remainder, was_truncated = xunit_report._truncate_log(text, max_lines=5)
        assert preview == text
        assert remainder == ""
        assert was_truncated is False

    def test_exact_max_lines_not_truncated(self):
        """Text with exactly max_lines lines is not truncated."""
        text = "\n".join(f"line {i}" for i in range(20))
        preview, remainder, was_truncated = xunit_report._truncate_log(text, max_lines=20)
        assert preview == text
        assert remainder == ""
        assert was_truncated is False

    def test_longer_text_is_truncated(self):
        """Text exceeding max_lines is split correctly."""
        lines = [f"line {i}" for i in range(30)]
        text = "\n".join(lines)
        preview, remainder, was_truncated = xunit_report._truncate_log(text, max_lines=20)
        assert preview == "\n".join(lines[:20])
        assert remainder == "\n".join(lines[20:])
        assert was_truncated is True

    def test_single_line_not_truncated(self):
        preview, remainder, was_truncated = xunit_report._truncate_log("hello", max_lines=5)
        assert preview == "hello"
        assert remainder == ""
        assert was_truncated is False

    def test_empty_string(self):
        preview, remainder, was_truncated = xunit_report._truncate_log("", max_lines=5)
        assert preview == ""
        assert remainder == ""
        assert was_truncated is False

    def test_default_max_lines(self):
        """Uses _DEFAULT_PREVIEW_LINES (20) when no max_lines given."""
        lines = [f"line {i}" for i in range(25)]
        text = "\n".join(lines)
        preview, remainder, was_truncated = xunit_report._truncate_log(text)
        assert preview == "\n".join(lines[:20])
        assert remainder == "\n".join(lines[20:])
        assert was_truncated is True

    def test_max_lines_one(self):
        text = "first\nsecond\nthird"
        preview, remainder, was_truncated = xunit_report._truncate_log(text, max_lines=1)
        assert preview == "first"
        assert remainder == "second\nthird"
        assert was_truncated is True


# ---------------------------------------------------------------------------
# _strip_headers — capture header removal and escape normalisation
# ---------------------------------------------------------------------------


class TestStripHeaders:
    def test_removes_capture_header(self):
        text = "---- Captured stdout ----\nhello world"
        assert xunit_report._strip_headers(text) == "hello world"

    def test_removes_multiple_headers(self):
        text = "---- Captured stdout ----\nfirst\n---- Captured stderr ----\nsecond"
        result = xunit_report._strip_headers(text)
        assert "Captured stdout" not in result
        assert "Captured stderr" not in result
        assert "first" in result
        assert "second" in result

    def test_normalises_escape_sequence(self):
        """pytest XML writer encodes ESC as #x1B (missing the &)."""
        text = "#x1B[31mred text#x1B[0m"
        result = xunit_report._strip_headers(text)
        assert "\x1b[31m" in result
        assert "#x1B" not in result

    def test_strips_surrounding_whitespace(self):
        text = "  \n  hello  \n  "
        assert xunit_report._strip_headers(text) == "hello"

    def test_preserves_ansi_codes(self):
        """ANSI escape codes should remain as-is (not converted to HTML)."""
        text = "\x1b[32mPASSED\x1b[0m"
        result = xunit_report._strip_headers(text)
        assert "\x1b[32m" in result
        assert "<span" not in result

    def test_empty_string(self):
        assert xunit_report._strip_headers("") == ""


# ---------------------------------------------------------------------------
# _ansi_to_html — ANSI code to HTML span conversion
# ---------------------------------------------------------------------------


class TestAnsiToHtml:
    def test_plain_text_unchanged(self):
        result = xunit_report._ansi_to_html("hello world")
        assert "hello world" in result

    def test_ansi_codes_converted_to_spans(self):
        text = "\x1b[31mERROR\x1b[0m"
        result = xunit_report._ansi_to_html(text)
        assert "<span" in result
        assert "ERROR" in result
        # Raw ANSI code should not appear in output
        assert "\x1b[" not in result

    def test_empty_string(self):
        result = xunit_report._ansi_to_html("")
        # Should not crash; result is either empty or minimal wrapper
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _safe_filename — collision-resistant filename from test identity
# ---------------------------------------------------------------------------


class TestSafeFilename:
    def test_basic_filename(self):
        result = xunit_report._safe_filename("E2E", "com.example.TestClass", "test_method")
        assert result.endswith(".txt")
        assert len(result) <= 100  # slug(80) + _ + hash(8) + suffix

    def test_includes_hash_for_collision_avoidance(self):
        """Different inputs produce different filenames even if slugs collide."""
        a = xunit_report._safe_filename("s", "a.b", "test (1)")
        b = xunit_report._safe_filename("s", "a.b", "test_1_")
        assert a != b

    def test_same_test_in_different_suites_does_not_collide(self):
        """Same classname.name in two suites must map to different files."""
        a = xunit_report._safe_filename("E2E", "a.b", "test")
        b = xunit_report._safe_filename("Integration", "a.b", "test")
        assert a != b

    def test_custom_suffix(self):
        result = xunit_report._safe_filename("suite", "cls", "name", suffix="_out.txt")
        assert result.endswith("_out.txt")

    def test_long_name_truncated(self):
        """Slug is capped at 80 chars."""
        long_name = "a" * 200
        result = xunit_report._safe_filename("suite", "", long_name)
        # Total: slug(<=80) + "_" + hash(8) + suffix
        slug_part = result.rsplit("_", 1)[0]
        assert len(slug_part) <= 80

    def test_special_chars_replaced(self):
        result = xunit_report._safe_filename("pkg suite", "pkg::cls", "test<foo>/bar")
        # No special characters in the filename
        assert "::" not in result
        assert "<" not in result
        assert "/" not in result

    def test_empty_classname(self):
        """When classname is empty, uses just the suite and name."""
        result = xunit_report._safe_filename("suite", "", "test_simple")
        assert "test_simple" in result

    def test_deterministic(self):
        """Same inputs always produce the same filename."""
        a = xunit_report._safe_filename("suite", "cls", "name")
        b = xunit_report._safe_filename("suite", "cls", "name")
        assert a == b


# ---------------------------------------------------------------------------
# _render_external_log — sidecar file writing and preview rendering
# ---------------------------------------------------------------------------


class TestRenderExternalLog:
    def test_short_log_no_sidecar(self, tmp_path):
        """Logs under 20 lines stay fully inline with no file written."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        text = "short log\nonly two lines"
        result = xunit_report._render_external_log(text, "suite", "cls", "test", "out", "system-out", log_dir)
        assert "<pre" in result
        assert "short log" in result
        # No link, no file
        assert "log-link" not in result
        assert len(list(log_dir.iterdir())) == 0

    def test_long_log_writes_sidecar(self, tmp_path):
        """Logs over 20 lines get written to a sidecar file."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        lines = [f"line {i}" for i in range(30)]
        text = "\n".join(lines)
        result = xunit_report._render_external_log(text, "suite", "cls", "test", "out", "system-out", log_dir)
        # Sidecar file created
        files = list(log_dir.iterdir())
        assert len(files) == 1
        assert files[0].suffix == ".html"
        # Link present in HTML
        assert "log-link" in result
        assert "View full log (30 lines)" in result

    def test_sidecar_contains_rendered_html(self, tmp_path):
        """The sidecar stores ANSI converted to HTML colour spans, not raw text."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        # Include ANSI codes in the text
        lines = [f"\x1b[32mline {i}\x1b[0m" for i in range(25)]
        text = "\n".join(lines)
        xunit_report._render_external_log(text, "suite", "cls", "test", "out", "system-out", log_dir)
        sidecar = list(log_dir.iterdir())[0]
        content = sidecar.read_text(encoding="utf-8")
        # ANSI converted to colour spans, raw escape codes gone
        assert "<span" in content
        assert "\x1b[32m" not in content

    def test_sidecar_escapes_log_markup(self, tmp_path):
        """Log content that looks like HTML is escaped, so innerHTML is safe."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        lines = ["<script>alert(1)</script>"] + [f"line {i}" for i in range(25)]
        text = "\n".join(lines)
        xunit_report._render_external_log(text, "suite", "cls", "test", "out", "system-out", log_dir)
        sidecar = list(log_dir.iterdir())[0]
        content = sidecar.read_text(encoding="utf-8")
        assert "<script>" not in content
        assert "&lt;script&gt;" in content

    def test_preview_contains_html(self, tmp_path):
        """The inline preview has ANSI codes converted to HTML spans."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        lines = [f"\x1b[31mERROR line {i}\x1b[0m" for i in range(25)]
        text = "\n".join(lines)
        result = xunit_report._render_external_log(text, "suite", "cls", "test", "out", "system-out", log_dir)
        # Preview portion should have HTML spans (ANSI converted)
        assert "<span" in result
        # Raw ANSI codes should NOT be in the HTML output
        assert "\x1b[" not in result

    def test_out_vs_err_different_files(self, tmp_path):
        """system-out and system-err for the same test get separate files."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        text = "\n".join(f"line {i}" for i in range(25))
        xunit_report._render_external_log(text, "suite", "cls", "test", "out", "system-out", log_dir)
        xunit_report._render_external_log(text, "suite", "cls", "test", "err", "system-err", log_dir)
        files = sorted(f.name for f in log_dir.iterdir())
        assert len(files) == 2
        assert any("_out.html" in f for f in files)
        assert any("_err.html" in f for f in files)


# ---------------------------------------------------------------------------
# _build_run_metadata — run summary JSON construction
# ---------------------------------------------------------------------------


class TestBuildRunMetadata:
    def _make_suite(self, name, passed=0, failed=0, skipped=0):
        """Create a Suite with dummy test cases matching the given counts."""
        tcs = []
        for i in range(passed):
            tcs.append(xunit_report.TestCase(
                name=f"pass_{i}", classname="test", duration=1.0, status=xunit_report.Status.PASSED
            ))
        for i in range(failed):
            tcs.append(xunit_report.TestCase(
                name=f"fail_{i}", classname="test", duration=2.0, status=xunit_report.Status.FAILED
            ))
        for i in range(skipped):
            tcs.append(xunit_report.TestCase(
                name=f"skip_{i}", classname="test", duration=0.0, status=xunit_report.Status.SKIPPED
            ))
        s = xunit_report.Suite(name=name)
        s.testcases = tcs
        return s

    def test_basic_metadata_structure(self):
        """Metadata has all required top-level keys."""
        suites = [self._make_suite("E2E", passed=5, failed=2, skipped=1)]
        result = xunit_report._build_run_metadata(suites, pipeline_id="123", commit_sha="abc123")

        assert result["schema_version"] == 1
        assert result["pipeline_id"] == "123"
        assert result["commit_sha"] == "abc123"
        assert "generated_at" in result
        assert "suites" in result
        assert "totals" in result

    def test_suite_summaries(self):
        """Each suite has correct per-suite counts."""
        suites = [
            self._make_suite("Unit", passed=10, failed=1, skipped=2),
            self._make_suite("E2E", passed=3, failed=0, skipped=0),
        ]
        result = xunit_report._build_run_metadata(suites)

        assert len(result["suites"]) == 2
        unit_meta = result["suites"][0]
        assert unit_meta["name"] == "Unit"
        assert unit_meta["total"] == 13
        assert unit_meta["passed"] == 10
        assert unit_meta["failed"] == 1
        assert unit_meta["skipped"] == 2
        assert unit_meta["duration_s"] == 12.0  # 10*1 + 1*2 + 2*0

    def test_totals_aggregated(self):
        """Totals section sums across all suites."""
        suites = [
            self._make_suite("Unit", passed=10, failed=1, skipped=2),
            self._make_suite("E2E", passed=3, failed=2, skipped=0),
        ]
        result = xunit_report._build_run_metadata(suites)

        totals = result["totals"]
        assert totals["suites"] == 2
        assert totals["tests"] == 18
        assert totals["passed"] == 13
        assert totals["failed"] == 3
        assert totals["skipped"] == 2

    def test_empty_suites(self):
        """Handles empty suite list gracefully."""
        result = xunit_report._build_run_metadata([])

        assert result["suites"] == []
        assert result["totals"]["suites"] == 0
        assert result["totals"]["tests"] == 0

    def test_empty_pipeline_id_and_commit_sha_default(self):
        """Pipeline ID and commit SHA default to empty string."""
        result = xunit_report._build_run_metadata([])

        assert result["pipeline_id"] == ""
        assert result["commit_sha"] == ""

    def test_generated_at_is_utc_iso_format(self):
        """Timestamp is ISO 8601 with UTC timezone."""
        result = xunit_report._build_run_metadata([])
        ts = result["generated_at"]
        # Should end with +00:00 (UTC)
        assert "+00:00" in ts or "Z" in ts

    def test_duration_rounded_to_2dp(self):
        """Duration values are rounded to 2 decimal places."""
        # Create a suite with durations that would produce floating point noise
        s = xunit_report.Suite(name="Precision")
        s.testcases = [
            xunit_report.TestCase(name="t1", classname="c", duration=0.1, status=xunit_report.Status.PASSED),
            xunit_report.TestCase(name="t2", classname="c", duration=0.2, status=xunit_report.Status.PASSED),
            xunit_report.TestCase(name="t3", classname="c", duration=0.3, status=xunit_report.Status.PASSED),
        ]
        result = xunit_report._build_run_metadata([s])

        # 0.1 + 0.2 + 0.3 can produce 0.6000000000000001 without rounding
        assert result["suites"][0]["duration_s"] == 0.6
        assert result["totals"]["duration_s"] == 0.6

    def test_json_serialisable(self):
        """The returned dict can be serialised to JSON without errors."""
        import json

        suites = [self._make_suite("E2E", passed=5, failed=2, skipped=1)]
        result = xunit_report._build_run_metadata(suites, pipeline_id="999", commit_sha="deadbeef")
        # Should not raise
        output = json.dumps(result, indent=2)
        assert "deadbeef" in output


# ---------------------------------------------------------------------------
# _build_results_json — per-test-case structured output for comparison engine
# ---------------------------------------------------------------------------


class TestBuildResultsJson:
    def _make_tc(self, name, classname="tests.module", status=xunit_report.Status.PASSED,
                 duration=1.0, labels=None):
        return xunit_report.TestCase(
            name=name, classname=classname, duration=duration,
            status=status, labels=labels or [],
        )

    def _make_suite(self, name, testcases):
        s = xunit_report.Suite(name=name)
        s.testcases = testcases
        return s

    def test_basic_structure(self):
        """Result has all required top-level keys."""
        tc = self._make_tc("test_a")
        suite = self._make_suite("E2E", [tc])
        result = xunit_report._build_results_json([suite], pipeline_id="42", commit_sha="abc")

        assert result["schema_version"] == 1
        assert result["pipeline_id"] == "42"
        assert result["commit_sha"] == "abc"
        assert "generated_at" in result
        assert "suites" in result

    def test_composite_key_format(self):
        """Test key is classname.name."""
        tc = self._make_tc("test_add", classname="math_tests.arithmetic")
        suite = self._make_suite("Unit", [tc])
        result = xunit_report._build_results_json([suite])

        entry = result["suites"][0]["tests"][0]
        assert entry["key"] == "math_tests.arithmetic.test_add"

    def test_empty_classname_key(self):
        """When classname is empty, key is just the name."""
        tc = self._make_tc("test_standalone", classname="")
        suite = self._make_suite("Unit", [tc])
        result = xunit_report._build_results_json([suite])

        entry = result["suites"][0]["tests"][0]
        assert entry["key"] == "test_standalone"

    def test_status_values(self):
        """All status types are serialised correctly."""
        tcs = [
            self._make_tc("t1", status=xunit_report.Status.PASSED),
            self._make_tc("t2", status=xunit_report.Status.FAILED),
            self._make_tc("t3", status=xunit_report.Status.ERROR),
            self._make_tc("t4", status=xunit_report.Status.SKIPPED),
        ]
        suite = self._make_suite("Mixed", tcs)
        result = xunit_report._build_results_json([suite])

        statuses = [t["status"] for t in result["suites"][0]["tests"]]
        assert statuses == ["passed", "failed", "error", "skipped"]

    def test_duration_rounded_to_3dp(self):
        """Duration is rounded to 3 decimal places (millisecond precision)."""
        tc = self._make_tc("t1", duration=1.23456789)
        suite = self._make_suite("E2E", [tc])
        result = xunit_report._build_results_json([suite])

        assert result["suites"][0]["tests"][0]["duration_s"] == 1.235

    def test_labels_preserved(self):
        """Labels are included in test entries."""
        tc = self._make_tc("t1", labels=["MVP-FUNC-1", "phy", "tsan"])
        suite = self._make_suite("E2E", [tc])
        result = xunit_report._build_results_json([suite])

        assert result["suites"][0]["tests"][0]["labels"] == ["MVP-FUNC-1", "phy", "tsan"]

    def test_empty_labels(self):
        """Tests with no labels have an empty list."""
        tc = self._make_tc("t1", labels=[])
        suite = self._make_suite("E2E", [tc])
        result = xunit_report._build_results_json([suite])

        assert result["suites"][0]["tests"][0]["labels"] == []

    def test_multiple_suites(self):
        """Multiple suites each have their own test list."""
        tc1 = self._make_tc("t1")
        tc2 = self._make_tc("t2")
        tc3 = self._make_tc("t3")
        s1 = self._make_suite("Unit", [tc1, tc2])
        s2 = self._make_suite("E2E", [tc3])
        result = xunit_report._build_results_json([s1, s2])

        assert len(result["suites"]) == 2
        assert result["suites"][0]["name"] == "Unit"
        assert len(result["suites"][0]["tests"]) == 2
        assert result["suites"][1]["name"] == "E2E"
        assert len(result["suites"][1]["tests"]) == 1

    def test_empty_suites(self):
        """Empty suite list produces empty suites array."""
        result = xunit_report._build_results_json([])
        assert result["suites"] == []

    def test_suite_with_no_tests(self):
        """A suite with no test cases produces an empty tests array."""
        suite = self._make_suite("Empty", [])
        result = xunit_report._build_results_json([suite])
        assert result["suites"][0]["tests"] == []

    def test_defaults_for_pipeline_and_commit(self):
        """Pipeline ID and commit SHA default to empty strings."""
        result = xunit_report._build_results_json([])
        assert result["pipeline_id"] == ""
        assert result["commit_sha"] == ""

    def test_generated_at_is_utc(self):
        """Timestamp is UTC ISO 8601."""
        result = xunit_report._build_results_json([])
        ts = result["generated_at"]
        assert "+00:00" in ts or "Z" in ts

    def test_json_serialisable(self):
        """The returned dict can be serialised to JSON without errors."""
        import json

        tc = self._make_tc("test_a", labels=["MVP-FUNC-1"])
        suite = self._make_suite("E2E", [tc])
        result = xunit_report._build_results_json([suite], pipeline_id="999", commit_sha="deadbeef")
        output = json.dumps(result, indent=2)
        assert "deadbeef" in output
        assert "MVP-FUNC-1" in output

    def test_large_suite_performance(self):
        """Handles a large number of test cases without issues."""
        tcs = [self._make_tc(f"test_{i}", classname=f"module.sub_{i % 10}") for i in range(1000)]
        suite = self._make_suite("Large", tcs)
        result = xunit_report._build_results_json([suite])

        assert len(result["suites"][0]["tests"]) == 1000
        # Spot check a few entries
        assert result["suites"][0]["tests"][0]["key"] == "module.sub_0.test_0"
        assert result["suites"][0]["tests"][999]["key"] == "module.sub_9.test_999"
