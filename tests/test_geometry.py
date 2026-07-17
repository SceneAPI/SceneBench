from __future__ import annotations

import json

from sceneapi_bench.cli import main
from sceneapi_bench.geometry import check_sfmapi_cubemap_geometry


def test_sfmapi_cubemap_geometry_is_consistent() -> None:
    result = check_sfmapi_cubemap_geometry()

    assert result.ok
    assert result.convention == "sfmapi-opencv"
    assert result.face_count == 6


def test_geometry_check_cli_json(capsys) -> None:
    assert main(["geometry-check", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["convention"] == "sfmapi-opencv"
    assert payload["face_count"] == 6
