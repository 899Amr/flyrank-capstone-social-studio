import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from PIL import Image

import app.main as main_module
from app.content import compose_caption, generate_variants, prompt_components, source_placeholder
from app.crypto import TokenCipher
from app.database import Repository
from app.models import CampaignCreate, Platform
from app.publishers import FakeInstagramPublisher, FakeXPublisher
from app.service import CampaignService


class SequenceClient:
    def __init__(self, sequence: list[object]) -> None:
        self.sequence = sequence
        self.calls = 0
        self.keys: list[str] = []

    def post(self, url: str, json: dict, headers: dict) -> httpx.Response:
        self.keys.append(headers["Idempotency-Key"])
        item = self.sequence[min(self.calls, len(self.sequence) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


def response(status: int, data: dict, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        json=data,
        headers=headers,
        request=httpx.Request("POST", "http://fake/posts"),
    )


def build_service(tmp_path: Path, client: SequenceClient) -> tuple[CampaignService, Repository]:
    repository = Repository(tmp_path / "studio.db")
    cipher = TokenCipher(main_module.settings.encryption_key)
    publishers = {
        "instagram": FakeInstagramPublisher("http://fake", client),
        "x": FakeXPublisher("http://fake", client),
    }
    service = CampaignService(repository, cipher, publishers, tmp_path / "artifacts")
    service.store_token(Platform.instagram, "secret-instagram-token")
    service.store_token(Platform.x, "secret-x-token")
    return service, repository


def create(service: CampaignService) -> dict:
    return service.create_campaign(
        CampaignCreate(
            title="One post, two platforms",
            body="Reliable delivery means retries and restarts never create duplicate social posts.",
            url="https://example.com/reliable-campaigns",
        )
    )


def test_image_dimensions_and_distinct_composed_captions(tmp_path: Path) -> None:
    source = source_placeholder(tmp_path / "source.jpg", "Campaign")
    variants = generate_variants(source, tmp_path / "variants")
    with Image.open(variants[Platform.instagram]) as instagram:
        assert instagram.size == (1080, 1080)
    with Image.open(variants[Platform.x]) as x_image:
        assert x_image.size == (1600, 900)
    instagram_caption = compose_caption(Platform.instagram, "Title", "Body text", "https://example.com")
    x_caption = compose_caption(Platform.x, "Title", "Body text", "https://example.com")
    assert instagram_caption != x_caption
    assert len(x_caption) <= 280
    assert prompt_components(Platform.instagram, "Title", "Body")["brand_voice"] == prompt_components(Platform.x, "Title", "Body")["brand_voice"]


def test_tokens_use_random_nonce_and_no_plaintext(tmp_path: Path) -> None:
    cipher = TokenCipher(main_module.settings.encryption_key)
    first_nonce, first_ciphertext = cipher.encrypt("top-secret-token")
    second_nonce, second_ciphertext = cipher.encrypt("top-secret-token")
    assert first_nonce != second_nonce
    assert b"top-secret-token" not in first_ciphertext + second_ciphertext
    assert cipher.decrypt(first_nonce, first_ciphertext) == "top-secret-token"


def test_duplicate_publish_and_timeout_use_one_idempotency_key(tmp_path: Path) -> None:
    timeout = httpx.ReadTimeout("accepted but response was lost")
    client = SequenceClient([timeout, response(200, {"post_id": "post-1", "duplicate": True})])
    service, repository = build_service(tmp_path, client)
    campaign = create(service)
    result = service.publish_due()
    assert result == {"claimed": 2, "accepted": 2, "failed": 0}
    assert len(set(client.keys)) == 2
    for post in repository.campaign(campaign["id"])["posts"]:
        assert post["status"] == "publishing"
        assert post["external_post_id"] == "post-1"


def test_rate_limit_honors_retry_after_and_retries_safely() -> None:
    client = SequenceClient(
        [
            response(429, {"error": "limited"}, {"Retry-After": "0"}),
            response(200, {"post_id": "post-2", "duplicate": False}),
        ]
    )
    publisher = FakeXPublisher("http://fake", client)
    post = {"idempotency_key": "stable-key", "caption": "caption", "image_path": "x.jpg"}
    result = publisher.publish(post, "encrypted-at-rest-token")
    assert result.external_post_id == "post-2"
    assert client.calls == 2
    assert client.keys == ["stable-key", "stable-key"]


def test_expired_worker_lease_is_recovered_after_restart(tmp_path: Path) -> None:
    client = SequenceClient([response(200, {"post_id": "post-3", "duplicate": False})])
    service, repository = build_service(tmp_path, client)
    create(service)
    claimed = repository.claim_due(limit=1)
    assert len(claimed) == 1
    with repository.connection() as db:
        db.execute(
            "UPDATE social_posts SET lease_until=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), claimed[0]["id"]),
        )
    restarted = Repository(repository.path)
    recovered = restarted.claim_due(limit=1)
    assert recovered[0]["id"] == claimed[0]["id"]


def test_forged_webhook_rejected_valid_webhook_updates_status(tmp_path: Path, monkeypatch) -> None:
    client = SequenceClient([response(200, {"post_id": "external-1", "duplicate": False})])
    service, repository = build_service(tmp_path, client)
    campaign = create(service)
    service.publish_due()
    monkeypatch.setattr(main_module, "repository", repository)
    api = TestClient(main_module.app)
    post = repository.campaign(campaign["id"])["posts"][0]
    event = {
        "event_id": "event-1",
        "idempotency_key": post["idempotency_key"],
        "external_post_id": "external-1",
        "status": "published",
    }
    body = json.dumps(event, separators=(",", ":")).encode()
    forged = api.post(
        "/webhook/social-delivery",
        content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": "forged"},
    )
    assert forged.status_code == 400
    assert repository.campaign(campaign["id"])["posts"][0]["status"] == "publishing"
    signature = hmac.new(main_module.settings.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    valid = api.post(
        "/webhook/social-delivery",
        content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": signature},
    )
    assert valid.status_code == 200
    assert repository.campaign(campaign["id"])["posts"][0]["status"] == "published"
    replay = api.post(
        "/webhook/social-delivery",
        content=body,
        headers={"Content-Type": "application/json", "X-Webhook-Signature": signature},
    )
    assert replay.json() == {"accepted": False}


