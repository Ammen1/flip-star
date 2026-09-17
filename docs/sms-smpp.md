# SMS over TIMWE SMPP

TIMWE SMPP is the only gateway for application SMS, OTPs included. OneVAS has
been removed: its HTTP gateway is gone from the code, and no setting can select
it. There is no fallback, deliberately — failing over to another gateway would
hide an SMPP outage.

## Shape

```
Django request
  └─ queue_sms()            writes SmsMessage(QUEUED), returns immediately
       └─ Celery, queue "sms"
            └─ SMS worker (1 replica, --pool=solo)
                 └─ TimweSmppGateway → SmppClient → submit_sm
                                             ↑
                                      deliver_sm (DLR) → SmsMessage.DELIVERED
```

No HTTP request ever binds SMPP, waits on a reconnect, or blocks on gateway
latency. A request that returns has a durable row; delivery is a later fact.

## Why a separate worker

SMPP is one authenticated, long-lived TCP session and operators cap how many
an account may hold. The general worker runs 2 replicas × `--concurrency=4`,
so putting SMS there would open up to **eight** binds and have eight processes
writing to sockets `smpplib` does not guard.

`flipstar-sms-worker` is therefore 1 replica, `--pool=solo`, `--queues=sms`,
`strategy: Recreate` (a rolling surge would briefly run two binds). The general
workers never receive these tasks because `CELERY_TASK_ROUTES` sends
`api.tasks.sms.*` to the `sms` queue, which they do not consume.

`SMS_WORKER=true` is set only on that Deployment. `api/celery.py` binds SMPP on
`worker_init` only when it is set, and unbinds on `worker_shutdown` so the
gateway frees the slot immediately instead of waiting for a timeout.

## Configuration

All values resolve through the normal chain — Vault → environment → `.env` —
and are declared in `infrastructure/config/schema.py` under the `sms` group.

| Key | Meaning |
|---|---|
| `SMS_PROVIDER` | `timwe_smpp` in production. Unset or unknown raises rather than defaulting. |
| `TIMWE_SMPP_HOST` / `TIMWE_SMPP_PORT` | Gateway address, e.g. `10.175.206.42` / `6986`. |
| `TIMWE_SMPP_SYSTEM_ID` | Bind login. |
| `TIMWE_SMPP_PASSWORD` | Bind password. **Secret — Vault only.** |
| `TIMWE_SMPP_SYSTEM_TYPE` | Sent on bind. Blank unless TIMWE specify one. |
| `TIMWE_SMPP_SOURCE_ADDR` | What the handset shows as sender. |
| `TIMWE_SMPP_SOURCE_TON` / `_NPI` | Source addressing. Default `3` / `0` (national short code). |
| `TIMWE_SMPP_DEST_TON` / `_NPI` | Destination addressing. Default `1` / `1` (international ISDN). |
| `TIMWE_SMPP_SERVICE_TYPE` | On `submit_sm`. Blank unless required. |
| `TIMWE_SMPP_REGISTERED_DELIVERY` | `1` requests a DLR. `0` means status can never pass `submitted`. |
| `TIMWE_SMPP_ENQUIRE_LINK_SECONDS` | Keepalive on an idle bind. Default 30. |
| `SMS_WORKER` | `true` on the SMS worker only. |

### system_id is not TIMWE_SP_ID

`TIMWE_SP_ID` and `TIMWE_SP_PASSWORD` already existed and are read **only** by
`api/integrations/timwe/charge.py` — the HTTP charging API. They are not SMPP
credentials and nothing infers one from the other.

This matters because integration material quotes **two** different SP
identifiers, `300263` and `015164`. Nothing here chooses between them: set
`TIMWE_SMPP_SYSTEM_ID` from the SMPP credentials TIMWE supplied, and
`TIMWE_SMPP_SOURCE_ADDR` from what should appear on the handset. They are
separate settings because they answer separate questions — one authenticates
the link, the other labels the message.

## What the app sends

Every message carries a `purpose`, which is how the ledger is read back.

