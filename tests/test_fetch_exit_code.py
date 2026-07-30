# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Integration tests for the fetch exit code fix in gitlab_fetch.py.

Verifies that the script exits non-zero when all artifact downloads fail,
rather than silently succeeding with an empty report.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import gitlab_fetch  # noqa: E402


class TestExitCodeOnFailure:
    """main() exits 1 when no XUnit files are downloaded."""

    def test_exits_nonzero_when_all_downloads_fail(self, tmp_path):
        """If _fetch_suite returns empty for all suites, exit code should be 1."""
        test_args = [
            "gitlab_fetch.py",
            "--suite", "E2E=https://gitlab.com/ocudu/ocudu/-/pipelines/123",
            "-o", str(tmp_path),
        ]
        with (
            patch.object(sys, "argv", test_args),
            patch("gitlab_fetch._fetch_suite", return_value=[]),
            pytest.raises(SystemExit) as exc_info,
        ):
            gitlab_fetch.main()

        assert exc_info.value.code == 1

    def test_prints_message_to_stderr(self, tmp_path, capsys):
        """Error message about no files should go to stderr, not stdout."""
        test_args = [
            "gitlab_fetch.py",
            "--suite", "E2E=https://gitlab.com/ocudu/ocudu/-/pipelines/123",
            "-o", str(tmp_path),
        ]
        with (
            patch.object(sys, "argv", test_args),
            patch("gitlab_fetch._fetch_suite", return_value=[]),
            pytest.raises(SystemExit),
        ):
            gitlab_fetch.main()

        captured = capsys.readouterr()
        assert "No XUnit files downloaded" in captured.err
        assert "No XUnit files downloaded" not in captured.out

    def test_multiple_suites_all_fail(self, tmp_path):
        """Even with multiple suites, if all return empty, exit 1."""
        test_args = [
            "gitlab_fetch.py",
            "--suite", "E2E=https://gitlab.com/ocudu/ocudu/-/pipelines/123",
            "--suite", "Unit=https://gitlab.com/ocudu/ocudu/-/pipelines/456",
            "--suite", "TIFG=https://gitlab.com/ocudu/ocudu/-/pipelines/789",
            "-o", str(tmp_path),
        ]
        with (
            patch.object(sys, "argv", test_args),
            patch("gitlab_fetch._fetch_suite", return_value=[]),
            pytest.raises(SystemExit) as exc_info,
        ):
            gitlab_fetch.main()

        assert exc_info.value.code == 1


class TestExitCodeOnSuccess:
    """main() exits cleanly when at least one file is downloaded."""

    def test_exits_zero_when_files_downloaded(self, tmp_path):
        """If _fetch_suite returns results, script should not call sys.exit(1)."""
        dummy_file = tmp_path / "E2E" / "test_xunit.xml"
        dummy_file.parent.mkdir(parents=True)
        dummy_file.write_text("<testsuites/>")

        test_args = [
            "gitlab_fetch.py",
            "--suite", "E2E=https://gitlab.com/ocudu/ocudu/-/pipelines/123",
            "-o", str(tmp_path),
        ]
        with (
            patch.object(sys, "argv", test_args),
            patch("gitlab_fetch._fetch_suite", return_value=[("test_xunit.xml", dummy_file)]),
        ):
            # Should complete without SystemExit
            gitlab_fetch.main()

    def test_prints_success_to_stdout(self, tmp_path, capsys):
        """Success message should go to stdout."""
        dummy_file = tmp_path / "E2E" / "test_xunit.xml"
        dummy_file.parent.mkdir(parents=True)
        dummy_file.write_text("<testsuites/>")

        test_args = [
            "gitlab_fetch.py",
            "--suite", "E2E=https://gitlab.com/ocudu/ocudu/-/pipelines/123",
            "-o", str(tmp_path),
        ]
        with (
            patch.object(sys, "argv", test_args),
            patch("gitlab_fetch._fetch_suite", return_value=[("test_xunit.xml", dummy_file)]),
        ):
            gitlab_fetch.main()

        captured = capsys.readouterr()
        assert "Downloaded files" in captured.out

    def test_partial_success_does_not_exit(self, tmp_path):
        """If at least one suite has results, script succeeds even if others are empty."""
        dummy_file = tmp_path / "E2E" / "test_xunit.xml"
        dummy_file.parent.mkdir(parents=True)
        dummy_file.write_text("<testsuites/>")

        call_count = [0]

        def mock_fetch_suite(client, name, ref, suite_dir):
            call_count[0] += 1
            # First suite returns results, second returns empty
            if call_count[0] == 1:
                return [("test_xunit.xml", dummy_file)]
            return []

        test_args = [
            "gitlab_fetch.py",
            "--suite", "E2E=https://gitlab.com/ocudu/ocudu/-/pipelines/123",
            "--suite", "Unit=https://gitlab.com/ocudu/ocudu/-/pipelines/456",
            "-o", str(tmp_path),
        ]
        with (
            patch.object(sys, "argv", test_args),
            patch("gitlab_fetch._fetch_suite", side_effect=mock_fetch_suite),
        ):
            # Should complete without SystemExit
            gitlab_fetch.main()


class TestOrderFileCreated:
    """The _order.txt file is always written, even on failure."""

    def test_order_file_written_before_exit(self, tmp_path):
        """_order.txt should exist even when exiting with error."""
        test_args = [
            "gitlab_fetch.py",
            "--suite", "E2E=https://gitlab.com/ocudu/ocudu/-/pipelines/123",
            "-o", str(tmp_path),
        ]
        with (
            patch.object(sys, "argv", test_args),
            patch("gitlab_fetch._fetch_suite", return_value=[]),
            pytest.raises(SystemExit),
        ):
            gitlab_fetch.main()

        order_file = tmp_path / "_order.txt"
        assert order_file.exists()
        assert "E2E" in order_file.read_text()
