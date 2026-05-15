from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from sfmapi_bench.cli import main
from sfmapi_bench.datasets import (
    DATASETS,
    BenchmarkDataset,
    DatasetFetchError,
    default_cache_dir,
    fetch_dataset,
)


def test_spheresfm_datasets_are_registered() -> None:
    expected = {
        "spheresfm-campus-parterre",
        "spheresfm-campus-building",
        "spheresfm-urban-street",
    }

    assert expected <= set(DATASETS)
    for dataset_id in expected:
        dataset = DATASETS[dataset_id]
        assert dataset.backend == "spheresfm"
        assert dataset.action_id == "spheresfm.reconstructPanoramaFolder"
        assert "google_drive" in dataset.mirrors
        assert "baidu_disk" in dataset.mirrors


def test_dataset_inputs_uses_local_paths(tmp_path: Path, capsys) -> None:
    dataset_root = tmp_path / "campus"
    images = dataset_root / "images"
    images.mkdir(parents=True)
    (dataset_root / "POS.txt").write_text("", encoding="utf-8")

    assert (
        main(
            [
                "dataset-inputs",
                "spheresfm-campus-parterre",
                "--dataset-root",
                str(dataset_root),
                "--workspace-root",
                str(tmp_path / "work"),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["action_id"] == "spheresfm.reconstructPanoramaFolder"
    assert payload["inputs"]["image_path"] == str(images.resolve())
    assert payload["inputs"]["workspace_path"] == str((tmp_path / "work" / "colmap").resolve())
    assert payload["inputs"]["pose_path"] == str((dataset_root / "POS.txt").resolve())
    assert "camera_mask_path" not in payload["inputs"]


def test_list_datasets_can_filter_by_backend(capsys) -> None:
    assert main(["list-datasets", "--backend", "spheresfm"]) == 0
    out = capsys.readouterr().out

    assert "spheresfm-campus-parterre" in out
    assert "spheresfm-urban-street" in out


def test_colmap_samples_are_registered_for_portable_pipeline() -> None:
    """The canonical COLMAP samples ride the portable
    /v1/projects/{pid}/pipelines/{recipe} route, not a backend action,
    so they advertise pipeline_recipe instead of action_id."""
    expected = {"colmap-south-building", "colmap-gerrard-hall"}
    assert expected <= set(DATASETS)
    for dataset_id in expected:
        ds = DATASETS[dataset_id]
        assert ds.backend == "colmap"
        assert ds.action_id is None
        assert ds.pipeline_recipe == "incremental"
        # An auto-fetchable URL is the whole point of moving these here.
        assert ds.fetch_url is not None
        assert ds.fetch_url.startswith("https://")


def _build_fake_archive(dataset_id: str) -> bytes:
    """Build a tiny zip that resembles the COLMAP sample layout
    (``<dataset>/images/*.jpg``) so the extractor + tests have something
    to assert against without hitting the network."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{dataset_id}/images/0001.jpg", b"\xff\xd8\xff\xd9")  # tiny JPEG sentinel
        zf.writestr(f"{dataset_id}/images/0002.jpg", b"\xff\xd8\xff\xd9")
        zf.writestr(f"{dataset_id}/README.txt", b"benchmark sample")
    return buf.getvalue()


def _fake_fetcher(content: bytes):
    def _fetch(_dataset: BenchmarkDataset, archive_path: Path) -> Path:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(content)
        return archive_path

    return _fetch


@pytest.fixture
def fake_dataset() -> BenchmarkDataset:
    """A test-only dataset with NO pinned sha256.

    Fetcher tests exercise extract + idempotency + force semantics using
    a synthetic in-memory zip; pinning a sha256 here would force every
    test to also produce the matching pre-image, which is the wrong
    concern. The dedicated sha256-mismatch test below registers its own
    fixture with a deliberately wrong hash.
    """
    ds = BenchmarkDataset(
        id="test-fetcher-fake",
        backend="test",
        name="fake",
        description="fetcher test fixture",
        source="x",
        license="x",
        mirrors={},
        pipeline_recipe="incremental",
        fetch_url="https://example.invalid/fake.zip",
    )
    DATASETS[ds.id] = ds
    try:
        yield ds
    finally:
        DATASETS.pop(ds.id, None)


def test_fetch_dataset_downloads_and_extracts(
    tmp_path: Path, fake_dataset: BenchmarkDataset
) -> None:
    cache = tmp_path / "cache"
    archive = _build_fake_archive(fake_dataset.id)
    extract_dir = fetch_dataset(fake_dataset.id, cache_dir=cache, fetcher=_fake_fetcher(archive))

    assert extract_dir == cache.resolve() / fake_dataset.id
    assert (extract_dir / fake_dataset.id / "images" / "0001.jpg").is_file()
    # Archive is preserved so a second call can skip the download.
    assert (cache / "_archives" / "fake.zip").is_file()


def test_fetch_dataset_is_idempotent(tmp_path: Path, fake_dataset: BenchmarkDataset) -> None:
    cache = tmp_path / "cache"
    calls = {"n": 0}

    def counting(_dataset: BenchmarkDataset, archive_path: Path) -> Path:
        calls["n"] += 1
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(_build_fake_archive(fake_dataset.id))
        return archive_path

    fetch_dataset(fake_dataset.id, cache_dir=cache, fetcher=counting)
    fetch_dataset(fake_dataset.id, cache_dir=cache, fetcher=counting)

    assert calls["n"] == 1, "second fetch must short-circuit on cached extract dir"


def test_fetch_dataset_force_redownloads(tmp_path: Path, fake_dataset: BenchmarkDataset) -> None:
    cache = tmp_path / "cache"
    calls = {"n": 0}

    def counting(_dataset: BenchmarkDataset, archive_path: Path) -> Path:
        calls["n"] += 1
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(_build_fake_archive(fake_dataset.id))
        return archive_path

    fetch_dataset(fake_dataset.id, cache_dir=cache, fetcher=counting)
    fetch_dataset(fake_dataset.id, cache_dir=cache, fetcher=counting, force=True)

    assert calls["n"] == 2, "force=True must re-fetch + re-extract"


def test_fetch_dataset_rejects_unknown_id(tmp_path: Path) -> None:
    with pytest.raises(DatasetFetchError, match="unknown dataset id"):
        fetch_dataset("not-a-real-dataset", cache_dir=tmp_path)


def test_fetch_dataset_rejects_dataset_without_fetch_url(tmp_path: Path) -> None:
    """The SphereSfM entries lack a direct HTTP URL (Drive/Baidu only);
    fetch_dataset must refuse rather than guess."""
    with pytest.raises(DatasetFetchError, match="no fetch_url"):
        fetch_dataset("spheresfm-campus-parterre", cache_dir=tmp_path)


def test_fetch_dataset_rejects_zip_slip(tmp_path: Path, fake_dataset: BenchmarkDataset) -> None:
    """An archive trying to escape the extract dir must be rejected
    before any file lands on disk."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../escape.txt", b"oops")

    with pytest.raises(DatasetFetchError, match="path escape"):
        fetch_dataset(
            fake_dataset.id,
            cache_dir=tmp_path / "cache",
            fetcher=_fake_fetcher(buf.getvalue()),
        )


def test_fetch_dataset_verifies_sha256(tmp_path: Path) -> None:
    """When fetch_sha256 is set, a corrupted download is rejected."""
    # Borrow the South Building fields but pin a bogus sha to trip the
    # check. Register through DATASETS so fetch_dataset finds it.
    bad = BenchmarkDataset(
        id="colmap-test-sha",
        backend="colmap",
        name="sha test",
        description="",
        source="x",
        license="x",
        mirrors={},
        pipeline_recipe="incremental",
        fetch_url="https://example.invalid/x.zip",
        fetch_sha256="0" * 64,
    )
    DATASETS[bad.id] = bad
    try:
        with pytest.raises(DatasetFetchError, match="sha256 mismatch"):
            fetch_dataset(
                bad.id,
                cache_dir=tmp_path / "cache",
                fetcher=_fake_fetcher(_build_fake_archive("colmap-test-sha")),
            )
    finally:
        DATASETS.pop(bad.id, None)


def test_default_cache_dir_honors_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SFMAPI_BENCH_CACHE", str(tmp_path / "override"))
    assert default_cache_dir() == tmp_path / "override"


def test_cli_fetch_extracts_into_cache(
    monkeypatch, tmp_path: Path, capsys, fake_dataset: BenchmarkDataset
) -> None:
    """The ``fetch`` CLI verb downloads + extracts when the cache is
    empty. Patches the fetcher to avoid the network."""
    import sfmapi_bench.datasets as ds_mod

    archive = _build_fake_archive(fake_dataset.id)
    monkeypatch.setattr(ds_mod, "_http_fetch", _fake_fetcher(archive))
    cache = tmp_path / "cache"

    assert main(["fetch", fake_dataset.id, "--cache-dir", str(cache)]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["dataset_id"] == fake_dataset.id
    assert Path(body["path"]).is_dir()
    assert (Path(body["path"]) / fake_dataset.id / "images" / "0001.jpg").is_file()
