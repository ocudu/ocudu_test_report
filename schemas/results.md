<!--
SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
SPDX-FileCopyrightText: Copyright (C) 2026 OCUDU contributors
SPDX-License-Identifier: BSD-3-Clause-Open-MPI
-->

# Test result upload format

Every lab sends results to the OCUDU test report as **JUnit XML** files. This document covers what a file must contain to be accepted.

- Schema: [`results.schema.yaml`](results.schema.yaml) (format version `1`)
- Validator: [`scripts/validate_results.py`](../scripts/validate_results.py)

Files are validated before upload and again when they are ingested. A file that fails is rejected as a whole.

## Before you start: register your lab

Your lab needs an entry in [`labs/labs.yaml`](../labs/labs.yaml). To add one, open an MR to that file:

```yaml
labs:
  - id: my-lab          # lowercase letters, digits and single hyphens
    name: My Lab
    url: https://...    # optional
```

The `id` is the value you put in the `lab` property of every result file. Results from labs that are not in this file are rejected.

## Minimal valid file

```xml
<?xml version="1.0" encoding="utf-8"?>
<testsuites name="TIFG tests">
  <testsuite name="TIFG" timestamp="2026-11-10T02:00:00+00:00">
    <properties>
      <property name="schema_version" value="1"/>
      <property name="lab" value="my-lab"/>
      <property name="ocudu_commit" value="65cbdb66cb726c6cdae97ec37e0c5dfd1f50eeca"/>
      <property name="run_url" value="https://ci.example.org/runs/1234"/>
      <property name="dut" value="O-CU/O-DU"/>
    </properties>
    <testcase name="5.3" classname="Initial registration" time="12.5"/>
    <testcase name="5.4" classname="UE detach" time="8.1">
      <failure message="UE did not detach">details / logs</failure>
    </testcase>
    <testcase name="5.5" classname="Handover">
      <error message="setup crashed"/>
    </testcase>
    <testcase name="5.6" classname="Paging">
      <skipped message="not supported by the lab setup"/>
    </testcase>
  </testsuite>
</testsuites>
```

## Structure

### Root element

The root must be either `<testsuites>` holding one or more `<testsuite>` elements, or a single `<testsuite>`.

- A file must contain **at least one** `<testsuite>`.
- `<!DOCTYPE>` declarations are **not allowed**. Files that contain one are rejected.
- The file must be well-formed XML. Use UTF-8.

### `<testsuite>`

