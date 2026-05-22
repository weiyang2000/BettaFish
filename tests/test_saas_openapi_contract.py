import re
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from apps.api.main import create_app


WORKSPACE_HEADERS = {"X-Workspace-Id": "workspace_contract"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        db_path=tmp_path / "saas_contract.sqlite3",
        artifact_dir=tmp_path / "artifacts",
        repo_root=Path.cwd(),
        run_workers=False,
    )
    return TestClient(app)


@pytest.fixture()
def worker_client(tmp_path: Path) -> TestClient:
    app = create_app(
        db_path=tmp_path / "saas_workers.sqlite3",
        artifact_dir=tmp_path / "worker_artifacts",
        repo_root=Path.cwd(),
        run_workers=True,
    )
    return TestClient(app)


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    contract_path = Path("docs/openapi/saas-platform.yaml")
    return yaml.safe_load(contract_path.read_text(encoding="utf-8"))


def test_contract_server_matches_fastapi_service_port(contract: dict[str, Any]):
    local_server = contract["servers"][0]["url"]
    assert local_server == "http://localhost:8000/api/v1"


def test_openapi_contract_paths_are_implemented(contract: dict[str, Any], client: TestClient):
    contract_operations = {
        (_normalize_path(path), method)
        for path, path_item in contract["paths"].items()
        for method in path_item
        if method in HTTP_METHODS
    }
    runtime_operations = {
        (_normalize_path(route.path_format.removeprefix("/api/v1")), method.lower())
        for route in client.app.routes
        for method in getattr(route, "methods", set())
        if route.path_format.startswith("/api/v1")
    }

    missing = sorted(contract_operations - runtime_operations)
    assert missing == []


def test_runtime_openapi_exposes_key_contract_operations(client: TestClient):
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    runtime_contract = response.json()
    assert runtime_contract["info"]["title"] == "BettaFish SaaS Platform API"

    paths = runtime_contract["paths"]
    expected_paths = [
        "/api/v1/system/config",
        "/api/v1/report-tasks",
        "/api/v1/report-tasks/{task_id}:cancel",
        "/api/v1/crawler-tasks/{task_id}:retry",
        "/api/v1/platforms/{platform_id}/identity-lists",
    ]
    for path in expected_paths:
        assert path in paths


def test_contract_error_cases_return_structured_errors(client: TestClient):
    missing_header = client.get("/api/v1/health")
    assert missing_header.status_code == 422
    assert missing_header.json()["error"]["code"] == "VALIDATION_ERROR"

    invalid_report = client.post(
        "/api/v1/report-tasks",
        headers=WORKSPACE_HEADERS,
        json={"topic": "", "outputFormats": ["html"]},
    )
    assert invalid_report.status_code == 422
    assert invalid_report.json()["error"]["code"] == "VALIDATION_ERROR"

    missing_task = client.get("/api/v1/crawler-tasks/missing", headers=WORKSPACE_HEADERS)
    assert missing_task.status_code == 404
    assert missing_task.json()["error"]["code"] == "NOT_FOUND"

    report = client.post(
        "/api/v1/report-tasks",
        headers=WORKSPACE_HEADERS,
        json={"topic": "合同测试报告", "outputFormats": ["html"]},
    ).json()["task"]
    premature_result = client.get(
        f"/api/v1/report-tasks/{report['id']}/result",
        headers=WORKSPACE_HEADERS,
    )
    assert premature_result.status_code == 409
    assert premature_result.json()["error"]["code"] == "EXPORT_UNAVAILABLE"

    allow = {"listType": "allow", "userId": "contract-user"}
    block = {"listType": "block", "userId": "contract-user"}
    assert client.post(
        "/api/v1/platforms/wb/identity-lists",
        headers=WORKSPACE_HEADERS,
        json=allow,
    ).status_code == 201
    conflict = client.post(
        "/api/v1/platforms/wb/identity-lists",
        headers=WORKSPACE_HEADERS,
        json=block,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CONFLICT"


def test_crawler_strategy_contract_sample_preserves_platform_id(
    contract: dict[str, Any],
    client: TestClient,
):
    schema = contract["components"]["schemas"]["CrawlerStrategyInput"]
    platform_policy_ref = schema["properties"]["platformPolicies"]["items"]["$ref"]
    assert platform_policy_ref == "#/components/schemas/StrategyPlatformPolicyInput"

    strategy_example = (
        contract["paths"]["/crawler-strategies"]["post"]["requestBody"]["content"]
        ["application/json"]["examples"]["wbStrategy"]["value"]
    )
    assert strategy_example["platformPolicies"][0]["platformId"] == "wb"

    response = client.post(
        "/api/v1/crawler-strategies",
        headers=WORKSPACE_HEADERS,
        json=strategy_example,
    )
    assert response.status_code == 201
    assert response.json()["strategy"]["platformPolicies"][0]["platformId"] == "wb"


def test_stub_workers_complete_report_and_crawler_main_flows(worker_client: TestClient):
    report_response = worker_client.post(
        "/api/v1/report-tasks",
        headers=WORKSPACE_HEADERS,
        json={
            "topic": "养老服务主流程",
            "templateId": "daily-monitoring",
            "outputFormats": ["html", "json"],
        },
    )
    assert report_response.status_code == 202
    report_id = report_response.json()["task"]["id"]

    completed_report = _wait_for_status(
        worker_client,
        f"/api/v1/report-tasks/{report_id}",
        "succeeded",
    )
    assert completed_report["progress"] == 100
    assert {item["format"] for item in completed_report["artifacts"]} == {"html", "json"}
    assert all(item["ready"] for item in completed_report["artifacts"])

    result = worker_client.get(
        f"/api/v1/report-tasks/{report_id}/result",
        headers=WORKSPACE_HEADERS,
    )
    assert result.status_code == 200
    assert "BettaFish SaaS report placeholder" in result.json()["htmlContent"]

    export = worker_client.get(
        f"/api/v1/report-tasks/{report_id}/exports/html",
        headers=WORKSPACE_HEADERS,
    )
    assert export.status_code == 200
    assert "text/html" in export.headers["content-type"]

    crawler_response = worker_client.post(
        "/api/v1/crawler-tasks",
        headers=WORKSPACE_HEADERS,
        json={
            "runMode": "full_workflow",
            "targetDate": "2026-05-22",
            "platforms": ["wb", "xhs"],
        },
    )
    assert crawler_response.status_code == 202
    crawler_id = crawler_response.json()["task"]["id"]

    completed_crawler = _wait_for_status(
        worker_client,
        f"/api/v1/crawler-tasks/{crawler_id}",
        "succeeded",
    )
    assert completed_crawler["progress"] == 100
    assert completed_crawler["stats"]["totalPlatforms"] == 2
    assert completed_crawler["stats"]["totalNotes"] > 0


def _normalize_path(path: str) -> str:
    return re.sub(r"\{[^}]+}", "{}", path)


def _wait_for_status(
    client: TestClient,
    path: str,
    expected_status: str,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_task: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(path, headers=WORKSPACE_HEADERS)
        assert response.status_code == 200
        last_task = response.json()["task"]
        if last_task["status"] == expected_status:
            return last_task
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {expected_status}; last task={last_task}")
