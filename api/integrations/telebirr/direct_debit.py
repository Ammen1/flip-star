"""
Telebirr Direct Debit SOAP Service

Handles SOAP API operations for direct debit mandate management:
- CreateDirectDebitMandateByCustomer
- ActivateCustomerDirectDebitMandate
- InitTrans_Initiate Direct Debit Transaction
- CancelCustomerDirectDebitMandateByPayer
"""
import logging
import re
import uuid
from datetime import datetime
from decimal import Decimal

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class TelebirrDirectDebitService:
    """Telebirr Direct Debit SOAP Service"""

    def __init__(self):
        self.soap_url = getattr(settings, 'TELEBIRR_SOAP_URL', '')
        self.third_party_id = getattr(settings, 'TELEBIRR_THIRD_PARTY_ID', '')
        self.third_party_password = getattr(settings, 'TELEBIRR_THIRD_PARTY_PASSWORD', '')
        self.shortcode = getattr(settings, 'TELEBIRR_SHORTCODE', '9286')
        self.result_url = getattr(settings, 'TELEBIRR_RESULT_URL', '')
        self.payee_account_name = getattr(settings, 'TELEBIRR_PAYEE_ACCOUNT_NAME', 'Flipstar')
        self.caller_type = getattr(settings, 'TELEBIRR_CALLER_TYPE', '2')
        self.sp_operator_id = getattr(settings, 'TELEBIRR_SP_OPERATOR_ID', '')
        self.sp_operator_credential = getattr(settings, 'TELEBIRR_SP_OPERATOR_CREDENTIAL', '')
        self.org_operator_id = getattr(settings, 'TELEBIRR_ORG_OPERATOR_ID', '')
        self.org_operator_credential = getattr(settings, 'TELEBIRR_ORG_OPERATOR_CREDENTIAL', '')

        # B2C (Business-to-Consumer payouts, e.g. withdrawal payouts)
        # The account payouts leave FROM. Distinct from self.shortcode, which
        # is where money arrives (C2B): telebirr issues one code per
        # direction. Falls back to the C2B code for a deployment that has only
        # been given one.
        self.b2c_shortcode = getattr(settings, 'TELEBIRR_B2C_SHORTCODE', '') or self.shortcode
        self.b2c_service_code = getattr(settings, 'TELEBIRR_B2C_SERVICE_CODE', '2304')
        self.b2c_reason_type = getattr(settings, 'TELEBIRR_B2C_REASON_TYPE', 'Pay for Individual B2C_VDF_Demo')
        self.b2c_result_url = getattr(settings, 'TELEBIRR_B2C_RESULT_URL', '')
        self.b2c_org_operator_id = getattr(settings, 'TELEBIRR_B2C_ORG_OPERATOR_ID', '')
        self.b2c_org_operator_credential = getattr(settings, 'TELEBIRR_B2C_ORG_OPERATOR_CREDENTIAL', '')
        self.b2c_soap_url = getattr(settings, 'TELEBIRR_B2C_SOAP_URL', '')
        self.b2c_third_party_id = getattr(settings, 'TELEBIRR_B2C_THIRD_PARTY_ID', '')
        self.b2c_third_party_password = getattr(settings, 'TELEBIRR_B2C_THIRD_PARTY_PASSWORD', '')

        # USSD Push (BuyGoodsForCustomer)
        self.ussd_merchant_shortcode = getattr(settings, 'TELEBIRR_USSD_MERCHANT_SHORTCODE', '')
        self.ussd_result_url = getattr(settings, 'TELEBIRR_USSD_RESULT_URL', '')
        self.ussd_soap_url = getattr(settings, 'TELEBIRR_USSD_SOAP_URL', '')
        self.ussd_third_party_id = getattr(settings, 'TELEBIRR_USSD_THIRD_PARTY_ID', '')
        self.ussd_third_party_password = getattr(settings, 'TELEBIRR_USSD_THIRD_PARTY_PASSWORD', '')
        self.ussd_org_operator_id = getattr(settings, 'TELEBIRR_USSD_ORG_OPERATOR_ID', '')
        self.ussd_org_operator_credential = getattr(settings, 'TELEBIRR_USSD_ORG_OPERATOR_CREDENTIAL', '')

        # No SOAP client initialization needed for raw requests
        self.client = None

    def _generate_originator_conversation_id(self):
        """Generate unique originator conversation ID"""
        return f"S_X{datetime.now().strftime('%Y%m%d%H%M%S')}"

    def _generate_conversation_id(self):
        """Generate unique conversation ID"""
        return f"AG_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:12]}"

    def _generate_timestamp(self):
        """Generate timestamp in YYYYMMDDHHMMSS format"""
        return datetime.now().strftime('%Y%m%d%H%M%S')

    def _build_soap_envelope(self, command_id, initiator, receiver_party, body_xml, caller_id=None, caller_password=None):
        """
        Build SOAP envelope for Telebirr Direct Debit API
        
        Args:
            command_id: SOAP command ID
            initiator: Initiator identifier dict (IdentifierType, Identifier, SecurityCredential)
            receiver_party: Receiver party dict (IdentifierType, Identifier)
            body_xml: Body XML string specific to the operation
            caller_id: Optional caller ID (defaults to third_party_id)
            caller_password: Optional caller password (defaults to third_party_password)
            
        Returns:
            str: Complete SOAP envelope XML
        """
        originator_conversation_id = self._generate_originator_conversation_id()
        conversation_id = self._generate_conversation_id()
        timestamp = self._generate_timestamp()

        # Use provided caller credentials or default to third_party
        caller_third_party_id = caller_id or self.third_party_id
        caller_password = caller_password or self.third_party_password

        shortcode_xml = ""
        if 'ShortCode' in initiator and initiator['ShortCode']:
            shortcode_xml = f"\n            <req:ShortCode>{initiator['ShortCode']}</req:ShortCode>"

        soap_envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:api="http://cps.huawei.com/cpsinterface/api_requestmgr" xmlns:req="http://cps.huawei.com/cpsinterface/request" xmlns:com="http://cps.huawei.com/cpsinterface/common">
  <soapenv:Header/>
  <soapenv:Body>
    <api:Request>
      <req:Header>
        <req:Version>1.0</req:Version>
        <req:CommandID>{command_id}</req:CommandID>
        <req:OriginatorConversationID>{originator_conversation_id}</req:OriginatorConversationID>
        <req:ConversationID>{conversation_id}</req:ConversationID>
        <req:Caller>
          <req:CallerType>{self.caller_type}</req:CallerType>
          <req:ThirdPartyID>{caller_third_party_id}</req:ThirdPartyID>
          <req:Password>{caller_password}</req:Password>
          <req:ResultURL>{self.result_url}</req:ResultURL>
        </req:Caller>
        <req:KeyOwner>1</req:KeyOwner>
        <req:Timestamp>{timestamp}</req:Timestamp>
      </req:Header>
      <req:Body>
        <req:Identity>
          <req:Initiator>
            <req:IdentifierType>{initiator['IdentifierType']}</req:IdentifierType>
            <req:Identifier>{initiator['Identifier']}</req:Identifier>
            <req:SecurityCredential>{initiator['SecurityCredential']}</req:SecurityCredential>{shortcode_xml}
          </req:Initiator>
          <req:ReceiverParty>
            <req:IdentifierType>{receiver_party['IdentifierType']}</req:IdentifierType>
            <req:Identifier>{receiver_party['Identifier']}</req:Identifier>
          </req:ReceiverParty>
        </req:Identity>
        {body_xml}
      </req:Body>
    </api:Request>
  </soapenv:Body>
