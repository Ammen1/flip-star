#!/usr/bin/env bash
#
# Send a single Telebirr SOAP request by hand, to check a credential or a short
# code against the gateway without going through the application.
#
# The envelopes here are transcribed from
# api/integrations/telebirr/direct_debit.py -- initiate_b2c_payment and
# initiate_ussd_push_payment. If you change one there, change it here, or this
# stops being a test of what the app actually sends.
#
#   ./telebirr_soap_test.sh b2c   251911000111 1.00      # cashout / payout
#   ./telebirr_soap_test.sh ussd  251911000111 1.00      # USSD PIN prompt
#
# Prints the envelope with credentials masked and exits. Add --send to
# actually transmit.
#
# THESE MOVE REAL MONEY
# ---------------------
# `b2c` pays the receiver. `ussd` raises a PIN prompt on the receiver's phone
# and debits them when they accept. Use a number you control and the smallest
# amount the gateway will take. There is no sandbox flag here; the testbed is
# whichever host TELEBIRR_*_SOAP_URL points at.
#
# Credentials come from the environment and are never echoed. Source them from
# Vault rather than typing them:
#
#   export VAULT_ADDR=http://127.0.0.1:8210
#   export VAULT_TOKEN=$(tr -d '\r\n' < new-root-token.txt)
#   eval "$(vault kv get -format=json secret/flipstar/backend/staging \
#            | python3 -c '
# import json,sys,shlex
# d=json.load(sys.stdin)["data"]["data"]
# for k in ("TELEBIRR_B2C_THIRD_PARTY_ID","TELEBIRR_B2C_THIRD_PARTY_PASSWORD",
#           "TELEBIRR_B2C_ORG_OPERATOR_ID","TELEBIRR_B2C_ORG_OPERATOR_CREDENTIAL",
#           "TELEBIRR_B2C_SHORTCODE","TELEBIRR_B2C_SOAP_URL","TELEBIRR_B2C_SERVICE_CODE",
#           "TELEBIRR_B2C_RESULT_URL","TELEBIRR_USSD_THIRD_PARTY_ID",
#           "TELEBIRR_USSD_THIRD_PARTY_PASSWORD","TELEBIRR_USSD_ORG_OPERATOR_ID",
#           "TELEBIRR_USSD_ORG_OPERATOR_CREDENTIAL","TELEBIRR_USSD_MERCHANT_SHORTCODE",
#           "TELEBIRR_USSD_SOAP_URL","TELEBIRR_USSD_RESULT_URL"):
#     if k in d: print("export %s=%s" % (k, shlex.quote(d[k])))
# ')"
#
set -euo pipefail

FLOW="${1:-}"
MSISDN="${2:-}"
AMOUNT="${3:-}"
SEND="${4:-}"

usage() {
  echo "usage: $0 {b2c|ussd} <msisdn> <amount> [--send]" >&2
  echo "  b2c   cashout: pays <msisdn>" >&2
  echo "  ussd  push:    prompts <msisdn> for a PIN, then debits them" >&2
  exit 64
}

[ -n "$FLOW" ] && [ -n "$MSISDN" ] && [ -n "$AMOUNT" ] || usage

need() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "missing: $name -- see the header for how to load these from Vault" >&2
    exit 78
  fi
}

# Same formats the application generates, so a gateway that is fussy about
# them behaves identically here.
OCID="S_X$(date +%Y%m%d%H%M%S)"
CONV="AG_$(date +%Y%m%d)_$(head -c 6 /dev/urandom | od -An -tx1 | tr -d ' \n')"
STAMP="$(date +%Y%m%d%H%M%S)"
AMOUNT_FMT="$(printf '%.2f' "$AMOUNT")"
CALLER_TYPE="${TELEBIRR_CALLER_TYPE:-2}"

NS='xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:com="http://cps.huawei.com/cpsinterface/common" xmlns:api="http://cps.huawei.com/cpsinterface/api_requestmgr" xmlns:req="http://cps.huawei.com/cpsinterface/request"'

