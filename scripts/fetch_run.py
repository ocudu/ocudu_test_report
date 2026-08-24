#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
Fetch a historical report run from the Generic Package Registry.

Downloads the report.zip for a given pipeline ID (or "latest") and extracts
it to a local directory. Used for viewing old reports locally or as input
to the comparison engine.

Usage:
    python fetch_run.py --project-id 12345 --run 67890 -o ./runs/67890
    python fetch_run.py --project-id 12345 --run latest -o ./runs/latest
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
_HTTP_TIMEOUT = 30


def _get_auth_headers(token: str, token_type: str = "private") -> dict[str, str]:
    """Return the appropriate auth header for the given token type."""
    if token_type == "job":
        return {"JOB-TOKEN": token}
    return {"PRIVATE-TOKEN": token}


def resolve_latest_version(
    api_url: str,
    project_id: str,
    headers: dict[str, str],
) -> str:
    """Find the latest (highest pipeline ID) version in the registry.

    Returns the version string of the most recent package.
    """
    url = f"{api_url}/projects/{project_id}/packages"
    params: dict[str, str | int] = {
        "package_name": _PACKAGE_NAME,
        "package_type": "generic",
        "per_page": 1,
        "order_by": "version",
        "sort": "desc",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    packages = resp.json()
    if not packages:
        print("ERROR: No archived runs found in the registry.", file=sys.stderr)
        sys.exit(1)
    return str(packages[0]["version"])


def download_run(
    api_url: str,
    project_id: str,
    version: str,
    headers: dict[str, str],
) -> bytes:
    """Download the report.zip for the given version.

    Returns the raw zip bytes.
    """
    url = f"{api_url}/projects/{project_id}/packages/generic" f"/{_PACKAGE_NAME}/{version}/report.zip"
    print(f"Downloading test-report-runs/{version}/report.zip...", file=sys.stderr)
    resp = requests.get(url, headers=headers, timeout=_HTTP_TIMEOUT, stream=True)
    resp.raise_for_status()

    chunks = []
    for chunk in resp.iter_content(chunk_size=65536):
        chunks.append(chunk)
    return b"".join(chunks)


def extract_run(zip_bytes: bytes, output_dir: Path) -> list[str]:
    """Extract the report zip to the output directory.

    Returns a list of extracted file paths (relative to output_dir).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for member in zf.namelist():
            # Skip directory entries
            if member.endswith("/"):
                continue
            # Strip leading "public/" prefix if present so files land directly in output_dir
            relative = member
            if relative.startswith("public/"):
                relative = relative[len("public/") :]
            target = output_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(member))
            extracted.append(relative)
    return extracted


def main():
    """Entry point: parse arguments, download, and extract a historical run."""
    parser = argparse.ArgumentParser(description="Fetch a historical report run from the Generic Package Registry")
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
        "--run",
        required=True,
        metavar="PIPELINE_ID",
        help="Pipeline ID of the run to fetch, or 'latest' for the most recent",
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
        "-o",
        "--output-dir",
        type=Path,
        default=Path("run_output"),
        help="Directory to extract the run into (default: ./run_output)",
    )
    args = parser.parse_args()

    # Resolve token from args or environment
    token = args.token or os.environ.get("GITLAB_TOKEN") or os.environ.get("CI_JOB_TOKEN") or ""
    if not token:
        print("ERROR: No token provided. Use --token, GITLAB_TOKEN, or CI_JOB_TOKEN.", file=sys.stderr)
        sys.exit(1)

    api_url = f"{args.gitlab_url.rstrip('/')}/api/v4"
    headers = _get_auth_headers(token, args.token_type)

    # Resolve "latest" to an actual version
    version = args.run
    if version.lower() == "latest":
        version = resolve_latest_version(api_url, args.project_id, headers)
        print(f"Latest run: {version}", file=sys.stderr)

    # Download and extract
    zip_bytes = download_run(api_url, args.project_id, version, headers)
    extracted = extract_run(zip_bytes, args.output_dir)

    print(f"Extracted {len(extracted)} files to {args.output_dir}/", file=sys.stderr)

    # Print metadata summary if available
    metadata_path = args.output_dir / "run_metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        totals = metadata.get("totals", {})
        print(
            f"Run {metadata.get('pipeline_id', version)}: "
            f"{totals.get('tests', '?')} tests, "
            f"{totals.get('passed', '?')} passed, "
            f"{totals.get('failed', '?')} failed, "
            f"{totals.get('skipped', '?')} skipped",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
