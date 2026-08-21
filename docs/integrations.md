# External integrations

All provider code lives under `api/integrations/`. Business logic calls into
these clients; it must not construct provider requests directly.

---

## Telebirr — checkout (REST)

`api/integrations/telebirr/checkout.py`

Coin purchases. The customer is redirected to Telebirr, pays, and Telebirr calls
back.

| Operation | Method |
|---|---|
| Create order | `initiate_payment(amount, phone_number, user_id, package_id)` |
| Handle callback | `process_callback(callback_data)` |
| Query status | `query_payment_status(transaction_id)` |

**Signing:** RSA PKCS#1 v1.5 over SHA-256, canonical JSON
(`sort_keys=True`, no whitespace), base64-encoded.

**Callback verification is implemented and correct** — the signature is checked
before the result is trusted. This is the reference for the other two webhooks.

Configuration: `TELEBIRR_BASE_URL`, `TELEBIRR_FABRIC_APP_ID`,
`TELEBIRR_APP_SECRET`, `TELEBIRR_MERCHANT_APP_ID`, `TELEBIRR_MERCHANT_CODE`,
`TELEBIRR_PRIVATE_KEY`, `TELEBIRR_PUBLIC_KEY`, `TELEBIRR_NOTIFY_URL`,
`TELEBIRR_RETURN_URL`.

---

## Telebirr — direct debit (SOAP)

`api/integrations/telebirr/direct_debit.py`

Recurring subscription payments via mandates.

```
create_mandate    -> pending_created
                     (webhook delivers the real MandateID)
activate_mandate  -> active
initiate_debit    -> DirectDebitTransaction
cancel_mandate    -> cancelled
```

Configuration: `TELEBIRR_SOAP_URL`, `TELEBIRR_THIRD_PARTY_ID`,
`TELEBIRR_THIRD_PARTY_PASSWORD`, `TELEBIRR_SHORTCODE`, `TELEBIRR_RESULT_URL`,
`TELEBIRR_SP_OPERATOR_ID`, `TELEBIRR_SP_OPERATOR_CREDENTIAL`,
`TELEBIRR_ORG_OPERATOR_ID`, `TELEBIRR_ORG_OPERATOR_CREDENTIAL`.

### Webhook

`POST /api/v1/webhooks/telebirr-direct-debit/` receives a SOAP `Result` envelope as
`text/xml`. DRF cannot parse it, so `views/direct_debit.py` extracts fields from
the raw body with regex and correlates on `OriginatorConversationID`.

**Two defects:**

1. No signature verification. The envelope is trusted as received.
2. The correlation ID is generated as `FLP{user_id}{unix_timestamp}` — guessable.

Together these let an attacker forge a success result and activate a mandate.
Fix: verify the signature, and generate the correlation ID with
`secrets.token_hex`.

The endpoint always returns HTTP 200, deliberately, to avoid retry storms.

---

## Onevas — SMS

`api/services/otp.py`

OTP delivery for registration and password reset. Posts to
`ONEVAS_SMS_URL` with `application_key`, `phone_number`, `text`, `product_number`.

**OTP state is in the Django cache**, now backed by Redis (`REDIS_URL/1`).
Previously no `CACHES` was configured at all, so it used per-process memory —
OTP verification would have failed roughly half the time behind more than one
worker, and the rate limiter was bypassable by hitting a different process.

Policy: 6 digits, 5-minute expiry, 3 attempts, one send per minute per number.

**Known defect:** `send_otp` returns success when delivery fails —
`return True, 'OTP generated (SMS error: ...)'` on both the exception path and a
non-200 response. During an Onevas outage, registration appears to work and no
user can complete it, with no error surfaced.

**Also:** codes are generated with `random.choice`, which is not
cryptographically secure. Use `secrets.randbelow`.

---

## Onevas — airtime charging

`api/integrations/onevas/charging.py`

On-demand subscription purchases charged to the user's airtime balance. Posts to
`ONEVAS_CHARGING_URL`; `parse_charging_response` maps the reply to
`success` / `insufficient_balance` / `failed`.

Results are recorded on `OnevasChargingTransaction`.

### Subscription webhooks

`OnevasWebhookView` handles four types at
`/api/v1/onevas/{subscription,unsubscription,renewal,stop}/`.

**There is no authentication, signature check, or source-IP allowlist.** Anyone
can POST a phone number and product code to activate a paid subscription. This is
the single highest-value unfixed issue in the integration layer.

Tier resolution falls back through: `product_number` → SMS keyword
(`1`→daily, `2`→weekly, `3`→monthly, `4`→ondemand). STOP keywords map
`STOP1`/`STOP2`/`STOP3`/`STOP` to the corresponding tier.

`OnevasWebhookLog` records every delivery but is written *after* routing and is
never consulted, so it does not provide deduplication.

---

## Web Push (VAPID)

`api/integrations/push/webpush.py`

Browser notifications. Subscriptions are stored per browser endpoint on
`PushSubscription`. Fanned out by a `post_save` signal on `Notification`.

Configuration: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`.
Silently no-ops when unset.

---

## FCM (mobile push)

`api/tasks/media.py::send_push_notification`

Celery task posting to the legacy `fcm.googleapis.com/fcm/send` endpoint with
`FIREBASE_SERVER_KEY`. Note that this legacy API is deprecated by Google in
favour of HTTP v1 with OAuth2; migration is outstanding.

---

## Cross-cutting gaps

Apply to every provider above.

| Gap | Consequence |
|---|---|
| **No idempotency keys** | A retried webhook reprocesses. A retried Onevas subscription extends the subscription twice and writes a duplicate payment. |
| **No reconciliation** | If Telebirr succeeds but the callback never arrives, money is taken and nothing is credited. There is no job to detect this. |
| **No circuit breakers** | A slow provider ties up Daphne workers for the full 30s timeout. |
| **No retry policy** | Only `process_reel_media` declares retries. Provider calls do not retry at all. |
| **Timeout semantics** | A timeout leaves the remote outcome *unknown*, not failed. `common.exceptions.IntegrationTimeout` exists to model this; no call site uses it yet. |

The minimum fix is a unique constraint on each provider transaction ID plus
`get_or_create` inside a transaction, returning 200 for a duplicate without
reprocessing.
