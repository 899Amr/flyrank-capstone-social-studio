# Design: Multi-Platform Social Campaign Publisher

## Problem

Turn one published blog post into reliable Instagram and X posts without duplicate publication, lost schedules, plaintext credentials, or untrusted status changes.

## Explicit non-goal

The core system never connects to a real social network. It targets the bundled fake platform only; artistic image generation and a large frontend are outside scope.

## API surface

- `POST /tokens/{platform}` stores a platform access token encrypted with AES-GCM.
- `POST /campaigns` validates a blog post, composes captions, generates variants, and persists queued platform entries.
- `POST /campaigns/{id}/schedule` durably schedules both entries.
- `POST /campaigns/{id}/publish` makes both entries due immediately.
- `POST /worker/run` atomically claims and publishes due entries.
- `POST /webhook/social-delivery` verifies HMAC before changing trusted delivery state.
- `GET /campaigns/{id}` returns campaign and platform status.

## Layers

HTTP routes call `CampaignService`; the service depends on repository and `SocialPublisher` interfaces; adapters alone know the fake-platform HTTP contract. SQLite owns durable state, while the worker is stateless and restartable.

## Data model

- `campaigns`: source title/body/URL and creation time.
- `social_posts`: campaign, platform, caption, image path, schedule, status, idempotency key, external ID, attempts, lease.
- `tokens`: platform plus AES-GCM nonce and ciphertext.
- `webhook_events`: unique event ID for replay prevention.

## State rules

`queued -> publishing -> published | failed`. The worker may set `publishing`; only a verified delivery webhook may set `published` or `failed`. Expired publishing leases return to queued so a restarted worker continues safely.

