# Telebirr Direct Debit — Outgoing SOAP Payloads (Flipstar UAT)

**Merchant:** `TestMer`
**Environment:** UAT
**Endpoint we POST to:** `http://10.180.79.13:30001/payment/services/APIRequestMgrService`
**Content-Type:** `text/xml; charset=utf-8`
**ResultURL embedded in every request:** `https://uat.flipstar.et/api/webhooks/telebirr-direct-debit/`

> The four envelopes below are the exact payloads our backend sends. **We use SP Operator (IdentifierType=14) for all commands** as requested. Static fields use our UAT credentials. Dynamic fields are shown as `<PLACEHOLDER>`; each request rotates them at runtime:
> - `OriginatorConversationID` → `S_X<YYYYMMDDHHMMSS>`
> - `ConversationID` → `AG_<YYYYMMDD>_<12-hex>`
> - `Timestamp` → `YYYYMMDDHHMMSS`

---

## 1. Create Direct Debit Mandate

**CommandID:** `CreateDirectDebitMandateByCustomer`
**SOAPAction:** `CreateDirectDebitMandateByCustomer`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:api="http://cps.huawei.com/cpsinterface/api_requestmgr"
                  xmlns:req="http://cps.huawei.com/cpsinterface/request"
                  xmlns:com="http://cps.huawei.com/cpsinterface/common">
  <soapenv:Header/>
  <soapenv:Body>
    <api:Request>
      <req:Header>
        <req:Version>1.0</req:Version>
        <req:CommandID>CreateDirectDebitMandateByCustomer</req:CommandID>
        <req:OriginatorConversationID>S_X20260518114500</req:OriginatorConversationID>
        <req:ConversationID>AG_20260518_a1b2c3d4e5f6</req:ConversationID>
        <req:Caller>
          <req:CallerType>2</req:CallerType>
          <req:ThirdPartyID>TestMer</req:ThirdPartyID>
          <req:Password>jIfxwUU1S7jJmh1dgP3+wK3fd4Qxlxxcc4cb4i0z4Tk=</req:Password>
          <req:ResultURL>https://uat.flipstar.et/api/webhooks/telebirr-direct-debit/</req:ResultURL>
        </req:Caller>
        <req:KeyOwner>1</req:KeyOwner>
        <req:Timestamp>20260518114500</req:Timestamp>
      </req:Header>
      <req:Body>
        <req:Identity>
          <req:Initiator>
            <req:IdentifierType>14</req:IdentifierType>
            <req:Identifier>TestSPOperAPI</req:Identifier>
            <req:SecurityCredential>2JKSrKYlLAVvKWuIUXcexc3GHiT0+lEKzeVb6JRcZUM=</req:SecurityCredential>
          </req:Initiator>
          <req:ReceiverParty>
            <req:IdentifierType>1</req:IdentifierType>
            <req:Identifier>251955111111</req:Identifier>
          </req:ReceiverParty>
        </req:Identity>
        <req:CreateDirectDebitMandateByPayerRequest>
          <req:Payee>
            <com:IdentifierType>4</com:IdentifierType>
            <com:IdentifierValue>232323</com:IdentifierValue>
          </req:Payee>
          <req:DirectDebitMandateInfo>
            <com:PayerReferenceNumber>FLPSPEC001</com:PayerReferenceNumber>
            <com:AgreedTC>1</com:AgreedTC>
            <com:PayeeAccountName>Flipstar</com:PayeeAccountName>
            <com:PayerAccountName></com:PayerAccountName>
            <com:FirstPaymentDate>20260518</com:FirstPaymentDate>
            <com:Frequency>05</com:Frequency>
            <com:StartRangeOfDays>1</com:StartRangeOfDays>
            <com:EndRangeOfDays>22</com:EndRangeOfDays>
            <com:ExpiryDate>20270518</com:ExpiryDate>
          </req:DirectDebitMandateInfo>
        </req:CreateDirectDebitMandateByPayerRequest>
      </req:Body>
    </api:Request>
  </soapenv:Body>
