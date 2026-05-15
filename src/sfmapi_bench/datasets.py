from __future__ import annotations

import hashlib
import os
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class BenchmarkDataset:
    id: str
    backend: str
    name: str
    description: str
    source: str
    license: str
    mirrors: dict[str, str]
    # ``action_id`` is set for datasets exercised through a specific
    # backend-action (e.g. spheresfm's ``reconstructPanoramaFolder``).
    # ``pipeline_recipe`` is set instead for datasets exercised through
    # a portable ``/v1/projects/{pid}/pipelines/{recipe}`` route — the
    # canonical "hello world" SfM samples (e.g. COLMAP South Building)
    # fall into this group.
    action_id: str | None = None
    pipeline_recipe: str | None = None
    # When ``fetch_url`` is set, the dataset is fetchable in-process via
    # :func:`fetch_dataset`. Mirrors lacking an HTTP-accessible URL
    # (Baidu, Google Drive auth flows) stay listed for humans but cannot
    # be auto-downloaded.
    fetch_url: str | None = None
    fetch_sha256: str | None = None
    fetch_format: str = "zip"
    tags: tuple[str, ...] = ()
    image_subdir: str = "images"
    workspace_subdir: str = "colmap"
    default_inputs: dict[str, Any] = field(default_factory=dict)
    optional_input_files: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "backend": self.backend,
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "license": self.license,
            "mirrors": dict(self.mirrors),
            "action_id": self.action_id,
            "pipeline_recipe": self.pipeline_recipe,
            "fetch_url": self.fetch_url,
            "fetch_sha256": self.fetch_sha256,
            "fetch_format": self.fetch_format,
            "tags": list(self.tags),
            "image_subdir": self.image_subdir,
            "workspace_subdir": self.workspace_subdir,
            "default_inputs": dict(self.default_inputs),
            "optional_input_files": dict(self.optional_input_files),
        }

    def action_payload(
        self,
        dataset_root: Path,
        *,
        workspace_root: Path | None = None,
        include_missing_optional: bool = False,
    ) -> dict[str, Any]:
        workspace_base = workspace_root or dataset_root
        inputs = {
            **self.default_inputs,
            "image_path": str((dataset_root / self.image_subdir).resolve()),
            "workspace_path": str((workspace_base / self.workspace_subdir).resolve()),
        }
        for field_name, relative_path in self.optional_input_files.items():
            candidate = dataset_root / relative_path
            if include_missing_optional or candidate.exists():
                inputs[field_name] = str(candidate.resolve())
        return {
            "dataset_id": self.id,
            "backend": self.backend,
            "action_id": self.action_id,
            "inputs": inputs,
        }


SPHERESFM_DATASETS = (
    BenchmarkDataset(
        id="spheresfm-campus-parterre",
        backend="spheresfm",
        name="Campus parterre",
        description="SphereSfM ERP panorama dataset recorded around a campus parterre scene.",
        source="https://github.com/json87/SphereSfM#dataset",
        license="not specified by upstream",
        mirrors={
            "google_drive": "https://drive.google.com/file/d/1KB1uk9wEUvEGVnFOwcrw4r_KxUk711eb/view?usp=drive_link",
            "baidu_disk": "https://pan.baidu.com/s/1C259Ygf_lJHd5iT-gmJWGA?pwd=5cqb",
        },
        action_id="spheresfm.reconstructPanoramaFolder",
        tags=("spherical", "erp", "panorama", "campus"),
        default_inputs={
            "camera_params": "1,3520,1760",
            "matching_mode": "spatial",
            "spatial_is_gps": False,
            "spatial_max_distance": 50,
        },
        optional_input_files={"camera_mask_path": "camera_mask.png", "pose_path": "POS.txt"},
    ),
    BenchmarkDataset(
        id="spheresfm-campus-building",
        backend="spheresfm",
        name="Campus building",
        description="SphereSfM ERP panorama dataset recorded around a campus building scene.",
        source="https://github.com/json87/SphereSfM#dataset",
        license="not specified by upstream",
        mirrors={
            "google_drive": "https://drive.google.com/file/d/17HfwXxuU-Q-tzZtlsroGa-ZibepAT0-a/view?usp=drive_link",
            "baidu_disk": "https://pan.baidu.com/s/1r_41WPs4R1wV2ow1rmgabw?pwd=olxy",
        },
        action_id="spheresfm.reconstructPanoramaFolder",
        tags=("spherical", "erp", "panorama", "campus"),
        default_inputs={
            "camera_params": "1,3520,1760",
            "matching_mode": "spatial",
            "spatial_is_gps": False,
            "spatial_max_distance": 50,
        },
        optional_input_files={"camera_mask_path": "camera_mask.png", "pose_path": "POS.txt"},
    ),
    BenchmarkDataset(
        id="spheresfm-urban-street",
        backend="spheresfm",
        name="Urban street",
        description="SphereSfM ERP panorama dataset recorded in an urban street scene.",
        source="https://github.com/json87/SphereSfM#dataset",
        license="not specified by upstream",
        mirrors={
            "google_drive": "https://drive.google.com/file/d/1Tmm7_7153ybi1mhzGUe2L8j_r1ho-UJf/view?usp=drive_link",
            "baidu_disk": "https://pan.baidu.com/s/1YcNiCH7oWSA4EW_x5epAsQ?pwd=sis5",
        },
        action_id="spheresfm.reconstructPanoramaFolder",
        tags=("spherical", "erp", "panorama", "street"),
        default_inputs={
            "camera_params": "1,3520,1760",
            "matching_mode": "spatial",
            "spatial_is_gps": False,
            "spatial_max_distance": 50,
        },
        optional_input_files={"camera_mask_path": "camera_mask.png", "pose_path": "POS.txt"},
    ),
)

