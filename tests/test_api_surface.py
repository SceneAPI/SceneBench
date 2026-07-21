from __future__ import annotations

from scenebench.api_surface import ApiSurfaceSpec, check_api_surface


def _fetcher(actions: list[dict], backend: dict | None = None):
    def fetch(url: str, timeout: float):
        if url.endswith("/v1/backend"):
            return backend or {"name": "test", "version": "1.0"}
        if "/v1/backend/actions" in url:
            return {"items": actions}
        raise AssertionError(url)

    return fetch


def test_check_api_surface_accepts_expected_actions() -> None:
    result = check_api_surface(
        "http://testserver",
        ApiSurfaceSpec(name="demo", expected_actions=frozenset({"demo.extract"})),
        fetcher=_fetcher([{"action_id": "demo.extract", "input_schema": {"type": "object"}}]),
    )

    assert result.ok
    assert result.backend_name == "test"
    assert result.actions == ("demo.extract",)


def test_check_api_surface_reports_missing_and_forbidden_actions() -> None:
    result = check_api_surface(
        "http://testserver",
        ApiSurfaceSpec(
            name="demo",
            expected_actions=frozenset({"demo.extract", "demo.map"}),
            forbidden_actions=frozenset({"demo.benchmark"}),
            forbidden_prefixes=("demo.dev.",),
        ),
        fetcher=_fetcher(
            [
                {"action_id": "demo.extract"},
                {"action_id": "demo.benchmark"},
                {"action_id": "demo.dev.debug"},
            ]
        ),
    )

    assert not result.ok
    assert result.missing_expected_actions == ("demo.map",)
    assert result.exposed_forbidden_actions == ("demo.benchmark",)
    assert result.exposed_forbidden_prefix_actions == ("demo.dev.debug",)


def test_check_api_surface_can_require_schemas() -> None:
    result = check_api_surface(
        "http://testserver",
        ApiSurfaceSpec(name="demo", require_input_schemas=True, require_output_schemas=True),
        fetcher=_fetcher([{"action_id": "demo.extract", "input_schema": {"type": "object"}}]),
    )

    assert not result.ok
    assert result.schema_issues == ("demo.extract: missing output_schema",)
