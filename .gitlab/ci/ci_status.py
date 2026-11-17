#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""
Status of the scheduled pipelines of a GitLab group over the last hours, from what the AI triage wrote to issues.

Usage:
    ci_status.py [--hours 24] [--group ocudu] [--ignore PROJECT[:SCHEDULE]]... [--wait MINUTES]

Per schedule, its latest pipeline that finished in the window, linked (IGNORE lists the schedules left out), with
the open issues the triage found for it:
  :white_check_mark:   passed
  :new:                an issue the triage opened for it
  :recycle:            a closed issue the triage reopened for it
  :repeat:             an open issue it was matched to again
  :construction:       failed only for infrastructure reasons (runner, cluster): not triaged
  :warning:            failed, but no triage reply found
  :heavy_minus_sign:   canceled
  :arrows_counterclockwise:   running (or jobs being retried), with the issues an earlier triage of it found
Then the other open bugs opened in the window (labelled `bug` or `bug::*`, not `bug::ci`), which may be related.

The triage's replies are found through its hidden markers, written by ocudu_tools' post_triage.py on every issue it
touches, all labelled bug::ci: the thread's first note starts with `<!-- ocudu-ai-triage -->`, and each reply holds
`<!-- ocudu-ai-triage-run {"action": "new|reopen|reply", "pipeline": <id>, ...} -->`.

Prints markdown, starting with a `## ` heading (see ci_status_wiki.py). Authentication: $GITLAB_TOKEN env var or --token.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

FINISHED = {"success", "failed", "canceled"}
RUNNING = {"created", "waiting_for_resource", "preparing", "pending", "running"}   # also jobs being retried
SCRIPT_REASONS = {None, "script_failure"}
ACTION_EMOJI = {"new": ":new:", "reopen": ":recycle:", "reply": ":repeat:"}
ACTION_ORDER = ["new", "reopen", "reply"]
# Schedules left out: "project" for all of a project's, or "project:schedule" for one.
POLL_SECONDS = 300
IGNORE = ["ocudu/ocudu_test_report"]


THREAD_MARKER = "<!-- ocudu-ai-triage -->"
RUN_MARKER_RE = re.compile(r"<!-- ocudu-ai-triage-run (\{.*?\}) -->", re.S)
CI_LABEL = "bug::ci"


class GitLabError(Exception):
    pass