COLMAP_DATASETS = (
    BenchmarkDataset(
        id="colmap-south-building",
        backend="colmap",
        name="South Building",
        description=(
            "COLMAP's canonical 128-image outdoor SfM sample. The standard "
            "'hello world' dataset for sparse reconstruction — small enough "
            "to map in a few minutes on a single GPU, large enough to "
            "exercise every pipeline stage."
        ),
        source="https://colmap.github.io/datasets.html",
        license=(
            "Provided by the COLMAP authors for research/demo use; see the "
            "COLMAP datasets page for the upstream terms."
        ),
        mirrors={"upstream": "https://demuc.de/colmap/datasets/south-building.zip"},
        pipeline_recipe="incremental",
        fetch_url="https://demuc.de/colmap/datasets/south-building.zip",
        fetch_format="zip",
        tags=("colmap", "incremental", "outdoor", "sample"),
    ),
    BenchmarkDataset(
        id="colmap-gerrard-hall",
        backend="colmap",
        name="Gerrard Hall",
        description=(
            "COLMAP's compact 100-image outdoor sample. Faster than South "
            "Building for smoke tests and CI runs while exercising the same "
            "incremental pipeline."
        ),
        source="https://colmap.github.io/datasets.html",
        license=(
            "Provided by the COLMAP authors for research/demo use; see the "
            "COLMAP datasets page for the upstream terms."
        ),
        mirrors={"upstream": "https://demuc.de/colmap/datasets/gerrard-hall.zip"},
        pipeline_recipe="incremental",
        fetch_url="https://demuc.de/colmap/datasets/gerrard-hall.zip",
        fetch_format="zip",
        tags=("colmap", "incremental", "outdoor", "sample", "compact"),
    ),
)


DATASETS: dict[str, BenchmarkDataset] = {
    dataset.id: dataset for dataset in (*SPHERESFM_DATASETS, *COLMAP_DATASETS)
}


# ---- Fetcher --------------------------------------------------------
#
# Plain stdlib (urllib + zipfile) so sfmapi-bench stays
# zero-third-party-dep. Caching is content-addressed via ``fetch_sha256``
# when supplied; otherwise the archive is keyed by URL only and the
# operator opts into the (slower) re-download by removing the cache dir.

DatasetFetcher = Callable[[BenchmarkDataset, Path], Path]
"""Callable that takes ``(dataset, archive_path)`` and produces the
downloaded archive at ``archive_path``. Default is HTTP via stdlib; tests
inject a fake to avoid the network."""


class DatasetFetchError(RuntimeError):
    """Raised when a dataset can't be fetched (no URL, hash mismatch, IO)."""


