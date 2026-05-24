"""Pydantic request models and contract constants for the SaaS API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PLATFORM_IDS = ("xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu")
COMPONENT_IDS = ("query", "media", "insight", "forum", "report", "mindspider", "database")
REPORT_FORMATS = ("html", "json", "md", "pdf")
REPORT_STATUSES = ("queued", "pending", "running", "succeeded", "failed", "cancelled")
CRAWLER_STATUSES = (
    "queued",
    "pending",
    "running",
    "succeeded",
    "failed",
    "stopping",
    "stopped",
    "cancelled",
)
RUN_MODES = ("topic_extraction", "deep_sentiment", "full_workflow")
KEYWORD_SOURCES = ("manual", "broad_topic_extraction", "mixed")
CRAWLER_ACCOUNT_STATUSES = (
    "active",
    "login_required",
    "expired",
    "disabled",
    "error",
    "unknown",
)
MASK = "********"


class UserRef(BaseModel):
    userId: str
    displayName: str | None = None
    role: Literal["owner", "operator", "reviewer", "service_account"] | None = None


class SystemConfigUpdateRequest(BaseModel):
    values: dict[str, str | int | float | bool | None]
    updatedBy: UserRef | None = None


class SearchRunRequest(BaseModel):
    query: str = Field(min_length=1)
    engines: list[str] = Field(default_factory=lambda: ["query", "media", "insight", "forum"])
    owner: UserRef | None = None

    @field_validator("engines")
    @classmethod
    def validate_engines(cls, value: list[str]) -> list[str]:
        invalid = sorted(set(value) - set(COMPONENT_IDS))
        if invalid:
            raise ValueError(f"unsupported engines: {', '.join(invalid)}")
        return value


class ReportSourceScope(BaseModel):
    searchRunId: str | None = None
    crawlerTaskIds: list[str] = Field(default_factory=list)
    includeForumLog: bool = True
    inputFileRefs: list[str] = Field(default_factory=list)


class CreateReportTaskRequest(BaseModel):
    topic: str = Field(min_length=1)
    templateId: str | None = None
    customTemplate: str | None = None
    sourceScope: ReportSourceScope = Field(default_factory=ReportSourceScope)
    outputFormats: list[str] = Field(default_factory=lambda: ["html"])
    owner: UserRef | None = None

    @field_validator("outputFormats")
    @classmethod
    def validate_formats(cls, value: list[str]) -> list[str]:
        formats = value or ["html"]
        invalid = sorted(set(formats) - set(REPORT_FORMATS))
        if invalid:
            raise ValueError(f"unsupported report formats: {', '.join(invalid)}")
        return list(dict.fromkeys(formats))


class CrawlFrequency(BaseModel):
    mode: Literal["manual", "hourly", "daily", "weekly", "cron"] = "manual"
    cron: str | None = None
    timezone: str = "Asia/Shanghai"


class PlatformPolicyInput(BaseModel):
    enabled: bool = True
    crawlDepth: int = Field(default=3, ge=1, le=10)
    maxKeywords: int = Field(default=100, ge=1, le=500)
    maxNotesPerKeyword: int = Field(default=50, ge=1, le=1000)
    maxCommentsPerNote: int = Field(default=100, ge=0, le=5000)
    keywords: list[str] = Field(default_factory=list)
    keywordSource: Literal["manual", "broad_topic_extraction", "mixed"] = "manual"
    frequency: CrawlFrequency = Field(default_factory=CrawlFrequency)
    loginType: Literal["qrcode", "phone", "cookie"] = "qrcode"
    headless: bool = True

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item and item.strip()]
        return list(dict.fromkeys(normalized))

    def to_policy(self, platform_id: str, updated_at: str, updated_by: UserRef | None = None) -> dict[str, Any]:
        policy = self.model_dump(mode="json")
        policy["platformId"] = platform_id
        policy["updatedAt"] = updated_at
        if updated_by:
            policy["updatedBy"] = updated_by.model_dump(exclude_none=True)
        return policy


class StrategyPlatformPolicyInput(PlatformPolicyInput):
    platformId: str

    @field_validator("platformId")
    @classmethod
    def validate_platform_id(cls, value: str) -> str:
        if value not in PLATFORM_IDS:
            raise ValueError(f"unsupported platform: {value}")
        return value


class CrawlerStrategyInput(BaseModel):
    name: str = Field(min_length=1)
    runMode: Literal["topic_extraction", "deep_sentiment", "full_workflow"]
    platformPolicies: list[StrategyPlatformPolicyInput]
    owner: UserRef | None = None


class CreateCrawlerTaskRequest(BaseModel):
    strategyId: str | None = None
    runMode: Literal["topic_extraction", "deep_sentiment", "full_workflow"]
    targetDate: str | None = None
    platforms: list[str] = Field(min_length=1)
    keywords: list[str] = Field(min_length=1, max_length=500)
    keywordSource: Literal["manual"]
    maxNotesPerKeyword: int | None = Field(default=None, ge=1, le=1000)
    maxCommentsPerNote: int | None = Field(default=None, ge=0, le=5000)
    loginType: Literal["qrcode", "phone", "cookie"] | None = None
    headless: bool | None = None
    overrides: list[PlatformPolicyInput] = Field(default_factory=list)
    owner: UserRef | None = None

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, value: list[str]) -> list[str]:
        invalid = sorted(set(value) - set(PLATFORM_IDS))
        if invalid:
            raise ValueError(f"unsupported platforms: {', '.join(invalid)}")
        return list(dict.fromkeys(value))

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item and item.strip()]
        if not normalized:
            raise ValueError("at least one keyword is required")
        return list(dict.fromkeys(normalized))


class CrawlerAccountUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platformId: str
    username: str | None = None
    displayName: str | None = None
    avatarUrl: str | None = None
    profileUrl: str | None = None
    status: Literal[
        "active",
        "login_required",
        "expired",
        "disabled",
        "error",
        "unknown",
    ]
    loginType: Literal["qrcode", "phone", "cookie"] | None = None
    lastLoginAt: str | None = None
    lastCheckedAt: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None

    @field_validator("platformId")
    @classmethod
    def validate_platform_id(cls, value: str) -> str:
        if value not in PLATFORM_IDS:
            raise ValueError(f"unsupported platform: {value}")
        return value


class IdentityRuleInput(BaseModel):
    listType: Literal["allow", "block"]
    userId: str = Field(min_length=1)
    label: str | None = None
    reason: str | None = None
    expiresAt: str | None = None
    createdBy: UserRef | None = None


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
