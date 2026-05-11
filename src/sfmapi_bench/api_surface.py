from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

JsonFetcher = Callable[[str, float], dict[str, Any]]


@dataclass(frozen=True)
class ApiSurfaceSpec:
    name: str = "custom"
    expected_actions: frozenset[str] = field(default_factory=frozenset)
    forbidden_actions: frozenset[str] = field(default_factory=frozenset)
    forbidden_prefixes: tuple[str, ...] = ()
    require_input_schemas: bool = False
    require_output_schemas: bool = False

    @classmethod
    def from_file(cls, path: str | Path) -> ApiSurfaceSpec:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ApiSurfaceSpec:
        return cls(
            name=str(data.get("name") or "custom"),
            expected_actions=frozenset(str(value) for value in data.get("expected_actions", [])),
            forbidden_actions=frozenset(str(value) for value in data.get("forbidden_actions", [])),
            forbidden_prefixes=tuple(str(value) for value in data.get("forbidden_prefixes", [])),
            require_input_schemas=bool(data.get("require_input_schemas", False)),
            require_output_schemas=bool(data.get("require_output_schemas", False)),
        )

    def merged(
        self,
        *,
        expected_actions: list[str] | tuple[str, ...] = (),
        forbidden_actions: list[str] | tuple[str, ...] = (),
        forbidden_prefixes: list[str] | tuple[str, ...] = (),
        require_input_schemas: bool | None = None,
        require_output_schemas: bool | None = None,
    ) -> ApiSurfaceSpec:
        return ApiSurfaceSpec(
            name=self.name,
            expected_actions=self.expected_actions | frozenset(expected_actions),
            forbidden_actions=self.forbidden_actions | frozenset(forbidden_actions),
            forbidden_prefixes=(*self.forbidden_prefixes, *tuple(forbidden_prefixes)),
            require_input_schemas=(
                self.require_input_schemas
                if require_input_schemas is None
                else require_input_schemas
            ),
            require_output_schemas=(
                self.require_output_schemas
                if require_output_schemas is None
                else require_output_schemas
            ),
        )


@dataclass(frozen=True)
class ApiSurfaceResult:
    base_url: str
    spec_name: str
    elapsed_ms: float
    backend_name: str | None
    backend_version: str | None
    action_count: int
    actions: tuple[str, ...]
    missing_expected_actions: tuple[str, ...]
    exposed_forbidden_actions: tuple[str, ...]
    exposed_forbidden_prefix_actions: tuple[str, ...]
    schema_issues: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not (
            self.missing_expected_actions
            or self.exposed_forbidden_actions
            or self.exposed_forbidden_prefix_actions
            or self.schema_issues
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "base_url": self.base_url,
            "spec_name": self.spec_name,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "backend_name": self.backend_name,
            "backend_version": self.backend_version,
            "action_count": self.action_count,
            "actions": list(self.actions),
            "missing_expected_actions": list(self.missing_expected_actions),
            "exposed_forbidden_actions": list(self.exposed_forbidden_actions),
            "exposed_forbidden_prefix_actions": list(self.exposed_forbidden_prefix_actions),
            "schema_issues": list(self.schema_issues),
        }


def fetch_json(url: str, timeout: float) -> dict[str, Any]:
    request = Request(url, headers={"accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_api_surface(
    base_url: str,
    spec: ApiSurfaceSpec,
    *,
    timeout: float = 30.0,
    fetcher: JsonFetcher = fetch_json,
) -> ApiSurfaceResult:
    base = base_url.rstrip("/") + "/"
    include_schemas = spec.require_input_schemas or spec.require_output_schemas
    query = urlencode({"include_schemas": str(include_schemas).lower(), "page_size": "500"})
    started = time.perf_counter()
    backend = fetcher(urljoin(base, "v1/backend"), timeout)
    payload = fetcher(urljoin(base, f"v1/backend/actions?{query}"), timeout)
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    items = [item for item in payload.get("items", []) if isinstance(item, dict)]
    action_ids = tuple(sorted(str(item["action_id"]) for item in items))
    action_set = set(action_ids)

    forbidden_by_prefix = sorted(
        action_id
        for action_id in action_ids
        if any(action_id.startswith(prefix) for prefix in spec.forbidden_prefixes)
    )
    schema_issues = _schema_issues(items, spec)

    return ApiSurfaceResult(
        base_url=base_url,
        spec_name=spec.name,
        elapsed_ms=elapsed_ms,
        backend_name=str(backend.get("name")) if backend.get("name") is not None else None,
        backend_version=str(backend.get("version")) if backend.get("version") is not None else None,
        action_count=len(action_ids),
        actions=action_ids,
        missing_expected_actions=tuple(sorted(spec.expected_actions - action_set)),
        exposed_forbidden_actions=tuple(sorted(spec.forbidden_actions & action_set)),
        exposed_forbidden_prefix_actions=tuple(forbidden_by_prefix),
        schema_issues=tuple(schema_issues),
    )


def _schema_issues(items: list[dict[str, Any]], spec: ApiSurfaceSpec) -> list[str]:
    issues: list[str] = []
    if not spec.require_input_schemas and not spec.require_output_schemas:
        return issues
    for item in items:
        action_id = str(item.get("action_id", "<unknown>"))
        if spec.require_input_schemas and not item.get("input_schema"):
            issues.append(f"{action_id}: missing input_schema")
        if spec.require_output_schemas and not item.get("output_schema"):
            issues.append(f"{action_id}: missing output_schema")
    return issues
