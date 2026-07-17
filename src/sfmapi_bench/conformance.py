from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

SuiteName = Literal[
    "plugins",
    "vismatch",
    "containers",
    "bicycle",
    "hloc",
    "pairs",
    "retrieval",
    "splatting",
    "official-plugins",
    "bridge",
    "bridge-plugin-state",
    "colmap",
    "sdk",
    "mcp",
    "api-parity",
]
BackendName = Literal["python", "cpp", "both"]

ALL_SUITES: tuple[SuiteName, ...] = (
    "plugins",
    "vismatch",
    "containers",
    "bicycle",
    "hloc",
    "pairs",
    "retrieval",
    "splatting",
    "official-plugins",
    "bridge",
    "bridge-plugin-state",
    "colmap",
    "sdk",
    "mcp",
    "api-parity",
)

PROJECTS_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SFMAPI_ROOT = PROJECTS_ROOT / "sfmapi"
DEFAULT_CPP_ROOT = PROJECTS_ROOT / "sfmapi-cpp"
DEFAULT_BICYCLE_IMAGE_DIR = PROJECTS_ROOT / "data" / "bicycle" / "images_2"

_VERDICT_RE = re.compile(r"\[(?:PY-|CPP-)?([A-Z][A-Z0-9_/-]*)\]")
_BLOCKING_STATUSES = frozenset({"SKIP", "SKIP-ENGINE", "DEVICE-UNAVAILABLE"})


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class ConformanceJob:
    suite: SuiteName
    dataset: str
    backend: BackendName
    command: tuple[str, ...]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 3600.0

    def to_json(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "dataset": self.dataset,
            "backend": self.backend,
            "command": list(self.command),
            "cwd": str(self.cwd),
            "env": dict(self.env),
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class ConformanceResult:
    suite: SuiteName
    dataset: str
    backend: BackendName
    ok: bool
    verdict: str
    elapsed_ms: float
    command: tuple[str, ...]
    cwd: str
    returncode: int
    status_counts: dict[str, int]
    stdout_tail: str
    stderr_tail: str

    def to_json(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "dataset": self.dataset,
            "backend": self.backend,
            "ok": self.ok,
            "verdict": self.verdict,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "command": list(self.command),
            "cwd": self.cwd,
            "returncode": self.returncode,
            "status_counts": dict(self.status_counts),
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }


@dataclass(frozen=True)
class ConformanceReport:
    results: tuple[ConformanceResult, ...]

    @property
    def ok(self) -> bool:
        return all(result.ok for result in self.results)

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "results": [result.to_json() for result in self.results],
        }


Runner = Callable[[ConformanceJob], CommandResult]


