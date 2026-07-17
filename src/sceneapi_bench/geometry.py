from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

Vec3 = tuple[float, float, float]

CUBEMAP_FACE_AXES: dict[str, dict[str, Vec3]] = {
    "front": {"forward": (0, 0, 1), "right": (1, 0, 0), "down": (0, 1, 0)},
    "right": {"forward": (1, 0, 0), "right": (0, 0, -1), "down": (0, 1, 0)},
    "back": {"forward": (0, 0, -1), "right": (-1, 0, 0), "down": (0, 1, 0)},
    "left": {"forward": (-1, 0, 0), "right": (0, 0, 1), "down": (0, 1, 0)},
    "up": {"forward": (0, -1, 0), "right": (1, 0, 0), "down": (0, 0, 1)},
    "down": {"forward": (0, 1, 0), "right": (1, 0, 0), "down": (0, 0, -1)},
}

EXPECTED_CENTER_UV = {
    "front": (0.5, 0.5),
    "right": (0.75, 0.5),
    "back": (1.0, 0.5),
    "left": (0.25, 0.5),
    "up": (0.5, 0.0),
    "down": (0.5, 1.0),
}


@dataclass(frozen=True)
class GeometryCheckResult:
    convention: str
    face_count: int
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "convention": self.convention,
            "face_count": self.face_count,
            "errors": list(self.errors),
        }


def check_sfmapi_cubemap_geometry(*, tolerance: float = 1e-6) -> GeometryCheckResult:
    errors: list[str] = []
    for face, axes in CUBEMAP_FACE_AXES.items():
        forward = axes["forward"]
        right = axes["right"]
        down = axes["down"]
        if abs(_norm(forward) - 1.0) > tolerance:
            errors.append(f"{face}: forward axis is not unit length")
        if abs(_norm(right) - 1.0) > tolerance:
            errors.append(f"{face}: right axis is not unit length")
        if abs(_norm(down) - 1.0) > tolerance:
            errors.append(f"{face}: down axis is not unit length")
        if abs(_dot(forward, right)) > tolerance:
            errors.append(f"{face}: forward and right axes are not orthogonal")
        if abs(_dot(forward, down)) > tolerance:
            errors.append(f"{face}: forward and down axes are not orthogonal")
        if abs(_dot(right, down)) > tolerance:
            errors.append(f"{face}: right and down axes are not orthogonal")

        u, v = _equirectangular_uv(forward)
        expected_u, expected_v = EXPECTED_CENTER_UV[face]
        if min(abs(u - expected_u), abs(u - expected_u + 1.0), abs(u - expected_u - 1.0)) > 1e-6:
            errors.append(f"{face}: center longitude maps to u={u:.6f}, expected {expected_u:.6f}")
        if abs(v - expected_v) > 1e-6:
            errors.append(f"{face}: center latitude maps to v={v:.6f}, expected {expected_v:.6f}")

    return GeometryCheckResult(
        convention="sfmapi-opencv",
        face_count=len(CUBEMAP_FACE_AXES),
        errors=tuple(errors),
    )


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(v: Vec3) -> float:
    return math.sqrt(_dot(v, v))


def _equirectangular_uv(ray: Vec3) -> tuple[float, float]:
    x, y, z = ray
    length = _norm(ray)
    x, y, z = x / length, y / length, z / length
    lon = math.atan2(x, z)
    lat_down = math.asin(max(-1.0, min(1.0, y)))
    u = lon / (2.0 * math.pi) + 0.5
    v = lat_down / math.pi + 0.5
    return u % 1.0, v


__all__ = ["CUBEMAP_FACE_AXES", "GeometryCheckResult", "check_sfmapi_cubemap_geometry"]
