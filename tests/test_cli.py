from __future__ import annotations

from sfmapi_bench.cli import main
from sfmapi_bench.presets import PRESETS


def test_list_presets(capsys) -> None:
    assert main(["list-presets"]) == 0
    out = capsys.readouterr().out
    assert "generic" in out
    assert "hloc" in out


def test_backend_presets_have_expected_actions() -> None:
    for name in ("colmap", "colmap-legacy", "hloc", "instantsfm", "realityscan", "spheresfm"):
        assert PRESETS[name].expected_actions
