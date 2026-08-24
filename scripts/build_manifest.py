#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
Build a runs.json manifest from the Generic Package Registry.

Queries GitLab for all versions of the test-report-runs package, downloads
run_metadata.json from each, and assembles a manifest listing all available
report runs. The manifest is used by the UI to offer run selection and by
the comparison engine to identify runs for diffing.

Usage:
    python build_manifest.py --project-id 12345 -o public/runs.json
    python build_manifest.py --project-id 12345 --gitlab-url https://gitlab.example.com -o runs.json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests is required. Install with: pip install requests", file=sys.stderr)
    sys.exit(2)

_PACKAGE_NAME = "test-report-runs"
_METADATA_FILENAME = "run_metadata.json"
_HTTP_TIMEOUT = 30


def _get_auth_headers(token: str, token_type: str = "private") -> dict[str, str]:
    """Return the appropriate auth header for the given token type."""
    if token_type == "job":
        return {"JOB-TOKEN": token}
    return {"PRIVATE-TOKEN": token}


def _list_package_versions(
    api_url: str,
    project_id: str,
    headers: dict[str, str],
) -> list[dict]:
    """Fetch all versions of the test-report-runs package from the registry.

    Returns a list of package dicts sorted by pipeline_id (descending, newest first).
    Each dict contains at minimum: id, version, created_at.
    """
    packages = []
    page = 1
    while True:
        url = f"{api_url}/projects/{project_id}/packages"
        params: dict[str, str | int] = {
            "package_name": _PACKAGE_NAME,
            "package_type": "generic",
            "per_page": 100,
            "page": page,
            "order_by": "version",
            "sort": "desc",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        packages.extend(batch)
        page += 1
    return packages


def _download_metadata_from_zip(
    api_url: str,
    project_id: str,
    version: str,
    headers: dict[str, str],
) -> dict | None:
    """Download report.zip for a given version and extract run_metadata.json.

    Returns the parsed metadata dict, or None if the metadata file is not
    found in the zip or the download fails.
    """
    url = f"{api_url}/projects/{project_id}/packages/generic" f"/{_PACKAGE_NAME}/{version}/report.zip"
    try:
        resp = requests.get(url, headers=headers, timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  WARNING: Failed to download {version}/report.zip: {exc}", file=sys.stderr)
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            # The metadata may be at public/run_metadata.json or run_metadata.json
            for candidate in [f"public/{_METADATA_FILENAME}", _METADATA_FILENAME]:
                if candidate in zf.namelist():
                    result: dict = json.loads(zf.read(candidate))
                    return result
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError) as exc:
        print(f"  WARNING: Failed to read metadata from {version}/report.zip: {exc}", file=sys.stderr)
        return None

    print(f"  WARNING: {_METADATA_FILENAME} not found in {version}/report.zip", file=sys.stderr)
    return None


def build_manifest(
    api_url: str,
    project_id: str,
    headers: dict[str, str],
    max_runs: int = 0,
) -> dict:
    """Build the complete runs.json manifest.

    Args:
        api_url: GitLab API base URL (e.g. https://gitlab.com/api/v4)
        project_id: Numeric project ID
        headers: Auth headers for API requests
        max_runs: Maximum number of runs to include (0 = all)

    Returns:
        A dict with schema_version and a runs list ready for JSON serialisation.
    """
    print(f"Fetching package list for {_PACKAGE_NAME}...", file=sys.stderr)
    packages = _list_package_versions(api_url, project_id, headers)

    if max_runs > 0:
        packages = packages[:max_runs]

    print(f"Found {len(packages)} archived run(s). Downloading metadata...", file=sys.stderr)

    runs = []
    for pkg in packages:
        version = pkg["version"]
        print(f"  Fetching metadata for run {version}...", file=sys.stderr)
        metadata = _download_metadata_from_zip(api_url, project_id, version, headers)
        if metadata is None:
            # Still include the run in the manifest with minimal info from the package
            metadata = {
                "pipeline_id": version,
                "generated_at": pkg.get("created_at", ""),
                "totals": {},
                "suites": [],
            }
        # Add the download URL so consumers know where to fetch the full archive
        metadata["package_version"] = version
        metadata["download_url"] = (
            f"{api_url}/projects/{project_id}/packages/generic" f"/{_PACKAGE_NAME}/{version}/report.zip"
        )
        runs.append(metadata)

    return {
        "schema_version": 1,
        "total_runs": len(runs),
        "runs": runs,
    }


def main():
    """Entry point: parse arguments and write the manifest."""
    parser = argparse.ArgumentParser(description="Build runs.json manifest from the Generic Package Registry")
    parser.add_argument(
        "--project-id",
        required=True,
        help="GitLab project ID (numeric)",
    )
    parser.add_argument(
        "--gitlab-url",
        default="https://gitlab.com",
        help="GitLab instance URL (default: https://gitlab.com)",
    )
    parser.add_argument(
        "--token",
        default="",
        help="GitLab API token (defaults to GITLAB_TOKEN or CI_JOB_TOKEN env var)",
    )
    parser.add_argument(
        "--token-type",
        choices=["private", "job"],
        default="private",
        help="Token type: 'private' for PRIVATE-TOKEN, 'job' for JOB-TOKEN (default: private)",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Maximum number of runs to include in the manifest (0 = all, default: 0)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("runs.json"),
        help="Output file path (default: runs.json)",
    )
    args = parser.parse_args()

    # Resolve token from args or environment
    token = args.token or os.environ.get("GITLAB_TOKEN") or os.environ.get("CI_JOB_TOKEN") or ""
    if not token:
        print("ERROR: No token provided. Use --token, GITLAB_TOKEN, or CI_JOB_TOKEN.", file=sys.stderr)
        sys.exit(1)

    api_url = f"{args.gitlab_url.rstrip('/')}/api/v4"
    headers = _get_auth_headers(token, args.token_type)

    manifest = build_manifest(api_url, args.project_id, headers, max_runs=args.max_runs)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest written to {args.output} ({manifest['total_runs']} runs)", file=sys.stderr)


if __name__ == "__main__":
    main()
