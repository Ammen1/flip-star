# API

243 routes under `/api/v1/`, declared in `api/urls.py`, implemented across
`api/views/`.

> **Postman collection:** [`docs/postman/`](postman/) — 376 requests across 34
> folders, generated from the URL resolver so it matches the served routes
> exactly. Import it plus the bundled environment, run the login request, and
> the auth token is captured automatically.

## Authentication

```
Authorization: Token <key>
```

Obtain a token from `POST /api/v1/auth/login/`, `/api/v1/auth/login-with-phone/`, or
any of the registration endpoints. Tokens expire after `AUTH_TOKEN_TTL_DAYS`
(default 14 days) -- see `common/authentication/tokens.py`.

## Route groups

| Prefix | Module |
|---|---|
| `/api/v1/auth/` | `views/core.py` |
| `/api/v1/posts/`, `/api/v1/reels/`, `/api/v1/explorer/` | `views/core.py`, `views/reels.py` |
| `/api/v1/comments/`, `/api/v1/saved/` | `views/extended.py` |
| `/api/v1/messages/` | `views/messaging.py` |
| `/api/v1/wallet/`, `/api/v1/coins/` | `views/wallet.py`, `views/contest.py` |
| `/api/v1/subscriptions/`, `/api/v1/onevas/` | `views/subscription.py` |
| `/api/v1/direct-debit/`, `/api/v1/charging/` | `views/direct_debit.py`, `views/charging.py` |
| `/api/v1/campaigns/` | `views/campaign*.py` |
| `/api/v1/boost/` | `views/boost.py` |
| `/api/v1/gamification/` | `views/gamification.py` |
| `/api/v1/gifts/` | `views/gift.py` |
| `/api/v1/legal/`, `/api/v1/support/`, `/api/v1/push/` | `views/legal.py`, `views/support.py`, `views/push.py` |
| `/api/v1/admin/` | `views/admin.py`, `views/settings.py`, `views/campaign_admin.py`, … |

Health:

| Endpoint | Behaviour |
|---|---|
| `GET /api/v1/health/` | Liveness. No DB access. Safe for frequent probes. |
| `GET /api/v1/health/deep/` | Diagnostics. Touches the DB. Currently unauthenticated — restrict it. |

## The contract is pinned by tests

`tests/integration/test_url_contract.py` asserts that every sampled route still
reverses to the same path and dispatches to the same view name, and that
`api/urls.py` still declares exactly 243 patterns.

A failure means a released mobile client breaks. Treat it as a release blocker,
not a test to update.

---

## Known inconsistencies

These are pre-existing. They are documented rather than fixed, because changing
any of them breaks consumers.

### Error shapes vary by endpoint

Three different shapes are in use:

```jsonc
// function-based views
{ "error": "Insufficient balance. Have 40, need 100." }

// DRF built-ins (auth, permission, 404, throttle)
{ "detail": "Authentication credentials were not provided." }

// serializer validation
{ "point_amount": ["This field is required."] }
```

A client must handle all three. `common/exceptions/handlers.py` deliberately
preserves each one — it adds logging and guarantees no traceback leaks, but does
not reshape bodies.

### Status codes are inconsistent

- `GET /api/v1/boost/eligible/` returns **500** for a missing profile attribute
  (`profile.gender` does not exist on `UserProfile`).
- `POST /api/v1/boost/impression/` returns **200** with `{"success": false}` for a
  business-rule rejection.
- `POST /api/v1/webhooks/telebirr-direct-debit/` always returns **200** by design,
  to avoid provider retry storms.

### Duplicate routes

Four paths are registered twice. Django resolves the first, so the second
handler is unreachable:

| Path | Reachable | Dead |
|---|---|---|
| `/api/v1/coins/purchase/` | `views/contest.py::purchase_coins` | `CoinTransactionViewSet.purchase` |
| `/api/v1/admin/wallet/withdrawals/` | first registration | second |
| `/api/v1/admin/wallet/withdrawals/<id>/action/` | first | second |
| `/api/v1/admin/wallet/adjust-balance/` | first | second |

### No pagination default

`REST_FRAMEWORK` sets no `DEFAULT_PAGINATION_CLASS`, so most list endpoints
return every row. Wallet and admin views hand-roll offset pagination with a
`{count, page, page_size, has_next, has_prev, results}` envelope.

`common/pagination/StandardResultsPagination` reproduces that exact shape, so
those views can adopt it without a contract change.
`CursorResultsPagination` is available for large append-only tables.

---

## Versioning

The API surface is mounted at `/api/v1/` (`config/urls.py`:
`path('api/v1/', include('api.urls'))`). Every route in `api/urls.py` inherits
the prefix from that single include -- individual `path()` declarations stay
unprefixed.

This was a deliberate hard cutover, not an alias: the previously unversioned
`/api/<resource>/` paths no longer resolve at all. That was an explicit choice
to replace rather than dual-serve both prefixes, made with the tradeoff
understood -- **any client still calling the old unversioned paths (the
released mobile app, in particular) breaks until it's updated to call
`/api/v1/...` instead.** This also affects inbound webhooks: Telebirr and
Onevas call back to URLs (`TELEBIRR_RESULT_URL`, `TELEBIRR_NOTIFY_URL`, etc.)
that were configured against the old unversioned paths. Those need updating
to the new `/api/v1/...` paths in both this project's environment
configuration *and* on the provider's side (their webhook target
configuration), or callbacks will 404 in production.

## Planned work

### Schema

No OpenAPI document exists. `drf-spectacular` would generate one from the
existing serializers with modest annotation effort, giving clients a contract and
enabling generated SDKs.
