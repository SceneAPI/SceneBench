from __future__ import annotations

import argparse
import atexit
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from .api_surface import ApiSurfaceSpec, check_api_surface
from .conformance import (
    ALL_SUITES,
    DEFAULT_CPP_ROOT,
    DEFAULT_SFMAPI_ROOT,
    SuiteName,
    build_jobs,
    report_from_file,
    run_conformance,
)
from .datasets import DATASETS, DatasetFetchError, default_cache_dir, fetch_dataset
from .geometry import check_sfmapi_cubemap_geometry
from .presets import PRESETS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sceneapi-bench")
    subcommands = parser.add_subparsers(dest="command", required=True)

    list_presets = subcommands.add_parser("list-presets", help="List built-in presets.")
    list_presets.set_defaults(func=_list_presets)

    list_datasets = subcommands.add_parser("list-datasets", help="List benchmark datasets.")
    list_datasets.add_argument("--backend", help="Only show datasets for this backend.")
    list_datasets.add_argument("--json", action="store_true", help="Print full JSON manifests.")
    list_datasets.set_defaults(func=_list_datasets)

    geometry = subcommands.add_parser(
        "geometry-check",
        help="Check sfmapi portable cubemap geometry conventions.",
    )
    geometry.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    geometry.set_defaults(func=_geometry_check)

    dataset_inputs = subcommands.add_parser(
        "dataset-inputs",
        help="Render backend action inputs for a local benchmark dataset.",
    )
    dataset_inputs.add_argument("dataset_id", choices=sorted(DATASETS))
    dataset_inputs.add_argument(
        "--dataset-root",
        required=True,
        type=Path,
        help="Path to the unpacked dataset root.",
    )
    dataset_inputs.add_argument(
        "--workspace-root",
        type=Path,
        help="Optional root for benchmark output workspaces. Defaults to the dataset root.",
    )
    dataset_inputs.add_argument(
        "--include-missing-optional",
        action="store_true",
        help="Include optional files such as POS.txt even if they are not present locally.",
    )
    dataset_inputs.set_defaults(func=_dataset_inputs)

    fetch = subcommands.add_parser(
        "fetch",
        help="Download and extract a benchmark dataset to the local cache.",
    )
    fetch.add_argument("dataset_id", choices=sorted(DATASETS))
    fetch.add_argument(
        "--cache-dir",
        type=Path,
        help=(
            "Cache root for archives + extracted datasets. "
            f"Default: {default_cache_dir()} (override via SFMAPI_BENCH_CACHE)."
        ),
    )
    fetch.add_argument(
        "--force",
        action="store_true",
        help="Re-download and re-extract even if the dataset is cached.",
    )
    fetch.set_defaults(func=_fetch)

    api = subcommands.add_parser(
        "api-surface",
        help="Check a live sfmapi backend action catalog.",
    )
    api.add_argument("--base-url", default="http://127.0.0.1:8000")
    api.add_argument("--timeout", type=float, default=30.0)
    api.add_argument("--preset", choices=sorted(PRESETS), default="generic")
    api.add_argument("--spec", type=Path, help="JSON API-surface spec to merge with the preset.")
    api.add_argument("--expect-action", action="append", default=[])
    api.add_argument("--forbid-action", action="append", default=[])
    api.add_argument("--forbid-prefix", action="append", default=[])
    api.add_argument("--require-input-schemas", action="store_true")
    api.add_argument("--require-output-schemas", action="store_true")
    api.add_argument("--quiet", action="store_true", help="Only print JSON on failure.")
    api.set_defaults(func=_api_surface)

    local = subcommands.add_parser(
        "local-api-surface",
        help="Check an in-process sfmapi backend action catalog.",
    )
    local.add_argument(
        "--backend", required=True, help="Import path like package.module:ClassName."
    )
    local.add_argument("--backend-id", required=True, help="Value to register as SCENEAPI_BACKEND.")
    local.add_argument("--preset", choices=sorted(PRESETS), default="generic")
    local.add_argument("--spec", type=Path, help="JSON API-surface spec to merge with the preset.")
    local.add_argument("--expect-action", action="append", default=[])
    local.add_argument("--forbid-action", action="append", default=[])
    local.add_argument("--forbid-prefix", action="append", default=[])
    local.add_argument("--require-input-schemas", action="store_true")
    local.add_argument("--require-output-schemas", action="store_true")
    local.add_argument("--quiet", action="store_true", help="Only print JSON on failure.")
    local.set_defaults(func=_local_api_surface)

    run = subcommands.add_parser(
        "run",
        help="Run sfmapi conformance/E2E benchmark suites through UV.",
    )
    run.add_argument(
        "--suite",
        action="append",
        choices=(*ALL_SUITES, "all"),
        required=True,
        help="Suite to run. Repeat for multiple suites, or pass all.",
    )
    run.add_argument("--dataset", default="bicycle", help="Dataset label for the report.")
    run.add_argument(
        "--backend",
        choices=("python", "cpp", "both"),
        default="both",
        help="Backend tier label. The plugins suite exercises both tiers.",
    )
    run.add_argument("--sfmapi-root", type=Path, default=DEFAULT_SFMAPI_ROOT)
    run.add_argument("--sceneapi-cpp-root", type=Path, default=DEFAULT_CPP_ROOT)
    run.add_argument("--image-dir", type=Path, help="Image directory for bicycle-backed suites.")
    run.add_argument("--uv", default="uv", help="UV executable to use.")
    run.add_argument(
        "--local-plugins",
        action="store_true",
        help="Add sibling plugin repos with --with-editable, including sfmapi_vismatch[engine].",
    )
    run.add_argument(
        "--with-editable",
        action="append",
        default=[],
        help="Additional editable package passed through to uv run.",
    )
    run.add_argument("--models", default="", help="Comma-separated Vismatch models.")
    run.add_argument(
        "--all-supported-models",
        action="store_true",
        help="Run every supported Vismatch model in the vismatch suite.",
    )
    run.add_argument("--device", default="cpu", help="Device for model-backed suites.")
    run.add_argument("--max-images", type=int, default=6, help="Image subset size.")
    run.add_argument("--timeout", type=float, default=3600.0, help="Minimum per-suite timeout.")
    run.add_argument(
        "--dry-run", action="store_true", help="Build report without executing suites."
    )
    run.add_argument("--json", action="store_true", help="Print JSON report.")
    run.add_argument("--output", type=Path, help="Write JSON report to this path.")
    run.set_defaults(func=_run_conformance)

    report = subcommands.add_parser("report", help="Read a sceneapi-bench JSON report.")
    report.add_argument("path", type=Path)
    report.add_argument("--format", choices=("text", "json"), default="text")
    report.set_defaults(func=_report)
    return parser


