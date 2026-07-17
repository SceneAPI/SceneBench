# sceneapi-bench

Standalone benchmark and conformance utilities for sceneapi-compatible APIs.

Renamed from `sfmapi-bench` at 0.1.0 as part of the sfmapi → sceneapi
migration: the distribution is `sceneapi-bench`, the import package is
`sceneapi_bench`, and the CLI binary is `sceneapi-bench`. The old
`sfmapi-bench` binary name ships as a deprecated alias for one release
(removed in 0.2.0). Bench-owned environment names (`SFMAPI_BENCH_CACHE`,
`SFMAPI_BENCH_BICYCLE_IMAGE_DIR`) and the on-disk cache directory name are
unchanged this release.

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
uv run sceneapi-bench api-surface --preset hloc --base-url http://127.0.0.1:8000
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
uv run sceneapi-bench api-surface `
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
uv run sceneapi-bench api-surface --base-url http://127.0.0.1:8000 --spec .\my-backend.json
```

The command exits non-zero if required actions are missing, forbidden actions
are exposed, or required schemas are absent.

For local backend packages, run the same check in-process without binding a
port:

```powershell
uv run --with-editable ..\sfmapi --with-editable ..\sfmapi_hloc `
  sceneapi-bench local-api-surface `
  --backend sfmapi_hloc.backend:HlocBackend `
  --backend-id hloc `
  --preset hloc
```

## Plugin E2E Conformance

`sceneapi-bench run` wraps the repo E2E suites that exercise installed plugins
through UV. The default `plugins` suite drives the Python API and the C++ API +
bridge against the same provider matrix. Missing engines, unavailable devices,
and skipped rows are reported as conformance failures so the root cause is
visible in the report tails.

```powershell
uv run sceneapi-bench run `
  --suite plugins `
  --dataset bicycle `
  --backend both `
  --image-dir C:\Users\opsiclear\Desktop\projects\data\bicycle\images_2 `
  --local-plugins `
  --json
```

Additional suites:

- `vismatch`: HLOC pairs -> Vismatch matching on a bicycle subset.
- `containers`: explicit `container_service` install/execution behavior.
- `bicycle`: endpoint sweep, features, actions, and reconstruction pipeline.
- `hloc`: HLOC matcher/reconstruction/localization matrix.
- `pairs`: COLMAP/PyCOLMAP/SphereSfM pair-mode and matcher matrix.
- `retrieval`: HLOC NetVLAD retrieval plus COLMAP vocab-tree build/match.
- `splatting`: build and run all registered 3DGS plugin containers on bicycle.
- `official-plugins`: heaviest official plugin action probes.
- `bridge`, `bridge-plugin-state`, `colmap`, `sdk`, `mcp`, `api-parity`:
  bridge, plugin-state, COLMAP, SDK, MCP, and two-way API parity checks.

Useful variants:

```powershell
uv run sceneapi-bench run --suite vismatch --dataset bicycle --backend cpp --models xfeat --device cpu
uv run sceneapi-bench run --suite vismatch --backend cpp --all-supported-models --device cuda
uv run sceneapi-bench run --suite all --output .\bench-report.json
uv run sceneapi-bench report .\bench-report.json --format json
```

Use `--dry-run --json` to validate command construction without running heavy
reconstruction work. Use `--with-editable <path>` for extra local plugin repos;
`--local-plugins` adds sibling sfmapi plugin repos, including
`sfmapi_vismatch[engine]`.

## Benchmark Datasets

The dataset catalog keeps dataset-specific material outside backend APIs. Two
groups are registered today:

**Portable-pipeline samples (COLMAP, auto-fetchable):**

- `colmap-south-building` - 128 images, about 400 MB zip, the canonical SfM
  "hello world"
- `colmap-gerrard-hall` - 100 images, about 960 MB zip, second sample for
  generalization checks

These ride the portable `/v1/projects/{pid}/pipelines/{recipe}` route
(`pipeline_recipe="incremental"`), have direct HTTPS mirrors (GitHub release
assets), and can be downloaded in-process via `sceneapi-bench fetch`. The
fetcher verifies the archive against a pinned sha256 before extracting.
Provided by the COLMAP authors for research/demo use; see the COLMAP datasets
page for upstream terms.

**Backend-action samples (SphereSfM):**

- `spheresfm-campus-parterre` - auto-fetchable from the upstream public Google
  Drive mirror and verified by sha256.
- `spheresfm-campus-building`
- `spheresfm-urban-street`

The benchmark package does not redistribute these. The upstream SphereSfM
README publishes Google Drive/Baidu mirrors but does not state a dataset
license, so the catalog reports `license: "not specified by upstream"`.
`spheresfm-campus-parterre` can be downloaded directly for conformance runs;
the other SphereSfM samples remain manual-only until direct, verifiable
archives are pinned. Confirm the dataset terms before redistributing data or
using it in a commercial benchmark report.

Fetch and extract an auto-fetchable sample to the local cache:

```powershell
uv run sceneapi-bench fetch colmap-south-building
uv run sceneapi-bench fetch spheresfm-campus-parterre
```

The cache root is `$XDG_CACHE_HOME/sfmapi-bench/datasets` or
`%LOCALAPPDATA%\sfmapi-bench\datasets` on Windows; override with
`SFMAPI_BENCH_CACHE` or `--cache-dir`. (The cache directory and env names
keep their pre-rename spelling this release.) The fetch is idempotent: a
second call short-circuits on the extracted directory. Pass `--force` to
re-download and re-extract.

List dataset manifests, including download mirrors:

```powershell
uv run sceneapi-bench list-datasets --backend spheresfm --json
```

After downloading and unpacking a dataset, render the action payload for the
SphereSfM backend:

```powershell
uv run sceneapi-bench dataset-inputs spheresfm-campus-parterre `
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

The benchmark utility code is licensed under `Apache-2.0`; see
`LICENSE`. Dataset entries are metadata only. The listed SphereSfM datasets are
not redistributed by this package and currently have no explicit upstream
dataset license.
