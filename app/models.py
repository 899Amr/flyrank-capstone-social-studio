from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, HttpUrl, field_validator


class Platform(StrEnum):
    instagram = "instagram"
    x = "x"


class PostStatus(StrEnum):
    queued = "queued"
    publishing = "publishing"
    published = "published"
    failed = "failed"


class CampaignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    body: str
    url: HttpUrl

    @field_validator("title", "body")
    @classmethod
    def non_empty(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned


class ScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled_at: datetime

    @field_validator("scheduled_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone is required")
        return value.astimezone(timezone.utc)


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: str

    @field_validator("access_token")
    @classmethod
    def token_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class DeliveryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    idempotency_key: str
    external_post_id: str
    status: PostStatus

    @field_validator("status")
    @classmethod
    def terminal_status(cls, value: PostStatus) -> PostStatus:
        if value not in (PostStatus.published, PostStatus.failed):
            raise ValueError("delivery status must be published or failed")
        return value
