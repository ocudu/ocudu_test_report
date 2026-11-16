# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Tests for validate_labs.py: labs.yaml and releases.yaml checks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import validate_labs as vl  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
LABS_SCHEMA = vl.load_yaml(REPO / "schemas" / "labs.schema.yaml")
RELEASES_SCHEMA = vl.load_yaml(REPO / "schemas" / "releases.schema.yaml")
SHA_A = "050a2bb72e1d794cd60570d809987c1fcda3e54b"
SHA_B = "e0db566aac6e6376ddd60e83c84f58698fcc4d70"


def _labs(*labs: dict) -> dict:
    return {"labs": list(labs) or [{"id": "valor", "name": "VALOR"}]}


def _release(name: str = "26.10 (v2.1)", tag: str = "release_26_10", sha: str = SHA_B) -> dict:
    return {"name": name, "tag": tag, "ocudu_commit": sha}


# ---------------------------------------------------------------------------
# The real files in the repo
# ---------------------------------------------------------------------------


def test_repo_files_are_valid(capsys):
    assert vl.main([]) == 0
    assert capsys.readouterr().out.count("OK") == 2


def test_repo_release_names_match_features_schema():
    """Release names are shared with features.yaml, so they must be names it knows."""
    features_schema = vl.load_yaml(REPO / "features" / "features.schema")
    allowed = features_schema["$defs"]["feature"]["properties"]["release"]["enum"]
    for release in vl.load_yaml(REPO / "releases.yaml")["releases"]:
        assert release["name"] in allowed


# ---------------------------------------------------------------------------
# labs.yaml
# ---------------------------------------------------------------------------


class TestLabs:
    """Schema and extra checks for labs.yaml."""

    def test_valid(self, tmp_path):
        assert vl.check_labs(_labs(), LABS_SCHEMA, tmp_path) == []

    def test_duplicate_id(self, tmp_path):
        data = _labs({"id": "valor", "name": "A"}, {"id": "valor", "name": "B"})
        errors = vl.check_labs(data, LABS_SCHEMA, tmp_path)
        assert any("duplicate id 'valor'" in e for e in errors)

    @pytest.mark.parametrize("lab_id", ["Valor", "valor lab", "-valor", "valor_", ""])
    def test_bad_id(self, tmp_path, lab_id):
        assert vl.check_labs(_labs({"id": lab_id, "name": "X"}), LABS_SCHEMA, tmp_path)

    def test_missing_name(self, tmp_path):
        assert vl.check_labs(_labs({"id": "valor"}), LABS_SCHEMA, tmp_path)

    def test_unknown_field(self, tmp_path):
        assert vl.check_labs(_labs({"id": "valor", "name": "V", "token": "x"}), LABS_SCHEMA, tmp_path)

    def test_public_key_must_exist(self, tmp_path):
        data = _labs({"id": "valor", "name": "V", "public_key": "valor.pub"})
        assert any("not found" in e for e in vl.check_labs(data, LABS_SCHEMA, tmp_path))
        (tmp_path / "valor.pub").write_text("ssh-ed25519 AAAA test\n")
        assert vl.check_labs(data, LABS_SCHEMA, tmp_path) == []

    def test_public_key_cannot_escape_labs_dir(self, tmp_path):
        data = _labs({"id": "valor", "name": "V", "public_key": "../secrets.pub"})
        assert vl.check_labs(data, LABS_SCHEMA, tmp_path)

    def test_empty_list(self, tmp_path):
        assert vl.check_labs({"labs": []}, LABS_SCHEMA, tmp_path)


# ---------------------------------------------------------------------------
# releases.yaml
# ---------------------------------------------------------------------------


class TestReleases:
    """Schema and extra checks for releases.yaml."""

    def test_valid(self):
        data = {"releases": [_release("26.04 (v1.0)", "release_26_04", SHA_A), _release()]}
        assert vl.check_releases(data, RELEASES_SCHEMA) == []

    def test_empty_list_allowed(self):
        assert vl.check_releases({"releases": []}, RELEASES_SCHEMA) == []

    @pytest.mark.parametrize("field", ["name", "tag", "ocudu_commit"])
    def test_duplicates(self, field):
        first = _release("26.04 (v1.0)", "release_26_04", SHA_A)
        second = _release()
        second[field] = first[field]
        errors = vl.check_releases({"releases": [first, second]}, RELEASES_SCHEMA)
        assert any(f"duplicate {field}" in e for e in errors)

    @pytest.mark.parametrize("sha", [SHA_B[:12], SHA_B.upper(), "release_26_10"])
    def test_commit_must_be_full_sha(self, sha):
        assert vl.check_releases({"releases": [_release(sha=sha)]}, RELEASES_SCHEMA)

    def test_missing_tag(self):
        release = _release()
        del release["tag"]
        assert vl.check_releases({"releases": [release]}, RELEASES_SCHEMA)


def test_main_reports_failures(tmp_path):
    labs = tmp_path / "labs.yaml"
    labs.write_text("labs:\n  - id: Bad Id\n    name: x\n")
    assert vl.main(["--labs", str(labs)]) == 1


def test_main_missing_file(tmp_path):
    assert vl.main(["--releases", str(tmp_path / "missing.yaml")]) == 2