def default_runner(job: ConformanceJob) -> CommandResult:
    env = dict(os.environ)
    env.update(job.env)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if job.command and Path(job.command[0]).name.lower() in {"uv", "uv.exe"}:
        env.pop("VIRTUAL_ENV", None)
    try:
        proc = subprocess.run(
            list(job.command),
            cwd=str(job.cwd),
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=job.timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _decode_output(exc.stdout)
        stderr = _decode_output(exc.stderr)
        return CommandResult(
            124,
            stdout,
            f"command timed out after {job.timeout_seconds}s\n{stderr}",
        )
    except FileNotFoundError as exc:
        return CommandResult(127, "", str(exc))
    except OSError as exc:
        return CommandResult(126, "", str(exc))
    return CommandResult(proc.returncode, proc.stdout, proc.stderr)


def build_jobs(
    *,
    suites: Iterable[SuiteName],
    dataset: str = "bicycle",
    backend: BackendName = "both",
    sfmapi_root: Path = DEFAULT_SFMAPI_ROOT,
    sfmapi_cpp_root: Path = DEFAULT_CPP_ROOT,
    image_dir: Path | None = None,
    uv_executable: str = "uv",
    local_plugins: bool = False,
    with_editables: Iterable[str] = (),
    models: str = "",
    all_supported_models: bool = False,
    device: str = "cpu",
    max_images: int = 6,
    timeout_seconds: float = 3600.0,
) -> tuple[ConformanceJob, ...]:
    suite_list = tuple(suites)
    resolved_image_dir = _resolve_image_dir(dataset, image_dir)
    editables = _editable_args(
        sfmapi_root=sfmapi_root,
        suites=suite_list,
        local_plugins=local_plugins,
        explicit=tuple(with_editables),
    )
    jobs: list[ConformanceJob] = []
    for suite in suite_list:
        effective_backend = _effective_backend(suite, backend)
        script, args, suite_timeout = _suite_script_args(
            suite=suite,
            cpp_root=sfmapi_cpp_root,
            image_dir=resolved_image_dir,
            models=models,
            all_supported_models=all_supported_models,
            device=device,
            max_images=max_images,
            timeout_seconds=timeout_seconds,
        )
        command = (
            uv_executable,
            "run",
            *_suite_uv_args(suite),
            *editables,
            "python",
            str(script),
            *args,
        )
        env = {"SFMAPI_E2E_IMAGE_DIR": str(resolved_image_dir)}
        if suite in {"plugins", "vismatch"}:
            env["VISMATCH_DEVICE"] = device
        jobs.append(
            ConformanceJob(
                suite=suite,
                dataset=dataset,
                backend=effective_backend,
                command=tuple(str(part) for part in command),
                cwd=sfmapi_root,
                env=env,
                timeout_seconds=suite_timeout,
            )
        )
    return tuple(jobs)


def run_conformance(
    *,
    jobs: Iterable[ConformanceJob],
    runner: Runner = default_runner,
    dry_run: bool = False,
) -> ConformanceReport:
    results: list[ConformanceResult] = []
    for job in jobs:
        started = time.perf_counter()
        if dry_run:
            command_text = " ".join(job.command)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            results.append(
                ConformanceResult(
                    suite=job.suite,
                    dataset=job.dataset,
                    backend=job.backend,
                    ok=True,
                    verdict="DRY-RUN",
                    elapsed_ms=elapsed_ms,
                    command=job.command,
                    cwd=str(job.cwd),
                    returncode=0,
                    status_counts={},
                    stdout_tail=f"DRY-RUN {command_text}\n",
                    stderr_tail="",
                )
            )
            continue
        command_result = runner(job)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        results.append(_result_from_command(job, command_result, elapsed_ms))
    return ConformanceReport(tuple(results))


def report_from_file(path: Path) -> ConformanceReport:
    data = json.loads(path.read_text(encoding="utf-8"))
    return ConformanceReport(
        tuple(
            ConformanceResult(
                suite=str(item["suite"]),  # type: ignore[arg-type]
                dataset=str(item["dataset"]),
                backend=str(item["backend"]),  # type: ignore[arg-type]
                ok=bool(item["ok"]),
                verdict=str(item["verdict"]),
                elapsed_ms=float(item.get("elapsed_ms") or 0),
                command=tuple(str(part) for part in item.get("command", [])),
                cwd=str(item.get("cwd") or ""),
                returncode=int(item.get("returncode") or 0),
                status_counts={
                    str(key): int(value)
                    for key, value in dict(item.get("status_counts") or {}).items()
                },
                stdout_tail=str(item.get("stdout_tail") or ""),
                stderr_tail=str(item.get("stderr_tail") or ""),
            )
            for item in data.get("results", [])
        )
    )


def _resolve_image_dir(dataset: str, image_dir: Path | None) -> Path:
    if image_dir is not None:
        return image_dir
    env_value = os.environ.get("SFMAPI_BENCH_BICYCLE_IMAGE_DIR") or os.environ.get(
        "SFMAPI_E2E_IMAGE_DIR"
    )
    if env_value:
        return Path(env_value)
    if dataset == "bicycle":
        return DEFAULT_BICYCLE_IMAGE_DIR
    raise ValueError(f"dataset {dataset!r} requires --image-dir")


def _effective_backend(suite: SuiteName, requested: BackendName) -> BackendName:
    if suite in {"plugins", "api-parity"}:
        if requested == "both":
            return "both"
        raise ValueError(f"{suite} suite exercises both tiers; use --backend both")
    if suite == "mcp":
        if requested in {"both", "python"}:
            return "python"
        raise ValueError("mcp suite is Python/MCP only; use --backend python or both")
    if requested in {"both", "cpp"}:
        return "cpp"
    raise ValueError(f"{suite} suite is C++/bridge only; use --backend cpp or both")


def _suite_uv_args(suite: SuiteName) -> tuple[str, ...]:
    if suite == "mcp":
        return ("--extra", "mcp")
    return ()


def _editable_args(
    *,
    sfmapi_root: Path,
    suites: tuple[SuiteName, ...],
    local_plugins: bool,
    explicit: tuple[str, ...],
) -> tuple[str, ...]:
    roots = [*explicit]
    if local_plugins:
        parent = sfmapi_root.parent
        roots.extend(
            [
                str(parent / "sfmapi_colmap_cli"),
                str(parent / "sfmapi_colmap"),
                str(parent / "sfmapi_pycolmap"),
                str(parent / "sfmapi_spheresfm"),
                str(parent / "sfmapi_hloc"),
                str(parent / "sfmapi_instantsfm"),
                str(parent / "sfmapi_realityscan"),
            ]
        )
        if "plugins" in suites or "vismatch" in suites:
            roots.append(str(parent / "sfmapi_vismatch") + "[engine]")
        if "splatting" in suites:
            roots.extend(
                [
                    str(parent / "sfmapi_gsplat"),
                    str(parent / "sfmapi_brush"),
                    str(parent / "sfmapi_lfs"),
                    str(parent / "sfmapi_spirulae"),
                    str(parent / "sfmapi_fastergs"),
                ]
            )
    args: list[str] = []
    for root in roots:
        args.extend(("--with-editable", root))
    return tuple(args)


def _suite_script_args(
    *,
    suite: SuiteName,
    cpp_root: Path,
    image_dir: Path,
    models: str,
    all_supported_models: bool,
    device: str,
    max_images: int,
    timeout_seconds: float,
) -> tuple[Path, tuple[str, ...], float]:
    parity = cpp_root / "parity"
    if suite == "plugins":
        return parity / "e2e_plugins.py", (), max(timeout_seconds, 1800.0)
    if suite == "containers":
        return parity / "e2e_container_service.py", (), max(timeout_seconds, 1200.0)
    if suite == "bicycle":
        return parity / "e2e_bicycle_full.py", (), max(timeout_seconds, 10800.0)
    if suite == "hloc":
        return parity / "e2e_hloc_matrix.py", (), max(timeout_seconds, 7200.0)
    if suite == "pairs":
        return parity / "e2e_pair_modes.py", (), max(timeout_seconds, 7200.0)
    if suite == "retrieval":
        return parity / "e2e_retrieval_vocab.py", (), max(timeout_seconds, 7200.0)
    if suite == "splatting":
        return parity / "e2e_splatting_plugins.py", (), max(timeout_seconds, 14400.0)
    if suite == "official-plugins":
        return (
            parity / "e2e_official_plugin_full_runs.py",
            (),
            max(timeout_seconds, 7200.0),
        )
    if suite == "bridge":
        return parity / "e2e_bridge.py", (), max(timeout_seconds, 1200.0)
    if suite == "bridge-plugin-state":
        return parity / "e2e_bridge_plugin_state.py", (), max(timeout_seconds, 300.0)
    if suite == "colmap":
        return parity / "e2e_colmap.py", (), max(timeout_seconds, 1800.0)
    if suite == "sdk":
        return parity / "e2e_sdk.py", (), max(timeout_seconds, 1200.0)
    if suite == "mcp":
        return parity / "e2e_mcp.py", (), max(timeout_seconds, 1200.0)
    if suite == "api-parity":
        return parity / "run_parity.py", (), max(timeout_seconds, 1200.0)
    if suite == "vismatch":
        args = [
            "--image-dir",
            str(image_dir),
            "--max-images",
            str(max_images),
            "--device",
            device,
        ]
        if all_supported_models:
            args.append("--all-supported-models")
        elif models:
            args.extend(("--models", models))
        return parity / "e2e_hloc_vismatch.py", tuple(args), max(timeout_seconds, 7200.0)
    raise ValueError(f"unknown suite: {suite}")


def _result_from_command(
    job: ConformanceJob,
    result: CommandResult,
    elapsed_ms: float,
) -> ConformanceResult:
    combined = f"{result.stdout}\n{result.stderr}"
    status_counts = Counter(_VERDICT_RE.findall(combined))
    verdict = _verdict(job.suite, result.returncode, combined, status_counts)
    ok = result.returncode == 0 and verdict == "OK"
    return ConformanceResult(
        suite=job.suite,
        dataset=job.dataset,
        backend=job.backend,
        ok=ok,
        verdict=verdict,
        elapsed_ms=elapsed_ms,
        command=job.command,
        cwd=str(job.cwd),
        returncode=result.returncode,
        status_counts=dict(sorted(status_counts.items())),
        stdout_tail=_tail(result.stdout),
        stderr_tail=_tail(result.stderr),
    )


def _verdict(
    suite: SuiteName,
    returncode: int,
    output: str,
    status_counts: Counter[str],
) -> str:
    if returncode != 0:
        return "FAIL"
    if _BLOCKING_STATUSES & set(status_counts):
        return "FAIL"
    markers = {
        "plugins": "PLUGINS-E2E OK",
        "vismatch": "RESULT=PASS",
        "containers": "CONTAINER-SERVICE-E2E OK",
        "bicycle": "BICYCLE-FULL OK",
        "hloc": "HLOC-MATRIX OK",
        "pairs": "PAIR-MODES OK",
        "retrieval": "RETRIEVAL-VOCAB OK",
        "splatting": "SPLATTING-PLUGINS-E2E OK",
        "official-plugins": "OFFICIAL-PLUGIN-FULL OK",
        "bridge": "E2E OK",
        "bridge-plugin-state": "BRIDGE-PLUGIN-STATE OK",
        "colmap": "COLMAP-E2E OK",
        "sdk": "SDK-E2E OK",
        "mcp": "MCP-E2E OK",
        "api-parity": "PARITY OK",
    }
    marker = markers[suite]
    return "OK" if marker in output else "UNKNOWN"


def _tail(text: str, *, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _decode_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value
