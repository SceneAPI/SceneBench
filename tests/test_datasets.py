from __future__ import annotations

import json
from pathlib import Path

from sfmapi_bench.cli import main
from sfmapi_bench.datasets import DATASETS


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
