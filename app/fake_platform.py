import hashlib
from collections import defaultdict

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict


class FakePost(BaseModel):
    model_config = ConfigDict(extra="forbid")
    caption: str
    image_path: str


app = FastAPI(title="Fake Social Platform")
posts: dict[str, dict] = {}
rate_limit_once: set[str] = set()
attempts: defaultdict[str, int] = defaultdict(int)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "posts": len(posts)}


@app.post("/platform/{platform}/posts")
def publish(
    platform: str,
    body: FakePost,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    authorization: str = Header(alias="Authorization"),
    x_simulate_rate_limit: bool = Header(default=False, alias="X-Simulate-Rate-Limit"),
) -> dict:
    if platform not in ("instagram", "x"):
        raise HTTPException(404, "Unknown platform")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Token required")
    attempts[idempotency_key] += 1
    if x_simulate_rate_limit and idempotency_key not in rate_limit_once:
        rate_limit_once.add(idempotency_key)
        response.headers["Retry-After"] = "0"
        raise HTTPException(429, "Rate limited", headers={"Retry-After": "0"})
    if idempotency_key in posts:
        return {"post_id": posts[idempotency_key]["post_id"], "duplicate": True}
    post_id = hashlib.sha256(f"{platform}:{idempotency_key}".encode()).hexdigest()[:20]
    posts[idempotency_key] = {"post_id": post_id, "platform": platform, **body.model_dump()}
    return {"post_id": post_id, "duplicate": False}


@app.get("/debug/posts")
def debug_posts() -> dict:
    return {"count": len(posts), "posts": list(posts.values()), "attempts": dict(attempts)}

