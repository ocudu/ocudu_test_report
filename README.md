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

## CI

Two GitLab CI jobs run automatically on every push:

| Job | Stage | What it does |
|-----|-------|--------------|
| `validate-features-yaml` | test | Validates `features.yaml` against the schema |
| `build-features-report` | build | Renders the HTML report and exposes it as a CI artifact |

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