</soapenv:Envelope>
```

**Observed Response (sync):**
```xml
<res:ResponseCode>0</res:ResponseCode>
<res:ResponseDesc>Accept the service request successfully.</res:ResponseDesc>
<res:ServiceStatus>0</res:ServiceStatus>
```

**Async Result (NOT yet received from UAT — please confirm.)**

---

## 2. Activate Customer Direct Debit Mandate

**CommandID:** `ActivateCustomerDirectDebitMandate`
**SOAPAction:** `ActivateCustomerDirectDebitMandate`

> `<req:MandateID>` is the Telebirr-generated MandateID (max 18 bytes) returned in the async Result of step 1. **We cannot test step 2 until the async Result of step 1 arrives.**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:api="http://cps.huawei.com/cpsinterface/api_requestmgr"
                  xmlns:req="http://cps.huawei.com/cpsinterface/request"
                  xmlns:com="http://cps.huawei.com/cpsinterface/common">
  <soapenv:Header/>
  <soapenv:Body>
    <api:Request>
      <req:Header>
        <req:Version>1.0</req:Version>
        <req:CommandID>ActivateCustomerDirectDebitMandate</req:CommandID>
        <req:OriginatorConversationID>S_X20260518114600</req:OriginatorConversationID>
        <req:ConversationID>AG_20260518_b2c3d4e5f6a1</req:ConversationID>
        <req:Caller>
          <req:CallerType>2</req:CallerType>
          <req:ThirdPartyID>TestMer</req:ThirdPartyID>
          <req:Password>jIfxwUU1S7jJmh1dgP3+wK3fd4Qxlxxcc4cb4i0z4Tk=</req:Password>
          <req:ResultURL>https://uat.flipstar.et/api/webhooks/telebirr-direct-debit/</req:ResultURL>
        </req:Caller>
        <req:KeyOwner>1</req:KeyOwner>
        <req:Timestamp>20260518114600</req:Timestamp>
      </req:Header>
      <req:Body>
        <req:Identity>
          <req:Initiator>
            <req:IdentifierType>14</req:IdentifierType>
            <req:Identifier>TestSPOperAPI</req:Identifier>
            <req:SecurityCredential>2JKSrKYlLAVvKWuIUXcexc3GHiT0+lEKzeVb6JRcZUM=</req:SecurityCredential>
          </req:Initiator>
          <req:ReceiverParty>
            <req:IdentifierType>1</req:IdentifierType>
            <req:Identifier>251955111111</req:Identifier>
          </req:ReceiverParty>
        </req:Identity>
        <req:ActivateDirectDebitMandateRequest>
          <req:MandateID>10101</req:MandateID>
          <req:AgreedTC>1</req:AgreedTC>
          <req:PayerAccountName>Test User</req:PayerAccountName>
        </req:ActivateDirectDebitMandateRequest>
      </req:Body>
    </api:Request>
  </soapenv:Body>
</soapenv:Envelope>
```

---

## 3. Initiate Direct Debit Transaction

**CommandID:** `InitTrans_Initiate Direct Debit Transaction`
**SOAPAction:** `InitTrans_Initiate Direct Debit Transaction`

> Requires an *active* mandate from step 2. Uses Initiator `TestMer` with `ShortCode=232323`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:api="http://cps.huawei.com/cpsinterface/api_requestmgr"
                  xmlns:req="http://cps.huawei.com/cpsinterface/request"
                  xmlns:com="http://cps.huawei.com/cpsinterface/common">
  <soapenv:Header/>
  <soapenv:Body>
    <api:Request>
      <req:Header>
        <req:Version>1.0</req:Version>
        <req:CommandID>InitTrans_Initiate Direct Debit Transaction</req:CommandID>
        <req:OriginatorConversationID>S_X20260518114700</req:OriginatorConversationID>
        <req:ConversationID>AG_20260518_c3d4e5f6a1b2</req:ConversationID>
        <req:Caller>
          <req:CallerType>2</req:CallerType>
          <req:ThirdPartyID>TestMer</req:ThirdPartyID>
          <req:Password>jIfxwUU1S7jJmh1dgP3+wK3fd4Qxlxxcc4cb4i0z4Tk=</req:Password>
          <req:ResultURL>https://uat.flipstar.et/api/webhooks/telebirr-direct-debit/</req:ResultURL>
        </req:Caller>
        <req:KeyOwner>1</req:KeyOwner>
        <req:Timestamp>20260518114700</req:Timestamp>
      </req:Header>
      <req:Body>
        <req:Identity>
          <req:Initiator>
            <req:IdentifierType>14</req:IdentifierType>
            <req:Identifier>TestMer</req:Identifier>
            <req:SecurityCredential>jIfxwUU1S7jJmh1dgP3+wK3fd4Qxlxxcc4cb4i0z4Tk=</req:SecurityCredential>
          </req:Initiator>
          <req:ReceiverParty>
            <req:IdentifierType>53</req:IdentifierType>
            <req:Identifier>FLPSPEC001</req:Identifier>
          </req:ReceiverParty>
        </req:Identity>
        <req:TransactionRequest>
          <req:Parameters>
            <req:Parameter>
              <com:Key>MandateID</com:Key>
              <com:Value>10101</com:Value>
            </req:Parameter>
            <req:Parameter>
              <com:Key>Amount</com:Key>
              <com:Value>10.00</com:Value>
            </req:Parameter>
            <req:Parameter>
              <com:Key>Currency</com:Key>
              <com:Value>ETB</com:Value>
            </req:Parameter>
          </req:Parameters>
        </req:TransactionRequest>
        <req:Remark>Direct debit for mandate 10101</req:Remark>
      </req:Body>
    </api:Request>
  </soapenv:Body>