case "$FLOW" in
  b2c)
    need TELEBIRR_B2C_SOAP_URL
    need TELEBIRR_B2C_THIRD_PARTY_ID
    need TELEBIRR_B2C_THIRD_PARTY_PASSWORD
    need TELEBIRR_B2C_ORG_OPERATOR_ID
    need TELEBIRR_B2C_ORG_OPERATOR_CREDENTIAL
    need TELEBIRR_B2C_SHORTCODE
    need TELEBIRR_B2C_SERVICE_CODE

    URL="$TELEBIRR_B2C_SOAP_URL"
    ACTION="InitTrans_${TELEBIRR_B2C_SERVICE_CODE}"
    SHORTCODE="$TELEBIRR_B2C_SHORTCODE"
    SECRET_PW="$TELEBIRR_B2C_THIRD_PARTY_PASSWORD"
    SECRET_CRED="$TELEBIRR_B2C_ORG_OPERATOR_CREDENTIAL"

    # ReceiverParty IdentifierType 1 = MSISDN: money leaves the short code and
    # lands on the customer's phone.
    ENVELOPE="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<soapenv:Envelope ${NS}>
   <soapenv:Header/>
   <soapenv:Body>
      <api:Request>
         <req:Header>
            <req:Version>1.0</req:Version>
            <req:CommandID>${ACTION}</req:CommandID>
            <req:OriginatorConversationID>${OCID}</req:OriginatorConversationID>
            <req:Caller>
               <req:CallerType>${CALLER_TYPE}</req:CallerType>
               <req:ThirdPartyID>${TELEBIRR_B2C_THIRD_PARTY_ID}</req:ThirdPartyID>
               <req:Password>${SECRET_PW}</req:Password>
               <req:ResultURL>${TELEBIRR_B2C_RESULT_URL:-}</req:ResultURL>
            </req:Caller>
            <req:KeyOwner>1</req:KeyOwner>
            <req:Timestamp>${STAMP}</req:Timestamp>
         </req:Header>
         <req:Body>
            <req:Identity>
               <req:Initiator>
                  <req:IdentifierType>12</req:IdentifierType>
                  <req:Identifier>${TELEBIRR_B2C_ORG_OPERATOR_ID}</req:Identifier>
                  <req:SecurityCredential>${SECRET_CRED}</req:SecurityCredential>
                  <req:ShortCode>${SHORTCODE}</req:ShortCode>
               </req:Initiator>
               <req:ReceiverParty>
                  <req:IdentifierType>1</req:IdentifierType>
                  <req:Identifier>${MSISDN}</req:Identifier>
               </req:ReceiverParty>
            </req:Identity>
            <req:TransactionRequest>
               <req:Parameters>
                  <req:Amount>${AMOUNT_FMT}</req:Amount>
                  <req:Currency>ETB</req:Currency>
               </req:Parameters>
            </req:TransactionRequest>
         </req:Body>
      </api:Request>
   </soapenv:Body>
