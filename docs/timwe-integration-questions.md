# TIMWE Master Aggregator — integration information required

**From:** FlipStar (Skykin Technologies)
**Re:** *New Partner Integration User Guide*, draft 14-04-2023
**Status:** FlipStar's side is implemented against the guide and unit-tested. We cannot connect, test, or go live until the items below are supplied.

We have implemented, from the guide:

- **`syncOrderRelation`** receiver (guide pp.10–17) — SOAP, all mandatory and optional fields, `extensionInfo`, `updateType` 1/2/3, the 30-second response budget, and result codes 0 / 1211 / 2030 / 2031 / 2032 / 2033 / 2034 / 2500.
- **`chargeAmount`** client (guide pp.17–24) — Parlay X 3.1, `spPassword = MD5(spId + Password + timeStamp)`, the full `RequestSOAPHeader`, `endUserIdentifier` / `charge` / `referenceCode`, and fault codes SVC0001 / SVC0002 / SVC0901 / SVC0270 / POL0910.

---

## 1. What we need from TIMWE

### 1.1 chargeAmount endpoint

The guide gives the path but not the host (p.19: *"IP and Port indicate the service IP address and Parlay X 3.1 port number of the API provided by the MA"*).

| Item | Value needed |
|---|---|
| Host / IP | |
| Port | |
| Full URL | `http://____:____/AmountChargingService/services/AmountCharging` |
| TLS? | Is there an HTTPS endpoint? If so, please supply that instead. |
| Separate UAT/sandbox endpoint? | |

### 1.2 Partner credentials

Allocated by the MA on registration (guide p.20).

| Item | Value needed |
|---|---|
| `spId` | |
| `Password` (for the MD5 digest — **not** transmitted) | |
| `serviceId` | |
| Authentication mode | SP ID + Password / SP ID + IP + Password / SP ID + IP |
| If IP-based: which of our IPs should be registered? | our egress is `196.189.236.140` |

### 1.3 Product and service identifiers

We need the MA-side `productID` and `serviceID` for each of our four subscription products, so `syncOrderRelation` events can be matched to the right one.

| FlipStar product | Price (ETB) | `productID` | `serviceID` |
|---|---|---|---|
| Daily | 3 | | |
| Weekly | 20 | | |
| Monthly | 70 | | |
| On-demand | 10 | | |

Also: are any of these **bundle** products? If so, please give the subservice IDs that will appear in `serviceList` (guide p.14).

### 1.4 SMPP access

Guide pp.24–26 describe bind, submit, DLR and charge-MT behaviour but give no connection details (*"MA will provide the SMPP IP, Port and credentials"*).

| Item | Value needed |
|---|---|
| SMPP host | |
| SMPP port | |
| `system_id` | |
| Password | |
| Bind type | guide says Transceiver — please confirm |
| Dedicated account per price point? | guide p.25 implies one per MT-billing service |
| Source address / short code | |

### 1.5 Source IP addresses

`syncOrderRelation` carries **no authentication** — the guide states the request has no header parameters at all (p.13). Our endpoint is therefore reachable by anyone who learns the URL, and a forged request could grant or cancel a paid subscription.

We have built an IP allowlist and need the addresses the MA will call us from:

| Item | Value needed |
|---|---|
| MA egress IP(s) for datasync calls | |
| Do these differ between UAT and production? | |

If TIMWE can additionally support HTTP Basic auth, a shared secret header, or mutual TLS on this callback, we would prefer that in addition to the allowlist. Please advise what is available.

---

## 2. Questions where the guide is ambiguous

These affect **billing correctness**. We have deliberately not guessed.

### 2.1 Amount format — how is 3.00 ETB expressed?

Guide p.21 specifies `amount` as `xsd:decimal`, length **4**, and states *"The MA system does not support the decimal point currently."*

Our prices are whole birr (3, 20, 70, 10), so we believe we send the integer birr value:

```xml
<amount>20</amount>   <!-- 20.00 ETB -->
```

**Please confirm.** The alternative reading — minor units, i.e. `<amount>2000</amount>` for 20.00 ETB — would be a **100× billing error** in either direction. Our implementation currently rejects any amount with a fractional part rather than rounding it, so nothing can be silently mis-billed while this is open.

Related: with a 4-character limit, is the maximum chargeable amount 9999?

### 2.2 Currency code

The guide is internally inconsistent:

- p.19 request example: `<currency>RAND</currency>`
- p.21 parameter table: *"[Example] USD"*

For Ethio Telecom we expect **`ETB`** (ISO 4217). **Please confirm the exact string.** Note `RAND` is not a valid ISO 4217 code (the South African rand is `ZAR`), which suggests the example is illustrative rather than normative.

### 2.3 `referenceCode` and idempotency

Guide p.21 defines `referenceCode` as *"Unique ID of the charge request"*, max 30 characters.

- If we retry a `chargeAmount` after a **timeout** using the same `referenceCode`, does the MA deduplicate, or would the subscriber be charged twice?
- Is there any query API to establish the outcome of a charge whose response we never received?

This matters because SVC0001 is documented as a timeout, and without idempotency or a status query there is no safe retry.

### 2.4 WEB subscription flow — missing from the guide

Guide p.6 reads, in full:

> **WEB**
> `<Will be added – awaiting for secure-d flow>`

FlipStar is a **mobile application**. Our users subscribe inside the app, not by sending an SMS keyword to a short code. The SMS flow documented on p.5 is therefore not our primary path, and the WEB flow that would be is undefined.

**This is our largest blocker.** Please supply the WEB / Secure-D subscription flow, including:

- the redirect or API contract for initiating a subscription from an app or web page
- how the resulting subscription is confirmed to us (we assume `syncOrderRelation` with `updateType=1`, but please confirm)
- any required parameters, signatures or landing pages
- whether Secure-D consent capture is mandatory, and what our side must render

### 2.5 chargeAmount response namespace

The request example (p.19) uses `.../amount_charging/v3_1/local` but the response example (p.22) uses `.../amount_charging/v2_1/local`. We parse namespace-agnostically so either works, but please confirm which is correct so we can validate strictly later.

### 2.6 `updateType=3` (Update)

The guide lists Update as an operation but gives no example and does not say what may change. Which fields can differ on an Update, and what should we do with it — renewal? tier change? expiry extension?

---

## 3. What FlipStar will provide to TIMWE

Once the above is settled we will supply:

| Item | Value |
|---|---|
| `syncOrderRelation` callback URL | `https://api.uat.flipstar.et/api/v1/timwe/sync-order-relation/` (UAT) |
| Production callback URL | to follow |
| Our egress IP | `196.189.236.140` |
| Technical contact | |

Our endpoint responds within the 30-second budget and returns `result=0` on success, or the appropriate code from the guide's error table (p.17) otherwise.

---

## 4. Suggested sequence

1. TIMWE supplies §1.1–1.3 → we configure and can attempt a live `chargeAmount` in UAT.
2. TIMWE confirms §2.1 and §2.2 → charging is safe to enable (until then it stays disabled).
3. TIMWE supplies §1.5 and registers our callback URL → we can receive real `syncOrderRelation` events.
4. TIMWE supplies §2.4 (WEB flow) → app subscription can be built.
5. TIMWE supplies §1.4 → SMPP work begins (not yet started).

Steps 1–3 can proceed in parallel with 4.