def _list_presets(args: argparse.Namespace) -> int:
    for name in sorted(PRESETS):
        print(name)
    return 0


def _list_datasets(args: argparse.Namespace) -> int:
    datasets = sorted(
        [
            dataset
            for dataset in DATASETS.values()
            if args.backend is None or dataset.backend == args.backend
        ],
        key=lambda item: item.id,
    )
    if args.json:
        print(json.dumps([dataset.to_json() for dataset in datasets], indent=2, sort_keys=True))
    else:
        for dataset in datasets:
            print(f"{dataset.id}\t{dataset.backend}\t{dataset.name}")
    return 0


def _dataset_inputs(args: argparse.Namespace) -> int:
    dataset = DATASETS[args.dataset_id]
    payload = dataset.action_payload(
        args.dataset_root,
        workspace_root=args.workspace_root,
        include_missing_optional=args.include_missing_optional,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _fetch(args: argparse.Namespace) -> int:
    try:
        extract_dir = fetch_dataset(args.dataset_id, cache_dir=args.cache_dir, force=args.force)
    except DatasetFetchError as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"dataset_id": args.dataset_id, "path": str(extract_dir)}, indent=2))
    return 0


def _geometry_check(args: argparse.Namespace) -> int:
    result = check_sfmapi_cubemap_geometry()
    if args.json:
        print(json.dumps(result.to_json(), indent=2, sort_keys=True))
    elif result.ok:
        print(f"ok\t{result.convention}\t{result.face_count} faces")
    else:
        for error in result.errors:
            print(error)
    return 0 if result.ok else 1


