# Security

This document describes the security posture as it **actually is**.

> **It supersedes the repository-root `SECURITY_DOCUMENTATION.md`**, which
> asserts controls that do not exist in the codebase — rate limiting, JWT
> authentication, PostgreSQL Transparent Data Encryption, column-level field
> encryption, encrypted Redis, and encrypted secrets at rest. None are
> implemented. That document also contradicts itself (line 49 claims JWT, line
> 312 correctly says DRF Token). If it was supplied to Ethio Telecom as evidence
> of security posture, it needs a correction issued.

---

## Credential exposure — act on this first

`.env`, `.env.production` and `render.env` (formerly nested under a `backend/`
directory that has since been flattened into the repository root) were
tracked in git. History contains multiple commits rotating and re-committing
Telebirr, Onevas and CRM credentials.

**Every secret that has ever been in this repository is compromised**, including
on `origin/master` and `origin/uat`.

Required:

1. Rotate `SECRET_KEY`, `DB_PASSWORD`, S3/MinIO keys, `VAPID_PRIVATE_KEY`,
   `ADMIN_PASSWORD`, and all Telebirr and Onevas credentials. Telebirr operator
   credentials must be reissued by Ethio Telecom. **Not yet done** — untracking
   the files does not rotate what they exposed.
2. ~~Untrack the files~~ **Done** — `.gitignore` now covers them and they were
   removed from the current index with `git rm --cached` (working-tree copies
   kept, only git no longer follows them). Still outstanding: purge history
   with `git filter-repo` across all three branches, since untracking a file
   in the current commit does not remove it from history a clone can still
   read.
3. Rotating `SECRET_KEY` invalidates sessions and password-reset tokens. DRF auth
   tokens are unaffected — they are random database rows, not signed.

The settings modules no longer carry credential defaults. A missing value now
yields an empty string, and production refuses to start.

---

## Authentication

| Property | Current state |
|---|---|
| Scheme | DRF `TokenAuthentication` (`Authorization: Token <key>`) |
| Password | Exactly 6 numeric digits — a 10⁶ keyspace |
| Hashing | Django PBKDF2, correct |
| Token expiry | **None.** A leaked token is valid indefinitely. |
| Token rotation | Only on password change |
| Rate limiting | **None anywhere in the application** |

The combination of a 6-digit PIN and no rate limiting means credentials are
brute-forceable in minutes. This is the highest-severity unfixed issue.

OTP has a 5-minute expiry and a 3-attempt cap — sound in design. It is now
backed by Redis rather than per-process memory, so the attempt counter is shared
across workers.

---

## Authorization

Admin endpoints consistently use `IsAdminUser` or explicit `is_staff` checks
(113 such checks). Spot-checking the `/api/v1/admin/*` surface found no gaps, and
object-scoped views generally filter by `user=request.user`. No systematic IDOR
was found. **This part is done well.**

The weakness is the default:

```python
# config/settings/base.py
'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny']
```

Every endpoint is public unless it opts in. This is preserved for now because
tightening it requires reviewing all 243 routes. It is the root cause of the
unauthenticated endpoints below.

---

## Endpoints that need removing

Not removed during the restructure — removing a route is an API change requiring
sign-off. Replacements are in place.

| Endpoint | Risk | Replacement |
|---|---|---|
| `POST /api/v1/setup-admin/` | Creates a Django superuser, unauthenticated, defaults to `Admin123!`. Promotes an existing user if the name matches. | `python manage.py create_superadmin` |
| `POST /api/v1/auth/reset-password/` | Sets any account's password from an email address. No token, no OTP. (Rate-limited as of the `password_reset` throttle scope -- see `common/throttling.py` -- but that only slows brute-forcing the endpoint; it does not verify the requester owns the email, which is the actual vulnerability.) | `forgot_password_confirm` / `forgot_password_phone_verify` already exist |
| `POST /api/v1/cleanup-reels/` | Unauthenticated. Nulls media on every Reel and Campaign. | `python manage.py cleanup_broken_media --apply --confirm` |
| `GET /api/v1/health/deep/` | Unauthenticated. Returns DB host and real usernames. | Restrict to staff |

---

