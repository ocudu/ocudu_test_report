#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
Download XUnit artifacts from GitLab jobs or pipelines.

Usage:
    fetch-xunit --suite "A=<job-url>" --suite "B=<pipeline-url>" -o ./artifacts
"""

import argparse
import io
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote

try:
    import requests
except ImportError:
    print("ERROR: requests is required. Install with: pip install requests", file=sys.stderr)
    sys.exit(2)

# Matches: https://gitlab.example.com/group/sub/project/-/jobs/123
#      or: https://gitlab.example.com/group/sub/project/-/pipelines/123
_URL_RE = re.compile(r"(https?://[^/]+)/(.+?)/-/(jobs|pipelines)/(\d+)/?$")

# XUnit files we recognize inside an artifacts zip
_XUNIT_RE = re.compile(r"(^|/)([^/]+_xunit\.xml|out\.xml)$")


def _parse_url(url: str):
    m = _URL_RE.match(url.rstrip("/"))
    if not m:
        raise ValueError(f"Cannot parse as GitLab job/pipeline URL: {url!r}")
    base, project, kind, id_ = m.group(1), m.group(2), m.group(3), int(m.group(4))
    return base, project, kind.rstrip("s"), id_  # 'jobs'->'job', 'pipelines'->'pipeline'


class _Client:
    def __init__(self, base_url: str, project_path: str):
        encoded = quote(project_path, safe="")
        self._root = f"{base_url}/api/v4/projects/{encoded}"
        self._session = requests.Session()

    def _get(self, path: str, **kwargs) -> requests.Response:
        r = self._session.get(f"{self._root}/{path}", **kwargs)
        r.raise_for_status()
        return r

    def pipeline_jobs(self, pipeline_id: int) -> list:
        """Return all jobs for a pipeline, handling pagination."""
        jobs, page = [], 1
        while True:
            batch = self._get(
                f"pipelines/{pipeline_id}/jobs",
                params={"per_page": 100, "page": page},
            ).json()
            if not batch:
                break
            jobs.extend(batch)
            page += 1
        return jobs

    def artifacts_zip(self, job_id: int) -> bytes:
        """Download the full artifacts zip for a job."""
        return self._get(f"jobs/{job_id}/artifacts").content


def _extract_xunits(zip_bytes: bytes) -> list[tuple[str, bytes]]:
    """Return [(filename, data)] for every XUnit file found in the zip."""
    results = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if _XUNIT_RE.search(name):
                results.append((Path(name).name, zf.read(name)))
    return results


def _safe_name(name: str) -> str:
    """Strip characters that are invalid or problematic in file/directory names."""
    return re.sub(r"[^\w\-.]", "_", name).strip("_. ")


def _fetch_job(client: _Client, job_id: int, report_name: str, suite_dir: Path) -> list[tuple[str, Path]]:
    """Download artifacts for one job into suite_dir. report_name is used as the xunit-report suite label."""
    print(f"  job {job_id} ({report_name}) — downloading artifacts ...", end=" ", flush=True)
    try:
        zip_bytes = client.artifacts_zip(job_id)
    except requests.HTTPError as exc:
        print(f"skipped ({exc})")
        return []

    files = _extract_xunits(zip_bytes)
    if not files:
        print("no XUnit files found")
        return []

    print(f"{len(files)} XUnit file(s) found")
    saved = []
    for filename, data in files:
        stem = Path(filename).stem
        out_name = report_name if len(files) == 1 else f"{report_name} ({stem})"
        out_path = suite_dir / f"{_safe_name(report_name)}_{_safe_name(stem)}.xml"
        out_path.write_bytes(data)
        print(f"    saved {out_path}")
        saved.append((out_name, out_path))

    return saved


def main():  # pylint: disable=too-many-locals
    """Entry point: parse arguments and download XUnit artifacts from GitLab."""
    parser = argparse.ArgumentParser(description="Download XUnit artifacts from GitLab jobs or pipelines")
    parser.add_argument(
        "--suite",
        metavar="NAME=URL",
        action="append",
        required=True,
        help="Suite label and GitLab URL, repeatable",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("artifacts"),
        help="Directory to save downloaded XUnit files (default: ./artifacts)",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    all_saved: list[tuple[str, Path]] = []
    suite_order: list[str] = []

    for entry in args.suite:
        if "=" not in entry:
            parser.error(f"Expected NAME=URL, got: {entry!r}")
        name, _, url = entry.partition("=")
        name, url = name.strip(), url.strip()

        try:
            base, project, kind, id_ = _parse_url(url)
        except ValueError as exc:
            parser.error(str(exc))

        client = _Client(base, project)
        suite_dir = args.output_dir / _safe_name(name)
        suite_dir.mkdir(parents=True, exist_ok=True)
        (suite_dir / "_url.txt").write_text(url, encoding="utf-8")
        suite_order.append(_safe_name(name))

        if kind == "job":
            print(f"'{name}' — job {id_}")
            saved = _fetch_job(client, id_, name, suite_dir)
            all_saved.extend(saved)
        else:
            print(f"'{name}' — pipeline {id_}")
            try:
                jobs = client.pipeline_jobs(id_)
            except requests.HTTPError as exc:
                print(f"  error fetching pipeline jobs: {exc}")
                continue
            print(f"  {len(jobs)} jobs in pipeline")
            for job in jobs:
                saved = _fetch_job(client, job["id"], job["name"], suite_dir)
                all_saved.extend(saved)

    (args.output_dir / "_order.txt").write_text("\n".join(suite_order), encoding="utf-8")

    if not all_saved:
        print("\nNo XUnit files downloaded.")
        return

    print("\nDownloaded files.")


if __name__ == "__main__":
    main()
