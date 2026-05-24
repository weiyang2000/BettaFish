"""FastAPI entrypoint for the BettaFish SaaS service layer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from apps.api.schemas import (
    ApiError,
    CrawlerAccountUpsertRequest,
    CreateCrawlerTaskRequest,
    CreateReportTaskRequest,
    CrawlerStrategyInput,
    IdentityRuleInput,
    PlatformPolicyInput,
    SearchRunRequest,
    SystemConfigUpdateRequest,
)
from apps.api.services.accounts import AccountService
from apps.api.services.common import utc_now
from apps.api.services.configuration import ConfigurationService
from apps.api.services.engines import EngineFacade
from apps.api.services.platforms import PlatformService
from apps.api.services.tasks import TaskService
from apps.api.storage import Store, dumps


def create_app(
    *,
    db_path: str | Path | None = None,
    artifact_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
    run_workers: bool | None = None,
) -> FastAPI:
    root = Path(repo_root or Path(__file__).resolve().parents[2])
    db = Path(db_path or os.getenv("BETTAFISH_API_DB_PATH", root / "data" / "saas_api.sqlite3"))
    artifacts = Path(
        artifact_dir
        or os.getenv("BETTAFISH_API_ARTIFACT_DIR", root / "data" / "saas_api_artifacts")
    )
    workers_enabled = (
        run_workers
        if run_workers is not None
        else os.getenv("BETTAFISH_API_RUN_WORKERS", "false").lower() == "true"
    )

    store = Store(db)
    account_service = AccountService(store)
    app = FastAPI(
        title="BettaFish SaaS Platform API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.store = store
    app.state.config_service = ConfigurationService(store)
    app.state.account_service = account_service
    app.state.platform_service = PlatformService(store, account_service)
    app.state.task_service = TaskService(store, artifacts, workers_enabled)
    app.state.engine_facade = EngineFacade(root)

    register_error_handlers(app)
    app.include_router(build_router())
    return app


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_response(
                "VALIDATION_ERROR",
                "Request validation failed",
                {"errors": sanitize_validation_errors(exc.errors())},
            ),
        )


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/health")
    def health(workspace_id: str = Depends(workspace_header)) -> dict[str, Any]:
        return {
            "success": True,
            "workspaceId": workspace_id,
            "status": "ok",
            "serverTime": utc_now(),
            "version": "0.1.0",
            "currentUser": {
                "userId": "service_account",
                "displayName": "BettaFish API",
                "role": "service_account",
            },
        }

    @router.get("/system/components")
    def list_components(
        request: Request,
        _: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        return {"success": True, "components": request.app.state.engine_facade.list_components()}

    @router.post("/system/components/{component_id}:start", status_code=202)
    def start_component(
        component_id: str,
        request: Request,
        _: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        component = request.app.state.engine_facade.set_component_status(component_id, "start")
        return {"success": True, "component": component, "message": "Start requested"}

    @router.post("/system/components/{component_id}:stop", status_code=202)
    def stop_component(
        component_id: str,
        request: Request,
        _: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        component = request.app.state.engine_facade.set_component_status(component_id, "stop")
        return {"success": True, "component": component, "message": "Stop requested"}

    @router.get("/system/config")
    def get_system_config(
        request: Request,
        workspace_id: str = Depends(workspace_header),
        include_schema: bool = Query(True, alias="includeSchema"),
    ) -> dict[str, Any]:
        del include_schema
        return {
            "success": True,
            "fields": request.app.state.config_service.list_fields(workspace_id),
            "updatedAt": utc_now(),
        }

    @router.patch("/system/config")
    def update_system_config(
        payload: SystemConfigUpdateRequest,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        service = request.app.state.config_service
        service.update_fields(workspace_id, payload.values, payload.updatedBy)
        return {"success": True, "fields": service.list_fields(workspace_id), "updatedAt": utc_now()}

    @router.get("/logs")
    def list_logs(
        request: Request,
        _: str = Depends(workspace_header),
        source: str | None = None,
        level: str | None = None,
        tail: int = Query(300, ge=1, le=2000),
    ) -> dict[str, Any]:
        lines = request.app.state.engine_facade.list_logs(source, level, tail)
        return {"success": True, "lines": lines}

    @router.post("/search", status_code=202)
    def create_search_run(
        payload: SearchRunRequest,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        run = request.app.state.task_service.create_search_run(
            workspace_id,
            payload.query,
            payload.engines,
            payload.owner,
        )
        return {"success": True, "run": run}

    @router.get("/report-templates")
    def list_report_templates(
        request: Request,
        _: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        return {
            "success": True,
            "templates": request.app.state.engine_facade.list_report_templates(),
        }

    @router.get("/report-tasks")
    def list_report_tasks(
        request: Request,
        workspace_id: str = Depends(workspace_header),
        status: str | None = None,
        page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    ) -> dict[str, Any]:
        tasks = request.app.state.task_service.list_report_tasks(workspace_id, status, page_size)
        return {"success": True, "tasks": tasks}

    @router.post("/report-tasks", status_code=202)
    def create_report_task(
        payload: CreateReportTaskRequest,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        task = request.app.state.task_service.create_report_task(workspace_id, payload)
        return {
            "success": True,
            "task": task,
            "eventStreamUrl": f"/api/v1/report-tasks/{task['id']}/events",
        }

    @router.get("/report-tasks/{task_id}")
    def get_report_task(
        task_id: str,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        return {"success": True, "task": request.app.state.task_service.get_report_task(workspace_id, task_id)}

    @router.get("/report-tasks/{task_id}/events")
    def stream_report_events(
        task_id: str,
        request: Request,
        workspace_id: str = Depends(workspace_header),
        last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        request.app.state.task_service.get_report_task(workspace_id, task_id)
        after_id = _parse_event_id(last_event_id)

        def generate():
            events = request.app.state.task_service.list_events(workspace_id, task_id, after_id)
            if not events:
                events = [
                    {
                        "id": "0",
                        "type": "heartbeat",
                        "taskId": task_id,
                        "timestamp": utc_now(),
                        "payload": {"status": "connected"},
                    }
                ]
            for event in events:
                yield format_sse(event)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @router.post("/report-tasks/{task_id}:cancel", status_code=202)
    def cancel_report_task(
        task_id: str,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        task = request.app.state.task_service.cancel_report_task(workspace_id, task_id)
        return {
            "success": True,
            "task": task,
            "eventStreamUrl": f"/api/v1/report-tasks/{task['id']}/events",
        }

    @router.get("/report-tasks/{task_id}/result")
    def get_report_result(
        task_id: str,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        return request.app.state.task_service.get_report_result(workspace_id, task_id)

    @router.get("/report-tasks/{task_id}/exports/{report_format}")
    def export_report(
        task_id: str,
        report_format: str,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ):
        task = request.app.state.task_service.get_report_task(workspace_id, task_id)
        path = request.app.state.task_service.artifact_path(task_id, report_format)
        artifact = next(
            (
                item
                for item in task.get("artifacts", [])
                if item["format"] == report_format and item.get("ready")
            ),
            None,
        )
        if not artifact or not path.exists():
            return JSONResponse(
                status_code=202,
                content={
                    "success": True,
                    "exportJobId": f"export_{task_id}_{report_format}",
                    "status": task["status"],
                },
            )
        media_type = {
            "html": "text/html",
            "md": "text/markdown",
            "json": "application/json",
            "pdf": "application/pdf",
        }[report_format]
        return FileResponse(
            path,
            media_type=media_type,
            filename=artifact.get("filename") or path.name,
        )

    @router.get("/crawler-strategies")
    def list_crawler_strategies(
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        return {
            "success": True,
            "strategies": request.app.state.task_service.list_crawler_strategies(workspace_id),
        }

    @router.post("/crawler-strategies", status_code=201)
    def create_crawler_strategy(
        payload: CrawlerStrategyInput,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        strategy = request.app.state.task_service.create_crawler_strategy(workspace_id, payload)
        return {"success": True, "strategy": strategy}

    @router.get("/crawler-accounts")
    def list_crawler_accounts(
        request: Request,
        workspace_id: str = Depends(workspace_header),
        platform: str | None = None,
        status: str | None = None,
        page_size: int = Query(50, alias="pageSize", ge=1, le=200),
    ) -> dict[str, Any]:
        accounts = request.app.state.account_service.list_accounts(
            workspace_id,
            platform,
            status,
            page_size,
        )
        return {"success": True, "accounts": accounts}

    @router.put("/crawler-accounts/{accountId}")
    def upsert_crawler_account(
        accountId: str,
        payload: CrawlerAccountUpsertRequest,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        account = request.app.state.account_service.upsert_account(
            workspace_id,
            accountId,
            payload,
        )
        return {"success": True, "account": account}

    @router.get("/crawler-tasks")
    def list_crawler_tasks(
        request: Request,
        workspace_id: str = Depends(workspace_header),
        status: str | None = None,
        platform: str | None = None,
        page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    ) -> dict[str, Any]:
        tasks = request.app.state.task_service.list_crawler_tasks(
            workspace_id,
            status,
            platform,
            page_size,
        )
        return {"success": True, "tasks": tasks}

    @router.post("/crawler-tasks", status_code=202)
    def create_crawler_task(
        payload: CreateCrawlerTaskRequest,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        task = request.app.state.task_service.create_crawler_task(workspace_id, payload)
        return {"success": True, "task": task}

    @router.get("/crawler-tasks/{task_id}")
    def get_crawler_task(
        task_id: str,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        return {"success": True, "task": request.app.state.task_service.get_crawler_task(workspace_id, task_id)}

    @router.post("/crawler-tasks/{task_id}:stop", status_code=202)
    def stop_crawler_task(
        task_id: str,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        task = request.app.state.task_service.stop_crawler_task(workspace_id, task_id)
        return {"success": True, "task": task}

    @router.post("/crawler-tasks/{task_id}:retry", status_code=202)
    def retry_crawler_task(
        task_id: str,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        task = request.app.state.task_service.retry_crawler_task(workspace_id, task_id)
        return {"success": True, "task": task}

    @router.get("/platforms")
    def list_platforms(
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        return {
            "success": True,
            "platforms": request.app.state.platform_service.list_platforms(workspace_id),
        }

    @router.get("/platforms/{platform_id}/policy")
    def get_platform_policy(
        platform_id: str,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        return {
            "success": True,
            "policy": request.app.state.platform_service.get_policy(workspace_id, platform_id),
        }

    @router.put("/platforms/{platform_id}/policy")
    def update_platform_policy(
        platform_id: str,
        payload: PlatformPolicyInput,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        policy = request.app.state.platform_service.update_policy(
            workspace_id,
            platform_id,
            payload,
        )
        return {"success": True, "policy": policy}

    @router.get("/platforms/{platform_id}/identity-lists")
    def list_identity_rules(
        platform_id: str,
        request: Request,
        workspace_id: str = Depends(workspace_header),
        list_type: str | None = Query(None, alias="listType"),
    ) -> dict[str, Any]:
        rules = request.app.state.platform_service.list_identity_rules(
            workspace_id,
            platform_id,
            list_type,
        )
        return {"success": True, "rules": rules}

    @router.post("/platforms/{platform_id}/identity-lists", status_code=201)
    def create_identity_rule(
        platform_id: str,
        payload: IdentityRuleInput,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> dict[str, Any]:
        rule = request.app.state.platform_service.create_identity_rule(
            workspace_id,
            platform_id,
            payload,
        )
        return {"success": True, "rule": rule}

    @router.delete("/platforms/{platform_id}/identity-lists/{rule_id}", status_code=204)
    def delete_identity_rule(
        platform_id: str,
        rule_id: str,
        request: Request,
        workspace_id: str = Depends(workspace_header),
    ) -> Response:
        request.app.state.platform_service.delete_identity_rule(
            workspace_id,
            platform_id,
            rule_id,
        )
        return Response(status_code=204)

    return router


def workspace_header(x_workspace_id: str = Header(..., alias="X-Workspace-Id")) -> str:
    return x_workspace_id


def error_response(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"success": False, "error": error}


def sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized = []
    for error in errors:
        item = dict(error)
        if "ctx" in item:
            item["ctx"] = {key: str(value) for key, value in item["ctx"].items()}
        sanitized.append(item)
    return sanitized


def format_sse(event: dict[str, Any]) -> str:
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {dumps(event)}\n\n"


def _parse_event_id(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


app = create_app()
