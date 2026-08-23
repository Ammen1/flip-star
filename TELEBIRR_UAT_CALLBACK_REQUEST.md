# Telebirr UAT — Direct Debit Async Result Callback Request

**To:** Telebirr / Ethio Telecom CPS Integration Team
**From:** Flipstar Engineering
**Environment:** UAT
**Issue:** Synchronous SOAP **Response** is received correctly. The asynchronous **Result** callback is never POSTed back to our `ResultURL`.

---

## 1. Top Three Questions

Please answer these explicitly before anything else:

1. **Is async Result delivery enabled in the UAT environment for merchant `TestMer`?** (Yes / No / Needs config)
2. **Has `https://api.uat.flipstar.et/api/webhooks/telebirr-direct-debit/` been added to your outbound whitelist for that merchant?** (Yes / No)
3. **For `OriginatorConversationID=S_X20260517183956`, what does your CPS Result Manager log show?** (Attempted / Not attempted / Error reason)

---

## 2. Merchant Identification

| Field                          | Value                                                             |
| ------------------------------ | ----------------------------------------------------------------- |
| Environment                    | UAT                                                               |
| Merchant / ThirdPartyID        | `TestMer`                                                         |
| SP Operator username           | `TestSPOperAPI`                                                   |
| Organization Operator username | `TestAPI`                                                         |
| ShortCode                      | `232323`                                                          |
| CPS endpoint we call           | `http://10.180.79.13:30001/payment/services/APIRequestMgrService` |

---

## 3. Our ResultURL (please whitelist)

- **URL:** `https://api.uat.flipstar.et/api/webhooks/telebirr-direct-debit/`
- **Protocol:** HTTPS, TLS 1.2+
- **Port:** 443
- **Method:** POST
- **Accepted Content-Types:** `text/xml`, `application/xml`, `application/json`
- **Trailing slash is required** (Django strict routing — without it our server replies `301 Moved Permanently`, which most SOAP clients do not follow).

### TLS certificate

- Issuer: Publicly trusted CA (Let's Encrypt). Not self-signed.
- CN / SAN: `api.uat.flipstar.et`

---

## 4. Our Network Coordinates

| Field                                       | Value                                          |
| ------------------------------------------- | ---------------------------------------------- |
| Hostname                                    | `api.uat.flipstar.et`                          |
| Public IPv4                                 | `<RUN THE SCRIPT IN SECTION 9 AND PASTE HERE>` |
| Cloud provider                              | `<your hosting provider>`                      |
| Backend outbound IP (when calling your CPS) | `<RUN THE SCRIPT IN SECTION 9 AND PASTE HERE>` |

If you whitelist inbound by source IP, the _Backend outbound IP_ is the one to allow.

---

## 5. What We've Verified On Our Side

- ✅ Our backend can reach your CPS: `tcp://10.180.79.13:30001` accepts connections from our network.
- ✅ Every `CreateDirectDebitMandateByCustomer` SOAP request returns:
  ```xml
  <res:ResponseCode>0</res:ResponseCode>
  <res:ResponseDesc>Accept the service request successfully.</res:ResponseDesc>
  <res:ServiceStatus>0</res:ServiceStatus>
  ```
- ✅ Our outgoing envelope includes `<req:ResultURL>https://api.uat.flipstar.et/api/webhooks/telebirr-direct-debit/</req:ResultURL>` in every request.
- ✅ Our webhook URL is publicly reachable. A test POST returns HTTP 200:
  ```
  $ curl -i -X POST https://api.uat.flipstar.et/api/webhooks/telebirr-direct-debit/ \
      -H "Content-Type: text/xml" -d '<x/>'
  HTTP/1.1 200 OK
  ```
- ✅ Our webhook handler accepts both `text/xml` (SOAP) and `application/json`, parses `OriginatorConversationID` / `ResultCode` / `ResultDesc` / `MandateID` / `TransactionID`, and correlates the callback to the originating mandate in our DB.
- ✅ End-to-end simulation: when we POST a Telebirr-shaped Result envelope to our own webhook, the mandate row correctly transitions `pending_created → pending_active` and the returned `MandateID` is persisted. The pipeline is fully functional from receipt onward.

- ❌ **No callback ever arrives** to our webhook for any of the test calls listed below. Our access log shows zero inbound POSTs from your network.

---

## 6. Test Calls For You To Trace

Please grep your CPS Result Manager logs for these `OriginatorConversationID`s and tell us, for each, whether the callback was attempted and what the outcome was (DNS failure, connection refused, TLS handshake error, HTTP 4xx/5xx, timeout, not attempted).

| OriginatorConversationID | Approx. timestamp (UTC) | Command                              |
| ------------------------ | ----------------------- | ------------------------------------ |
| `S_X20260517181734`      | 2026-05-17 18:17        | `CreateDirectDebitMandateByCustomer` |
| `S_X20260517182512`      | 2026-05-17 18:25        | `CreateDirectDebitMandateByCustomer` |
| `S_X20260517183956`      | 2026-05-17 18:39        | `CreateDirectDebitMandateByCustomer` |

---

## 7. Expected Result Envelope Shape

This is what we expect to receive on our webhook (taken from the Huawei CPS spec). Please confirm whether your UAT actually emits this:

```xml
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <api:Result xmlns:api="http://cps.huawei.com/cpsinterface/api_resultmgr"
                xmlns:res="http://cps.huawei.com/cpsinterface/result">
      <res:Header>
        <res:Version>1.0</res:Version>
        <res:OriginatorConversationID>S_X20260517183956</res:OriginatorConversationID>
        <res:ConversationID>AG_20260517_c0b7e6f2b0b7</res:ConversationID>
      </res:Header>
      <res:Body>
        <res:ResultType>0</res:ResultType>
        <res:ResultCode>0</res:ResultCode>
        <res:ResultDesc>Process service request successfully.</res:ResultDesc>
        <res:MandateID>10101</res:MandateID>
      </res:Body>
    </api:Result>
  </soapenv:Body>
</soapenv:Envelope>
```

---

## 8. Other Useful Info

- **Retry policy expectations:** Please confirm how your Result Manager retries on non-200 responses (count, backoff). Our endpoint always returns HTTP 200 so retries should not be triggered, but we'd like to know your defaults.
- **Authentication on the callback:** If you sign or attach a credential to the callback envelope, please share the scheme so we can validate it.
- **Source IPs:** If you have a fixed pool of source IPs for CPS outbound, please share them so we can add them to our firewall allow-list.

---

## 9. Diagnostic Script (run on our server, paste output below)

```bash
echo "=== Public IPv4 ==="
curl -s ifconfig.me; echo
echo "=== api.uat.flipstar.et resolves to ==="
getent hosts api.uat.flipstar.et
echo "=== Webhook URL health ==="
curl -sI -X POST https://api.uat.flipstar.et/api/webhooks/telebirr-direct-debit/ \
     -H "Content-Type: text/xml" -d '<x/>' | head -3
echo "=== TLS cert ==="
echo | openssl s_client -connect api.uat.flipstar.et:443 -servername api.uat.flipstar.et 2>/dev/null \
     | openssl x509 -noout -subject -issuer -dates
echo "=== Backend outbound IP ==="
docker compose exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('https://api.ipify.org').read().decode())"
```

**Paste output here before sending:**

```
<paste here>
```

---

## 10. Contact

- **Engineering contact:** `<your name / email / phone>`
- **Preferred response channel:** `<email / Slack / phone>`

Thank you.
