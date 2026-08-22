# Troubleshooting

Failures actually present in this system, and what causes them.

---

## The container will not start: `ImproperlyConfigured`

```
django.core.exceptions.ImproperlyConfigured: Refusing to start with an
unsafe production configuration:
  - SECRET_KEY is required in production but is empty.
  - Production requires PostgreSQL, got ENGINE='django.db.backends.sqlite3'.
```

**Working as intended.** `config/settings/production.py` validates at import and
lists every problem at once. Fill in the missing values in `.env`.

The previous behaviour was worse: the old settings module ran `SELECT 1` while
importing and silently rewrote `DATABASES` to a local SQLite file if it failed.
A startup blip brought the service up healthy against an empty throwaway database
that accepted writes and vanished with the container.

---

## WebSockets never connect

Chat, typing indicators, presence and delivery receipts do not work.

**Two independent causes; both must be fixed.**

### 1. Authentication can never succeed

`config/asgi.py` wraps the router in `AuthMiddlewareStack`, which resolves
`scope["user"]` from a Django **session cookie**. The API authenticates with DRF
**tokens** and issues no session, so `scope["user"]` is always `AnonymousUser` and
both consumers close immediately:

```python
# api/websockets/consumers.py
if self.scope["user"].is_anonymous:
    await self.close()
```

Fix: a `TokenAuthMiddleware` that reads the DRF token from the query string or
subprotocol and populates `scope["user"]`.

### 2. nginx does not route `/ws/`

