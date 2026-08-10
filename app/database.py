import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS campaigns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  url TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS social_posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
  platform TEXT NOT NULL,
  caption TEXT NOT NULL,
  image_path TEXT NOT NULL,
  scheduled_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('queued','publishing','published','failed')),
  idempotency_key TEXT NOT NULL UNIQUE,
  external_post_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  lease_until TEXT,
  last_error TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(campaign_id, platform)
);
CREATE INDEX IF NOT EXISTS idx_posts_due ON social_posts(status, scheduled_at);
CREATE TABLE IF NOT EXISTS tokens (
  platform TEXT PRIMARY KEY,
  nonce BLOB NOT NULL,
  ciphertext BLOB NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webhook_events (
  event_id TEXT PRIMARY KEY,
  received_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def create_campaign(self, title: str, body: str, url: str, posts: list[dict]) -> int:
        now = utc_now()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                "INSERT INTO campaigns(title,body,url,created_at) VALUES(?,?,?,?)",
                (title, body, url, now),
            )
            campaign_id = cursor.lastrowid
            for post in posts:
                db.execute(
                    """INSERT INTO social_posts
                    (campaign_id,platform,caption,image_path,scheduled_at,status,idempotency_key,updated_at)
                    VALUES(?,?,?,?,?,'queued',?,?)""",
                    (campaign_id, post["platform"], post["caption"], post["image_path"], now, post["idempotency_key"], now),
                )
            db.commit()
            return int(campaign_id)

    def save_token(self, platform: str, nonce: bytes, ciphertext: bytes) -> None:
        with self.connection() as db:
            db.execute(
                """INSERT INTO tokens(platform,nonce,ciphertext,updated_at) VALUES(?,?,?,?)
                ON CONFLICT(platform) DO UPDATE SET nonce=excluded.nonce,ciphertext=excluded.ciphertext,updated_at=excluded.updated_at""",
                (platform, nonce, ciphertext, utc_now()),
            )

    def token(self, platform: str) -> sqlite3.Row | None:
        with self.connection() as db:
            return db.execute("SELECT nonce,ciphertext FROM tokens WHERE platform=?", (platform,)).fetchone()

    def schedule(self, campaign_id: int, scheduled_at: str) -> int:
        with self.connection() as db:
            cursor = db.execute(
                """UPDATE social_posts SET scheduled_at=?,status='queued',lease_until=NULL,updated_at=?
                WHERE campaign_id=? AND status NOT IN ('published')""",
                (scheduled_at, utc_now(), campaign_id),
            )
            return cursor.rowcount

    def campaign(self, campaign_id: int) -> dict | None:
        with self.connection() as db:
            campaign = db.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            if campaign is None:
                return None
            posts = db.execute(
                "SELECT platform,caption,image_path,scheduled_at,status,idempotency_key,external_post_id,attempts,last_error FROM social_posts WHERE campaign_id=? ORDER BY platform",
                (campaign_id,),
            ).fetchall()
            return {**dict(campaign), "posts": [dict(row) for row in posts]}

    def claim_due(self, limit: int = 20) -> list[dict]:
        now = datetime.now(timezone.utc)
        lease = (now + timedelta(minutes=2)).isoformat()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE social_posts SET status='queued',lease_until=NULL WHERE status='publishing' AND lease_until < ?",
                (now.isoformat(),),
            )
            rows = db.execute(
                "SELECT * FROM social_posts WHERE status='queued' AND scheduled_at <= ? ORDER BY scheduled_at,id LIMIT ?",
                (now.isoformat(), limit),
            ).fetchall()
            ids = [row["id"] for row in rows]
            for post_id in ids:
                db.execute(
                    "UPDATE social_posts SET status='publishing',lease_until=?,attempts=attempts+1,updated_at=? WHERE id=? AND status='queued'",
                    (lease, now.isoformat(), post_id),
                )
            db.commit()
            return [dict(row) for row in rows]

    def accepted(self, post_id: int, external_post_id: str) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE social_posts SET external_post_id=?,lease_until=NULL,updated_at=? WHERE id=?",
                (external_post_id, utc_now(), post_id),
            )

    def retry(self, post_id: int, error: str) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE social_posts SET status='queued',lease_until=NULL,last_error=?,updated_at=? WHERE id=?",
                (error[:500], utc_now(), post_id),
            )

    def apply_delivery(self, event_id: str, key: str, external_id: str, status: str) -> bool:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM webhook_events WHERE event_id=?", (event_id,)).fetchone():
                db.rollback()
                return False
            db.execute("INSERT INTO webhook_events(event_id,received_at) VALUES(?,?)", (event_id, utc_now()))
            cursor = db.execute(
                "UPDATE social_posts SET status=?,external_post_id=?,lease_until=NULL,updated_at=? WHERE idempotency_key=? AND status='publishing'",
                (status, external_id, utc_now(), key),
            )
            db.commit()
            return cursor.rowcount == 1


