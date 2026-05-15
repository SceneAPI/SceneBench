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

## Benchmark Datasets

The dataset catalog keeps dataset-specific material outside backend APIs. Two
groups are registered today:

**Portable-pipeline samples (COLMAP, auto-fetchable):**

- `colmap-south-building` — the canonical 128-image SfM "hello world"
- `colmap-gerrard-hall` — compact 100-image variant for smoke tests / CI

These ride the portable `/v1/projects/{pid}/pipelines/{recipe}` route
(`pipeline_recipe="incremental"`), have direct HTTPS mirrors, and can be
downloaded in-process via `sfmapi-bench fetch`. Provided by the COLMAP
authors for research/demo use — see the COLMAP datasets page for upstream
terms.

**Backend-action samples (SphereSfM):**

- `spheresfm-campus-parterre`
- `spheresfm-campus-building`
- `spheresfm-urban-street`

The benchmark package does not redistribute these. The upstream SphereSfM
README publishes Google Drive / Baidu mirrors but does not state a dataset
license, so the catalog reports `license: "not specified by upstream"` and
`fetch_url: null` (no auto-download — grab them manually). Confirm the
dataset terms before redistributing data or using it in a commercial
benchmark report.

Fetch + extract one of the auto-fetchable samples to the local cache:

```powershell
uv run sfmapi-bench fetch colmap-south-building
# {"dataset_id": "colmap-south-building", "path": "C:\\Users\\…\\sfmapi-bench\\datasets\\colmap-south-building"}
```

The cache root is `$XDG_CACHE_HOME/sfmapi-bench/datasets` (or
`%LOCALAPPDATA%\sfmapi-bench\datasets` on Windows); override with
`SFMAPI_BENCH_CACHE` or `--cache-dir`. The fetch is idempotent — a second
call short-circuits on the extracted directory. Pass `--force` to
re-download and re-extract.

List dataset manifests, including download mirrors:

```powershell
uv run sfmapi-bench list-datasets --backend spheresfm --json
```

After downloading and unpacking a dataset, render the action payload for the
SphereSfM backend:

```powershell
uv run sfmapi-bench dataset-inputs spheresfm-campus-parterre `
  --dataset-root C:\data\spheresfm\campus-parterre `
  --workspace-root C:\bench\spheresfm\campus-parterre
```

The generated payload targets `spheresfm.reconstructPanoramaFolder` and includes
optional `POS.txt` or `camera_mask.png` paths only when those files exist.

## Development

```powershell
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```

## License

The benchmark utility code is licensed under `AGPL-3.0-or-later`; see
`LICENSE`. Dataset entries are metadata only. The listed SphereSfM datasets are
not redistributed by this package and currently have no explicit upstream
dataset license.
