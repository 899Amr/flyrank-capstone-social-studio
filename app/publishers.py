import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class PublishResult:
    external_post_id: str
    duplicate: bool


class SocialPublisher(ABC):
    platform: str

    @abstractmethod
    def publish(self, post: dict, access_token: str) -> PublishResult:
        raise NotImplementedError


class FakePlatformPublisher(SocialPublisher):
    def __init__(self, platform: str, base_url: str, client: httpx.Client | None = None) -> None:
        self.platform = platform
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=10)

    def publish(self, post: dict, access_token: str) -> PublishResult:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": post["idempotency_key"],
        }
        payload = {"caption": post["caption"], "image_path": post["image_path"]}
        for attempt in range(3):
            try:
                response = self.client.post(
                    f"{self.base_url}/platform/{self.platform}/posts",
                    json=payload,
                    headers=headers,
                )
            except httpx.TimeoutException:
                if attempt == 2:
                    raise
                time.sleep(0.05 * (2**attempt))
                continue
            if response.status_code == 429:
                if attempt == 2:
                    response.raise_for_status()
                time.sleep(max(0, float(response.headers.get("Retry-After", "1"))))
                continue
            response.raise_for_status()
            data = response.json()
            return PublishResult(data["post_id"], data.get("duplicate", False))
        raise RuntimeError("publish attempts exhausted")



class FakeInstagramPublisher(FakePlatformPublisher):
    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        super().__init__("instagram", base_url, client)


class FakeXPublisher(FakePlatformPublisher):
    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        super().__init__("x", base_url, client)
