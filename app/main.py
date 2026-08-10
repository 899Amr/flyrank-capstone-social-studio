import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.crypto import TokenCipher
from app.database import Repository
from app.models import CampaignCreate, DeliveryEvent, Platform, ScheduleRequest, TokenRequest
from app.publishers import FakeInstagramPublisher, FakeXPublisher
from app.service import CampaignService


repository = Repository(settings.database_path)
cipher = TokenCipher(settings.encryption_key)
publishers = {
    "instagram": FakeInstagramPublisher(settings.fake_platform_url),
    "x": FakeXPublisher(settings.fake_platform_url),
}
service = CampaignService(repository, cipher, publishers, Path("artifacts/generated"))

app = FastAPI(title="FlyRank Social Studio", version="1.0.0")


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "Invalid request", "details": exc.errors()})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/tokens/{platform}", status_code=204)
def save_token(platform: Platform, body: TokenRequest) -> None:
    service.store_token(platform, body.access_token)


@app.post("/campaigns", status_code=201)
def create_campaign(body: CampaignCreate) -> dict:
    return service.create_campaign(body)


@app.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int) -> dict:
    campaign = repository.campaign(campaign_id)
    if campaign is None:
        raise HTTPException(404, "Campaign not found")
    return campaign


@app.post("/campaigns/{campaign_id}/schedule")
def schedule_campaign(campaign_id: int, body: ScheduleRequest) -> dict:
    campaign = service.schedule(campaign_id, body.scheduled_at)
    if campaign is None:
        raise HTTPException(404, "Campaign not found or already published")
    return campaign


@app.post("/campaigns/{campaign_id}/publish")
def publish_campaign(campaign_id: int) -> dict:
    campaign = service.schedule(campaign_id, datetime.now(timezone.utc))
    if campaign is None:
        existing = repository.campaign(campaign_id)
        if existing is None:
            raise HTTPException(404, "Campaign not found")
        return existing
    return campaign


@app.post("/worker/run")
def run_worker_once() -> dict:
    return service.publish_due()


@app.post("/webhook/social-delivery")
async def delivery_webhook(
    request: Request,
    x_webhook_signature: str | None = Header(default=None),
) -> dict:
    body = await request.body()
    expected = hmac.new(settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not x_webhook_signature or not hmac.compare_digest(expected, x_webhook_signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature")
    try:
        event = DeliveryEvent.model_validate(json.loads(body))
    except Exception as exc:
        raise HTTPException(400, "Invalid webhook payload") from exc
    changed = repository.apply_delivery(
        event.event_id,
        event.idempotency_key,
        event.external_post_id,
        event.status.value,
    )
    return {"accepted": changed}


