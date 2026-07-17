from __future__ import annotations

import sys
from pathlib import Path

from sceneapi_bench.conformance import (
    ALL_SUITES,
    CommandResult,
    ConformanceJob,
    build_jobs,
    default_runner,
    run_conformance,
)


def test_build_jobs_uses_uv_and_plugin_suite() -> None:
    jobs = build_jobs(
        suites=("plugins",),
        sfmapi_root=Path("C:/repo/sfmapi"),
        sfmapi_cpp_root=Path("C:/repo/sfmapi-cpp"),
        image_dir=Path("C:/data/bicycle/images_2"),
        local_plugins=True,
    )

    assert len(jobs) == 1
    job = jobs[0]
    assert job.command[:2] == ("uv", "run")
    assert "e2e_plugins.py" in job.command[-1]
    assert "--with-editable" in job.command
    assert any("sfmapi_vismatch[engine]" in part for part in job.command)
    assert job.env["SFMAPI_E2E_IMAGE_DIR"] == "C:\\data\\bicycle\\images_2"


def test_run_conformance_parses_plugin_verdict() -> None:
    jobs = build_jobs(
        suites=("plugins",),
        sfmapi_root=Path("C:/repo/sfmapi"),
        sfmapi_cpp_root=Path("C:/repo/sfmapi-cpp"),
        image_dir=Path("C:/data/bicycle/images_2"),
    )

    def runner(_job):
        return CommandResult(
            0,
            "[PY-OK] colmap_cli\n[CPP-OK] colmap_cli\n[PY-N/A] native\n"
            "PLUGINS-E2E OK -- python OK 8/9\n",
            "",
        )

    report = run_conformance(jobs=jobs, runner=runner)

    assert report.ok
    result = report.results[0]
    assert result.verdict == "OK"
    assert result.status_counts["OK"] == 2
    assert result.status_counts["N/A"] == 1


def test_run_conformance_marks_missing_success_marker_unknown() -> None:
    jobs = build_jobs(
        suites=("containers",),
        sfmapi_root=Path("C:/repo/sfmapi"),
        sfmapi_cpp_root=Path("C:/repo/sfmapi-cpp"),
        image_dir=Path("C:/data/bicycle/images_2"),
    )

    report = run_conformance(jobs=jobs, runner=lambda _job: CommandResult(0, "done", ""))

    assert not report.ok
    assert report.results[0].verdict == "UNKNOWN"


def test_build_jobs_labels_cpp_only_suites_as_cpp() -> None:
    jobs = build_jobs(
        suites=("vismatch",),
        sfmapi_root=Path("C:/repo/sfmapi"),
        sfmapi_cpp_root=Path("C:/repo/sfmapi-cpp"),
        image_dir=Path("C:/data/bicycle/images_2"),
    )

    assert jobs[0].backend == "cpp"


def test_build_jobs_all_suites_have_scripts() -> None:
    jobs = build_jobs(
        suites=ALL_SUITES,
        sfmapi_root=Path("C:/repo/sfmapi"),
        sfmapi_cpp_root=Path("C:/repo/sfmapi-cpp"),
        image_dir=Path("C:/data/bicycle/images_2"),
    )

    commands = "\n".join(" ".join(job.command) for job in jobs)
    assert len(jobs) == len(ALL_SUITES)
    assert "e2e_pair_modes.py" in commands
    assert "e2e_retrieval_vocab.py" in commands
    assert "e2e_splatting_plugins.py" in commands
    assert "e2e_official_plugin_full_runs.py" in commands
    assert "e2e_mcp.py" in commands
    assert "run_parity.py" in commands
    assert {job.suite: job.backend for job in jobs}["api-parity"] == "both"
    assert {job.suite: job.backend for job in jobs}["mcp"] == "python"


def test_splatting_suite_adds_all_local_plugin_repos() -> None:
    jobs = build_jobs(
        suites=("splatting",),
        sfmapi_root=Path("C:/repo/sfmapi"),
        sfmapi_cpp_root=Path("C:/repo/sfmapi-cpp"),
        image_dir=Path("C:/data/bicycle/images_2"),
        local_plugins=True,
    )

    command = jobs[0].command

    assert "e2e_splatting_plugins.py" in command[-1]
    for name in (
        "sfmapi_gsplat",
        "sfmapi_brush",
        "sfmapi_lfs",
        "sfmapi_spirulae",
        "sfmapi_fastergs",
    ):
        assert any(name in part for part in command)


def test_run_conformance_fails_skip_statuses() -> None:
    jobs = build_jobs(
        suites=("hloc",),
        sfmapi_root=Path("C:/repo/sfmapi"),
        sfmapi_cpp_root=Path("C:/repo/sfmapi-cpp"),
        image_dir=Path("C:/data/bicycle/images_2"),
    )

    report = run_conformance(
        jobs=jobs,
        runner=lambda _job: CommandResult(0, "[SKIP-ENGINE] missing torch\nHLOC-MATRIX OK", ""),
    )

    assert not report.ok
    assert report.results[0].verdict == "FAIL"
    assert report.results[0].status_counts["SKIP-ENGINE"] == 1


def test_mcp_suite_uses_mcp_extra() -> None:
    jobs = build_jobs(
        suites=("mcp",),
        sfmapi_root=Path("C:/repo/sfmapi"),
        sfmapi_cpp_root=Path("C:/repo/sfmapi-cpp"),
        image_dir=Path("C:/data/bicycle/images_2"),
    )

    assert jobs[0].backend == "python"
    assert jobs[0].command[2:4] == ("--extra", "mcp")


def test_default_runner_reports_missing_executable(tmp_path) -> None:
    job = ConformanceJob(
        suite="plugins",
        dataset="bicycle",
        backend="both",
        command=("sfmapi-bench-missing-executable",),
        cwd=tmp_path,
    )

    result = default_runner(job)

    assert result.returncode == 127
    assert result.stderr


def test_default_runner_reports_timeout(tmp_path) -> None:
    job = ConformanceJob(
        suite="plugins",
        dataset="bicycle",
        backend="both",
        command=(sys.executable, "-c", "import time; time.sleep(5)"),
        cwd=tmp_path,
        timeout_seconds=0.01,
    )

    result = default_runner(job)

    assert result.returncode == 124
    assert "timed out" in result.stderr
