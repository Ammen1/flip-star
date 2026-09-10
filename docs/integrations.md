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

## TIMWE — SMS (SMPP)

`api/services/otp.py` → `api/services/sms/` → `api/integrations/smpp/`

Every SMS — OTPs for registration, login and PIN reset, subscription welcome
messages, notices — is queued as an `SmsMessage` and submitted over TIMWE SMPP
by a single-replica worker. There is no other gateway and no fallback. Full
detail: [sms-smpp.md](sms-smpp.md).

**OTP state is in the Django cache**, backed by Redis (`REDIS_URL/1`).

Policy: 6 digits, 5-minute expiry, 3 attempts, one send per minute per number.

**Known:** codes are generated with `random.choice`, which is not
cryptographically secure. Use `secrets.randbelow`.

---

## TIMWE — subscriptions and airtime charging

Subscriptions arrive as `syncOrderRelation` notifications from the TIMWE Master
Aggregator (`api/views/timwe.py`, logged on `TimweSyncOrderLog`). Airtime
charging is TIMWE `chargeAmount` (`api/integrations/timwe/charge.py`), recorded
on `TimweChargeTransaction` — see [timwe-charging.md](timwe-charging.md).

Tier resolution falls back through: product id → SMS keyword
(`1`→daily, `2`→weekly, `3`→monthly, `4`→ondemand).

---

## OneVAS — removed

OneVAS has been removed. Its SMS gateway, its airtime charging client, its four
webhooks at `/api/v1/onevas/…` and every `ONEVAS_*` setting are gone, and
`SMS_PROVIDER` cannot select it.

What remains is data: `OnevasWebhookLog` and `OnevasChargingTransaction` keep
their history (visible in the admin), and past OneVAS subscriptions are
ordinary `SubscriptionPlan` rows. The `onevas_*` columns on those rows are
reused by TIMWE subscriptions, and `SubscriptionTier.onevas_code` is still the
tier identifier the telebirr mandate flow uses.

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
| **No idempotency keys** | A retried Telebirr webhook reprocesses. (TIMWE datasync and SMS are keyed; see their docs.) |
| **No reconciliation** | If Telebirr succeeds but the callback never arrives, money is taken and nothing is credited. There is no job to detect this. |
| **No circuit breakers** | A slow provider ties up Daphne workers for the full 30s timeout. |
| **No retry policy** | Only `process_reel_media` declares retries. Provider calls do not retry at all. |
| **Timeout semantics** | A timeout leaves the remote outcome *unknown*, not failed. `common.exceptions.IntegrationTimeout` exists to model this; no call site uses it yet. |

The minimum fix is a unique constraint on each provider transaction ID plus
`get_or_create` inside a transaction, returning 200 for a duplicate without
reprocessing.
