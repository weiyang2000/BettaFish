import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app


WORKSPACE_HEADERS = {"X-Workspace-Id": "workspace_test"}


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        db_path=tmp_path / "saas_api.sqlite3",
        artifact_dir=tmp_path / "artifacts",
        repo_root=Path.cwd(),
        run_workers=False,
    )
    return TestClient(app)


def test_system_components_do_not_expose_legacy_ui_ports(client: TestClient):
    response = client.get("/api/v1/system/components", headers=WORKSPACE_HEADERS)
    assert response.status_code == 200

    components = {component["id"]: component for component in response.json()["components"]}
    for component_id in ("query", "media", "insight"):
        assert "port" not in components[component_id]


def test_system_config_masks_secrets_and_ignores_mask_placeholder(client: TestClient):
    response = client.patch(
        "/api/v1/system/config",
        headers=WORKSPACE_HEADERS,
        json={
            "values": {
                "REPORT_ENGINE_API_KEY": "sk-real-secret",
                "SEARCH_TOOL_TYPE": "BochaAPI",
            }
        },
    )
    assert response.status_code == 200

    fields = _config_fields(client)
    assert fields["REPORT_ENGINE_API_KEY"]["value"] == "********"
    assert fields["REPORT_ENGINE_API_KEY"]["sensitive"] is True
    assert fields["SEARCH_TOOL_TYPE"]["value"] == "BochaAPI"

    response = client.patch(
        "/api/v1/system/config",
        headers=WORKSPACE_HEADERS,
        json={"values": {"REPORT_ENGINE_API_KEY": "********"}},
    )
    assert response.status_code == 200
    assert _config_fields(client)["REPORT_ENGINE_API_KEY"]["value"] == "********"


def test_identity_duplicate_block_conflict_and_delete(client: TestClient):
    allow_response = client.post(
        "/api/v1/platforms/wb/identity-lists",
        headers=WORKSPACE_HEADERS,
        json={"userId": "user-001", "label": "spam"},
    )
    assert allow_response.status_code == 201
    rule_id = allow_response.json()["rule"]["id"]
    assert allow_response.json()["rule"]["listType"] == "block"

    block_response = client.post(
        "/api/v1/platforms/wb/identity-lists",
        headers=WORKSPACE_HEADERS,
        json={"listType": "block", "userId": "user-001"},
    )
    assert block_response.status_code == 409
    assert block_response.json()["error"]["code"] == "CONFLICT"

    list_response = client.get(
        "/api/v1/platforms/wb/identity-lists?listType=block",
        headers=WORKSPACE_HEADERS,
    )
    assert list_response.status_code == 200
    assert [rule["userId"] for rule in list_response.json()["rules"]] == ["user-001"]

    delete_response = client.delete(
        f"/api/v1/platforms/wb/identity-lists/{rule_id}",
        headers=WORKSPACE_HEADERS,
    )
    assert delete_response.status_code == 204


def test_identity_allow_rules_remain_listable_but_are_not_crawler_filters(
    client: TestClient,
):
    allow_response = client.post(
        "/api/v1/platforms/xhs/identity-lists",
        headers=WORKSPACE_HEADERS,
        json={"listType": "allow", "userId": "same-user", "label": "legacy allow"},
    )
    assert allow_response.status_code == 201
    assert allow_response.json()["rule"]["listType"] == "allow"

    block_response = client.post(
        "/api/v1/platforms/xhs/identity-lists",
        headers=WORKSPACE_HEADERS,
        json={"listType": "block", "userId": "same-user", "label": "active block"},
    )
    assert block_response.status_code == 201
    assert block_response.json()["rule"]["listType"] == "block"

    list_allow = client.get(
        "/api/v1/platforms/xhs/identity-lists?listType=allow",
        headers=WORKSPACE_HEADERS,
    )
    assert list_allow.status_code == 200
    assert [rule["userId"] for rule in list_allow.json()["rules"]] == ["same-user"]

    list_block = client.get(
        "/api/v1/platforms/xhs/identity-lists?listType=block",
        headers=WORKSPACE_HEADERS,
    )
    assert list_block.status_code == 200
    assert [rule["userId"] for rule in list_block.json()["rules"]] == ["same-user"]

    active_rules = client.app.state.platform_service.list_active_block_rules(
        "workspace_test",
        ["xhs", "wb"],
    )
    assert {
        platform: [rule["userId"] for rule in rules]
        for platform, rules in active_rules.items()
    } == {"xhs": ["same-user"], "wb": []}


