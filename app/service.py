import hashlib
from datetime import datetime, timezone
from pathlib import Path

from app.content import compose_caption, generate_variants, source_placeholder
from app.crypto import TokenCipher
from app.database import Repository
from app.models import CampaignCreate, Platform
from app.publishers import SocialPublisher


class CampaignService:
    def __init__(
        self,
        repository: Repository,
        cipher: TokenCipher,
        publishers: dict[str, SocialPublisher],
        artifact_root: Path,
    ) -> None:
        self.repository = repository
        self.cipher = cipher
        self.publishers = publishers
        self.artifact_root = artifact_root

    def store_token(self, platform: Platform, token: str) -> None:
        nonce, ciphertext = self.cipher.encrypt(token)
        self.repository.save_token(platform.value, nonce, ciphertext)

    def create_campaign(self, request: CampaignCreate) -> dict:
        fingerprint = hashlib.sha256(f"{request.url}|{request.title}".encode()).hexdigest()[:16]
        campaign_dir = self.artifact_root / fingerprint
        source = source_placeholder(campaign_dir / "source.jpg", request.title)
        variants = generate_variants(source, campaign_dir)
        posts = []
        for platform in Platform:
            posts.append(
                {
                    "platform": platform.value,
                    "caption": compose_caption(platform, request.title, request.body, str(request.url)),
                    "image_path": str(variants[platform]),
                    "idempotency_key": hashlib.sha256(f"{fingerprint}:{platform.value}".encode()).hexdigest(),
                }
            )
        campaign_id = self.repository.create_campaign(request.title, request.body, str(request.url), posts)
        return self.repository.campaign(campaign_id)

    def schedule(self, campaign_id: int, scheduled_at: datetime) -> dict | None:
        count = self.repository.schedule(campaign_id, scheduled_at.astimezone(timezone.utc).isoformat())
        return self.repository.campaign(campaign_id) if count else None

    def publish_due(self) -> dict[str, int]:
        claimed = self.repository.claim_due()
        accepted = failed = 0
        for post in claimed:
            token_row = self.repository.token(post["platform"])
            if token_row is None:
                self.repository.retry(post["id"], "platform token is not configured")
                failed += 1
                continue
            try:
                token = self.cipher.decrypt(token_row["nonce"], token_row["ciphertext"])
                result = self.publishers[post["platform"]].publish(post, token)
                self.repository.accepted(post["id"], result.external_post_id)
                accepted += 1
            except Exception as exc:
                self.repository.retry(post["id"], type(exc).__name__)
                failed += 1
        return {"claimed": len(claimed), "accepted": accepted, "failed": failed}


