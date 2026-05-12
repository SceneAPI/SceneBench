from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BenchmarkDataset:
    id: str
    backend: str
    name: str
    description: str
    source: str
    mirrors: dict[str, str]
    action_id: str
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
            "mirrors": dict(self.mirrors),
            "action_id": self.action_id,
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

DATASETS: dict[str, BenchmarkDataset] = {dataset.id: dataset for dataset in SPHERESFM_DATASETS}
