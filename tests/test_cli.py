from __future__ import annotations

from scenebench.cli import main
from scenebench.presets import PRESETS


def test_list_presets(capsys) -> None:
    assert main(["list-presets"]) == 0
    out = capsys.readouterr().out
    assert "generic" in out
    assert "hloc" in out


def test_backend_presets_have_expected_actions() -> None:
    for name in ("colmap", "colmap-legacy", "hloc", "instantsfm", "realityscan", "spheresfm"):
        assert PRESETS[name].expected_actions


def test_run_command_has_dry_run_json(capsys) -> None:
    assert main(["run", "--suite", "plugins", "--dry-run", "--json"]) == 0
    out = capsys.readouterr().out
    assert "e2e_plugins.py" in out
    assert '"verdict": "DRY-RUN"' in out


def test_run_command_rejects_python_for_cpp_only_suite(capsys) -> None:
    assert main(["run", "--suite", "vismatch", "--backend", "python", "--dry-run"]) == 2
    err = capsys.readouterr().err
    assert "C++/bridge only" in err