class Client:
    def __init__(self, base_url: str, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self._headers = {"PRIVATE-TOKEN": token} if token else {}

    def get(self, path: str, params: dict | None = None):
        url = f"{self.base_url}/api/v4/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=self._headers), timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise GitLabError(f"HTTP {exc.code} GET {url}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise GitLabError(f"GET {url}: {exc}") from exc

    def get_all(self, path: str, params: dict | None = None) -> list:
        items, page = [], 1
        while True:
            batch = self.get(path, {**(params or {}), "per_page": 100, "page": page})
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1


def triage_runs(discussions: list[dict]) -> list[dict]:
    """The run markers of the issue's triage thread, oldest first."""
    for d in discussions:
        notes = d.get("notes") or []
        if notes and notes[0].get("body", "").lstrip().startswith(THREAD_MARKER):
            runs = []
            for note in notes:
                m = RUN_MARKER_RE.search(note.get("body", ""))
                try:
                    if m:
                        runs.append(json.loads(m.group(1)))
                except json.JSONDecodeError:
                    pass
            return runs
    return []


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ignored(project: dict, schedule: dict, ignore: list[str]) -> bool:
    path = project["path_with_namespace"]
    return path in ignore or f"{path}:{schedule['description']}" in ignore


def scheduled_pipelines(client: Client, group: str, since: datetime, ignore: list[str]) -> list[dict]:
    """Per schedule of the group's projects, its latest pipeline that finished, or ran, since `since`."""
    projects = client.get_all(f"groups/{group.replace('/', '%2F')}/projects",
                              {"include_subgroups": "true", "archived": "false", "per_page": 100})

    def schedules(project: dict) -> list[tuple[dict, dict]]:
        try:
            found = client.get(f"projects/{project['id']}/pipeline_schedules", {"per_page": 100})
        except GitLabError:
            return []   # no access to the project's schedules
        return [(project, s) for s in found if not ignored(project, s, ignore)]

    def latest(item: tuple[dict, dict]) -> dict | None:
        project, schedule = item
        pipelines = client.get(f"projects/{project['id']}/pipeline_schedules/{schedule['id']}/pipelines",
                               {"per_page": 20, "sort": "desc"})
        done = [p for p in pipelines if p["status"] in FINISHED | RUNNING and _time(p["updated_at"]) >= since]
        if not done:
            return None
        p = max(done, key=lambda p: p["id"])
        return {"project": project, "schedule": schedule["description"], "pipeline": p}

    with ThreadPoolExecutor(max_workers=8) as pool:
        pairs = [pair for found in pool.map(schedules, projects) for pair in found]
        return [r for r in pool.map(latest, pairs) if r]


def triage_replies(client: Client, group: str, since: datetime, pipelines: set[int]) -> dict[int, list[dict]]:
    """Per pipeline, the issues the triage replied to for it: {issue, action}."""
    issues = client.get_all(f"groups/{group.replace('/', '%2F')}/issues",
                            {"labels": CI_LABEL, "updated_after": since.isoformat(), "state": "opened"})

    def runs(issue: dict) -> list[tuple[dict, dict, bool]]:
        discussions = client.get_all(f"projects/{issue['project_id']}/issues/{issue['iid']}/discussions")
        found = triage_runs(discussions)
        return [(issue, run, n == 0) for n, run in enumerate(found)]

    out: dict = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for found in pool.map(runs, issues):
            for issue, run, first in found:
                if run.get("pipeline") not in pipelines:
                    continue
                # Replies from before the marker named the action: new if the issue is no older than the run.
                action = run.get("action") or ("new" if first and issue["created_at"][:10] >= run.get("date", "")
                                               else "reply")
                out.setdefault(run["pipeline"], []).append({"issue": issue, "action": action})
    return out


def infra_only(client: Client, project_id: int, pipeline_id: int) -> bool:
    jobs = client.get_all(f"projects/{project_id}/pipelines/{pipeline_id}/jobs", {"scope[]": "failed"})
    return bool(jobs) and all(j.get("failure_reason") not in SCRIPT_REASONS for j in jobs)


def is_bug(labels: list[str]) -> bool:
    return CI_LABEL not in labels and any(lb == "bug" or lb.startswith("bug::") for lb in labels)


def other_bugs(client: Client, group: str, since: datetime) -> list[dict]:
    issues = client.get_all(f"groups/{group.replace('/', '%2F')}/issues",
                            {"created_after": since.isoformat(), "state": "opened", "per_page": 100})
    return [i for i in issues if is_bug(i.get("labels", []))]


_MAX_TITLE = 80


def render(results: list[dict], replies: dict, infra: dict, issues: list[dict]) -> str:
    """Header, then the passing schedules on one line, then one block per project with something to look at."""
    def issue_line(issue: dict, project_id: int | None) -> str:
        ref = issue["references"]["full"]
        ref = f"#{issue['iid']}" if issue["project_id"] == project_id else ref.split("/", 1)[-1]
        title = re.sub(r"^\[CI\]\s*", "", issue["title"])
        title = title if len(title) <= _MAX_TITLE else title[:_MAX_TITLE - 1].rstrip() + "…"
        return f"[{ref}]({issue['web_url']}) {title}"

    def link(text: str, r: dict) -> str:
        return f"[{text}]({r['pipeline']['web_url']})"

    passing: dict = {}   # project path -> [result]
    blocks: dict = {}    # project path -> [lines]
    for r in sorted(results, key=lambda r: (r["project"]["path_with_namespace"], r["schedule"].lower())):
        project, p = r["project"], r["pipeline"]
        if p["status"] == "success":
            passing.setdefault(project["path"], []).append(r)
            continue
        lines = blocks.setdefault(project["path"], [])
        head = f"- {link(r['schedule'], r)}"
        found = replies.get(p["id"], [])
        if p["status"] == "canceled":
            lines.append(f"{head}: :heavy_minus_sign: canceled")
            continue
        if p["status"] in RUNNING:
            head += ": :arrows_counterclockwise: running" + (", triaged before:" if found else "")
        elif not found:
            head += ": " + (":construction: infra failures only (retry)" if infra.get(p["id"])
                            else ":warning: failed, no triage found")
        lines.append(head)
        best: dict = {}
        for item in found:
            key = item["issue"]["id"]
            if key not in best or ACTION_ORDER.index(item["action"]) < ACTION_ORDER.index(best[key]["action"]):
                best[key] = item
        for item in sorted(best.values(), key=lambda i: ACTION_ORDER.index(i["action"])):
            lines.append(f"  - {ACTION_EMOJI[item['action']]} {issue_line(item['issue'], project['id'])}")

    out = [f"## {datetime.now(timezone.utc):%Y-%m-%d}", ""]
    if passing:
        out += [":white_check_mark: " + " · ".join(
            f"{path} " + ", ".join(link(r["schedule"], r) for r in rs) for path, rs in passing.items()), ""]
    for path, lines in blocks.items():
        out += [f"**{path}**"] + lines + [""]
    if issues:
        out += ["**Other bug issues**"] + [f"- {issue_line(i, None)}" for i in issues] + [""]
    return "\n".join(out).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Status of a group's scheduled pipelines, from the AI triage")
    parser.add_argument("--hours", type=float, default=24, help="Window, in hours (default 24)")
    parser.add_argument("--group", default="ocudu", help="GitLab group (default: ocudu)")
    parser.add_argument("--ignore", action="append", default=[], metavar="PROJECT[:SCHEDULE]",
                        help=f"Leave out a project's schedules, or one; adds to {IGNORE}")
    parser.add_argument("--base-url", default="https://gitlab.com")
    parser.add_argument("--token", default=os.environ.get("GITLAB_TOKEN", ""),
                        help="GitLab access token (default: $GITLAB_TOKEN)")
    parser.add_argument("--wait", type=float, default=0, metavar="MINUTES",
                        help="Wait up to this long for running scheduled pipelines to finish (default 0)")
    args = parser.parse_args()
    client = Client(args.base_url, args.token)
    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    deadline = time.monotonic() + args.wait * 60

    try:
        while True:
            results = scheduled_pipelines(client, args.group, since, IGNORE + args.ignore)
            running = [r for r in results if r["pipeline"]["status"] in RUNNING]
            left = deadline - time.monotonic()
            if not running or left <= 0:
                break
            names = ", ".join(f"{r['project']['path']} {r['schedule']}" for r in running)
            print(f"Waiting for {len(running)} running pipelines ({names}); {left / 60:.0f} min left",
                  file=sys.stderr)
            time.sleep(min(POLL_SECONDS, left))
        failed = [r for r in results if r["pipeline"]["status"] in {"failed"} | RUNNING]
        replies = triage_replies(client, args.group, since - timedelta(days=1),
                                 {r["pipeline"]["id"] for r in failed})
        untriaged = [r for r in failed if r["pipeline"]["id"] not in replies and r["pipeline"]["status"] == "failed"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            flags = pool.map(lambda r: infra_only(client, r["project"]["id"], r["pipeline"]["id"]), untriaged)
            infra = {r["pipeline"]["id"]: flag for r, flag in zip(untriaged, flags)}
        issues = other_bugs(client, args.group, since)
    except GitLabError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print(render(results, replies, infra, issues), end="")


if __name__ == "__main__":
    main()