</soapenv:Envelope>
```

> **Note:** We use SP Operator (IdentifierType=14) for InitTrans as requested, consistent with the other commands.

---

## 4. Cancel Customer Direct Debit Mandate

**CommandID:** `CancelCustomerDirectDebitMandateByPayer`
**SOAPAction:** `CancelCustomerDirectDebitMandateByPayer`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:api="http://cps.huawei.com/cpsinterface/api_requestmgr"
                  xmlns:req="http://cps.huawei.com/cpsinterface/request"
                  xmlns:com="http://cps.huawei.com/cpsinterface/common">
  <soapenv:Header/>
  <soapenv:Body>
    <api:Request>
      <req:Header>
        <req:Version>1.0</req:Version>
        <req:CommandID>CancelCustomerDirectDebitMandateByPayer</req:CommandID>
        <req:OriginatorConversationID>S_X20260518114800</req:OriginatorConversationID>
        <req:ConversationID>AG_20260518_d4e5f6a1b2c3</req:ConversationID>
        <req:Caller>
          <req:CallerType>2</req:CallerType>
          <req:ThirdPartyID>TestMer</req:ThirdPartyID>
          <req:Password>jIfxwUU1S7jJmh1dgP3+wK3fd4Qxlxxcc4cb4i0z4Tk=</req:Password>
          <req:ResultURL>https://uat.flipstar.et/api/webhooks/telebirr-direct-debit/</req:ResultURL>
        </req:Caller>
        <req:KeyOwner>1</req:KeyOwner>
        <req:Timestamp>20260518114800</req:Timestamp>
      </req:Header>
      <req:Body>
        <req:Identity>
          <req:Initiator>
            <req:IdentifierType>14</req:IdentifierType>
            <req:Identifier>TestSPOperAPI</req:Identifier>
            <req:SecurityCredential>2JKSrKYlLAVvKWuIUXcexc3GHiT0+lEKzeVb6JRcZUM=</req:SecurityCredential>
          </req:Initiator>
          <req:ReceiverParty>
            <req:IdentifierType>1</req:IdentifierType>
            <req:Identifier>251955111111</req:Identifier>
          </req:ReceiverParty>
        </req:Identity>
        <req:CancelDirectDebitMandateByPayerRequest>
          <req:MandateID>10101</req:MandateID>
        </req:CancelDirectDebitMandateByPayerRequest>
      </req:Body>
    </api:Request>
  </soapenv:Body>
</soapenv:Envelope>
```

---

## Credentials Reference (UAT — for the team's verification)

| Field | Value |
|---|---|
| `ThirdPartyID` | `TestMer` |
| `Password` | `jIfxwUU1S7jJmh1dgP3+wK3fd4Qxlxxcc4cb4i0z4Tk=` |
| `SP Operator Identifier` | `TestSPOperAPI` (IdentifierType=14) |
| `SP Operator SecurityCredential` | `2JKSrKYlLAVvKWuIUXcexc3GHiT0+lEKzeVb6JRcZUM=` |
| `Payee ShortCode` | `232323` |
| `Test Customer MSISDN` | `251955111111` |
| `CallerType` | `2` (Third Party) |
| `KeyOwner` | `1` |

> **Note on frequency:** You mentioned changing the frequency value — please specify what value you'd like us to use. Currently we send `05` (Monthly) per the spec.

---

## What we need from your side

1. **Confirm async Result delivery is enabled for `TestMer` in UAT.**
2. **Whitelist** `https://uat.flipstar.et/api/webhooks/telebirr-direct-debit/` as the outbound destination.
3. **Trace these `OriginatorConversationID`s** in your Result Manager log and tell us why no callback fired:
   - `S_X20260517181734`
   - `S_X20260517182512`
   - `S_X20260517183956`
4. **Confirm InitTrans Initiator type:** SP Operator (14) vs Organization Operator (11). The spec example shows 11.

Thank you.