</soapenv:Envelope>"
    ;;

  ussd)
    need TELEBIRR_USSD_SOAP_URL
    need TELEBIRR_USSD_THIRD_PARTY_ID
    need TELEBIRR_USSD_THIRD_PARTY_PASSWORD
    need TELEBIRR_USSD_ORG_OPERATOR_ID
    need TELEBIRR_USSD_ORG_OPERATOR_CREDENTIAL
    need TELEBIRR_USSD_MERCHANT_SHORTCODE

    URL="$TELEBIRR_USSD_SOAP_URL"
    ACTION="InitTrans_BuyGoodsForCustomer"
    SHORTCODE="$TELEBIRR_USSD_MERCHANT_SHORTCODE"
    SECRET_PW="$TELEBIRR_USSD_THIRD_PARTY_PASSWORD"
    SECRET_CRED="$TELEBIRR_USSD_ORG_OPERATOR_CREDENTIAL"

    # The short code appears TWICE: as the initiator's account, and as the
    # ReceiverParty (IdentifierType 4 = short code) because money is coming
    # IN. PrimaryParty is the payer.
    ENVELOPE="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<soapenv:Envelope ${NS}>
  <soapenv:Header/>
  <soapenv:Body>
    <api:Request>
      <req:Header>
        <req:Version>1.0</req:Version>
        <req:CommandID>${ACTION}</req:CommandID>
        <req:OriginatorConversationID>${OCID}</req:OriginatorConversationID>
        <req:ConversationID>${CONV}</req:ConversationID>
        <req:Caller>
          <req:CallerType>${CALLER_TYPE}</req:CallerType>
          <req:ThirdPartyID>${TELEBIRR_USSD_THIRD_PARTY_ID}</req:ThirdPartyID>
          <req:Password>${SECRET_PW}</req:Password>
          <req:ResultURL>${TELEBIRR_USSD_RESULT_URL:-}</req:ResultURL>
        </req:Caller>
        <req:KeyOwner>1</req:KeyOwner>
        <req:Timestamp>${STAMP}</req:Timestamp>
      </req:Header>
      <req:Body>
        <req:Identity>
          <req:Initiator>
            <req:IdentifierType>12</req:IdentifierType>
            <req:Identifier>${TELEBIRR_USSD_ORG_OPERATOR_ID}</req:Identifier>
            <req:SecurityCredential>${SECRET_CRED}</req:SecurityCredential>
            <req:ShortCode>${SHORTCODE}</req:ShortCode>
          </req:Initiator>
          <req:PrimaryParty>
            <req:IdentifierType>1</req:IdentifierType>
            <req:Identifier>${MSISDN}</req:Identifier>
          </req:PrimaryParty>
          <req:ReceiverParty>
            <req:IdentifierType>4</req:IdentifierType>
            <req:Identifier>${SHORTCODE}</req:Identifier>
          </req:ReceiverParty>
        </req:Identity>
        <req:TransactionRequest>
          <req:Parameters>
            <req:Amount>${AMOUNT_FMT}</req:Amount>
            <req:Currency>ETB</req:Currency>
          </req:Parameters>
        </req:TransactionRequest>
      </req:Body>
    </api:Request>
  </soapenv:Body>
</soapenv:Envelope>"
    ;;

  *) usage ;;
esac

# Mask both credentials for display. Never print the envelope unmasked.
masked() {
  printf '%s' "$ENVELOPE" \
    | sed "s|<req:Password>.*</req:Password>|<req:Password>***MASKED***</req:Password>|" \
    | sed "s|<req:SecurityCredential>.*</req:SecurityCredential>|<req:SecurityCredential>***MASKED***</req:SecurityCredential>|"
}

echo "flow        : $FLOW"
echo "url         : $URL"
echo "SOAPAction  : $ACTION"
echo "short code  : $SHORTCODE"
echo "receiver    : $MSISDN"
echo "amount      : $AMOUNT_FMT ETB"
echo "conversation: $OCID"
echo
masked
echo

if [ "$SEND" != "--send" ]; then
  echo ">>> not sent. Re-run with --send as the 4th argument to transmit." >&2
  exit 0
fi

echo ">>> sending..." >&2

# --insecure because the testbed serves a private certificate; this mirrors
# TELEBIRR_VERIFY_SSL=false, which is the default for those hosts. Drop it
# against a properly chained endpoint.
CURL_OPTS=(-sS -X POST "$URL"
  -H 'Content-Type: text/xml; charset=utf-8'
  -H "SOAPAction: $ACTION"
  --data-binary @-
  --max-time 45
  -w '\n--- http %{http_code}, %{time_total}s ---\n')
case "${TELEBIRR_VERIFY_SSL:-false}" in
  true|True|1) : ;;
  *) CURL_OPTS+=(--insecure) ;;
esac

printf '%s' "$ENVELOPE" | curl "${CURL_OPTS[@]}"

echo
echo "ResponseCode 0 means ACCEPTED, not paid. The outcome arrives later on" >&2
echo "the ResultURL webhook -- check it, or the withdrawal stays 'processing'." >&2