## Webhooks

| Webhook | Verification |
|---|---|
| `POST /api/v1/wallet/telebirr-callback/` | **RSA PKCS#1 v1.5 + SHA-256, verified.** Correct. |
| `POST /api/v1/webhooks/telebirr-direct-debit/` | **None.** Correlates on `OriginatorConversationID`, which the backend generates as the guessable `FLP{user_id}{unix_timestamp}`. |
| `POST /api/v1/timwe/sync-order-relation` | Optional source-IP allowlist (`TIMWE_ALLOWED_IPS`); reached only over the operator tunnel. |

The OneVAS subscription webhooks (`/api/v1/onevas/…`), which had no
verification at all and let anyone POST a paid subscription into existence,
have been removed along with OneVAS.

The webhook URLs changed with the `/api/v1/` cutover (see
[docs/api.md](api.md#versioning)) -- each provider's callback configuration
must match, or it stops receiving callbacks entirely, independent of the
verification gaps above.

The Telebirr checkout callback shows the correct pattern. Apply it to the
direct-debit webhook, use `secrets.token_hex` for correlation IDs, and
allowlist provider source IPs.

The Telebirr webhooks are not idempotent; providers retry by default.

---

## Transport

Production settings (`config/settings/production.py`) now enforce:

- `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS=31536000` with preload and subdomains
- `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`
- `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY`, `SECURE_REFERRER_POLICY`

`manage.py check --deploy` passes clean. These settings existed before but were
in a module nothing loaded.

nginx sets no security headers of its own and has no `limit_req` zones.

---

## CORS

`common/middleware/cors.py` answers unknown origins with
`Access-Control-Allow-Origin: *` while also sending
`Access-Control-Allow-Credentials: true`. Browsers reject that pairing, and the
intent is unsafe regardless.

Preserved unchanged — correcting it is a behaviour change. The allow-list now
reads from `settings.CORS_ALLOWED_ORIGINS`, so the fix is configuration:
set `CORS_ALLOW_ALL_ORIGINS=false` and enumerate origins. Production settings
already refuse to start with it enabled.

---

## Logging

`common/middleware/logging.py` provides a `SensitiveDataFilter` that redacts
values keyed by password, otp, token, secret, credential, api_key,
application_key, private_key and authorization.

It is a backstop. Roughly 480 `print()` calls remain, several of which emit OTP
codes, password-hash prefixes and auth-token prefixes. Those bypass the filter
entirely because they write to stdout directly.

---

## Cryptography

| Use | Implementation | Assessment |
|---|---|---|
| Telebirr signing | RSA PKCS#1 v1.5, SHA-256, canonical JSON | Correct |
| Telebirr callback verification | Same, verified before trusting | Correct |
| API key generation | `secrets.token_urlsafe(48)` | Correct |
| OTP generation | `random.choice` | **Not cryptographically secure.** Use `secrets.randbelow`. |
| Password hashing | Django PBKDF2 | Correct |

---

## Data at rest

- No column-level encryption anywhere, despite the root document's claim.
- Backups are plain gzip, unencrypted, containing all user PII and financial records.
- User-uploaded media (34 files) is committed to git.
- Two database dumps, `flipstar_db` and `neondb` — both real SQLite databases,
  not empty placeholders — were tracked in git (`.gitignore` excluded the
  pattern but not retroactively; `git rm --cached` has since removed both
  from the index, working-tree copies kept). Still outstanding: they remain
  readable from git history in any existing clone until that history is
  purged (see "Credential exposure" above).

---

## Base images

`python:3.11-slim` is a floating tag and currently reports known critical and
high CVEs. Pin to a specific patch digest and rebuild on a schedule.

---

## Priority order

1. Rotate every credential; purge git history.
2. Delete the four endpoints listed above.
3. Verify signatures on the Telebirr direct-debit webhook. (The unauthenticated
   OneVAS webhooks are gone — removed with OneVAS.)
4. Add rate limiting to auth, OTP and payment endpoints (Redis cache is now
   configured, which was the blocker).
5. Flip the DRF default permission to `IsAuthenticated` and audit all 242 routes.
6. Replace remaining `print()` calls with the logging framework.
