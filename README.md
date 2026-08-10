# FlyRank Capstone: Social Studio

One published blog post becomes a reliable Instagram and X campaign: platform-sized images, distinct captions, durable scheduling, idempotent fake-platform publishing, encrypted tokens, rate-limit retry, and signature-verified delivery status.

The core never touches a real social account. Everything runs against the bundled fake social platform.

## Architecture

```text
Blog post
  |-- Caption composer: shared voice + platform rules + summary
  |-- Pillow pipeline: Instagram 1080x1080 | X 1600x900
  v
CampaignService -> SQLite repository -> durable queued SocialPostEntry records
                           |
Worker -> SocialPublisher interface -> Instagram adapter --+
                               \-----> X adapter ------------+-> Fake platform
       stable idempotency key | Retry-After | encrypted token

Fake platform -> HMAC delivery webhook -> signature + replay verification
                                         -> published | failed
```

## Quick start

Requires Docker Desktop or another Docker Compose engine.

```bash
cp .env.example .env
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Put that generated value in `.env` as `ENCRYPTION_KEY`, choose a long random `WEBHOOK_SECRET`, then run:

```bash
docker compose up --build
docker compose exec api python -m app.seed
```

- API and Swagger: http://localhost:8000/docs
- Fake-platform inspector: http://localhost:9000/debug/posts

The seed stores fake tokens encrypted, creates both variants/captions, and schedules the campaign ten seconds ahead. The durable worker publishes it automatically.

## Demo commands

Create a campaign directly:

```bash
curl -X POST http://localhost:8000/campaigns \
  -H "Content-Type: application/json" \
  -d '{"title":"Reliable social publishing","body":"Retries and restarts should never create duplicate posts.","url":"https://example.com/post"}'
```

Publish immediately and inspect status:

```bash
curl -X POST http://localhost:8000/campaigns/1/publish
curl -X POST http://localhost:8000/worker/run
curl http://localhost:8000/campaigns/1
```

Calling publish and worker repeatedly is safe: `(campaign_id, platform)` is unique locally and every adapter reuses the same idempotency key remotely.

## Reliability model

- SQLite stores every schedule and creates an index on `(status, scheduled_at)`.
- A worker claims due rows inside `BEGIN IMMEDIATE`, marks them `publishing`, and adds a two-minute lease.
- A restarted worker recovers expired leases. The stable idempotency key makes a repeated remote call safe.
- `429` honors `Retry-After`; timeouts retry with exponential delay and the same key.
- Platform acceptance does not mean delivery. Status remains `publishing` until a valid HMAC webhook arrives.
- Webhook event IDs prevent replay, and `hmac.compare_digest` rejects modified signatures.
- AES-GCM stores only a random nonce and ciphertext. Tokens are decrypted only at the adapter boundary and never logged.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The deterministic suite covers all six evaluator probes: media dimensions/captions, response-lost idempotency, `429 Retry-After`, worker crash recovery, forged/valid/replayed webhooks, and encrypted token storage.

## Submission pack

- [DESIGN.md](DESIGN.md) - problem, non-goal, model, API, and layer sketch
- [EVIDENCE.md](EVIDENCE.md) - proof for every Definition-of-Done checkbox
- [BUILDLOG.md](BUILDLOG.md) - honest AI assistance and corrections
- [capstone.yaml](capstone.yaml) - machine-readable run, seed, test, URL, and probes
- [.env.example](.env.example) - safe placeholders only

## Limitations

This portfolio core uses SQLite and a polling worker rather than a distributed queue. SQLite is deliberately appropriate for one-node durability and deterministic evaluation; horizontal workers would require PostgreSQL row locking or a real queue. The placeholder image keeps its subject centered but does not perform semantic face/object detection. The fake platform models the important failure contracts without contacting real social networks.