</soapenv:Envelope>'''

        return soap_envelope, originator_conversation_id, conversation_id

    def create_mandate(self, payer_msisdn, payer_reference_number, frequency,
                      first_payment_date, expiry_date, payee_shortcode=None,
                      payee_account_name=None, start_range_of_days=1,
                      end_range_of_days=31, debug=False):
        """
        Create Direct Debit Mandate
        
        Args:
            payer_msisdn: Payer phone number (MSISDN)
            payer_reference_number: Payer reference number for mandate
            frequency: Debit frequency (02=Daily, 03=Weekly, 04=Bi-Weekly, 05=Monthly, etc.)
            first_payment_date: First payment date (YYYYMMDD format or date object)
            expiry_date: Mandate expiry date (YYYYMMDD format or date object)
            payee_shortcode: Payee shortcode (defaults to TELEBIRR_SHORTCODE)
            payee_account_name: Payee account name (defaults to Flipstar)
            start_range_of_days: Start range of days for payment (default 1)
            end_range_of_days: End range of days for payment (default 31)
            debug: If True, print the SOAP envelope for debugging
            
        Returns:
            dict: Response with success status and mandate details
        """
        try:
            # Format dates
            if isinstance(first_payment_date, datetime):
                first_payment_date = first_payment_date.strftime('%Y%m%d')
            if isinstance(expiry_date, datetime):
                expiry_date = expiry_date.strftime('%Y%m%d')

            # Set defaults
            if payee_shortcode is None:
                payee_shortcode = self.shortcode
            if payee_account_name is None:
                payee_account_name = self.payee_account_name

            # Build initiator (SP Operator)
            initiator = {
                'IdentifierType': 14,  # SP Operator Username
                'Identifier': self.sp_operator_id or self.third_party_id,
                'SecurityCredential': self.sp_operator_credential or self.third_party_password,
            }

            # Build receiver party (Payer MSISDN)
            receiver_party = {
                'IdentifierType': 1,  # MSISDN
                'Identifier': payer_msisdn,
            }

            # Build body XML according to Telebirr documentation
            body_xml = f'''<req:CreateDirectDebitMandateByPayerRequest>
          <req:Payee> 
            <com:IdentifierType>4</com:IdentifierType>
            <com:IdentifierValue>{payee_shortcode}</com:IdentifierValue>
          </req:Payee>
          <req:DirectDebitMandateInfo>
            <com:PayerReferenceNumber>{payer_reference_number}</com:PayerReferenceNumber>
            <com:AgreedTC>1</com:AgreedTC>
            <com:FirstPaymentDate>{first_payment_date}</com:FirstPaymentDate>
            <com:Frequency>{frequency}</com:Frequency>
            <com:StartRangeOfDays>{start_range_of_days}</com:StartRangeOfDays>
            <com:EndRangeOfDays>{end_range_of_days}</com:EndRangeOfDays>
            <com:ExpiryDate>{expiry_date}</com:ExpiryDate>
          </req:DirectDebitMandateInfo>
        </req:CreateDirectDebitMandateByPayerRequest>'''

            # Build SOAP envelope
            soap_envelope, originator_conversation_id, conversation_id = self._build_soap_envelope(
                command_id='CreateDirectDebitMandateByCustomer',
                initiator=initiator,
                receiver_party=receiver_party,
                body_xml=body_xml
            )

            # Print SOAP envelope for debugging if debug=True
            if debug:
                print("=" * 80)
                print("SOAP ENVELOPE BEING SENT TO TELEBIRR:")
                print("=" * 80)
                print(soap_envelope)
                print("=" * 80)

            # Make raw SOAP request
            headers = {
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': 'CreateDirectDebitMandateByCustomer'
            }

            response = requests.post(self.soap_url, data=soap_envelope, headers=headers, timeout=30, verify=False)

            # Parse response
            if response.status_code == 200:
                # Check for SOAP fault
                if 'soapenv:Fault' in response.text:
                    return {
                        'success': False,
                        'error': 'SOAP Fault returned',
                        'response_text': response.text[:500]
                    }

                # Parse ResponseCode and ResponseDesc
                # Simple XML parsing for response
                try:
                    import re
                    response_code_match = re.search(r'<res:ResponseCode>(\d+)</res:ResponseCode>', response.text)
                    response_desc_match = re.search(r'<res:ResponseDesc>([^<]+)</res:ResponseDesc>', response.text)

                    response_code = response_code_match.group(1) if response_code_match else '1'
                    response_desc = response_desc_match.group(1) if response_desc_match else 'Unknown error'

                    if response_code == '0':
                        return {
                            'success': True,
                            'originator_conversation_id': originator_conversation_id,
                            'conversation_id': conversation_id,
                            'message': response_desc,
                            'response_code': response_code
                        }
                    else:
                        return {
                            'success': False,
                            'error': response_desc,
                            'response_code': response_code,
                            'conversation_id': conversation_id
                        }
                except Exception as parse_error:
                    return {
                        'success': False,
                        'error': f'Failed to parse response: {str(parse_error)}',
                        'response_text': response.text[:500]
                    }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}: {response.text[:200]}'
                }

        except Exception as e:
            return {
                'success': False,
                'error': f'Mandate creation failed: {str(e)}'
            }

    def activate_mandate(self, mandate_id, payer_msisdn, agreed_tc=True,
                        payer_account_name=''):
        """
        Activate Direct Debit Mandate
        
        Args:
            mandate_id: Telebirr mandate ID
            payer_msisdn: Payer phone number (MSISDN)
            agreed_tc: Whether user agreed to terms and conditions
            payer_account_name: Payer account name (optional)
            
        Returns:
            dict: Response with success status
        """
        try:
            # Build initiator (SP Operator)
            initiator = {
                'IdentifierType': 14,  # SP Operator Username
                'Identifier': self.sp_operator_id or self.third_party_id,
                'SecurityCredential': self.sp_operator_credential or self.third_party_password,
            }

            # Build receiver party (Payer MSISDN)
            receiver_party = {
                'IdentifierType': 1,  # MSISDN
                'Identifier': payer_msisdn,
            }

            # Build body XML according to Telebirr documentation
            body_xml = f'''<req:ActivateDirectDebitMandateRequest>
          <req:MandateID>{mandate_id}</req:MandateID>
          <req:AgreedTC>{'1' if agreed_tc else '0'}</req:AgreedTC>
        </req:ActivateDirectDebitMandateRequest>'''

            # Build SOAP envelope
            soap_envelope, originator_conversation_id, conversation_id = self._build_soap_envelope(
                command_id='ActivateCustomerDirectDebitMandate',
                initiator=initiator,
                receiver_party=receiver_party,
                body_xml=body_xml
            )

            # Make raw SOAP request
            headers = {
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': 'ActivateCustomerDirectDebitMandate'
            }

            response = requests.post(self.soap_url, data=soap_envelope, headers=headers, timeout=30, verify=False)

            # Parse response
            if response.status_code == 200:
                if 'soapenv:Fault' in response.text:
                    return {
                        'success': False,
                        'error': 'SOAP Fault returned',
                        'response_text': response.text[:500]
                    }

                try:
                    import re
                    response_code_match = re.search(r'<res:ResponseCode>(\d+)</res:ResponseCode>', response.text)
                    response_desc_match = re.search(r'<res:ResponseDesc>([^<]+)</res:ResponseDesc>', response.text)

                    response_code = response_code_match.group(1) if response_code_match else '1'
                    response_desc = response_desc_match.group(1) if response_desc_match else 'Unknown error'

                    if response_code == '0':
                        return {
                            'success': True,
                            'originator_conversation_id': originator_conversation_id,
                            'conversation_id': conversation_id,
                            'message': response_desc,
                            'response_code': response_code
                        }
                    else:
                        return {
                            'success': False,
                            'error': response_desc,
                            'response_code': response_code,
                            'conversation_id': conversation_id
                        }
                except Exception as parse_error:
                    return {
                        'success': False,
                        'error': f'Failed to parse response: {str(parse_error)}',
                        'response_text': response.text[:500]
                    }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}: {response.text[:200]}'
                }

        except Exception as e:
            return {
                'success': False,
                'error': f'Mandate activation failed: {str(e)}'
            }

    def initiate_debit(self, payer_reference_number, amount,
                      currency='ETB', shortcode=None, mandate_id=None, debug=False):
        """
        Initiate Direct Debit Transaction

        Args:
            payer_reference_number: Payer reference number
            amount: Amount to debit
            currency: Currency code (default ETB)
            shortcode: Shortcode for receiver party (defaults to TELEBIRR_SHORTCODE)
            mandate_id: Telebirr MandateID (optional per docs, but recommended --
                without it Telebirr cannot tie this debit to a specific mandate
                when a payer has more than one)
            debug: If True, print the SOAP envelope for debugging

        Returns:
            dict: Response with success status and transaction ID
        """
        try:
            # Set default shortcode
            if shortcode is None:
                shortcode = self.shortcode

            # Build initiator (Organization Operator or SP Operator)
            initiator = {
                'IdentifierType': 11,  # Organization Operator
                'Identifier': self.org_operator_id or self.third_party_id,
                'SecurityCredential': self.org_operator_credential or self.third_party_password,
                'ShortCode': shortcode,
            }

            # Build receiver party (Payer Reference Number)
            receiver_party = {
                'IdentifierType': 53,  # Payer Reference Number
                'Identifier': payer_reference_number,
            }

            # MandateID is optional per Telebirr's docs but recommended, so it's
            # only included when the caller has one to send.
            mandate_param = ''
            if mandate_id:
                mandate_param = f'''
            <req:Parameter>
              <com:Key>MandateID</com:Key>
              <com:Value>{mandate_id}</com:Value>
            </req:Parameter>'''

            # Build body XML according to Telebirr documentation
            body_xml = f'''<req:TransactionRequest>
          <req:Parameters>{mandate_param}
            <req:Parameter>
              <com:Key>Amount</com:Key>
              <com:Value>{amount}</com:Value>
            </req:Parameter>
            <req:Parameter>
              <com:Key>Currency</com:Key>
              <com:Value>{currency}</com:Value>
            </req:Parameter>
          </req:Parameters>
        </req:TransactionRequest>
        <req:Remark>Direct debit for {payer_reference_number}</req:Remark>'''

            # Build SOAP envelope (Caller uses ThirdParty credentials, Initiator uses Organization Operator)
            soap_envelope, originator_conversation_id, conversation_id = self._build_soap_envelope(
                command_id='InitTrans_Initiate Direct Debit Transaction',
                initiator=initiator,
                receiver_party=receiver_party,
                body_xml=body_xml
            )

            # Print SOAP envelope for debugging if debug=True
            if debug:
                print("=" * 80)
                print("SOAP ENVELOPE BEING SENT TO TELEBIRR:")
                print("=" * 80)
                print(soap_envelope)
                print("=" * 80)

            # Make raw SOAP request
            headers = {
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': 'InitTrans_Initiate Direct Debit Transaction'
            }

            response = requests.post(self.soap_url, data=soap_envelope, headers=headers, timeout=30, verify=False)

            # Parse response
            if response.status_code == 200:
                if 'soapenv:Fault' in response.text:
                    return {
                        'success': False,
                        'error': 'SOAP Fault returned',
                        'response_text': response.text[:500]
                    }

                try:
                    import re
                    response_code_match = re.search(r'<res:ResponseCode>(\d+)</res:ResponseCode>', response.text)
                    response_desc_match = re.search(r'<res:ResponseDesc>([^<]+)</res:ResponseDesc>', response.text)
                    transaction_id_match = re.search(r'<res:TransactionID>([^<]+)</res:TransactionID>', response.text)

                    response_code = response_code_match.group(1) if response_code_match else '1'
                    response_desc = response_desc_match.group(1) if response_desc_match else 'Unknown error'
                    transaction_id = transaction_id_match.group(1) if transaction_id_match else None

                    if response_code == '0':
                        return {
                            'success': True,
                            'originator_conversation_id': originator_conversation_id,
                            'conversation_id': conversation_id,
                            'transaction_id': transaction_id,
                            'message': response_desc,
                            'response_code': response_code
                        }
                    else:
                        return {
                            'success': False,
                            'error': response_desc,
                            'response_code': response_code,
                            'conversation_id': conversation_id
                        }
                except Exception as parse_error:
                    return {
                        'success': False,
                        'error': f'Failed to parse response: {str(parse_error)}',
                        'response_text': response.text[:500]
                    }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}: {response.text[:200]}'
                }

        except Exception as e:
            return {
                'success': False,
                'error': f'Direct debit initiation failed: {str(e)}'
            }

    def create_one_off_payment(self, payer_msisdn, payer_reference_number,
                              frequency='01', first_payment_date=None, expiry_date=None,
                              payee_shortcode=None, payee_account_name=None,
                              start_range_of_days=1, end_range_of_days=31,
                              debug=False):
        """
        Create One-Off Payment for Coin Purchasing
        
        This method creates a one-off payment using frequency (default '01' for Once)
        for coin purchases. The payment is processed via Telebirr Direct Debit.
        
        Args:
            payer_msisdn: Payer phone number (MSISDN)
            payer_reference_number: Payer reference number for payment
            frequency: Debit frequency (default '01' for Once)
            first_payment_date: Payment date (YYYYMMDD format or date object, defaults to today)
            expiry_date: Mandate expiry date (YYYYMMDD format or date object, defaults to today for one-off)
            payee_shortcode: Payee shortcode (defaults to TELEBIRR_SHORTCODE)
            payee_account_name: Payee account name (defaults to Flipstar)
            start_range_of_days: Start range of days for payment (default 1)
            end_range_of_days: End range of days for payment (default 31)
            debug: If True, print the SOAP envelope for debugging
            
        Returns:
            dict: Response with success status and payment details
        """
        try:
            # Format dates - default to today if not provided.
            #
            # isinstance(x, datetime) alone misses a plain date object: a
            # datetime.date is NOT a datetime.datetime instance (the
            # inheritance runs the other way), so a caller passing e.g.
            # datetime.date.today() fell through both checks below and got
            # embedded in the SOAP request as a raw date object -- str()'d
            # into "2026-08-16" instead of Telebirr's required "20260816" --
            # instead of being formatted at all. hasattr(..., 'strftime')
            # catches date the same way it catches datetime.
            if first_payment_date is None:
                first_payment_date = datetime.now().strftime('%Y%m%d')
            elif hasattr(first_payment_date, 'strftime'):
                first_payment_date = first_payment_date.strftime('%Y%m%d')

            # Format expiry date - default to today for one-off if not provided
            if expiry_date is None:
                expiry_date = first_payment_date
            elif hasattr(expiry_date, 'strftime'):
                expiry_date = expiry_date.strftime('%Y%m%d')

            # Use provided frequency (default '01' for one-off payment)
            # Can be overridden for testing other frequencies
            if not frequency:
                frequency = '01'

            # Set defaults
            if payee_shortcode is None:
                payee_shortcode = self.shortcode
            if payee_account_name is None:
                payee_account_name = self.payee_account_name

            # Build initiator (SP Operator)
            initiator = {
                'IdentifierType': 14,  # SP Operator Username
                'Identifier': self.sp_operator_id or self.third_party_id,
                'SecurityCredential': self.sp_operator_credential or self.third_party_password,
            }

            # Build receiver party (Payer MSISDN)
            receiver_party = {
                'IdentifierType': 1,  # MSISDN
                'Identifier': payer_msisdn,
            }

            # Build body XML for one-off payment
            body_xml = f'''<req:CreateDirectDebitMandateByPayerRequest>
          <req:Payee> 
            <com:IdentifierType>4</com:IdentifierType>
            <com:IdentifierValue>{payee_shortcode}</com:IdentifierValue>
          </req:Payee>
          <req:DirectDebitMandateInfo>
            <com:PayerReferenceNumber>{payer_reference_number}</com:PayerReferenceNumber>
            <com:AgreedTC>1</com:AgreedTC>
            <com:FirstPaymentDate>{first_payment_date}</com:FirstPaymentDate>
            <com:Frequency>{frequency}</com:Frequency>
            <com:StartRangeOfDays>{start_range_of_days}</com:StartRangeOfDays>
            <com:EndRangeOfDays>{end_range_of_days}</com:EndRangeOfDays>
            <com:ExpiryDate>{expiry_date}</com:ExpiryDate>
          </req:DirectDebitMandateInfo>
        </req:CreateDirectDebitMandateByPayerRequest>'''

            # Build SOAP envelope
            soap_envelope, originator_conversation_id, conversation_id = self._build_soap_envelope(
                command_id='CreateDirectDebitMandateByCustomer',
                initiator=initiator,
                receiver_party=receiver_party,
                body_xml=body_xml
            )

            # Print SOAP envelope for debugging if debug=True
            if debug:
                print("=" * 80)
                print("SOAP ENVELOPE BEING SENT TO TELEBIRR (ONE-OFF PAYMENT):")
                print("=" * 80)
                print(soap_envelope)
                print("=" * 80)

            # Make raw SOAP request
            headers = {
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': 'CreateDirectDebitMandateByCustomer'
            }

            response = requests.post(self.soap_url, data=soap_envelope, headers=headers, timeout=30, verify=False)

            # Parse response
            if response.status_code == 200:
                # Check for SOAP fault
                if 'soapenv:Fault' in response.text:
                    return {
                        'success': False,
                        'error': 'SOAP Fault returned',
                        'response_text': response.text[:500]
                    }

                # Parse ResponseCode and ResponseDesc using regex
                try:
                    import re
                    response_code_match = re.search(r'<res:ResponseCode>(\d+)</res:ResponseCode>', response.text)
                    response_desc_match = re.search(r'<res:ResponseDesc>([^<]+)</res:ResponseDesc>', response.text)

                    response_code = response_code_match.group(1) if response_code_match else '1'
                    response_desc = response_desc_match.group(1) if response_desc_match else 'Unknown error'
                except:
                    response_code = '1'
                    response_desc = 'Parse error'

                if response_code == '0':
                    return {
                        'success': True,
                        'originator_conversation_id': originator_conversation_id,
                        'conversation_id': conversation_id,
                        'message': response_desc or 'One-off payment request accepted successfully',
                        'response_code': response_code
                    }
                else:
                    return {
                        'success': False,
                        'error': response_desc or 'One-off payment request failed',
                        'response_code': response_code,
                        'response_text': response.text[:500]
                    }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}: {response.text[:200]}'
                }

        except Exception as e:
            return {
                'success': False,
                'error': f'One-off payment request failed: {str(e)}'
            }

    def cancel_mandate(self, mandate_id, payer_msisdn, debug=False):
        """
        Cancel Direct Debit Mandate
        
        Args:
            mandate_id: Telebirr mandate ID
            payer_msisdn: Payer phone number (MSISDN)
            debug: If True, print the SOAP envelope for debugging
            
        Returns:
            dict: Response with success status
        """
        try:
            # Build initiator (SP Operator)
            initiator = {
                'IdentifierType': 14,  # SP Operator Username
                'Identifier': self.sp_operator_id or self.third_party_id,
                'SecurityCredential': self.sp_operator_credential or self.third_party_password,
            }

            # Build receiver party (Payer MSISDN)
            receiver_party = {
                'IdentifierType': 1,  # MSISDN
                'Identifier': payer_msisdn,
            }

            # Build body XML according to Telebirr documentation
            body_xml = f'''<req:CancelDirectDebitMandateByPayerRequest>
               <req:MandateID>{mandate_id}</req:MandateID>
            </req:CancelDirectDebitMandateByPayerRequest>'''

            # Build SOAP envelope
            soap_envelope, originator_conversation_id, conversation_id = self._build_soap_envelope(
                command_id='CancelCustomerDirectDebitMandateByPayer',
                initiator=initiator,
                receiver_party=receiver_party,
                body_xml=body_xml
            )

            # Print SOAP envelope for debugging if debug=True
            if debug:
                print("=" * 80)
                print("SOAP ENVELOPE BEING SENT TO TELEBIRR:")
                print("=" * 80)
                print(soap_envelope)
                print("=" * 80)

            # Make raw SOAP request
            headers = {
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': 'CancelCustomerDirectDebitMandateByPayer'
            }

            response = requests.post(self.soap_url, data=soap_envelope, headers=headers, timeout=30, verify=False)

            # Parse response
            if response.status_code == 200:
                if 'soapenv:Fault' in response.text:
                    return {
                        'success': False,
                        'error': 'SOAP Fault returned',
                        'response_text': response.text[:500]
                    }

                try:
                    import re
                    response_code_match = re.search(r'<res:ResponseCode>(\d+)</res:ResponseCode>', response.text)
                    response_desc_match = re.search(r'<res:ResponseDesc>([^<]+)</res:ResponseDesc>', response.text)

                    response_code = response_code_match.group(1) if response_code_match else '1'
                    response_desc = response_desc_match.group(1) if response_desc_match else 'Unknown error'

                    if response_code == '0':
                        return {
                            'success': True,
                            'originator_conversation_id': originator_conversation_id,
                            'conversation_id': conversation_id,
                            'message': response_desc,
                            'response_code': response_code
                        }
                    else:
                        return {
                            'success': False,
                            'error': response_desc,
                            'response_code': response_code,
                            'conversation_id': conversation_id
                        }
                except Exception as parse_error:
                    return {
                        'success': False,
                        'error': f'Failed to parse response: {str(parse_error)}',
                        'response_text': response.text[:500]
                    }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}: {response.text[:200]}'
                }

        except Exception as e:
            return {
                'success': False,
                'error': f'Mandate cancellation failed: {str(e)}'
            }

    def query_mandate_by_payer(self, payer_msisdn, mandate_statuses=None, debug=False):
        """
        Query Direct Debit Mandate by Payer
        
        Args:
            payer_msisdn: Payer phone number (MSISDN)
            mandate_statuses: Optional list of mandate status codes (e.g., ['03', '01'])
            debug: If True, print the SOAP envelope for debugging
            
        Returns:
            dict: Response with success status and mandate data
        """
        try:
            # Build initiator (Organization Operator)
            initiator = {
                'IdentifierType': 11,  # Organization Operator
                'Identifier': self.org_operator_id or self.third_party_id,
                'SecurityCredential': self.org_operator_credential or self.third_party_password,
                'ShortCode': self.shortcode,
            }

            # Build receiver party (Payer MSISDN)
            receiver_party = {
                'IdentifierType': 1,  # MSISDN
                'Identifier': payer_msisdn,
            }

            # Build body XML with mandate statuses
            if mandate_statuses and len(mandate_statuses) > 0:
                status_xml = '\n'.join([f'          <req:MandateStatus>{status}</req:MandateStatus>' for status in mandate_statuses])
            else:
                status_xml = ''

            body_xml = f'''<req:QueryDirectDebitMandateByPayerRequest>
{status_xml}
        </req:QueryDirectDebitMandateByPayerRequest>'''

            # Build SOAP envelope
            soap_envelope, originator_conversation_id, conversation_id = self._build_soap_envelope(
                command_id='QueryDirectDebitMandateByPayer',
                initiator=initiator,
                receiver_party=receiver_party,
                body_xml=body_xml
            )

            # Print SOAP envelope for debugging if debug=True
            if debug:
                print("=" * 80)
                print("SOAP ENVELOPE BEING SENT TO TELEBIRR:")
                print("=" * 80)
                print(soap_envelope)
                print("=" * 80)

            # Make raw SOAP request
            headers = {
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': 'QueryDirectDebitMandateByPayer'
            }

            response = requests.post(self.soap_url, data=soap_envelope, headers=headers, timeout=30, verify=False)

            # Parse response
            if response.status_code == 200:
                if 'soapenv:Fault' in response.text:
                    return {
                        'success': False,
                        'error': 'SOAP Fault returned',
                        'response_text': response.text[:500]
                    }

                try:
                    import re
                    response_code_match = re.search(r'<res:ResponseCode>(\d+)</res:ResponseCode>', response.text)
                    response_desc_match = re.search(r'<res:ResponseDesc>([^<]+)</res:ResponseDesc>', response.text)

                    # A payer can have more than one mandate on file, and
                    # Telebirr's response can include several
                    # DirectDebitMandateInfo blocks -- without parsing each
                    # one individually a caller has no way to tell which
                    # mandate_id/status belongs to which entry, only the raw
                    # response_text to re-parse itself.
                    mandate_blocks = re.findall(
                        r'<res:DirectDebitMandateInfo>.*?</res:DirectDebitMandateInfo>', response.text, re.DOTALL,
                    )
                    if not mandate_blocks:
                        mandate_blocks = re.findall(
                            r'<com:DirectDebitMandateInfo>.*?</com:DirectDebitMandateInfo>', response.text, re.DOTALL,
                        )

                    mandate_id_match = re.search(r'<com:MandateID>([^<]+)</com:MandateID>', response.text)
                    mandate_status_match = re.search(r'<com:MandateStatus>([^<]+)</com:MandateStatus>', response.text)
                    payer_reference_match = re.search(
                        r'<com:PayerReferenceNumber>([^<]+)</com:PayerReferenceNumber>', response.text,
                    )

                    response_code = response_code_match.group(1) if response_code_match else '1'
                    response_desc = response_desc_match.group(1) if response_desc_match else 'Unknown error'

                    if response_code == '0':
                        mandates = []
                        for block in mandate_blocks:
                            block_mandate_id = re.search(r'<com:MandateID>([^<]+)</com:MandateID>', block)
                            block_payer_ref = re.search(
                                r'<com:PayerReferenceNumber>([^<]+)</com:PayerReferenceNumber>', block,
                            )
                            block_mandate_status = re.search(r'<com:MandateStatus>([^<]+)</com:MandateStatus>', block)
                            if block_mandate_id:
                                mandates.append({
                                    'mandate_id': block_mandate_id.group(1),
                                    'payer_reference_number': block_payer_ref.group(1) if block_payer_ref else None,
                                    'mandate_status': block_mandate_status.group(1) if block_mandate_status else None,
                                })

                        return {
                            'success': True,
                            'originator_conversation_id': originator_conversation_id,
                            'conversation_id': conversation_id,
                            'message': response_desc,
                            'response_code': response_code,
                            'response_text': response.text,
                            'mandate_id': mandate_id_match.group(1) if mandate_id_match else None,
                            'mandate_status': mandate_status_match.group(1) if mandate_status_match else None,
                            'payer_reference_number': payer_reference_match.group(1) if payer_reference_match else None,
                            'mandates': mandates,
                        }
                    else:
                        return {
                            'success': False,
                            'error': response_desc,
                            'response_code': response_code,
                            'conversation_id': conversation_id
                        }
                except Exception as parse_error:
                    return {
                        'success': False,
                        'error': f'Failed to parse response: {str(parse_error)}',
                        'response_text': response.text[:500]
                    }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}: {response.text[:200]}'
                }

        except Exception as e:
            return {
                'success': False,
                'error': f'Mandate query failed: {str(e)}'
            }

    def process_callback(self, callback_data):
        """
        Process async callback from Telebirr
        
        Args:
            callback_data: Callback data from Telebirr (SOAP Result envelope)
            
        Returns:
            dict: Processed callback result
        """
        try:
            # Extract result data
            result_type = callback_data.get('ResultType')
            result_code = callback_data.get('ResultCode')
            result_desc = callback_data.get('ResultDesc')
            conversation_id = callback_data.get('ConversationID')
            originator_conversation_id = callback_data.get('OriginatorConversationID')

            # Determine success
            is_success = result_code == '0' and result_type == '0'

            # Extract transaction ID if present
            transaction_id = None
            if 'TransactionResult' in callback_data:
                transaction_id = callback_data['TransactionResult'].get('TransactionID')

            return {
                'success': is_success,
                'result_code': result_code,
                'result_desc': result_desc,
                'conversation_id': conversation_id,
                'originator_conversation_id': originator_conversation_id,
                'transaction_id': transaction_id,
                'raw_data': callback_data
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'Callback processing failed: {str(e)}'
            }

    def initiate_b2c_payment(self, receiver_msisdn, amount, currency='ETB',
                           reason_type=None, remark='', reference_data=None,
                           initiator_type='org_operator', debug=False):
        """
        Initiate Individual B2C Payment Transaction

        Pays individual customers one by one. Used for withdrawal payouts,
        salaries, relief, allowances, rewards, bonuses, interest payments, etc.

        Args:
            receiver_msisdn: Customer phone number (MSISDN)
            amount: Payment amount
            currency: Currency code (default ETB)
            reason_type: Reason type for payment (defaults to b2c_reason_type)
            remark: Additional remarks
            reference_data: Optional reference data as dict (e.g., {'withdrawal_id': '...'})
            initiator_type: 'org_operator' (12) or 'sp_operator' (14)
            debug: If True, log the SOAP envelope for debugging

        Returns:
            dict: Response with success status and transaction details
        """
        try:
            if reason_type is None:
                reason_type = self.b2c_reason_type
            if reference_data is None:
                reference_data = {}

            # Refuse before sending rather than after being refused.
            #
            # The envelope renders <req:ShortCode> unconditionally, so an
            # unset short code goes out as an empty element and telebirr
            # answers with a generic failure that names nothing. Every payout
            # then fails identically, and the withdrawal is marked failed with
            # no way to tell a misconfiguration from an outage. This is how
            # staging ran: TELEBIRR_SHORTCODE was never set.
            if not self.b2c_shortcode:
                logger.error(
                    'B2C payout refused: no short code configured '
                    '(set TELEBIRR_B2C_SHORTCODE, or TELEBIRR_SHORTCODE)'
                )
                return {
                    'success': False,
                    'error': 'Payouts are not configured. Please contact support.',
                    'code': 'b2c_shortcode_missing',
                }

            # Build initiator based on type -- use B2C-specific credentials
            # for B2C payments, falling back to the direct-debit ones.
            if initiator_type == 'sp_operator':
                initiator = {
                    'IdentifierType': 14,  # SP Operator Username
                    'Identifier': self.sp_operator_id,
                    'SecurityCredential': self.sp_operator_credential,
                }
            else:
                b2c_org_id = self.b2c_org_operator_id or self.org_operator_id
                b2c_org_credential = self.b2c_org_operator_credential or self.org_operator_credential
                initiator = {
                    'IdentifierType': 12,  # Organization Operator/Username
                    'Identifier': b2c_org_id,
                    'SecurityCredential': b2c_org_credential,
                    'ShortCode': self.b2c_shortcode,
                }

            receiver_party = {
                'IdentifierType': 1,  # MSISDN
                'Identifier': receiver_msisdn,
            }

            b2c_caller_id = self.b2c_third_party_id or self.third_party_id
            b2c_caller_password = self.b2c_third_party_password or self.third_party_password

            originator_conversation_id = self._generate_originator_conversation_id()
            conversation_id = self._generate_conversation_id()
            timestamp = self._generate_timestamp()

            amount_formatted = f"{Decimal(amount):.2f}"

            soap_envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:com="http://cps.huawei.com/cpsinterface/common" xmlns:api="http://cps.huawei.com/cpsinterface/api_requestmgr" xmlns:req="http://cps.huawei.com/cpsinterface/request">
   <soapenv:Header/>
   <soapenv:Body>
      <api:Request>
         <req:Header>
            <req:Version>1.0</req:Version>
            <req:CommandID>InitTrans_{self.b2c_service_code}</req:CommandID>
            <req:OriginatorConversationID>{originator_conversation_id}</req:OriginatorConversationID>
            <req:Caller>
               <req:CallerType>{self.caller_type}</req:CallerType>
               <req:ThirdPartyID>{b2c_caller_id}</req:ThirdPartyID>
               <req:Password>{b2c_caller_password}</req:Password>
               <req:ResultURL>{self.b2c_result_url or self.result_url}</req:ResultURL>
            </req:Caller>
            <req:KeyOwner>1</req:KeyOwner>
            <req:Timestamp>{timestamp}</req:Timestamp>
         </req:Header>
         <req:Body>
            <req:Identity>
               <req:Initiator>
                  <req:IdentifierType>{initiator['IdentifierType']}</req:IdentifierType>
                  <req:Identifier>{initiator['Identifier']}</req:Identifier>
                  <req:SecurityCredential>{initiator['SecurityCredential']}</req:SecurityCredential>
                  <req:ShortCode>{initiator.get('ShortCode', '')}</req:ShortCode>
               </req:Initiator>
               <req:ReceiverParty>
                  <req:IdentifierType>{receiver_party['IdentifierType']}</req:IdentifierType>
                  <req:Identifier>{receiver_party['Identifier']}</req:Identifier>
               </req:ReceiverParty>
            </req:Identity>
            <req:TransactionRequest>
               <req:Parameters>
                  <req:Amount>{amount_formatted}</req:Amount>
                  <req:Currency>{currency}</req:Currency>
               </req:Parameters>
            </req:TransactionRequest>
         </req:Body>
      </api:Request>
   </soapenv:Body>
</soapenv:Envelope>'''

            if debug:
                logger.info('B2C SOAP envelope:\n%s', soap_envelope)

            logger.info(
                'Initiating B2C payment: receiver=%s, amount=%s %s, reason_type=%s',
                receiver_msisdn, amount, currency, reason_type,
            )

            b2c_soap_url = self.b2c_soap_url or self.soap_url
            headers = {
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': f'InitTrans_{self.b2c_service_code}',
            }

            response = requests.post(b2c_soap_url, data=soap_envelope, headers=headers, timeout=30, verify=False)

            if response.status_code != 200:
                return {
                    'success': False,
                    'error': f'HTTP {response.status_code}: {response.text[:500]}',
                }

            if 'soapenv:Fault' in response.text:
                return {
                    'success': False,
                    'error': 'SOAP Fault returned',
                    'response_text': response.text[:500],
                }

            try:
                response_code_match = re.search(r'<res:ResponseCode>(\d+)</res:ResponseCode>', response.text)
                response_desc_match = re.search(r'<res:ResponseDesc>([^<]+)</res:ResponseDesc>', response.text)

                response_code = response_code_match.group(1) if response_code_match else '1'
                response_desc = response_desc_match.group(1) if response_desc_match else 'Unknown error'

                if response_code == '0':
                    return {
                        'success': True,
                        'originator_conversation_id': originator_conversation_id,
                        'conversation_id': conversation_id,
                        'message': response_desc,
                        'response_code': response_code,
                    }
                return {
                    'success': False,
                    'error': response_desc,
                    'response_code': response_code,
                    'originator_conversation_id': originator_conversation_id,
                    'conversation_id': conversation_id,
                }
            except Exception as parse_error:
                return {
                    'success': False,
                    'error': f'Failed to parse response: {str(parse_error)}',
                    'response_text': response.text[:500],
                }

        except Exception as e:
            return {
                'success': False,
                'error': f'B2C payment initiation failed: {str(e)}',
            }

    def initiate_ussd_push_payment(self, amount, phone_number, coins, result_url=None):
        """
        Initiate a USSD Push payment (InitTrans_BuyGoodsForCustomer) --
        triggers an immediate PIN-entry prompt on the payer's phone, unlike
        the direct-debit mandate flow above which requires a one-time setup.

        Args:
            amount: Payment amount in ETB (string or Decimal)
            phone_number: Customer MSISDN (251 format)
            coins: Number of coins being purchased (0 if not a coin purchase,
                e.g. a subscription payment)
            result_url: Optional override for the configured webhook URL

        Returns:
            dict: {'success': bool, 'originator_conversation_id': str,
                   'conversation_id': str, 'message': str, 'error': str (if failed)}
        """
        try:
            ussd_soap_url = self.ussd_soap_url or self.soap_url
            ussd_result_url = result_url or self.ussd_result_url or self.result_url
            ussd_third_party_id = self.ussd_third_party_id or self.third_party_id
            ussd_third_party_password = self.ussd_third_party_password or self.third_party_password
            ussd_org_operator_id = self.ussd_org_operator_id or self.sp_operator_id
            ussd_org_operator_credential = self.ussd_org_operator_credential or self.sp_operator_credential
            ussd_merchant_shortcode = self.ussd_merchant_shortcode or self.shortcode

            originator_conversation_id = self._generate_originator_conversation_id()
            conversation_id = self._generate_conversation_id()
            timestamp = self._generate_timestamp()

            soap_envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:api="http://cps.huawei.com/cpsinterface/api_requestmgr" xmlns:req="http://cps.huawei.com/cpsinterface/request" xmlns:com="http://cps.huawei.com/cpsinterface/common">
  <soapenv:Header/>
  <soapenv:Body>
    <api:Request>
      <req:Header>
        <req:Version>1.0</req:Version>
        <req:CommandID>InitTrans_BuyGoodsForCustomer</req:CommandID>
        <req:OriginatorConversationID>{originator_conversation_id}</req:OriginatorConversationID>
        <req:ConversationID>{conversation_id}</req:ConversationID>
        <req:Caller>
          <req:CallerType>{self.caller_type}</req:CallerType>
          <req:ThirdPartyID>{ussd_third_party_id}</req:ThirdPartyID>
          <req:Password>{ussd_third_party_password}</req:Password>
          <req:ResultURL>{ussd_result_url}</req:ResultURL>
        </req:Caller>
        <req:KeyOwner>1</req:KeyOwner>
        <req:Timestamp>{timestamp}</req:Timestamp>
      </req:Header>
      <req:Body>
        <req:Identity>
          <req:Initiator>
            <req:IdentifierType>12</req:IdentifierType>
            <req:Identifier>{ussd_org_operator_id}</req:Identifier>
            <req:SecurityCredential>{ussd_org_operator_credential}</req:SecurityCredential>
            <req:ShortCode>{ussd_merchant_shortcode}</req:ShortCode>
          </req:Initiator>
          <req:PrimaryParty>
            <req:IdentifierType>1</req:IdentifierType>
            <req:Identifier>{phone_number}</req:Identifier>
          </req:PrimaryParty>
          <req:ReceiverParty>
            <req:IdentifierType>4</req:IdentifierType>
            <req:Identifier>{ussd_merchant_shortcode}</req:Identifier>
          </req:ReceiverParty>
        </req:Identity>
        <req:TransactionRequest>
          <req:Parameters>
            <req:Amount>{amount}</req:Amount>
            <req:Currency>ETB</req:Currency>
          </req:Parameters>
        </req:TransactionRequest>
      </req:Body>
    </api:Request>
  </soapenv:Body>
