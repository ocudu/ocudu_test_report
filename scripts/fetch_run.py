#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
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
_INDEX_VERSION = "index"
_INDEX_FILENAME = "runs.json"
_HTTP_TIMEOUT = 30

# A missing generic-package index reads as 404 with a personal token but as
# 401/403 with the CI job token. All mean "no index yet" (e.g. first run).
_INDEX_ABSENT_STATUSES = (401, 403, 404)


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
    """Find the latest (highest pipeline ID) run from the runs.json index.

    Reads the index file that build_manifest.py maintains in the registry
    rather than listing packages via GET /projects/:id/packages, which the CI
    job token is not authorised to call. Returns the version string of the
    most recent run. Exits 1 (cleanly) when there is no index yet: GitLab
    reports a missing generic-package file as 404 for a personal token but as
    401/403 for the CI job token, so all of those mean "no runs to compare
    against".
    """
    url = f"{api_url}/projects/{project_id}/packages/generic" f"/{_PACKAGE_NAME}/{_INDEX_VERSION}/{_INDEX_FILENAME}"
    resp = requests.get(url, headers=headers, timeout=_HTTP_TIMEOUT)
    if resp.status_code in _INDEX_ABSENT_STATUSES:
        print(
            f"ERROR: No runs index found in the registry (HTTP {resp.status_code}; first run?).",
            file=sys.stderr,
        )
        sys.exit(1)
    resp.raise_for_status()

    try:
        manifest = json.loads(resp.content)
    except json.JSONDecodeError:
        print("ERROR: Runs index is not valid JSON.", file=sys.stderr)
        sys.exit(1)

    runs = manifest.get("runs", [])
    if not runs:
        print("ERROR: No archived runs found in the registry.", file=sys.stderr)
        sys.exit(1)

    def _pipeline_id(run: dict) -> int:
        value = run.get("pipeline_id") or run.get("package_version") or ""
        try:
            return int(value)
        except (TypeError, ValueError):
            return -1

    latest = max(runs, key=_pipeline_id)
    version = latest.get("pipeline_id") or latest.get("package_version")
    if not version:
        print("ERROR: Latest run in the index has no pipeline_id.", file=sys.stderr)
        sys.exit(1)
    return str(version)


def download_run(
    api_url: str,
    project_id: str,
    version: str,
    headers: dict[str, str],
) -> bytes | None:
    """Download the report.zip for the given version.

    Returns the raw zip bytes, or None when the run cannot be read. A missing
    or unauthorised package file (404, or 401/403 with the CI job token) means
    "no readable run", which callers treat as skip-this-run rather than a hard
    failure. Transport errors are likewise reported and skipped so a single
    flaky read never fails the whole report job.
    """
    url = f"{api_url}/projects/{project_id}/packages/generic" f"/{_PACKAGE_NAME}/{version}/report.zip"
    print(f"Downloading test-report-runs/{version}/report.zip...", file=sys.stderr)
    try:
        resp = requests.get(url, headers=headers, timeout=_HTTP_TIMEOUT, stream=True)
    except requests.RequestException as exc:
        print(f"WARNING: Could not reach the registry to download run {version}: {exc}", file=sys.stderr)
        return None

    if resp.status_code in _INDEX_ABSENT_STATUSES:
        print(
            f"Run {version} is not readable (HTTP {resp.status_code}); skipping.",
            file=sys.stderr,
        )
        return None

    resp.raise_for_status()

    chunks = []
    for chunk in resp.iter_content(chunk_size=65536):
        chunks.append(chunk)
    return b"".join(chunks)


def extract_run(zip_bytes: bytes, output_dir: Path, only: list[str] | None = None) -> list[str]:
    """Extract the report zip to the output directory.

    When ``only`` is given, extract just the named files (matched on the
    path after any leading ``public/`` is stripped, e.g. ``results.json``).
    This lets callers pull the small comparison inputs for every run without
    unpacking the full report and its logs. Returns a list of extracted file
    paths (relative to output_dir).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    only_set = set(only) if only else None
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
            if only_set is not None and relative not in only_set:
                continue
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
    parser.add_argument(
        "--only",
        nargs="+",
        default=None,
        metavar="FILE",
        help="Extract only these files from the run (e.g. --only results.json run_metadata.json). "
        "Paths are matched after stripping any leading 'public/'. Lets you pull the small "
        "comparison inputs for every run without unpacking the full report and logs.",
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
    if zip_bytes is None:
        print(f"WARNING: Run {version} could not be downloaded. Nothing extracted.", file=sys.stderr)
        sys.exit(1)
    extracted = extract_run(zip_bytes, args.output_dir, only=args.only)

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
