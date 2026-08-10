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
