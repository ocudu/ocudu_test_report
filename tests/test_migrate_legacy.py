# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Tests for migrate_legacy.py: adding lab/commit properties to existing results."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import migrate_legacy as ml  # noqa: E402
import validate_results as vr  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


REPO = Path(__file__).resolve().parent.parent
SCHEMA = vr.load_yaml(REPO / "schemas" / "results.schema.yaml")
LAB_IDS = vr.load_lab_ids(REPO / "labs" / "labs.yaml")
TAG = "e0db566aac6e6376ddd60e83c84f58698fcc4d70"
OTHER = "35d45fac7482203aa3b6529f624c0e88b01ac069"


def _suite(props: str = "", name: str = "bands") -> str:
    props_block = f"<properties>{props}</properties>" if props else ""
    return f'<testsuite name="{name}">{props_block}<testcase name="t" classname="c"/></testsuite>'


def _xml(*suites: str) -> bytes:
    return f'<?xml version="1.0"?><testsuites>{"".join(suites or (_suite(),))}</testsuites>'.encode()


def _prop(name: str, value: str) -> str:
    return f'<property name="{name}" value="{value}"/>'


def _suite_props(data: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(data)
    return [{p.get("name", ""): p.get("value", "") for p in ts.findall("properties/property")} for ts in root]


# ---------------------------------------------------------------------------
# Commit handling
# ---------------------------------------------------------------------------


class TestCommit:
    """Which commit each suite ends up with."""

    def test_missing_commit_is_filled(self):
        data, actions = ml.migrate_bytes(_xml(), "ocudu-ci", TAG)
        assert actions == {"filled": 1}
        assert _suite_props(data)[0]["ocudu_commit"] == TAG

    def test_empty_commit_is_filled(self):
        data, actions = ml.migrate_bytes(_xml(_suite(_prop("ocudu_commit", ""))), "ocudu-ci", TAG)
        assert actions == {"filled": 1}
        assert _suite_props(data)[0]["ocudu_commit"] == TAG

    def test_matching_commit(self):
        _, actions = ml.migrate_bytes(_xml(_suite(_prop("ocudu_commit", TAG))), "ocudu-ci", TAG)
        assert actions == {"matched": 1}

    def test_different_commit_is_kept_by_default(self):
        data, actions = ml.migrate_bytes(_xml(_suite(_prop("ocudu_commit", OTHER))), "ocudu-ci", TAG)
        assert actions == {"kept": 1}
        assert _suite_props(data)[0]["ocudu_commit"] == OTHER

    def test_different_commit_overwritten_when_asked(self):
        data, actions = ml.migrate_bytes(_xml(_suite(_prop("ocudu_commit", OTHER))), "ocudu-ci", TAG, True)
        assert actions == {"overwritten": 1}
        assert _suite_props(data)[0]["ocudu_commit"] == TAG

    def test_short_commit_expanded(self):
        data, actions = ml.migrate_bytes(
            _xml(_suite(_prop("ocudu_commit", "35d45fa"))), "ocudu-ci", TAG, expansions={"35d45fa": OTHER}
        )
        assert actions == {"expanded": 1}
        assert _suite_props(data)[0]["ocudu_commit"] == OTHER

    def test_short_commit_expanding_to_target_counts_as_matched(self):
        _, actions = ml.migrate_bytes(
            _xml(_suite(_prop("ocudu_commit", "e0db566"))), "ocudu-ci", TAG, expansions={"e0db566": TAG}
        )
        assert actions == {"matched": 1}

    def test_mixed_suites_in_one_file(self):
        data = _xml(_suite(), _suite(_prop("ocudu_commit", TAG)), _suite(_prop("ocudu_commit", OTHER)))
        _, actions = ml.migrate_bytes(data, "ocudu-ci", TAG)
        assert actions == {"filled": 1, "matched": 1, "kept": 1}


class TestParseExpansions:
    """--expand-commit must never change which commit a result names."""

    def test_valid(self):
        assert ml.parse_expansions([f"35d45fa={OTHER}"]) == {"35d45fa": OTHER}

    @pytest.mark.parametrize(
        "value",
        [
            "35d45fa",  # no '='
            f"abcdef0={OTHER}",  # FULL does not start with SHORT
            "35d45fa=35d45fa",  # FULL not a full SHA
            f"={OTHER}",  # empty SHORT
        ],
    )
    def test_invalid(self, value):
        with pytest.raises(ValueError):
            ml.parse_expansions([value])


# ---------------------------------------------------------------------------
# Lab and other properties
# ---------------------------------------------------------------------------


class TestProperties:
    """lab and schema_version are added; existing properties survive."""

    def test_adds_lab_and_version_and_passes_validation(self):
        data, _ = ml.migrate_bytes(_xml(), "ocudu-ci", TAG)
        props = _suite_props(data)[0]
        assert props["lab"] == "ocudu-ci"
        assert props["schema_version"] == ml.SCHEMA_VERSION
        assert vr.validate_bytes(data, SCHEMA, LAB_IDS, "ocudu-ci") == []

    def test_existing_properties_preserved(self):
        data, _ = ml.migrate_bytes(_xml(_suite(_prop("url", "https://x") + _prop("test_commit", "abc"))), "valor", TAG)
        props = _suite_props(data)[0]
        assert props["url"] == "https://x" and props["test_commit"] == "abc"

    def test_same_lab_already_present_is_fine(self):
        _, actions = ml.migrate_bytes(_xml(_suite(_prop("lab", "valor"))), "valor", TAG)
        assert actions == {"filled": 1}

    def test_different_lab_is_an_error(self):
        with pytest.raises(ml.MigrationError, match="already names lab 'niwc'"):
            ml.migrate_bytes(_xml(_suite(_prop("lab", "niwc"))), "valor", TAG)

    def test_properties_block_inserted_first(self):
        data, _ = ml.migrate_bytes(_xml(), "ocudu-ci", TAG)
        suite = ET.fromstring(data)[0]
        assert suite[0].tag == "properties"

    def test_testcases_untouched(self):
        cases = '<testcase name="a" classname="c" time="1.5"><failure message="m">boom</failure></testcase>'
        src = f'<testsuites><testsuite name="s">{cases}</testsuite></testsuites>'.encode()
        data, _ = ml.migrate_bytes(src, "ocudu-ci", TAG)
        tc = ET.fromstring(data).find("testsuite/testcase")
        assert tc is not None and tc.get("time") == "1.5"
        failure = tc.find("failure")
        assert failure is not None and failure.text == "boom"

    def test_bare_testsuite_root(self):
        data, actions = ml.migrate_bytes(f'<?xml version="1.0"?>{_suite()}'.encode(), "ocudu-ci", TAG)
        assert actions == {"filled": 1}
        assert vr.validate_bytes(data, SCHEMA, LAB_IDS) == []

    def test_leading_comment_survives(self):
        # The lab XMLs keep their licence header in a comment above the root element.
        # This test uses a plain comment, because reuse lint treats anything that
        # looks like an SPDX tag as this file's own licence.
        src = b'<?xml version="1.0"?><!-- header comment --><testsuites>' + _suite().encode() + b"</testsuites>"
        data, _ = ml.migrate_bytes(src, "ocudu-ci", TAG)
        assert b"<!-- header comment -->" in data


class TestBadInput:
    """Files that can't be migrated are reported, not guessed at."""

    @pytest.mark.parametrize(
        "data, match",
        [
            (b"not xml", "not well-formed"),
            (b"<report/>", "root element"),
            (b"<testsuites/>", "no <testsuite>"),
            (b'<?xml version="1.0"?><!DOCTYPE x><testsuites/>', "DOCTYPE"),
        ],
    )
    def test_rejected(self, data, match):
        with pytest.raises(ml.MigrationError, match=match):
            ml.migrate_bytes(data, "ocudu-ci", TAG)


# ---------------------------------------------------------------------------
# Folder migration and CLI
# ---------------------------------------------------------------------------


def _make_tree(root: Path) -> None:
    (root / "E2E").mkdir(parents=True)
    (root / "E2E" / "a.xml").write_bytes(_xml())
    (root / "E2E" / "a_url.txt").write_text("https://example.org/job/1\n")
    (root / "_order.txt").write_text("E2E\n")


class TestTree:
    """migrate_tree copies everything and leaves the source alone."""

    def test_copies_and_migrates(self, tmp_path):
        src, out = tmp_path / "src", tmp_path / "out"
        _make_tree(src)
        original = (src / "E2E" / "a.xml").read_bytes()

        reports = ml.migrate_tree(src, out, "ocudu-ci", TAG, lab_ids=LAB_IDS, schema=SCHEMA)

        assert [r.ok for r in reports] == [True]
        assert (out / "E2E" / "a_url.txt").read_text() == "https://example.org/job/1\n"
        assert (out / "_order.txt").exists()
        assert _suite_props((out / "E2E" / "a.xml").read_bytes())[0]["lab"] == "ocudu-ci"
        assert (src / "E2E" / "a.xml").read_bytes() == original

    def test_bad_file_reported_and_others_still_migrated(self, tmp_path):
        src, out = tmp_path / "src", tmp_path / "out"
        _make_tree(src)
        (src / "E2E" / "broken.xml").write_bytes(b"<oops")

        reports = {r.path.name: r for r in ml.migrate_tree(src, out, "ocudu-ci", TAG)}

        assert reports["a.xml"].ok
        assert "not well-formed" in reports["broken.xml"].error
        assert not (out / "E2E" / "broken.xml").exists()

    def test_validation_errors_recorded(self, tmp_path):
        src, out = tmp_path / "src", tmp_path / "out"
        src.mkdir()
        (src / "short.xml").write_bytes(_xml(_suite(_prop("ocudu_commit", "35d45fa"))))

        [report] = ml.migrate_tree(src, out, "ocudu-ci", TAG, lab_ids=LAB_IDS, schema=SCHEMA)

        assert report.commits == {"kept": 1}
        assert any("ocudu_commit" in e for e in report.validation_errors)


class TestMain:
    """Command-line behaviour and exit codes."""

    def test_success(self, tmp_path, capsys):
        src = tmp_path / "src"
        _make_tree(src)
        assert ml.main([str(src), "-o", str(tmp_path / "out"), "--lab", "ocudu-ci", "--commit", TAG]) == 0
        assert "1 of 1 XML file(s) migrated and valid" in capsys.readouterr().out

    def test_invalid_result_exits_1(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "short.xml").write_bytes(_xml(_suite(_prop("ocudu_commit", "35d45fa"))))
        args = [str(src), "-o", str(tmp_path / "out"), "--lab", "ocudu-ci", "--commit", TAG]
        assert ml.main(args) == 1
        assert ml.main(args + ["--expand-commit", f"35d45fa={OTHER}"]) == 0

    @pytest.mark.parametrize(
        "extra",
        [
            ["--lab", "ocudu-ci", "--commit", TAG[:12]],
            ["--lab", "nobody", "--commit", TAG],
            ["--lab", "ocudu-ci", "--commit", TAG, "--expand-commit", "bad"],
        ],
    )
    def test_usage_errors(self, tmp_path, extra):
        src = tmp_path / "src"
        _make_tree(src)
        with pytest.raises(SystemExit) as exc:
            ml.main([str(src), "-o", str(tmp_path / "out"), *extra])
        assert exc.value.code == 2

    def test_output_inside_source_rejected(self, tmp_path):
        src = tmp_path / "src"
        _make_tree(src)
        with pytest.raises(SystemExit):
            ml.main([str(src), "-o", str(src / "out"), "--lab", "ocudu-ci", "--commit", TAG])
