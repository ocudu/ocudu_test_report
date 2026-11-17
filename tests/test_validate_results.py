# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Tests for validate_results.py: XML conversion, schema rules and identity checks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import validate_results as vr  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
SCHEMA = vr.load_yaml(REPO / "schemas" / "results.schema.yaml")
LAB_IDS = {"ocudu-ci", "valor", "niwc"}
SHA = "e0db566aac6e6376ddd60e83c84f58698fcc4d70"
OTHER_SHA = "050a2bb72e1d794cd60570d809987c1fcda3e54b"


def _props(**overrides: str | None) -> str:
    """Build a suite <properties> block. Pass a value of None to drop a property."""
    values: dict[str, str | None] = {"schema_version": "1", "lab": "valor", "ocudu_commit": SHA}
    values.update(overrides)
    body = "".join(f'<property name="{k}" value="{v}"/>' for k, v in values.items() if v is not None)
    return f"<properties>{body}</properties>"


def _suite(props: str | None = None, name: str = "TIFG", cases: str | None = None) -> str:
    if props is None:
        props = _props()
    if cases is None:
        cases = '<testcase name="5.3" classname="Registration" time="1.5"/>'
    return f'<testsuite name="{name}" timestamp="2026-11-10T02:00:00Z">{props}{cases}</testsuite>'


def _xml(*suites: str) -> bytes:
    if not suites:
        suites = (_suite(),)
    return f'<?xml version="1.0" encoding="utf-8"?><testsuites>{"".join(suites)}</testsuites>'.encode()


def _errors(data: bytes, expected_lab: str | None = None) -> list[str]:
    return vr.validate_bytes(data, SCHEMA, LAB_IDS, expected_lab)


# ---------------------------------------------------------------------------
# Valid files
# ---------------------------------------------------------------------------


class TestValid:
    """Files that should pass."""

    def test_minimal_valid_file(self):
        assert _errors(_xml()) == []

    def test_bare_testsuite_root_is_accepted(self):
        data = f'<?xml version="1.0"?>{_suite()}'.encode()
        assert _errors(data) == []

    def test_optional_and_extra_properties_allowed(self):
        # ocudu_ref is not part of the contract, but labs may still send it as an extra property.
        props = _props(ocudu_ref="release_26_10", run_url="https://example.org/run/1", dut="O-CU/O-DU")
        props = props.replace("</properties>", '<property name="test_commit" value="abc"/></properties>')
        assert _errors(_xml(_suite(props=props))) == []

    def test_multiple_suites_sharing_identity(self):
        assert _errors(_xml(_suite(name="TIFG"), _suite(name="WG11"))) == []

    def test_expected_lab_matches(self):
        assert _errors(_xml(), expected_lab="valor") == []

    def test_testcase_properties_do_not_count_as_identity(self):
        cases = '<testcase name="5.3"><properties><property name="lab" value="nobody"/></properties></testcase>'
        assert _errors(_xml(_suite(cases=cases))) == []


# ---------------------------------------------------------------------------
# Missing or malformed identity
# ---------------------------------------------------------------------------


class TestIdentity:
    """Every suite must say which lab ran it, which commit, and which format version."""

    @pytest.mark.parametrize("prop", ["schema_version", "lab", "ocudu_commit"])
    def test_required_property_missing(self, prop):
        errors = _errors(_xml(_suite(props=_props(**{prop: None}))))
        assert any(f"'{prop}' is a required property" in e for e in errors)

    def test_no_properties_block_at_all(self):
        errors = _errors(_xml(_suite(props="")))
        assert len(errors) == 3

    @pytest.mark.parametrize("sha", [SHA[:12], SHA.upper(), SHA + "0", "not-a-sha"])
    def test_commit_must_be_full_lowercase_sha(self, sha):
        errors = _errors(_xml(_suite(props=_props(ocudu_commit=sha))))
        assert any("ocudu_commit" in e for e in errors)

    def test_unknown_lab_rejected(self):
        errors = _errors(_xml(_suite(props=_props(lab="mystery-lab"))))
        assert any("unknown lab 'mystery-lab'" in e for e in errors)

    def test_lab_with_invalid_characters_rejected(self):
        errors = _errors(_xml(_suite(props=_props(lab="Valor Lab"))))
        assert any("lab" in e for e in errors)

    def test_expected_lab_mismatch(self):
        errors = _errors(_xml(), expected_lab="niwc")
        assert any("does not match the expected lab 'niwc'" in e for e in errors)

    def test_unsupported_schema_version(self):
        errors = _errors(_xml(_suite(props=_props(schema_version="99"))))
        assert any("unsupported schema_version '99'" in e for e in errors)

    def test_suites_with_different_labs_rejected(self):
        data = _xml(_suite(), _suite(props=_props(lab="niwc")))
        assert any("share one 'lab'" in e for e in _errors(data))

    def test_suites_with_different_commits_rejected(self):
        data = _xml(_suite(), _suite(props=_props(ocudu_commit=OTHER_SHA)))
        assert any("share one 'ocudu_commit'" in e for e in _errors(data))

    def test_conflicting_duplicate_property_rejected(self):
        props = _props().replace("</properties>", '<property name="lab" value="niwc"/></properties>')
        assert any("given twice" in e for e in _errors(_xml(_suite(props=props))))

    def test_identical_duplicate_property_tolerated(self):
        props = _props().replace("</properties>", '<property name="lab" value="valor"/></properties>')
        assert _errors(_xml(_suite(props=props))) == []

    def test_bad_run_url(self):
        errors = _errors(_xml(_suite(props=_props(run_url="ftp://example.org"))))
        assert any("run_url" in e for e in errors)


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


