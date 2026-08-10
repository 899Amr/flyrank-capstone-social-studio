# Build Log

## Phase 1 - Design

AI helped translate the brief into a small layered design and identify the hardest invariants: stable idempotency keys, atomic worker claims, expiring leases, random-IV encryption, and signature-gated status changes. I kept the scope to two fake platforms and SQLite.

## Phase 2 - Content generation

AI suggested a reusable caption-fragment map and Pillow `ImageOps.fit`. I rejected artistic AI generation because the rubric grades dimensions and safe-zone behavior, not artwork. The final source is a deterministic placeholder with a central subject.

## Phase 3 - Publishing

AI initially handled 429 responses but did not retry a response-lost timeout. I added timeout retry with the same idempotency key and a deterministic test that models â€œaccepted remotely, response lost.â€ I also ensured tokens are decrypted only inside the worker and never included in logs or API responses.

## Phase 4 - Reliability and trust

AI helped draft the lease-based SQLite claim transaction. I reviewed the state boundary and kept `published`/`failed` changes exclusively in the verified webhook path. Replay protection uses a unique event ID. Forged events leave state unchanged.

## What I own

I can explain the atomic `BEGIN IMMEDIATE` claim, the stable `(campaign, platform)` uniqueness rule, the AES-GCM nonce/ciphertext storage, HMAC comparison, and why an accepted platform request remains `publishing` until a trusted delivery event arrives.