def default_cache_dir() -> Path:
    """Resolve the cache root for fetched datasets.

    Honors ``SFMAPI_BENCH_CACHE`` first; falls back to
    ``$XDG_CACHE_HOME/sfmapi-bench/datasets`` on POSIX-style systems and
    ``%LOCALAPPDATA%\\sfmapi-bench\\datasets`` on Windows.
    """
    override = os.environ.get("SFMAPI_BENCH_CACHE")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "sfmapi-bench" / "datasets"
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "sfmapi-bench" / "datasets"
    return Path.home() / ".cache" / "sfmapi-bench" / "datasets"


def _archive_name(dataset: BenchmarkDataset) -> str:
    if dataset.fetch_url is None:
        raise DatasetFetchError(
            f"dataset {dataset.id!r} has no fetch_url; download manually from "
            f"one of: {sorted(dataset.mirrors.values())}"
        )
    parsed = urlsplit(dataset.fetch_url)
    return Path(parsed.path).name or f"{dataset.id}.archive"


def _http_fetch(dataset: BenchmarkDataset, archive_path: Path) -> Path:
    if dataset.fetch_url is None:
        raise DatasetFetchError(f"dataset {dataset.id!r} has no fetch_url")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = archive_path.with_suffix(archive_path.suffix + ".partial")
    # User-agent set so plain demuc.de doesn't 403 the urllib default.
    req = Request(
        dataset.fetch_url,
        headers={"User-Agent": "sfmapi-bench/0.0 (+https://sfmapi.github.io)"},
    )
    with urlopen(req, timeout=120) as response, tmp_path.open("wb") as out:
        shutil.copyfileobj(response, out, length=1024 * 1024)
    tmp_path.replace(archive_path)
    return archive_path


def _verify_sha256(path: Path, expected: str) -> None:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual.lower() != expected.lower():
        raise DatasetFetchError(
            f"sha256 mismatch for {path.name}: expected {expected}, got {actual}"
        )


def _extract(dataset: BenchmarkDataset, archive_path: Path, extract_dir: Path) -> Path:
    if dataset.fetch_format != "zip":
        raise DatasetFetchError(
            f"dataset {dataset.id!r}: only fetch_format='zip' is supported, got "
            f"{dataset.fetch_format!r}"
        )
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as zf:
        # Reject zip-slip: every entry must resolve inside extract_dir.
        for member in zf.namelist():
            member_path = (extract_dir / member).resolve()
            try:
                member_path.relative_to(extract_dir.resolve())
            except ValueError as exc:
                raise DatasetFetchError(
                    f"refusing to extract path escape: {member!r} in {archive_path.name}"
                ) from exc
        zf.extractall(extract_dir)
    return extract_dir


def fetch_dataset(
    dataset_id: str,
    *,
    cache_dir: Path | None = None,
    fetcher: DatasetFetcher | None = None,
    force: bool = False,
) -> Path:
    """Fetch + extract a benchmark dataset, returning the extracted root.

    Idempotent: the archive is downloaded once, kept under ``cache_dir``,
    and the extraction is skipped if the ``<dataset_id>/`` directory
    already exists. Pass ``force=True`` to re-download and re-extract.

    Raises :class:`DatasetFetchError` for unknown ids, missing
    ``fetch_url``, sha256 mismatch, or zip-slip extraction attempts.
    """
    dataset = DATASETS.get(dataset_id)
    if dataset is None:
        raise DatasetFetchError(f"unknown dataset id: {dataset_id!r}")
    # Resolve the default at call time, not at def-time — so test
    # monkeypatches of ``_http_fetch`` actually take effect.
    if fetcher is None:
        fetcher = _http_fetch
    root = (cache_dir or default_cache_dir()).resolve()
    extract_dir = root / dataset.id
    if extract_dir.exists() and not force:
        return extract_dir

    archive_path = root / "_archives" / _archive_name(dataset)
    if force or not archive_path.is_file():
        if archive_path.exists():
            archive_path.unlink()
        fetcher(dataset, archive_path)
    if dataset.fetch_sha256:
        _verify_sha256(archive_path, dataset.fetch_sha256)

    if extract_dir.exists() and force:
        shutil.rmtree(extract_dir)
    _extract(dataset, archive_path, extract_dir)
    return extract_dir