def test_platform_policy_update_round_trip(client: TestClient):
    payload = {
        "enabled": True,
        "crawlDepth": 4,
        "maxKeywords": 20,
        "maxNotesPerKeyword": 10,
        "maxCommentsPerNote": 50,
        "keywords": ["养老服务", "养老服务", "医保"],
        "keywordSource": "manual",
        "frequency": {"mode": "daily", "timezone": "Asia/Shanghai"},
        "loginType": "qrcode",
        "headless": True,
    }
    response = client.put(
        "/api/v1/platforms/xhs/policy",
        headers=WORKSPACE_HEADERS,
        json=payload,
    )
    assert response.status_code == 200
    policy = response.json()["policy"]
    assert policy["platformId"] == "xhs"
    assert policy["crawlDepth"] == 4
    assert policy["keywords"] == ["养老服务", "医保"]


def test_crawler_accounts_list_filters_without_sensitive_credentials(client: TestClient):
    upsert = client.put(
        "/api/v1/crawler-accounts/wb_1088",
        headers=WORKSPACE_HEADERS,
        json={
            "platformId": "wb",
            "username": "bettafish_ops",
            "displayName": "BettaFish 运营号",
            "status": "active",
            "loginType": "qrcode",
            "lastCheckedAt": "2026-05-22T08:30:00Z",
            "details": {
                "message": "账号可用于搜索和评论采集。",
                "accessToken": "not-allowed",
                "nested": {"cookie": "not-allowed", "safe": "kept"},
            },
        },
    )
    assert upsert.status_code == 200

    response = client.get("/api/v1/crawler-accounts?platform=wb", headers=WORKSPACE_HEADERS)
    assert response.status_code == 200

    accounts = response.json()["accounts"]
    assert accounts
    assert {account["platformId"] for account in accounts} == {"wb"}
    account = accounts[0]
    assert account["status"] == "active"
    assert account["accountId"] == "wb_1088"
    assert account["displayName"] == "BettaFish 运营号"
    assert "lastCheckedAt" in account
    assert account["details"]["nested"] == {"safe": "kept"}

    serialized = json.dumps(account, ensure_ascii=False)
    for forbidden_text in ("password", "token", "secret", "cookie", "not-allowed"):
        assert forbidden_text not in serialized.lower()


def test_crawler_accounts_are_workspace_scoped_and_page_sized(client: TestClient):
    workspace_a = {"X-Workspace-Id": "workspace_accounts_a"}
    workspace_b = {"X-Workspace-Id": "workspace_accounts_b"}

    response = client.put(
        "/api/v1/crawler-accounts/wb_public_2001",
        headers=workspace_a,
        json={"platformId": "wb", "displayName": "微博采集号", "status": "active"},
    )
    assert response.status_code == 200

    list_response = client.get(
        "/api/v1/crawler-accounts?platform=wb&status=active&pageSize=1",
        headers=workspace_a,
    )
    assert list_response.status_code == 200
    assert [item["accountId"] for item in list_response.json()["accounts"]] == [
        "wb_public_2001"
    ]

    other_workspace = client.get("/api/v1/crawler-accounts", headers=workspace_b)
    assert other_workspace.status_code == 200
    assert other_workspace.json()["accounts"] == []