| Attribute | Required | Description |
| --- | --- | --- |
| `name` | **yes** (non-empty) | The test plan name, e.g. `TIFG` or `WG11`. This decides which test plan in [`testplans/`](../testplans/) maps your test IDs to OCUDU features (see [Feature mapping](#feature-mapping)). |
| `timestamp` | no | When the run happened. Use ISO 8601 with a timezone, e.g. `2026-11-10T02:00:00+00:00`. |
| `tests`, `failures`, `errors`, `skipped`, `time`, `hostname` | no | Standard JUnit counters. They are ignored, because the counts are worked out from the test cases. |

Each `<testsuite>` must contain **at least one** `<testcase>`.

### Suite properties (`<testsuite><properties>`)

These properties identify the result. Only the suite-level `<properties>` block is read for them. Properties set on a `<testcase>` do not count.

| Property | Required | Format | Description |
| --- | --- | --- | --- |
| `schema_version` | **yes** | `1` | The version of this upload format. Only `1` is supported today. |
| `lab` | **yes** | `^[a-z0-9]+(-[a-z0-9]+)*$` | Your lab `id` from `labs/labs.yaml`. |
| `ocudu_commit` | **yes** | `^[0-9a-f]{40}$` | The **full** 40-character lowercase SHA of the OCUDU commit under test. Short SHAs, tags and branch names are rejected. |
| `run_url` | no | `^https?://` | A link to the run, e.g. for full logs. |
| `dut` | no | non-empty | The device under test, e.g. `O-CU/O-DU`. |
| *anything else* | no | string | Your own properties are allowed and kept (CI adds `url` and `test_commit`, for example). |

Rules:

- Each required property must appear in **every** `<testsuite>` of the file.
- All `<testsuite>` elements in one file must have the **same** `lab` and the **same** `ocudu_commit`. If you tested several commits, send one file per commit.
- If you repeat `schema_version`, `lab` or `ocudu_commit` within one suite, every copy must have the same value.

### `<testcase>`

| Attribute | Required | Description |
| --- | --- | --- |
| `name` | **yes** (non-empty) | The test ID. For third-party test plans, use the plan's `test_id` exactly as written (e.g. `5.3`, `6.3.2`). |
| `classname` | no | A readable test name or group. |
| `time` | no | Duration in seconds. Must be a number ≥ 0. |
| `timestamp` | no | When this test case ran (ISO 8601). |

The result of a test case depends on which of these child elements it contains, checked in this order. The first match wins, wherever the element sits in the test case:

| Child element | Status |
| --- | --- |
| `<failure>` | `failed` |
| `<error>` | `error` |
| `<skipped>` | `skipped` |
| *none of the above* | `passed` |

For example, a test case with both `<skipped>` and `<failure>` is `failed`, whichever comes first. Other children, such as `<properties>` or `<system-out>`, do not affect the result.

Use `failure` when the DUT did not meet the test's criteria. Use `error` when the test could not run properly, e.g. because of a setup or tooling problem. You can add a `message` attribute and text to any of these elements to explain the result. `<system-out>` and `<system-err>` are optional and are shown in the report.

### Test case properties (optional)

A `<testcase>` can have its own `<properties>`. These are not used for validation, but the report uses them:

- `markers`, `cmake_labels`, `requirements`: feature labels separated by `;`, e.g. `MVP-FUNC-PHY-16-4;zmq_mme`. These link the test case directly to features in `features/features.yaml`.
- Any other property, e.g. `Comments`, is shown next to the test case.

## Feature mapping

There are two ways to link a test case to OCUDU features:

1. **Test plan lookup.** If the `<testsuite name>` is a known test plan (`TIFG` → `testplans/tifg.yaml`, `WG11` → `testplans/wg11.yaml`), each `<testcase name>` is looked up as a `test_id` in that plan, and the plan's `ocudu_features` are attached. The suite name is not case-sensitive, but the test ID must match exactly.
2. **Explicit labels.** List feature IDs in a `markers` (or `cmake_labels` / `requirements`) property on the test case.

A test case that matches no feature is still stored, but it will not appear in the feature overview.

## Validating locally

```bash
pip install pyyaml jsonschema
python3 scripts/validate_results.py --lab my-lab results/*.xml
```

`--lab` is optional. It checks that every file names that lab. Exit codes: `0` means all files are valid, `1` means at least one file is invalid, and `2` means a setup error (the schema or labs file is missing).

Example output:

```text
FAILED results/run.xml (2 error(s)):
  [testsuites -> 0 -> properties] 'lab' is a required property
  [testsuites -> 0 -> properties -> ocudu_commit] 'abc123' does not match '^[0-9a-f]{40}$'
OK     results/other.xml

1 of 2 file(s) valid.
```

## Common mistakes

| Error | Fix |
| --- | --- |
| `'schema_version' is a required property` | Add `<property name="schema_version" value="1"/>` to each suite. |
| `unknown lab '...'` | Register the lab in `labs/labs.yaml`, or fix the typo. |
| `ocudu_commit ... does not match` | Use the full SHA from `git rev-parse HEAD`, not a short SHA or a tag. |
| `all testsuites in a file must share one 'ocudu_commit'` | Split the file so there is one commit per file. |
| `DOCTYPE declarations are not allowed` | Remove the `<!DOCTYPE ...>` line. |
| `[... -> testcases] [] is too short` | Each suite needs at least one `<testcase>`. |
| `time ... is not of type 'number'` | `time` must be in seconds, e.g. `12.5`, not `00:00:12`. |
