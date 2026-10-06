# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Tests for scripts/fetch_run.py — historical run retrieval."""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_run  # noqa: E402  # isort: skip


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_zip_bytes(files: dict[str, bytes]) -> bytes:
    """Create an in-memory zip with the given filename->content mapping."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# resolve_latest_version
# ---------------------------------------------------------------------------


class TestResolveLatestVersion:
    @patch("fetch_run.requests.get")
    def test_returns_latest_version_from_index(self, mock_get):
        manifest = {"runs": [{"pipeline_id": "5000"}, {"pipeline_id": "4000"}]}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = json.dumps(manifest).encode()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_run.resolve_latest_version("https://gitlab.com/api/v4", "123", {})
        assert result == "5000"

    @patch("fetch_run.requests.get")
    def test_picks_highest_even_if_unordered(self, mock_get):
        manifest = {"runs": [{"pipeline_id": "100"}, {"pipeline_id": "900"}, {"pipeline_id": "300"}]}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = json.dumps(manifest).encode()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_run.resolve_latest_version("https://gitlab.com/api/v4", "123", {})
        assert result == "900"

    @patch("fetch_run.requests.get")
    def test_reads_index_file_not_package_list(self, mock_get):
        manifest = {"runs": [{"pipeline_id": "42"}]}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = json.dumps(manifest).encode()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        fetch_run.resolve_latest_version("https://gitlab.com/api/v4", "123", {})

        called_url = mock_get.call_args[0][0]
        assert called_url.endswith("/packages/generic/test-report-runs/index/runs.json")
        assert not called_url.endswith("/packages")

    @pytest.mark.parametrize("status", [401, 403, 404])
    @patch("fetch_run.requests.get")
    def test_exits_on_missing_index(self, mock_get, status):
        # A missing index reads as 404 with a personal token but 401/403 with
        # the CI job token (e.g. first run). All must exit cleanly with code 1
        # rather than raising an uncaught HTTPError.
        mock_resp = MagicMock()
        mock_resp.status_code = status
        mock_resp.raise_for_status = MagicMock(side_effect=AssertionError("must not raise; should exit cleanly"))
        mock_get.return_value = mock_resp

        with pytest.raises(SystemExit) as exc_info:
            fetch_run.resolve_latest_version("https://gitlab.com/api/v4", "123", {})
        assert exc_info.value.code == 1

    @patch("fetch_run.requests.get")
    def test_exits_on_empty_runs(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = json.dumps({"runs": []}).encode()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with pytest.raises(SystemExit) as exc_info:
            fetch_run.resolve_latest_version("https://gitlab.com/api/v4", "123", {})
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# download_run
# ---------------------------------------------------------------------------


class TestDownloadRun:
    @patch("fetch_run.requests.get")
    def test_downloads_and_returns_bytes(self, mock_get):
        content = b"fake zip content"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content.return_value = [content]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_run.download_run("https://gitlab.com/api/v4", "123", "999", {})
        assert result == content

    @patch("fetch_run.requests.get")
    def test_constructs_correct_url(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content.return_value = [b"data"]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        fetch_run.download_run("https://gitlab.com/api/v4", "456", "777", {"PRIVATE-TOKEN": "tok"})

        call_url = mock_get.call_args[0][0]
        assert "projects/456/packages/generic/test-report-runs/777/report.zip" in call_url

    @pytest.mark.parametrize("status", [401, 403, 404])
    @patch("fetch_run.requests.get")
    def test_returns_none_on_missing_or_unauthorised(self, mock_get, status):
        # A run zip that is missing (404) or that the CI job token cannot read
        # (401/403) must be skipped by returning None, not by raising. This is
        # what keeps both the comparison and inline-extraction CI steps from
        # crashing the whole report job.
        mock_resp = MagicMock()
        mock_resp.status_code = status
        mock_resp.raise_for_status = MagicMock(side_effect=AssertionError("must not raise; should return None"))
        mock_get.return_value = mock_resp

        result = fetch_run.download_run("https://gitlab.com/api/v4", "123", "999", {})
        assert result is None

    @patch("fetch_run.requests.get")
    def test_returns_none_on_transport_error(self, mock_get):
        mock_get.side_effect = fetch_run.requests.RequestException("boom")

        result = fetch_run.download_run("https://gitlab.com/api/v4", "123", "999", {})
        assert result is None

    @patch("fetch_run.requests.get")
    def test_still_raises_on_unexpected_server_error(self, mock_get):
        # A genuine 500 is not an "absent" status, so it should still surface
        # via raise_for_status rather than being silently swallowed.
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status = MagicMock(side_effect=fetch_run.requests.HTTPError("500"))
        mock_get.return_value = mock_resp

        with pytest.raises(fetch_run.requests.HTTPError):
            fetch_run.download_run("https://gitlab.com/api/v4", "123", "999", {})


# ---------------------------------------------------------------------------
# extract_run
# ---------------------------------------------------------------------------


class TestExtractRun:
    def test_extracts_files_to_output_dir(self, tmp_path):
        zip_bytes = _make_zip_bytes(
            {
                "public/report.html": b"<html>report</html>",
                "public/all.html": b"<html>all</html>",
                "public/run_metadata.json": b'{"pipeline_id": "100"}',
            }
        )

        extracted = fetch_run.extract_run(zip_bytes, tmp_path / "out")

        assert (tmp_path / "out" / "report.html").exists()
        assert (tmp_path / "out" / "all.html").exists()
        assert (tmp_path / "out" / "run_metadata.json").exists()
        assert len(extracted) == 3

    def test_strips_public_prefix(self, tmp_path):
        zip_bytes = _make_zip_bytes(
            {
                "public/logs/test_abc.txt": b"log content",
            }
        )

        extracted = fetch_run.extract_run(zip_bytes, tmp_path / "out")

        assert (tmp_path / "out" / "logs" / "test_abc.txt").exists()
        assert "logs/test_abc.txt" in extracted

    def test_handles_files_without_public_prefix(self, tmp_path):
        zip_bytes = _make_zip_bytes(
            {
                "run_metadata.json": b'{"pipeline_id": "200"}',
            }
        )

        extracted = fetch_run.extract_run(zip_bytes, tmp_path / "out")

        assert (tmp_path / "out" / "run_metadata.json").exists()
        assert "run_metadata.json" in extracted

    def test_creates_output_dir_if_missing(self, tmp_path):
        zip_bytes = _make_zip_bytes({"public/index.html": b"<html/>"})
        output = tmp_path / "deeply" / "nested" / "dir"

        fetch_run.extract_run(zip_bytes, output)

        assert (output / "index.html").exists()

    def test_skips_directory_entries(self, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("public/", "")  # directory entry
            zf.writestr("public/file.txt", "content")
        zip_bytes = buf.getvalue()

        extracted = fetch_run.extract_run(zip_bytes, tmp_path / "out")

        assert len(extracted) == 1
        assert "file.txt" in extracted[0]

    def test_empty_zip(self, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w"):
            pass
        zip_bytes = buf.getvalue()

        extracted = fetch_run.extract_run(zip_bytes, tmp_path / "out")

        assert extracted == []