def _api_surface(args: argparse.Namespace) -> int:
    spec = _spec_from_args(args)
    result = check_api_surface(args.base_url, spec, timeout=args.timeout)
    if not args.quiet or not result.ok:
        print(json.dumps(result.to_json(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


def _local_api_surface(args: argparse.Namespace) -> int:
    spec = _spec_from_args(args)
    result = check_api_surface(
        "http://testserver",
        spec,
        fetcher=_local_fetcher(args.backend, args.backend_id),
    )
    if not args.quiet or not result.ok:
        print(json.dumps(result.to_json(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


def _run_conformance(args: argparse.Namespace) -> int:
    suites = _expand_suites(args.suite)
    try:
        jobs = build_jobs(
            suites=suites,
            dataset=args.dataset,
            backend=args.backend,
            sfmapi_root=args.sfmapi_root,
            sceneapi_cpp_root=args.sceneapi_cpp_root,
            image_dir=args.image_dir,
            uv_executable=args.uv,
            local_plugins=args.local_plugins,
            with_editables=args.with_editable,
            models=args.models,
            all_supported_models=args.all_supported_models,
            device=args.device,
            max_images=args.max_images,
            timeout_seconds=args.timeout,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    bench_report = run_conformance(jobs=jobs, dry_run=args.dry_run)
    payload = bench_report.to_json()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_report_summary(payload)
    return 0 if bench_report.ok else 1


def _report(args: argparse.Namespace) -> int:
    bench_report = report_from_file(args.path)
    payload = bench_report.to_json()
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _print_report_summary(payload)
    return 0 if bench_report.ok else 1


def _expand_suites(raw: list[str]) -> tuple[SuiteName, ...]:
    if "all" in raw:
        return ALL_SUITES
    return tuple(raw)  # type: ignore[return-value]


def _print_report_summary(payload: dict[str, Any]) -> None:
    print(f"ok={payload.get('ok')}")
    for item in payload.get("results", []):
        counts = item.get("status_counts") or {}
        count_text = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        print(
            f"{item.get('suite')}\t{item.get('verdict')}\t"
            f"returncode={item.get('returncode')}\t{count_text}"
        )


def _spec_from_args(args: argparse.Namespace) -> ApiSurfaceSpec:
    spec = PRESETS[args.preset]
    if args.spec:
        spec = _merge_specs(spec, ApiSurfaceSpec.from_file(args.spec))
    return spec.merged(
        expected_actions=args.expect_action,
        forbidden_actions=args.forbid_action,
        forbidden_prefixes=args.forbid_prefix,
        require_input_schemas=True if args.require_input_schemas else None,
        require_output_schemas=True if args.require_output_schemas else None,
    )


def _local_fetcher(backend_import: str, backend_id: str):
    try:
        module_name, attr_name = backend_import.split(":", 1)
    except ValueError as exc:
        raise SystemExit("--backend must be in module:attribute form") from exc

    module = importlib.import_module(module_name)
    backend_factory = getattr(module, attr_name)

    from fastapi.testclient import TestClient
    from sceneapi.backends import register_backend
    from sceneapi.runtime import create_app
    from sceneapi.testing import reset_runtime_for_tests_sync

    os.environ["SCENEAPI_BACKEND"] = backend_id
    os.environ.setdefault("SCENEAPI_MCP_MODE", "off")
    reset_runtime_for_tests_sync(
        ephemeral=True,
        db_url="sqlite+aiosqlite:///file::memory:?cache=shared&uri=true",
        blob_backend="memory",
        queue_backend="inline",
        inline_tasks=True,
    )
    # Alias the backend under its own id as a provider so any stage spec
    # carrying ``provider=backend_id`` in a recorded fixture routes
    # correctly through the new provider-aware worker resolver.
    try:
        register_backend(backend_id, backend_factory, providers=[backend_id])
    except TypeError:
        # Older sfmapi without the ``providers=`` kwarg.
        register_backend(backend_id, backend_factory)
    client = TestClient(create_app())
    client.__enter__()
    atexit.register(client.__exit__, None, None, None)

    def fetch(url: str, timeout: float) -> dict[str, Any]:
        path = "/" + url.split("://", 1)[-1].split("/", 1)[-1]
        response = client.get(path)
        response.raise_for_status()
        return response.json()

    return fetch


def _merge_specs(base: ApiSurfaceSpec, override: ApiSurfaceSpec) -> ApiSurfaceSpec:
    return ApiSurfaceSpec(
        name=override.name if override.name != "custom" else base.name,
        expected_actions=base.expected_actions | override.expected_actions,
        forbidden_actions=base.forbidden_actions | override.forbidden_actions,
        forbidden_prefixes=(*base.forbidden_prefixes, *override.forbidden_prefixes),
        require_input_schemas=base.require_input_schemas or override.require_input_schemas,
        require_output_schemas=base.require_output_schemas or override.require_output_schemas,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
