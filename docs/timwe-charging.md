# TIMWE chargeAmount

Charging a subscriber's airtime through the TIMWE Master Aggregator.
Protocol reference: *New Partner Integration User Guide — TIMWE ETHIO MA v1.3*,
pp. 17–24.

> **Status: not yet proven against TIMWE.** The implementation is complete and
> tested against a mocked gateway, but the real endpoint has not been supplied,
> so no request has ever reached the MA. See [Before going live](#before-going-live).

## Not the SMPP link

| | SMPP | chargeAmount |
|---|---|---|
| Purpose | SMS / OTP delivery | Deduct a fee from airtime |
| Protocol | SMPP v3.4, persistent TCP | Parlay X 3.1, SOAP over HTTP |
| Address | `TIMWE_SMPP_HOST:PORT` | `TIMWE_CHARGE_URL` |
| Auth | bind `system_id` / password | `MD5(spId + Password + timeStamp)` per request |

**Never point `TIMWE_CHARGE_URL` at the SMPP host.** The guide gives the charge
endpoint's shape but not its address; TIMWE must supply it.

## Flow

```
POST /api/v1/charging/coin-purchase/   package_id + Idempotency-Key
  └─ api/views/charging.py              flag gate, request parsing, HTTP status
       └─ api/services/timwe_charging.py
            purchase_coins_with_airtime  price from CoinPackage, account's own number
              └─ request_charge          validate → PENDING row (committed)
                   └─ TimweChargeService.execute   SOAP → classify the reply
                   ← record exactly one outcome (claim_transition)
              └─ fulfil_coin_purchase    credit coins exactly once, on success only
```

The client (`api/integrations/timwe/charge.py`) speaks the protocol and
classifies answers. It records nothing and never retries. The service owns
the transaction, idempotency and fulfilment, and is the only caller.

## Configuration

All values resolve through Vault → environment → `.env`, declared in
`infrastructure/config/schema.py` under the `timwe` group. Staging path:
`secret/flipstar/backend/staging`.

| Key | Value | Who supplies it |
|---|---|---|
| `TIMWE_CHARGE_URL` | `http://IP:Port/AmountChargingService/services/AmountCharging` | **TIMWE — unknown today** |
| `TIMWE_SP_ID` | believed `300263` | TIMWE; matches SMPP login and partner-log `spID` |
| `TIMWE_SP_PASSWORD` | secret | **TIMWE — confirm; need not equal the SMPP password** |
| `TIMWE_SERVICE_ID` | believed `30026300007331` | TIMWE; partner log pairs it with `spID=300263` |
| `TIMWE_CURRENCY` | `ETB` | ISO 4217, three letters |
| `TIMWE_CHARGE_TIMEOUT` | `60` | Guide p.17: the MA answers within 60s |
| `TIMWE_AIRTIME_PURCHASE_ENABLED` | `false` | **Business decision** — see below |

Add missing keys with `vault kv patch` — never `put`, which replaces the whole
secret. Restart `flipstar-backend` afterwards.

## Authentication

```
timeStamp  = UTC now, yyyyMMddHHmmss          (guide p.20)
spPassword = MD5(spId + Password + timeStamp)  (guide p.20)
```

One clock read feeds both the header and the digest — two reads can straddle a
second boundary and fail as `SVC0901`. The password is hashed exactly once,
never sent, never logged; the digest is never logged either.

## Request

Namespaces are exactly those of the guide's example (p.19): Huawei
`common/v2_1` for the header, Parlay X `amount_charging/v3_1/local` for the
body. The MA replies in `v2_1` (p.22); the parser is namespace-agnostic rather
than the request changing to match.

| Field | Rule | Source |
|---|---|---|
| `OA`, `FA` | `251XXXXXXXXX`, identical | p.20–21 |
| `endUserIdentifier` | `tel:251XXXXXXXXX` | p.21 |
| `description` | mandatory, ≤ 255 | p.21 |
| `currency` | ISO 4217, 3 letters | p.21 |
| `amount` | positive integer, ≤ 4 digits, **no decimal point** | p.21–22 |
| `code` | optional, ≤ 30 | p.22 |
| `referenceCode` | mandatory, unique, ≤ 30 | p.21 |

MSISDNs go through `common.validators.phone.normalize_ethiopian_phone` — the
same normaliser as login and SMS — so `0912…`, `+251912…` and `251912…` all
reach the MA with the country code.

Amounts are validated, never rounded: `3.50` is refused, because sending `3`
under-bills and `4` over-bills. Floats and booleans are refused outright.

## Outcomes

Every call is classified into exactly one outcome. The distinction that
matters is whether it **proves** the subscriber was not charged.

| Outcome | Meaning | Charged? | Status | Retry? |
|---|---|---|---|---|
| `success` | `chargeAmountResponse` received | yes | `success` | — |
| `rejected` | SOAP Fault, or 4xx with no SOAP body | **no** | `failed` | per SVC/POL code, new key |
| `unreachable` | refused, DNS, connect timeout | **no** | `failed` | yes, new key |
| `timeout` | sent, no answer in the read deadline | **unknown** | `timeout` | **never** |
| `unknown` | unreadable reply, 5xx without Fault, reset after send | **unknown** | `unknown` | **never** |

Two details that decide safety:

- **`ConnectTimeout` is caught before `ReadTimeout`.** It subclasses both
  `ConnectionError` and `Timeout`; handled in the wrong order, a connection
  that never opened would be read as an ambiguous charge.
- **`ConnectionError` is split by its cause.** A refused connection or DNS
  failure wraps urllib3's `NewConnectionError` — nothing was sent. A reset
  *after* sending is a `ProtocolError` — the MA may already have charged.

Success requires an actual `chargeAmountResponse` element. Well-formed XML
without a Fault is **not** enough: a proxy's XML maintenance page would
otherwise read as a successful charge.

## Error codes

The MA's code lives in `<detail><messageId>` (Parlay X); `<faultcode>` is
usually SOAP's own classification (`soapenv:Server`) and is only used when it
is itself an `SVC`/`POL` code. The original code is always stored on the
transaction; the user sees a safe message from `user_message()`, never the
MA's text.

| Code | Guide meaning | Class | User is told |
|---|---|---|---|
| `SVC0001` | MA internal timeout | retryable | temporarily unavailable |
| `SVC0002` | blank / invalid field | permanent | temporarily unavailable |
| `SVC0901` | SP / password / service auth | permanent | temporarily unavailable |
| `SVC0270` | MDSP charge failed | retryable | check your airtime balance |
| `POL0910` | amount outside permitted range | permanent | amount cannot be charged |

`SVC0001` is the MA reporting *its* internal timeout — a definite fault. It is
not the same thing as *our* read timeout, which is ambiguous; the old client
conflated the two.

## Transaction lifecycle

`TimweChargeTransaction` answers: what was requested, from whom, how much,
when, under which reference, and what TIMWE said.

1. **Validate** configuration, MSISDN, amount, description. Failure raises
   before anything is recorded.
2. **Record `pending`** and commit — *before* calling the MA. If the process
   dies during the up-to-60s call, this row is the evidence a charge may be in
   flight.
3. **Call the MA** outside any database transaction.
4. **Record the outcome** once, via `claim_transition` from `pending`:
   `outcome`, `status`, `error_code`, `error_message`, `retryable`,
   `http_status`, `duration_ms`, `completed_at`.
5. **Fulfil** on success only: `fulfilled_at` is claimed and coins credited in
   one database transaction, so a charge is never marked fulfilled without its
   coins, nor credited twice.

Stored: the normalised MSISDN (reconciliation with TIMWE needs it), amount,
currency, description, reference. **Not** stored: the password, the digest,
the SOAP headers.

## Idempotency

- Every charge requires an idempotency key. The purchase endpoint takes it
  from the `Idempotency-Key` header (or `idempotency_key` in the body) and
  refuses without one — only the client knows two requests are the same
  purchase.
- `idempotency_key` and `reference_code` are both unique in the database.
- A repeated key returns the existing transaction **without calling the MA**,
  whatever its state — including `timeout`.
- The same key with a different amount or number is refused: silently
  returning the old result would report a charge the caller never asked for.
- **One transaction row is at most one MA call.** A retry is a new key, and
  should only be made when the last outcome was definitely-not-charged.

## Reconciliation

The guide defines no status query for chargeAmount. An ambiguous charge is
resolved by matching `reference_code` against TIMWE's records — never by
charging again to find out. Every generated reference is `FS` + 28 hex digits
(30 characters, the guide's limit), so FlipStar's charges are recognisable in
TIMWE reports. Coin credits carry the same reference in
`CoinTransaction.payment_reference`.

```sql
SELECT reference_code, status, outcome, error_code, amount, created_at
FROM api_timwechargetransaction
WHERE status IN ('timeout', 'unknown')
   OR (status = 'pending' AND created_at < now() - interval '5 minutes')
ORDER BY created_at;
```

## Automatic renewal of short-code subscriptions

`api/services/subscription_renewal.py`

When a TIMWE short-code subscriber's period runs out, the backend charges their
registered number once for the next period and renews the plan on a confirmed
charge. The client never asks for it and supplies none of its terms.

> **Before switching this on, ask TIMWE one question:** *does the MA renew and
> charge these subscriptions itself?* If it does, a charge from here is a
> **second charge for the same period**. Leave it off unless TIMWE confirms
> renewals on this service are the SP's to charge.

### Switches — both default off

| Setting | Meaning |
|---|---|
| `TIMWE_CHARGING_ENABLED` | Master switch. While false no chargeAmount is ever sent — coin purchases, renewals and `timwe_charge_check --charge` alike. |
| `TIMWE_SUBSCRIPTION_RENEWAL_ENABLED` | This flow. Renewal needs both. |

### What is renewable

A plan is renewed only when **all** hold:

- `payment_method='timwe'` and `subscription_source='sms'` — OneVAS, telebirr
  and coin plans never are;
- its tier is on `SMS_SHORT_CODE`, with a price and a duration (not on-demand);
- TIMWE recorded it under `TIMWE_SERVICE_ID`, when it recorded a service;
- status `active`, `expired` or `grace_period` with `end_date` in the past —
  **never `cancelled`**: that subscriber sent STOP;
- the account has no other active subscription;
- the account's registered number is the number TIMWE subscribed.

Amount = the tier's `price_etb`. Number = the profile's phone, normalised
(`9xxxxxxxx` → `2519xxxxxxxx`). Duration = the tier's `duration_days`, from now
— the one-off free-trial days are not granted again.

### Once per period

The period is *(plan, the `end_date` that ran out)*. It is charged at most once:

- the idempotency key is `sub-renewal:<plan>:<end_date>`, unique in the database;
- a partial unique constraint allows one renewal charge per
  `(subscription, renewal_period_end)`;
- a concurrent request finds the existing row and gets its state instead.

A **pending or ambiguous** attempt is never followed by another, and neither is
a **failed** one — the plan stays expired until the subscriber opts in again.

### Where it runs

| Trigger | How |
|---|---|
| `GET /subscription/status/` | **Queues** a Celery task (`renew_expired_subscription`) and answers immediately with `status: PAYMENT_PENDING`. It never waits on TIMWE. |
| Posting a video (`create_post`) | Renews **inline**. On a confirmed charge the post goes through; while one is pending it answers `403` with `code: PAYMENT_PENDING`. |

PIN reset does not trigger a charge.

### `/subscription/status/` additions

The existing fields are unchanged. Two are added:

| `status` | Meaning |
|---|---|
| `ACTIVE` | Subscribed. |
| `PAYMENT_PENDING` | A renewal is queued, in flight, ambiguous or paid-but-unapplied. Not "no subscription". |
| `EXPIRED` | A lapsed short-code subscriber not being renewed; `renewal.state` says why (`renewal_disabled`, `renewal_failed`, …). |
| `INACTIVE` | No subscription to renew. |

### After a success

The charge is marked fulfilled and the plan renewed, with a
`SubscriptionPayment` (`payment_method='timwe'`, the reference in
`onevas_transaction_id`) and a `renewed` history entry, all in one database
transaction. If that transaction fails after TIMWE has charged, the charge stays
success-but-unfulfilled; the next check applies it **without charging again**.

### Reconciliation

```
kubectl -n flipstar-staging exec deploy/flipstar-backend -- python manage.py timwe_charge_check --reconcile
```

Lists every PENDING, TIMEOUT or UNKNOWN charge and every one paid but not yet
applied, with its reference code, and summarises the last 24 hours by purpose
and status, latency and TIMWE error codes. It never charges.

Log events: `SUBSCRIPTION_RENEWAL_STARTED`, `…_QUEUED`,
`…_DUPLICATE_PREVENTED`, `…_APPLIED`, `…_FAILED`, `…_AMBIGUOUS`, `…_SKIPPED`,
`…_APPLY_FAILED`, plus the charge's own `TIMWE_CHARGE_REQUESTED` /
`TIMWE_CHARGE_COMPLETED` (latency, TIMWE error code). Numbers are masked.

## The business flow is switched off

Coin purchase via airtime (`purchase_coins_on_demand`) is the flow chargeAmount
was built for — `TimweChargeTransaction` replaces `OnevasChargingTransaction`.
It was **disabled by policy**: *"Ethio Telecom SIM cards are only accessible
for SMS OTP verification."*

`TIMWE_AIRTIME_PURCHASE_ENABLED` defaults to `false`, and with it off the
endpoint behaves exactly as before — the same 403, the same message. Turning it
on reverses that policy. That is a product decision, not a deployment detail.

The airtime price rule (`common/validators/payment.py`: 10 ETB only) is
enforced before the flag check, so it holds either way.

A second disabled flow, `initiate_on_demand_charging` (the `ondemand`
subscription tier), is not wired. `request_charge` accepts `subscription_tier`
and could serve it.

## Staging test

One command, run inside the backend pod. Safe by default:

```
kubectl -n flipstar-staging exec deploy/flipstar-backend -- python manage.py timwe_charge_check
```

It reports which settings are present (names only), builds a request without
sending it, and opens a TCP connection to the charge endpoint **from the pod** —
the host's network is not the pod's.

Only once every prerequisite below holds, charge once:

```
kubectl -n flipstar-staging exec deploy/flipstar-backend -- python manage.py timwe_charge_check \
    --charge --msisdn <approved-test-number> --amount 1 --username <staff-user> --confirm
```

Every flag is required. The charge goes through the production service, so it
is recorded, idempotent and masked in output. If it reports **AMBIGUOUS**, do
not run it again — reconcile the printed `reference_code` with TIMWE.

## Deploying is not activating

The code ships with every switch off, and nothing in the deployment turns one
on (a test fails the build if a manifest or env file ever does). Deploying runs
migration 0117 through the Argo CD Sync hook and changes no charging behaviour.

What holds charging off, in code rather than by convention:

| Guard | Where |
|---|---|
| `TIMWE_CHARGING_ENABLED` false → nothing is sent | `TimweChargeService.execute()` — the only function that sends a chargeAmount — and again in `request_charge`, before a row is written |
| Renewal needs `TIMWE_SUBSCRIPTION_RENEWAL_ENABLED` as well | `subscription_renewal.renewal_enabled()` |
| The guide's `http://IP:Port/...` template is refused | `TimweChargeService.endpoint_problem()`, checked by `ensure_configured()` |
| The SMPP gateway (`TIMWE_SMPP_HOST:TIMWE_SMPP_PORT`) is refused as the charge URL | the same |
| A charging password equal to the SMPP one is flagged for confirmation | `timwe_charge_check` |

### Verify a deployment — sends nothing

```
kubectl -n flipstar-staging exec deploy/flipstar-backend -- python manage.py showmigrations api | tail -2
kubectl -n flipstar-staging exec deploy/flipstar-backend -- python manage.py timwe_charge_check
kubectl -n flipstar-staging exec deploy/flipstar-backend -- python manage.py timwe_charge_check --reconcile
```

Expect `[X] 0117_timwe_subscription_renewal` and all three switches `off`. The
first check opens a TCP connection to `TIMWE_CHARGE_URL` if it is fully
configured — no HTTP, no charge; `--reconcile` only reads.

## Activation sequence

In this order, and not because a deploy succeeded:

1. Deploy; migration 0117 applied; switches verified **off**.
2. TIMWE supplies the real `AmountChargingService` address → `TIMWE_CHARGE_URL`.
3. TIMWE confirms the **charging** credentials — not assumed to be the SMPP ones.
4. TIMWE confirms the authentication mode: SP ID + Password, SP ID + IP +
   Password, or SP ID + IP. If IP is part of it, the egress address the MA sees
   must be registered with them.
5. `TIMWE_SERVICE_ID` and `TIMWE_CURRENCY` confirmed (and whether amounts are
   whole birr). Every value into Vault with `vault kv patch`.
6. `timwe_charge_check` passes from the backend pod.
7. `TIMWE_CHARGING_ENABLED=true`, then one confirmed 1-ETB charge to an
   approved test number (never a customer's), balance observed to drop, the
   reference found in TIMWE's records.
8. **Ask TIMWE: "Does the MA already renew and charge short-code
   subscriptions?"** — and get the answer in writing.
   * **Yes** → `TIMWE_SUBSCRIPTION_RENEWAL_ENABLED` stays **false**, for good.
     Renewal is theirs; ours would be a second charge for the same period.
   * **No, renewal is the SP's** → only then consider turning it on.
9. Separately, a product decision on `TIMWE_AIRTIME_PURCHASE_ENABLED` (it
   reverses the "SIM cards are for OTP only" policy).