| `purpose` | When | Where |
|---|---|---|
| `otp_<action>` (`otp_login`, `otp_password_reset`, …), `otp_subscription_setup` | The user asks for a code | `api/services/otp.py`, `api/views/direct_debit.py` |
| `subscription_welcome` | First charge on the short code: what they bought, the link and the OTP | `api/views/timwe.py` |
| `subscription_renewal` | A period charged again — by the MA, or by our own renewal job. No OTP: the subscriber's existing code stays valid | `api/views/timwe.py`, `api/services/subscription_renewal.py` |
| `subscription_cancelled` | They texted STOP. Without it, the only sign the cancellation worked is a charge that never arrives | `api/views/timwe.py` |
| `withdrawal_paid` | The payout left, with the reference to quote to telebirr or the bank | `api/services/withdrawal_sms.py` |
| `withdrawal_failed` | It did not, and what happened to the points | `api/services/withdrawal_sms.py` |

Two rules hold across all of them:

* **One message per event.** The idempotency key names the event — the MA's
  `transactionID`, the charge's reference code, `withdrawal:<id>:paid` — so a
  retried notification or a repeated Telebirr webhook cannot text somebody
  twice.
* **A message is never allowed to undo the thing it reports.** Every caller
  queues outside the transaction and swallows failures: a subscription that
  was charged, a cancellation the MA already applied, and a payout that has
  left all stand whether or not the SMS could be queued.

## Delivery state

`SmsMessage.status` distinguishes acceptance from delivery:

| Status | Meaning |
|---|---|
| `queued` | Recorded, not yet submitted. |
| `submitted` | The gateway accepted it. **Not** proof a handset received it. |
| `delivered` | A DLR said `DELIVRD`. |
| `failed` | Submission failed, or a DLR reported failure. |
| `rejected` | The gateway refused it. |
| `expired` | A DLR said `EXPIRED`. |

## Idempotency, and the ambiguous case

Every message carries a unique `idempotency_key`. Queueing the same key twice
returns the existing row rather than creating a second — that is what stops a
Celery retry, a duplicated task or a worker restart producing a second OTP that
silently invalidates the first.

A failure **after** `submit_sm` is different from one before it. The gateway
may already hold the message. `SmppSubmitUncertain` therefore marks the row
`failed` *and* sets `submitted_at`, so nothing retries it. This is a deliberate
bias: a subscriber who receives nothing contacts support, while one who
receives two codes can log in with neither.

Only `SmppConnectionError` — where nothing reached the gateway — is retried,
with exponential backoff, up to 5 attempts.

## Operations

```
GET /api/v1/admin/sms/health/     # staff only
```

Reports bind state, reconnect count, last `enquire_link`, last submit, last
error, message counts by status, and the oldest still-queued message. It never
sends a test SMS and never exposes credentials.

Structured log events: `SMS_QUEUED`, `SMS_SUBMIT_STARTED`, `SMS_SUBMITTED`,
`SMS_SUBMIT_FAILED`, `SMS_SUBMIT_UNCERTAIN`, `SMS_DELIVERED`,
`SMS_DELIVERY_FAILED`, `SMPP_CONNECTING`, `SMPP_CONNECTED`, `SMPP_BOUND`,
`SMPP_BIND_FAILED`, `SMPP_DISCONNECTED`, `SMPP_RECONNECTING`. Recipients are
masked (`25191****678`); the password and `system_id` never appear.

## No rollback to OneVAS

OneVAS has been removed. `SMS_PROVIDER=onevas_http` used to select its HTTP
gateway as an emergency rollback; that gateway is deleted and the value now
fails at the first send like any other unknown provider. The OTP service no
longer takes a OneVAS application key or product number either.

## Not yet verified

The SMPP bind, a real `submit_sm` and DLR behaviour have **not** been tested
against the live TIMWE gateway. `telnet 10.175.206.42 6986` connecting proves
TCP reachability only — not that the credentials authenticate, that the
addressing is what TIMWE expect, or that receipts arrive. Treat this as
unproven until a real bind and a test submission have been run.