The root `nginx.conf` has no `/ws/` location and sets no `Upgrade` headers, so
WebSocket requests fall through to `location /` and reach the React frontend.
See [deployment.md](deployment.md#nginx-does-not-route-websockets-or-the-django-admin).

---

## `/admin/` shows the React app

Same cause. The root `nginx.conf` proxies only `/static/`, `/media/` and `/api/v1/`
to the backend; `/admin/` falls through to the frontend. Django admin is
unreachable over HTTPS. Snippet in
[deployment.md](deployment.md#nginx-does-not-route-websockets-or-the-django-admin).

---

## Phone registration: fixed

`POST /api/v1/auth/register-with-phone/` used to raise
`OperationalError: no such table: api_phoneotp`.

The OTP flow was half-migrated. `send_phone_otp` and `verify_phone_otp` moved to
the cache-backed `OTPService`, but registration still looked for a verified row
in the `api_phoneotp` table that migrations 0051 and 0054 had dropped.

**Now:** `verify_phone_otp` leaves a single-use marker in the cache
(`phone_verified:<msisdn>`, 15-minute TTL) and registration consumes it. No
table, no migration, same store as the rest of the flow.

Two related fixes landed with it:

- `verify_phone_otp` and `register_with_phone` now normalize the phone number.
  `send_phone_otp` always did, so a caller sending `09XXXXXXXX` stored the code
  under `251XXXXXXXXX` and every subsequent lookup missed — every code read as
  "OTP expired or not found". All four accepted formats (`09…`, `+251…`,
  `251…`, `9…`) now work end to end.
- The marker is consumed on success, so one verification cannot register
  multiple accounts.

### Working flow

```
POST /api/v1/auth/send-phone-otp/     {"phone": "0912345678"}
    -> 200, and in DEBUG the response carries "dev_code"

POST /api/v1/auth/verify-phone-otp/   {"phone": "0912345678", "code": "<code>"}
    -> 200

POST /api/v1/auth/register-with-phone/
     {"phone": "0912345678", "username": "...", "password": "123456"}
    -> 201 with an auth token
```

Still true: the `skip_otp` bypass remains. An unlinked active SMS subscription
for the number skips verification entirely, so knowing a subscriber's phone
number is enough to claim the account. That is audit finding H-16 and is a
separate decision.

---

## Email password reset still fails with a database error

Two endpoints raise `ProgrammingError` / `OperationalError`:

- `POST /api/v1/auth/forgot-password/`
- `POST /api/v1/auth/forgot-password/confirm/`

**Cause.** `api/models/auth.py` declares `PasswordResetToken`, but its `user`
column was dropped:

| Migration | Effect |
|---|---|
| `0043` | Creates `PhoneOTP` and `PasswordResetToken` |
| `0051` | `DeleteModel PhoneOTP`; `RemoveField PasswordResetToken.user` |
| `0053` | Recreates `PhoneOTP` |
| `0054:285` | Deletes `PhoneOTP` again |

`api_passwordresettoken` exists without its `user` column, which
`views/core.py` queries directly (`PasswordResetToken.objects.filter(user=user)`).

**Pre-existing, not caused by the restructure.** Both models are deliberately
*not* exported from `api/models/__init__.py`; exporting them would register them
and make `makemigrations` want to recreate the tables.
`tests/integration/test_model_registry.py::test_unregistered_auth_models_stay_unregistered`
guards that.

**Fix requires a decision:** either add a migration restoring
`PasswordResetToken.user`, or retire the email reset path in favour of the phone
one. The phone-based reset (`forgot_password_phone_request` / `_verify`) does
**not** use these models and works — it goes through the cache-backed OTP
service, the same mechanism phone registration now uses.

---

## Registration succeeds but no SMS arrives

`OTPService.send_otp` returns success even when delivery fails:

```python
return True, f'OTP generated (SMS delivery failed: {response.text})'
```

The client shows "code sent" and monitoring stays green. Check the logs for
`SMS delivery failed` or `SMS error`, and verify `ONEVAS_APPLICATION_KEY` and
`ONEVAS_PRODUCT_NUMBER`.

---

## OTP verification fails intermittently

Symptom of running more than one worker process with a per-process cache.

`config/settings/base.py` now configures Redis as the Django cache, so OTP state
is shared. If you set `USE_LOCMEM_CACHE=true` you reintroduce the problem — that
flag is for local single-process development only.

Restarting the backend still invalidates in-flight OTPs, which is expected.

---

## Uploaded media disappears after redeploy

Object storage is not configured, so media falls back to the container
filesystem.

`env.production.example` documented `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY` and `AWS_STORAGE_BUCKET_NAME`, while the code read the
unprefixed names. An operator following the documented procedure got local
storage with no error.

`infrastructure/storage/config.py` now accepts both spellings. Verify:

```python
from infrastructure.storage import is_object_storage_enabled
is_object_storage_enabled()   # must be True
```

---

## Boosted posts return HTTP 500

`GET /api/v1/boost/eligible/` fails for any campaign with targeting.
`api/views/boost.py` reads `profile.gender`, `profile.age` and `profile.city`;
none of these fields exist on `UserProfile`. The `AttributeError` is caught by a
blanket handler and returned as 500, while the advertiser's coins continue to be
spent.

Fix requires a product decision: add the demographic fields, or remove targeting
from the boost purchase flow.

---

## A fresh database cannot be created — `Related model 'api.comment' cannot be resolved`

```
$ python manage.py migrate
  Applying api.0001_initial... OK
  Applying api.0063_add_mentions...
ValueError: Related model 'api.comment' cannot be resolved
```

**The migration history is not replayable.** No new environment can be
provisioned from it, database-backed tests cannot run, and recovery requires
restoring a dump rather than rebuilding the schema.

**Cause.** `api/migrations/0063_add_mentions.py` — a hand-written migration —
declares:

```python
dependencies = [('api', '0001_initial')]
```

Django honours that literally and schedules 0063 immediately after the initial
migration, long before `0002_comment` creates the `Comment` model. `Mention`
declares a foreign key to `api.comment`, which does not exist yet.

**Pre-existing.** Reproduces on an unmodified checkout of the base commit. Not
caused by the restructure.

**Fix.** One line — point it at its real predecessor:

```python
dependencies = [('api', '0061_subscriptionplan_setup_otp')]
```

Note `0062` does not exist; the numbering has gaps at 18, 19, 62, 64 and 67.
`0065_pushsubscription.py` has the same class of stale dependency
(`0055_add_free_trial_fields`); it does not currently break the build but should
be corrected in the same pass.

Existing deployed databases are unaffected — they applied these migrations
incrementally as they were written, so `django_migrations` already records them.
Only a from-scratch build hits this.

Until it is fixed, `tests/conftest.py` skips database-backed tests with a pointer
to this section. Flip `MIGRATIONS_ARE_REPLAYABLE = True` there once corrected.

---

## `makemigrations --check` reports drift on a clean tree

```
Migrations for 'api':
  0088_alter_message_media.py
    - Alter field media on message
```

**Pre-existing.** It reproduces at the base commit, before any restructuring.
`Message.media` declares `storage=message_media_storage`, a `FileSystemStorage`
instance built from `MEDIA_ROOT`/`MEDIA_URL`; its deconstructed form differs from
what the migration recorded.

Anything *beyond* this single line was introduced by a change — investigate it.

---

## `ImportError` from `api.serializers.subscription`

```
ImportError: cannot import name 'Subscription' from 'api.models.subscription'
```

**Pre-existing dead code.** The module imports a `Subscription` model that
`models/subscription.py` never defined (the model is `SubscriptionPlan`). Nothing
imports this module, so it has never executed. Left in place pending a decision
to delete it.

---

## Celery tasks vanish without an error

Only `process_reel_media` declares retries. Everything else uses Celery's
defaults: no retry, no dead-letter queue, and `acks_late=False`, so a worker
killed mid-task loses the task entirely.

There is also a single queue, so a backlog of ffmpeg transcodes starves push
notification delivery. Splitting into `media` and `default` queues is the fix.

---

## Subscriptions never expire

`ExpiredSubscriptionAction` is a fully modelled scheduled-action system —
`scheduled_at`, `action_status`, five action types — and **nothing executes it**.
The only registered beat job is `cleanup_typing_indicators`, which counts Redis
keys and deletes nothing.

Subscriptions appear expired only because reads compare `end_date` to now. No
process transitions status to `expired` or fires revocation.
