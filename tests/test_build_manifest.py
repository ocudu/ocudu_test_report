# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Tests for scripts/build_manifest.py — incremental runs index logic."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_manifest  # noqa: E402  # isort: skip

_API = "https://gitlab.com/api/v4"


# ---------------------------------------------------------------------------
# _get_auth_headers
# ---------------------------------------------------------------------------


class TestGetAuthHeaders:
    def test_private_token(self):
        assert build_manifest._get_auth_headers("my-token", "private") == {"PRIVATE-TOKEN": "my-token"}

    def test_job_token(self):
        assert build_manifest._get_auth_headers("job-tok", "job") == {"JOB-TOKEN": "job-tok"}


# ---------------------------------------------------------------------------
# download_index
# ---------------------------------------------------------------------------


class TestDownloadIndex:
    @patch("build_manifest.requests.get")
    def test_returns_existing_manifest(self, mock_get):
        manifest = {"schema_version": 1, "total_runs": 1, "runs": [{"pipeline_id": "100"}]}
        resp = MagicMock()
        resp.status_code = 200
        resp.content = json.dumps(manifest).encode()
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        result = build_manifest.download_index(_API, "123", {})
        assert result == manifest

    @patch("build_manifest.requests.get")
    def test_404_returns_empty_manifest(self, mock_get):
        resp = MagicMock()
        resp.status_code = 404
        mock_get.return_value = resp

        result = build_manifest.download_index(_API, "123", {})
        assert result == {"schema_version": 1, "total_runs": 0, "runs": []}

    @patch("build_manifest.requests.get")
    def test_bad_json_returns_empty_manifest(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"not json"
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        result = build_manifest.download_index(_API, "123", {})
        assert result["runs"] == []

    @patch("build_manifest.requests.get")
    def test_missing_runs_list_returns_empty_manifest(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.content = json.dumps({"schema_version": 1}).encode()
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        result = build_manifest.download_index(_API, "123", {})
        assert result["runs"] == []

    @patch("build_manifest.requests.get")
    def test_transport_error_returns_empty_manifest(self, mock_get):
        import requests

        mock_get.side_effect = requests.RequestException("boom")
        result = build_manifest.download_index(_API, "123", {})
        assert result["runs"] == []

    @patch("build_manifest.requests.get")
    def test_does_not_hit_package_list_endpoint(self, mock_get):
        resp = MagicMock()
        resp.status_code = 404
        mock_get.return_value = resp

        build_manifest.download_index(_API, "123", {})

        called_url = mock_get.call_args[0][0]
        assert "/packages/generic/test-report-runs/index/runs.json" in called_url
        assert called_url.endswith("runs.json")
        # It must not use the unauthorised package-list endpoint.
        assert not called_url.endswith("/packages")


# ---------------------------------------------------------------------------
# upload_index
# ---------------------------------------------------------------------------


class TestUploadIndex:
    @patch("build_manifest.requests.put")
    def test_success_201(self, mock_put):
        resp = MagicMock()
        resp.status_code = 201
        mock_put.return_value = resp

        assert build_manifest.upload_index(_API, "123", {}, {"runs": []}) is True

    @patch("build_manifest.requests.put")
    def test_success_200(self, mock_put):
        resp = MagicMock()
        resp.status_code = 200
        mock_put.return_value = resp

        assert build_manifest.upload_index(_API, "123", {}, {"runs": []}) is True

    @patch("build_manifest.requests.put")
    def test_failure_status(self, mock_put):
        resp = MagicMock()
        resp.status_code = 403
        mock_put.return_value = resp

        assert build_manifest.upload_index(_API, "123", {}, {"runs": []}) is False

    @patch("build_manifest.requests.put")
    def test_transport_error(self, mock_put):
        import requests

        mock_put.side_effect = requests.RequestException("network")
        assert build_manifest.upload_index(_API, "123", {}, {"runs": []}) is False

    @patch("build_manifest.requests.put")
    def test_uploads_to_index_path(self, mock_put):
        resp = MagicMock()
        resp.status_code = 201
        mock_put.return_value = resp

        build_manifest.upload_index(_API, "456", {}, {"runs": []})
        called_url = mock_put.call_args[0][0]
        assert called_url.endswith("/packages/generic/test-report-runs/index/runs.json")


# ---------------------------------------------------------------------------
# add_run
# ---------------------------------------------------------------------------


class TestAddRun:
    def test_appends_to_empty_manifest(self):
        manifest = build_manifest._empty_manifest()
        run = {"pipeline_id": "100", "totals": {"tests": 10}}

        result = build_manifest.add_run(manifest, run, _API, "123")

        assert result["total_runs"] == 1
        assert result["runs"][0]["pipeline_id"] == "100"
        assert result["runs"][0]["package_version"] == "100"
        assert (
            result["runs"][0]["download_url"]
            == "https://gitlab.com/api/v4/projects/123/packages/generic/test-report-runs/100/report.zip"
        )

    def test_sorts_newest_first(self):
        manifest = {"schema_version": 1, "total_runs": 1, "runs": [{"pipeline_id": "100"}]}
        run = {"pipeline_id": "200"}

        result = build_manifest.add_run(manifest, run, _API, "123")

        assert [r["pipeline_id"] for r in result["runs"]] == ["200", "100"]

    def test_inserts_older_run_in_order(self):
        manifest = {"schema_version": 1, "total_runs": 1, "runs": [{"pipeline_id": "200"}]}
        run = {"pipeline_id": "150"}

        result = build_manifest.add_run(manifest, run, _API, "123")

        assert [r["pipeline_id"] for r in result["runs"]] == ["200", "150"]

    def test_replaces_duplicate_pipeline_id(self):
        manifest = {
            "schema_version": 1,
            "total_runs": 1,
            "runs": [{"pipeline_id": "100", "totals": {"tests": 1}}],
        }
        run = {"pipeline_id": "100", "totals": {"tests": 99}}

        result = build_manifest.add_run(manifest, run, _API, "123")

        assert result["total_runs"] == 1
        assert result["runs"][0]["totals"]["tests"] == 99

    def test_max_runs_caps_and_keeps_newest(self):
        manifest = {
            "schema_version": 1,
            "total_runs": 3,
            "runs": [{"pipeline_id": "300"}, {"pipeline_id": "200"}, {"pipeline_id": "100"}],
        }
        run = {"pipeline_id": "400"}

        result = build_manifest.add_run(manifest, run, _API, "123", max_runs=2)

        assert result["total_runs"] == 2
        assert [r["pipeline_id"] for r in result["runs"]] == ["400", "300"]

    def test_non_numeric_pipeline_ids_sort_last(self):
        manifest = {"schema_version": 1, "total_runs": 1, "runs": [{"pipeline_id": "abc"}]}
        run = {"pipeline_id": "100"}

        result = build_manifest.add_run(manifest, run, _API, "123")

        assert result["runs"][0]["pipeline_id"] == "100"
        assert result["runs"][1]["pipeline_id"] == "abc"


# ---------------------------------------------------------------------------
# _load_current_run
# ---------------------------------------------------------------------------


class TestLoadCurrentRun:
    def test_loads_valid_json(self, tmp_path):
        p = tmp_path / "run_metadata.json"
        p.write_text(json.dumps({"pipeline_id": "100"}), encoding="utf-8")

        assert build_manifest._load_current_run(p) == {"pipeline_id": "100"}

    def test_missing_file_returns_none(self, tmp_path):
        assert build_manifest._load_current_run(tmp_path / "nope.json") is None

    def test_bad_json_returns_none(self, tmp_path):
        p = tmp_path / "run_metadata.json"
        p.write_text("not json", encoding="utf-8")

        assert build_manifest._load_current_run(p) is None
