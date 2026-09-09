# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Tests for validate_features.py — duplicate ID detection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import validate_features  # noqa: E402


# ---------------------------------------------------------------------------
# check_duplicate_ids — detect repeated feature IDs
# ---------------------------------------------------------------------------


class TestCheckDuplicateIds:
    """Test duplicate feature ID detection."""

    def test_no_duplicates_returns_empty(self):
        data = {"features": [{"id": "A"}, {"id": "B"}, {"id": "C"}]}
        assert validate_features.check_duplicate_ids(data) == []

    def test_single_duplicate_detected(self):
        data = {"features": [{"id": "A"}, {"id": "B"}, {"id": "A"}]}
        errors = validate_features.check_duplicate_ids(data)
        assert len(errors) == 1
        assert "A" in errors[0]
        assert "index 2" in errors[0]
        assert "index 0" in errors[0]

    def test_multiple_duplicates_all_reported(self):
        data = {"features": [
            {"id": "A"}, {"id": "B"}, {"id": "A"}, {"id": "B"}, {"id": "C"},
        ]}
        errors = validate_features.check_duplicate_ids(data)
        assert len(errors) == 2

    def test_empty_features_list(self):
        data = {"features": []}
        assert validate_features.check_duplicate_ids(data) == []

    def test_missing_features_key(self):
        data = {"something_else": []}
        assert validate_features.check_duplicate_ids(data) == []

    def test_features_not_a_list(self):
        data = {"features": "not a list"}
        assert validate_features.check_duplicate_ids(data) == []

    def test_feature_without_id_skipped(self):
        data = {"features": [{"id": "A"}, {"description": "no id"}, {"id": "B"}]}
        assert validate_features.check_duplicate_ids(data) == []

    def test_feature_with_empty_id_skipped(self):
        data = {"features": [{"id": ""}, {"id": ""}, {"id": "A"}]}
        assert validate_features.check_duplicate_ids(data) == []

    def test_non_dict_entries_skipped(self):
        data = {"features": [{"id": "A"}, None, "string", {"id": "B"}]}
        assert validate_features.check_duplicate_ids(data) == []