</soapenv:Envelope>'''

            logger.info('Initiating USSD Push payment for %s, amount=%s ETB, coins=%s', phone_number, amount, coins)

            headers = {
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': 'InitTrans_BuyGoodsForCustomer',
            }
            response = requests.post(ussd_soap_url, data=soap_envelope, headers=headers, verify=False, timeout=30)

            if response.status_code != 200:
                return {'success': False, 'error': f'HTTP {response.status_code}: {response.text[:200]}'}

            response_code_match = re.search(r'<res:ResponseCode>(\d+)</res:ResponseCode>', response.text)
            response_desc_match = re.search(r'<res:ResponseDesc>([^<]+)</res:ResponseDesc>', response.text)
            conversation_id_match = re.search(r'<res:ConversationID>([^<]+)</res:ConversationID>', response.text)

            response_code = response_code_match.group(1) if response_code_match else None
            response_desc = response_desc_match.group(1) if response_desc_match else 'Unknown'

            if response_code == '0':
                return {
                    'success': True,
                    'originator_conversation_id': originator_conversation_id,
                    'conversation_id': conversation_id_match.group(1) if conversation_id_match else conversation_id,
                    'message': response_desc,
                    'response_code': response_code,
                }
            return {
                'success': False,
                'error': response_desc,
                'response_code': response_code,
                'conversation_id': conversation_id,
            }

        except Exception as e:
            return {'success': False, 'error': f'USSD Push payment failed: {str(e)}'}


# Singleton instance
telebirr_direct_debit_service = TelebirrDirectDebitService()
