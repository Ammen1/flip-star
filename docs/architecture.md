# Architecture

## Shape

A modular monolith. One Django app (`api`), one Celery worker pool, one
PostgreSQL database, Redis for cache/channels/broker, S3-compatible object
storage for media.

This is the right shape for the product's current stage. The problems worth
solving are *inside* the monolith, not in splitting it apart — see
[Known duplication](#known-duplication).

## Why one Django app

`api` holds 94 registered models. Only 14 declare an explicit `db_table`; the
other 80 derive their table name from the app label (`api_reel`,
`api_userprofile`, …).

Moving models to new apps therefore renames their tables, which means:

- 97 migration cross-references to the `'api'` label become invalid
- raw SQL in `api/tasks/media.py` and `api/views/core.py` that hardcodes
  `api_reel`, `api_userprofile`, `api_campaignentry` breaks silently at runtime
- index names baked into migrations (`api_reel_user_id_4de8e3_idx`) no longer match

Doing it safely requires pinning `db_table` on every model *and* paired
`SeparateDatabaseAndState` migrations in both the old and new app. That is a
data-migration project against a live financial database.

The layering below achieves the same legibility without touching the schema.
`tests/integration/test_model_registry.py` enforces it.

## Layers

```
    api/views/          HTTP: routing, authn/authz, status codes
         │
         ▼
    api/serializers/    field validation, representation
         │
         ▼
    api/services/       business workflows
         │
         ├──────▶ api/integrations/   external providers
         ▼
    api/models/         persistence
```

### Rules

1. **Views** receive requests, authorize, delegate, and shape responses. They do
   not implement multi-step business workflows.
2. **Serializers** validate fields and represent data. They do not orchestrate.
3. **Services** own business workflows and are the only layer that should
   coordinate multiple models plus an external call.
4. **Integrations** own provider transport: HTTP/SOAP, signing, parsing, error
   mapping. A service calls an integration; it never builds a provider request.
5. **`common/` and `infrastructure/` must never import from `api/`.** They are
   generic support code. This is the one dependency rule that keeps the graph
   acyclic.

### Where the current code does not yet follow the rules

The restructure moved code without rewriting it. Several views still contain
business logic that belongs in a service — most notably:

- `api/views/core.py::create_post` — coin charging, ffmpeg probing, thumbnail
  extraction and reel creation, inline in the request path
- `api/views/wallet.py::request_withdrawal` — balance mutation inline

Extracting these is follow-up work. The directory structure now makes the
target obvious; the moves themselves were deliberately out of scope.

## Known duplication

Five subsystems exist in two or three parallel generations. This is the largest
source of maintenance cost in the codebase.

| Domain | Implementations | Recommended survivor |
|---|---|---|
| Subscriptions | `models/core.Subscription`, `models/contest.UserSubscription`, `models/subscription.SubscriptionPlan` | `SubscriptionPlan` — the telecom integrations use it |
| Coins | `models/contest.{UserCoinBalance,CoinTransaction}`, `models/subscription.SubscriptionCoinTransaction`, `UserProfile.coins` | `UserCoinBalance` + `CoinTransaction` |
| Scoring | `models/contest.ContestPostScore`, `models/campaign_extended.PostScore` + `services/scoring/` | `PostScore` + the engine |
| Gifts | `models/contest.GiftToCreator`, `models/gift.GiftTransaction` | `GiftTransaction` |
| Boosts | `models/contest.PostBoost`, `models/boost.BoostCampaign` | `BoostCampaign` |

`api/views/subscription.py::UserSubscriptionStatusView` already queries two
subscription systems and falls back between them.

Consolidating these requires data migration and should be done one domain at a
time, behind tests, with a reconciliation script proving no balance changed.

## Data flow: a coin purchase

```
POST /api/v1/wallet/telebirr/initiate/
  └─ views/wallet.py::telebirr_initiate_payment
       ├─ resolves CoinPackage
       ├─ integrations/telebirr/checkout.py::initiate_payment   (RSA-signed)
       └─ writes a pending CoinTransaction

  ... user completes payment in Telebirr ...

POST /api/v1/wallet/telebirr-callback/          [unauthenticated by design]
  └─ views/wallet.py::telebirr_callback
       ├─ integrations/telebirr/checkout.py::process_callback   (verifies RSA signature)
       ├─ UserCoinBalance.add_purchased()
       └─ marks the CoinTransaction successful
```

Two gaps in this flow are documented in [integrations.md](integrations.md): there
is no idempotency key, and there is no reconciliation job for the case where
Telebirr succeeds but the callback never arrives.

## Realtime

`config/routing.py` maps two WebSocket routes to consumers in
`api/websockets/consumers.py`:

- `ws/chat/<conversation_id>/` — messages, typing, delivery receipts
- `ws/presence/` — online/offline

Both are currently unreachable in production. See
[troubleshooting.md](troubleshooting.md#websockets-never-connect).

## Background work

`api/tasks/` holds Celery tasks; `config/settings/base.py` configures the broker.
One beat schedule is registered (`cleanup_typing_indicators`, every 60s).

Several modelled scheduled behaviours have no scheduler entry —
`ExpiredSubscriptionAction` is a complete scheduled-action system that nothing
executes. Subscriptions expire only by `end_date` comparison at read time.