def test_crawler_account_rejects_top_level_secret_fields(client: TestClient):
    response = client.put(
        "/api/v1/crawler-accounts/wb_secret",
        headers=WORKSPACE_HEADERS,
        json={"platformId": "wb", "status": "active", "token": "not-allowed"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_crawler_strategy_platform_policy_round_trip_and_invalid_platform(client: TestClient):
    payload = {
        "name": "微博每日采集",
        "runMode": "deep_sentiment",
        "platformPolicies": [_strategy_policy("wb")],
    }
    response = client.post(
        "/api/v1/crawler-strategies",
        headers=WORKSPACE_HEADERS,
        json=payload,
    )
    assert response.status_code == 201
    strategy = response.json()["strategy"]
    assert strategy["platformPolicies"][0]["platformId"] == "wb"

    list_response = client.get("/api/v1/crawler-strategies", headers=WORKSPACE_HEADERS)
    assert list_response.status_code == 200
    assert list_response.json()["strategies"][0]["platformPolicies"][0]["platformId"] == "wb"

    invalid_payload = {
        **payload,
        "name": "非法平台策略",
        "platformPolicies": [_strategy_policy("manual")],
    }
    invalid_response = client.post(
        "/api/v1/crawler-strategies",
        headers=WORKSPACE_HEADERS,
        json=invalid_payload,
    )
    assert invalid_response.status_code == 422
    assert invalid_response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_report_task_basic_lifecycle_and_events(client: TestClient):
    create_response = client.post(
        "/api/v1/report-tasks",
        headers=WORKSPACE_HEADERS,
        json={
            "topic": "养老服务发展趋势",
            "templateId": "daily-monitoring",
            "outputFormats": ["html", "md"],
        },
    )
    assert create_response.status_code == 202
    task = create_response.json()["task"]
    assert task["status"] == "queued"
    assert create_response.json()["eventStreamUrl"].endswith(f"{task['id']}/events")

    get_response = client.get(f"/api/v1/report-tasks/{task['id']}", headers=WORKSPACE_HEADERS)
    assert get_response.status_code == 200
    assert get_response.json()["task"]["topic"] == "养老服务发展趋势"

    event_response = client.get(
        f"/api/v1/report-tasks/{task['id']}/events",
        headers=WORKSPACE_HEADERS,
    )
    assert event_response.status_code == 200
    assert "event: status" in event_response.text

    cancel_response = client.post(
        f"/api/v1/report-tasks/{task['id']}:cancel",
        headers=WORKSPACE_HEADERS,
    )
    assert cancel_response.status_code == 202
    assert cancel_response.json()["task"]["status"] == "cancelled"

    second_cancel = client.post(
        f"/api/v1/report-tasks/{task['id']}:cancel",
        headers=WORKSPACE_HEADERS,
    )
    assert second_cancel.status_code == 409
    assert second_cancel.json()["error"]["code"] == "TASK_NOT_CANCELLABLE"


def test_crawler_task_stop_retry_and_conflict(client: TestClient):
    create_response = client.post(
        "/api/v1/crawler-tasks",
        headers=WORKSPACE_HEADERS,
        json={
            "runMode": "deep_sentiment",
            "targetDate": "2026-05-22",
            "platforms": ["wb", "xhs"],
            "keywords": ["养老服务", "医保支付"],
            "keywordSource": "manual",
        },
    )
    assert create_response.status_code == 202
    task = create_response.json()["task"]
    task_id = task["id"]
    assert task["keywords"] == ["养老服务", "医保支付"]
    assert task["keywordSource"] == "manual"

    stop_response = client.post(
        f"/api/v1/crawler-tasks/{task_id}:stop",
        headers=WORKSPACE_HEADERS,
    )
    assert stop_response.status_code == 202
    assert stop_response.json()["task"]["status"] == "stopped"

    retry_response = client.post(
        f"/api/v1/crawler-tasks/{task_id}:retry",
        headers=WORKSPACE_HEADERS,
    )
    assert retry_response.status_code == 202
    assert retry_response.json()["task"]["status"] == "queued"

    conflict_response = client.post(
        f"/api/v1/crawler-tasks/{task_id}:retry",
        headers=WORKSPACE_HEADERS,
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["error"]["code"] == "CONFLICT"


def test_crawler_task_platform_filter_applies_before_pagination(client: TestClient):
    xhs_task = _create_crawler_task(client, ["xhs"], run_mode="topic_extraction")
    wb_task = _create_crawler_task(client, ["wb"], run_mode="deep_sentiment")

    response = client.get(
        "/api/v1/crawler-tasks?platform=xhs&pageSize=1",
        headers=WORKSPACE_HEADERS,
    )
    assert response.status_code == 200
    assert [task["id"] for task in response.json()["tasks"]] == [xhs_task["id"]]
    assert response.json()["tasks"][0]["id"] != wb_task["id"]


def test_crawler_task_keywords_are_required_and_normalized(client: TestClient):
    response = client.post(
        "/api/v1/crawler-tasks",
        headers=WORKSPACE_HEADERS,
        json={
            "runMode": "deep_sentiment",
            "platforms": ["wb", "wb", "xhs"],
            "keywords": ["  养老服务  ", "", "医保支付", "养老服务"],
            "keywordSource": "manual",
            "maxNotesPerKeyword": 1,
            "maxCommentsPerNote": 0,
            "loginType": "cookie",
            "headless": False,
        },
    )
    assert response.status_code == 202
    task = response.json()["task"]
    assert task["platforms"] == ["wb", "xhs"]
    assert task["keywords"] == ["养老服务", "医保支付"]
    assert task["maxNotesPerKeyword"] == 1
    assert task["maxCommentsPerNote"] == 0
    assert task["loginType"] == "cookie"
    assert task["headless"] is False
    assert task["stats"]["totalKeywords"] == 2
    assert task["stats"]["totalTasks"] == 4

    invalid = client.post(
        "/api/v1/crawler-tasks",
        headers=WORKSPACE_HEADERS,
        json={
            "runMode": "deep_sentiment",
            "platforms": ["wb"],
            "keywords": [],
            "keywordSource": "manual",
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    out_of_bounds = client.post(
        "/api/v1/crawler-tasks",
        headers=WORKSPACE_HEADERS,
        json={
            "runMode": "deep_sentiment",
            "platforms": ["wb"],
            "keywords": ["养老服务"],
            "keywordSource": "manual",
            "maxCommentsPerNote": -1,
        },
    )
    assert out_of_bounds.status_code == 422
    assert out_of_bounds.json()["error"]["code"] == "VALIDATION_ERROR"


def test_crawler_task_status_filter_applies_before_pagination(client: TestClient):
    stopped_task = _create_crawler_task(client, ["xhs"], run_mode="topic_extraction")
    stop_response = client.post(
        f"/api/v1/crawler-tasks/{stopped_task['id']}:stop",
        headers=WORKSPACE_HEADERS,
    )
    assert stop_response.status_code == 202
    queued_task = _create_crawler_task(client, ["wb"], run_mode="deep_sentiment")

    response = client.get(
        "/api/v1/crawler-tasks?status=stopped&pageSize=1",
        headers=WORKSPACE_HEADERS,
    )
    assert response.status_code == 200
    assert [task["id"] for task in response.json()["tasks"]] == [stopped_task["id"]]
    assert response.json()["tasks"][0]["id"] != queued_task["id"]


def test_contract_error_response_for_missing_task(client: TestClient):
    response = client.get("/api/v1/report-tasks/missing", headers=WORKSPACE_HEADERS)
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"


def _config_fields(client: TestClient) -> dict[str, dict]:
    response = client.get("/api/v1/system/config", headers=WORKSPACE_HEADERS)
    assert response.status_code == 200
    return {field["key"]: field for field in response.json()["fields"]}


def _strategy_policy(platform_id: str) -> dict:
    return {
        "platformId": platform_id,
        "enabled": True,
        "crawlDepth": 3,
        "maxKeywords": 10,
        "maxNotesPerKeyword": 20,
        "maxCommentsPerNote": 50,
        "keywords": ["养老服务", "医保"],
        "keywordSource": "manual",
        "frequency": {"mode": "daily", "timezone": "Asia/Shanghai"},
        "loginType": "qrcode",
        "headless": True,
    }


def _create_crawler_task(
    client: TestClient,
    platforms: list[str],
    *,
    run_mode: str,
) -> dict:
    response = client.post(
        "/api/v1/crawler-tasks",
        headers=WORKSPACE_HEADERS,
        json={
            "runMode": run_mode,
            "targetDate": "2026-05-22",
            "platforms": platforms,
            "keywords": ["养老服务", "医保支付"],
            "keywordSource": "manual",
        },
    )
    assert response.status_code == 202
    return response.json()["task"]
