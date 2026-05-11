# sfmapi-bench

Standalone benchmark and conformance utilities for sfmapi-compatible APIs.

The first utility checks the live backend action catalog exposed by
`GET /v1/backend/actions`. It is meant to keep backend APIs clean: reusable
actions should be exposed, while benchmark- or dataset-specific scripts should
stay outside the normal API surface.

## Install

```powershell
uv venv
uv sync --extra dev
```

## API Surface Benchmark

Run a built-in preset against a live server:

```powershell
uv run sfmapi-bench api-surface --preset hloc --base-url http://127.0.0.1:8000
```

Built-in presets currently cover:

- `hloc`
- `colmap`
- `colmap-legacy`
- `instantsfm`
- `realityscan`
- `spheresfm`

Check another backend by passing explicit expectations:

```powershell
uv run sfmapi-bench api-surface `
  --base-url http://127.0.0.1:8000 `
  --expect-action colmap.feature_extractor `
  --expect-action colmap.mapper `
  --forbid-prefix colmap.benchmark.
```

Or use a JSON spec:

```json
{
  "name": "my-backend",
  "expected_actions": ["my.extract", "my.match", "my.map"],
  "forbidden_actions": ["my.demoOnly"],
  "forbidden_prefixes": ["my.benchmark."]
}
```

```powershell
uv run sfmapi-bench api-surface --base-url http://127.0.0.1:8000 --spec .\my-backend.json
```

The command exits non-zero if required actions are missing, forbidden actions
are exposed, or required schemas are absent.

For local backend packages, run the same check in-process without binding a
port:

```powershell
uv run --with-editable ..\sfmapi --with-editable ..\sfmapi_hloc `
  sfmapi-bench local-api-surface `
  --backend sfmapi_hloc.backend:HlocBackend `
  --backend-id hloc `
  --preset hloc
```

## Development

```powershell
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```
