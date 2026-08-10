# Definition-of-Done Evidence

## Content generation

- **Image variants:** `test_image_dimensions_and_distinct_composed_captions` opens the artifacts and asserts Instagram `1080x1080` and X `1600x900`.
- **Composable platform captions:** the same test proves captions differ, X stays within 280 characters, and both platforms reuse the identical shared brand fragment.

## Adapter layer

- **Interface and two implementations:** `SocialPublisher` is the application boundary; `FakeInstagramPublisher` and `FakeXPublisher` implement the fake-platform contract.
- **Encrypted OAuth tokens:** `test_tokens_use_random_nonce_and_no_plaintext` proves two encryptions use different nonces, ciphertext contains no plaintext, and decryption succeeds.

## Reliability

- **Idempotent timeout retry:** `test_duplicate_publish_and_timeout_use_one_idempotency_key` simulates a lost response after acceptance and proves retries retain the stable key.
- **Rate limits:** `test_rate_limit_honors_retry_after_and_retries_safely` returns `429 Retry-After: 0`, then success, and proves exactly two attempts with one key.
- **Crash recovery:** `test_expired_worker_lease_is_recovered_after_restart` claims a job, simulates an expired crashed-worker lease, creates a new repository instance, and recovers the same job.

## Status and trust

- **Forged webhook:** `test_forged_webhook_rejected_valid_webhook_updates_status` returns 400 and proves status remains `publishing`.
- **Verified status:** the same test signs the exact raw body, changes status to `published`, and rejects a replayed event ID.

## Test output

```text
6 passed
```

The GitHub Actions link in the capstone submission is the authoritative clean-machine run.


