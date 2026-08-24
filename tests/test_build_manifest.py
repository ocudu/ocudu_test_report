# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Tests for scripts/build_manifest.py — run manifest building logic."""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_manifest  # noqa: E402


# ---------------------------------------------------------------------------
# _get_auth_headers
# ---------------------------------------------------------------------------


class TestGetAuthHeaders:
    def test_private_token(self):
        headers = build_manifest._get_auth_headers("my-token", "private")
        assert headers == {"PRIVATE-TOKEN": "my-token"}

    def test_job_token(self):
        headers = build_manifest._get_auth_headers("job-tok", "job")
        assert headers == {"JOB-TOKEN": "job-tok"}


# ---------------------------------------------------------------------------
# _download_metadata_from_zip
# ---------------------------------------------------------------------------


def _make_zip_bytes(files: dict[str, bytes]) -> bytes:
    """Create an in-memory zip with the given filename->content mapping."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


class TestDownloadMetadataFromZip:
    @patch("build_manifest.requests.get")
    def test_extracts_metadata_from_public_path(self, mock_get):
        metadata = {"schema_version": 1, "pipeline_id": "100", "totals": {"tests": 50}}
        zip_bytes = _make_zip_bytes({"public/run_metadata.json": json.dumps(metadata).encode()})

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = zip_bytes
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = build_manifest._download_metadata_from_zip(
            "https://gitlab.com/api/v4", "123", "999", {}
        )
        assert result == metadata

    @patch("build_manifest.requests.get")
    def test_extracts_metadata_from_root_path(self, mock_get):
        metadata = {"schema_version": 1, "pipeline_id": "200"}
        zip_bytes = _make_zip_bytes({"run_metadata.json": json.dumps(metadata).encode()})

        mock_resp = MagicMock()
        mock_resp.content = zip_bytes
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = build_manifest._download_metadata_from_zip(
            "https://gitlab.com/api/v4", "123", "200", {}
        )
        assert result == metadata

    @patch("build_manifest.requests.get")
    def test_returns_none_on_missing_metadata(self, mock_get):
        zip_bytes = _make_zip_bytes({"public/report.html": b"<html></html>"})

        mock_resp = MagicMock()
        mock_resp.content = zip_bytes
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = build_manifest._download_metadata_from_zip(
            "https://gitlab.com/api/v4", "123", "300", {}
        )
        assert result is None

    @patch("build_manifest.requests.get")
    def test_returns_none_on_bad_zip(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = b"not a zip file"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = build_manifest._download_metadata_from_zip(
            "https://gitlab.com/api/v4", "123", "400", {}
        )
        assert result is None

    @patch("build_manifest.requests.get")
    def test_returns_none_on_request_failure(self, mock_get):
        import requests

        mock_get.side_effect = requests.RequestException("timeout")

        result = build_manifest._download_metadata_from_zip(
            "https://gitlab.com/api/v4", "123", "500", {}
        )
        assert result is None


# ---------------------------------------------------------------------------
# _list_package_versions
# ---------------------------------------------------------------------------


class TestListPackageVersions:
    @patch("build_manifest.requests.get")
    def test_single_page(self, mock_get):
        packages = [
            {"id": 1, "version": "1000", "created_at": "2026-08-01T00:00:00Z"},
            {"id": 2, "version": "999", "created_at": "2026-07-31T00:00:00Z"},
        ]
        mock_resp = MagicMock()
        mock_resp.json.side_effect = [packages, []]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = build_manifest._list_package_versions(
            "https://gitlab.com/api/v4", "123", {}
        )
        assert len(result) == 2
        assert result[0]["version"] == "1000"

    @patch("build_manifest.requests.get")
    def test_multi_page_pagination(self, mock_get):
        page1 = [{"id": i, "version": str(1000 - i)} for i in range(100)]
        page2 = [{"id": 100, "version": "900"}]

        mock_resp_1 = MagicMock()
        mock_resp_1.json.return_value = page1
        mock_resp_1.raise_for_status = MagicMock()

        mock_resp_2 = MagicMock()
        mock_resp_2.json.return_value = page2
        mock_resp_2.raise_for_status = MagicMock()

        mock_resp_3 = MagicMock()
        mock_resp_3.json.return_value = []
        mock_resp_3.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_resp_1, mock_resp_2, mock_resp_3]

        result = build_manifest._list_package_versions(
            "https://gitlab.com/api/v4", "123", {}
        )
        assert len(result) == 101

    @patch("build_manifest.requests.get")
    def test_empty_registry(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = build_manifest._list_package_versions(
            "https://gitlab.com/api/v4", "123", {}
        )
        assert result == []


# ---------------------------------------------------------------------------
# build_manifest — integration of the pieces
# ---------------------------------------------------------------------------


class TestBuildManifest:
    @patch("build_manifest._download_metadata_from_zip")
    @patch("build_manifest._list_package_versions")
    def test_assembles_manifest_from_metadata(self, mock_list, mock_download):
        mock_list.return_value = [
            {"id": 1, "version": "1000", "created_at": "2026-08-01T00:00:00Z"},
            {"id": 2, "version": "999", "created_at": "2026-07-31T00:00:00Z"},
        ]
        mock_download.side_effect = [
            {"schema_version": 1, "pipeline_id": "1000", "generated_at": "2026-08-01T10:00:00+00:00", "totals": {"tests": 100}, "suites": []},
            {"schema_version": 1, "pipeline_id": "999", "generated_at": "2026-07-31T10:00:00+00:00", "totals": {"tests": 95}, "suites": []},
        ]

        result = build_manifest.build_manifest(
            "https://gitlab.com/api/v4", "123", {}, max_runs=0
        )

        assert result["schema_version"] == 1
        assert result["total_runs"] == 2
        assert len(result["runs"]) == 2
        assert result["runs"][0]["pipeline_id"] == "1000"
        assert result["runs"][1]["pipeline_id"] == "999"
        assert "download_url" in result["runs"][0]
        assert "package_version" in result["runs"][0]

    @patch("build_manifest._download_metadata_from_zip")
    @patch("build_manifest._list_package_versions")
    def test_max_runs_limits_output(self, mock_list, mock_download):
        mock_list.return_value = [
            {"id": i, "version": str(1000 - i), "created_at": "2026-08-01T00:00:00Z"}
            for i in range(10)
        ]
        mock_download.return_value = {"schema_version": 1, "pipeline_id": "x", "totals": {}, "suites": []}

        result = build_manifest.build_manifest(
            "https://gitlab.com/api/v4", "123", {}, max_runs=3
        )

        assert result["total_runs"] == 3
        assert mock_download.call_count == 3

    @patch("build_manifest._download_metadata_from_zip")
    @patch("build_manifest._list_package_versions")
    def test_fallback_when_metadata_missing(self, mock_list, mock_download):
        mock_list.return_value = [
            {"id": 1, "version": "500", "created_at": "2026-08-01T12:00:00Z"},
        ]
        mock_download.return_value = None  # metadata extraction failed

        result = build_manifest.build_manifest(
            "https://gitlab.com/api/v4", "123", {}, max_runs=0
        )

        assert result["total_runs"] == 1
        run = result["runs"][0]
        assert run["pipeline_id"] == "500"
        assert run["generated_at"] == "2026-08-01T12:00:00Z"
        assert "download_url" in run

    @patch("build_manifest._download_metadata_from_zip")
    @patch("build_manifest._list_package_versions")
    def test_empty_registry_produces_empty_manifest(self, mock_list, mock_download):
        mock_list.return_value = []

        result = build_manifest.build_manifest(
            "https://gitlab.com/api/v4", "123", {}, max_runs=0
        )

        assert result["total_runs"] == 0
        assert result["runs"] == []
        mock_download.assert_not_called()

    @patch("build_manifest._download_metadata_from_zip")
    @patch("build_manifest._list_package_versions")
    def test_download_url_format(self, mock_list, mock_download):
        mock_list.return_value = [
            {"id": 1, "version": "777", "created_at": "2026-08-01T00:00:00Z"},
        ]
        mock_download.return_value = {"schema_version": 1, "pipeline_id": "777", "totals": {}, "suites": []}

        result = build_manifest.build_manifest(
            "https://gitlab.com/api/v4", "456", {}, max_runs=0
        )

        expected_url = "https://gitlab.com/api/v4/projects/456/packages/generic/test-report-runs/777/report.zip"
        assert result["runs"][0]["download_url"] == expected_url