class TestStructure:
    """File-level and test-case-level shape."""

    def test_not_xml(self):
        assert any("not well-formed XML" in e for e in _errors(b"this is not xml"))

    def test_wrong_root_element(self):
        assert any("root element" in e for e in _errors(b"<report/>"))

    def test_doctype_rejected(self):
        data = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><testsuites/>'
        assert any("DOCTYPE" in e for e in _errors(data))

    def test_empty_testsuites(self):
        assert any("testsuites" in e for e in _errors(b"<testsuites/>"))

    def test_suite_without_testcases(self):
        assert any("testcases" in e for e in _errors(_xml(_suite(cases=""))))

    def test_suite_without_name(self):
        data = _xml(_suite().replace('name="TIFG" ', ""))
        assert any("name" in e for e in _errors(data))

    def test_testcase_without_name(self):
        assert any("name" in e for e in _errors(_xml(_suite(cases='<testcase classname="x"/>'))))

    def test_non_numeric_time(self):
        errors = _errors(_xml(_suite(cases='<testcase name="a" time="slow"/>')))
        assert any("time" in e for e in errors)

    def test_negative_time(self):
        errors = _errors(_xml(_suite(cases='<testcase name="a" time="-1"/>')))
        assert any("time" in e for e in errors)


# ---------------------------------------------------------------------------
# XML -> dict conversion
# ---------------------------------------------------------------------------


class TestParse:
    """parse_results produces the shape the schema describes."""

    @pytest.mark.parametrize(
        "child, status",
        [
            ("", "passed"),
            ("<failure/>", "failed"),
            ("<error/>", "error"),
            ("<skipped/>", "skipped"),
            ("<failure/><skipped/>", "failed"),  # same precedence as xunit_report.py
        ],
    )
    def test_status(self, child, status):
        doc, _ = vr.parse_results(_xml(_suite(cases=f'<testcase name="a">{child}</testcase>')))
        assert doc["testsuites"][0]["testcases"][0]["status"] == status

    def test_fields(self):
        doc, errors = vr.parse_results(_xml())
        assert errors == []
        suite = doc["testsuites"][0]
        assert suite["name"] == "TIFG"
        assert suite["timestamp"] == "2026-11-10T02:00:00Z"
        assert suite["properties"] == {"schema_version": "1", "lab": "valor", "ocudu_commit": SHA}
        assert suite["testcases"] == [{"name": "5.3", "status": "passed", "classname": "Registration", "time": 1.5}]

    def test_parse_raises_on_bad_xml(self):
        with pytest.raises(vr.ResultsFileError):
            vr.parse_results(b"<unclosed>")


# ---------------------------------------------------------------------------
# Files, lab registry and CLI
# ---------------------------------------------------------------------------


class TestFilesAndCli:
    """validate_file, load_lab_ids and main()."""

    def test_repo_labs_file_lists_expected_labs(self):
        assert vr.load_lab_ids(REPO / "labs" / "labs.yaml") >= LAB_IDS

    def test_missing_file_reported_not_raised(self, tmp_path):
        errors = vr.validate_file(tmp_path / "nope.xml", SCHEMA, LAB_IDS)
        assert errors and "cannot read file" in errors[0]

    def test_existing_ci_xml_only_lacks_lab_and_version(self):
        """CI XMLs already carry ocudu_commit; migration only has to add lab and schema_version."""
        path = REPO / "test_reports" / "example" / "E2E_Functional" / "mocn_out.xml"
        errors = vr.validate_file(path, SCHEMA, LAB_IDS)
        assert len(errors) == 2
        assert any("'lab'" in e for e in errors)
        assert any("'schema_version'" in e for e in errors)

    def test_main_exit_codes(self, tmp_path, capsys):
        good = tmp_path / "good.xml"
        good.write_bytes(_xml())
        bad = tmp_path / "bad.xml"
        bad.write_bytes(_xml(_suite(props=_props(lab=None))))

        assert vr.main([str(good)]) == 0
        assert vr.main([str(good), str(bad)]) == 1
        assert vr.main(["--lab", "niwc", str(good)]) == 1
        out = capsys.readouterr().out
        assert "FAILED" in out and "OK" in out

    def test_main_missing_schema_is_setup_error(self, tmp_path):
        good = tmp_path / "good.xml"
        good.write_bytes(_xml())
        assert vr.main(["--schema", str(tmp_path / "missing.yaml"), str(good)]) == 2
