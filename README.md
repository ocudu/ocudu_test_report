# OCUDU Test Report

This repo contains a structured YAML file that includes the current and future feature-set of OCUDU.
We currently support validation agains a schema and rendering the features into a self-contained HTML report.

## Repository layout

```
features/
  features.yaml       # feature definitions (edit this)
  features.schema     # JSON Schema (YAML format) for validation
scripts/
  validate_features.py  # validates features.yaml against the schema
  render_report.py      # renders features.yaml to an HTML report
```

## Usage

**Validate:**

```bash
pip install pyyaml jsonschema
python3 scripts/validate_features.py --schema features/features.schema --data features/features.yaml
```

**Render report:**

```bash
pip install pyyaml
python3 scripts/render_report.py --data features/features.yaml --output features_report.html
```

**gitlab_fetch.py:**

Downloads XUnit XML files from GitLab job or pipeline artifact zips and saves them under a local directory, one subfolder per `--suite`.

```bash
python gitlab_fetch.py --suite "NAME=URL" [--suite "NAME2=URL2" ...] [-o OUTPUT_DIR]
```

| Argument | Default | Description |
|---|---|---|
| `--suite NAME=URL` | required, repeatable | Suite label and GitLab job or pipeline URL |
| `-o / --output-dir` | `./artifacts` | Root folder where files are saved |

**xunit_report.py:**

Reads the artifact folder produced by `gitlab_fetch.py` and renders a single self-contained HTML file.

```bash
python xunit_report.py --dir FOLDER [-o OUTPUT] [--link URL] [--favicon URL]
```

| Argument | Default | Description |
|---|---|---|
| `--dir FOLDER` | required | Root artifacts folder (each subfolder → one suite) |
| `-o / --output` | `report.html` | Output HTML file |
| `--link URL` | — | GitLab branch/tag/pipeline URL shown in the report header |
| `--favicon URL` | ocudu favicon | Favicon URL embedded in the HTML |

Suite names are derived from subfolder names with underscores replaced by spaces.
If a `_url.txt` file is present in a subfolder the suite header will include a link to the original GitLab job/pipeline.

## Feature fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique feature identifier |
| `source` | enum | `ATIS-MVP`, `Customer defined`, or `SRS defined` |
| `scope` | enum | `CU/DU`, `Unspecified`, `Entire RAN Product`, or `Platform/deployment/auxiliary component` |
| `description` | string | Requirement text |
| `release` | enum | Target release (e.g. `v26.04`) |
| `primary_test_type` | array | One or more of `unit`, `integration`, `e2e` |
| `comment` | string | Notes on implementation or test status |

## License

This project is licensed under the BSD 3-Clause Open MPI variant License – see the [LICENSE](./LICENSE) file for details.
