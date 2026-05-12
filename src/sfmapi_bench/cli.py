from __future__ import annotations

import argparse
import asyncio
import atexit
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from .api_surface import ApiSurfaceSpec, check_api_surface
from .datasets import DATASETS
from .geometry import check_sfmapi_cubemap_geometry
from .presets import PRESETS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sfmapi-bench")
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
    local.add_argument("--backend-id", required=True, help="Value to register as SFMAPI_BACKEND.")
    local.add_argument("--preset", choices=sorted(PRESETS), default="generic")
    local.add_argument("--spec", type=Path, help="JSON API-surface spec to merge with the preset.")
    local.add_argument("--expect-action", action="append", default=[])
    local.add_argument("--forbid-action", action="append", default=[])
    local.add_argument("--forbid-prefix", action="append", default=[])
    local.add_argument("--require-input-schemas", action="store_true")
    local.add_argument("--require-output-schemas", action="store_true")
    local.add_argument("--quiet", action="store_true", help="Only print JSON on failure.")
    local.set_defaults(func=_local_api_surface)
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

    from app.adapters.registry import register_backend
    from app.core.capabilities import reset_capabilities_cache
    from app.core.config import reset_settings_for_tests
    from app.db.session import reset_engine_for_tests
    from app.main import create_app
    from fastapi.testclient import TestClient

    os.environ["SFMAPI_BACKEND"] = backend_id
    os.environ.setdefault("SFMAPI_MCP_MODE", "off")
    settings = reset_settings_for_tests(
        ephemeral=True,
        db_url="sqlite+aiosqlite:///file::memory:?cache=shared&uri=true",
        blob_backend="memory",
        queue_backend="inline",
        inline_tasks=True,
    )
    asyncio.run(reset_engine_for_tests(settings))
    reset_capabilities_cache()
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
