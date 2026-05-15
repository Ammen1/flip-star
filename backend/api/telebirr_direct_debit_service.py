"""
Telebirr Direct Debit SOAP Service

Handles SOAP API operations for direct debit mandate management:
- CreateDirectDebitMandateByCustomer
- ActivateCustomerDirectDebitMandate
- InitTrans_Initiate Direct Debit Transaction
- CancelCustomerDirectDebitMandateByPayer
"""
import uuid
from datetime import datetime
from decimal import Decimal
from django.conf import settings
import requests


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
    
    def _build_soap_envelope(self, command_id, initiator, receiver_party, body_xml):
        """
        Build SOAP envelope for Telebirr Direct Debit API
        
        Args:
            command_id: SOAP command ID
            initiator: Initiator identifier dict (IdentifierType, Identifier, SecurityCredential)
            receiver_party: Receiver party dict (IdentifierType, Identifier)
            body_xml: Body XML string specific to the operation
            
        Returns:
            str: Complete SOAP envelope XML
        """
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
        <req:CommandID>{command_id}</req:CommandID>
        <req:OriginatorConversationID>{originator_conversation_id}</req:OriginatorConversationID>
        <req:ConversationID>{conversation_id}</req:ConversationID>
        <req:Caller>
          <req:CallerType>{self.caller_type}</req:CallerType>
          <req:ThirdPartyID>{self.third_party_id}</req:ThirdPartyID>
          <req:Password>{self.third_party_password}</req:Password>
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
            <req:SecurityCredential>{initiator['SecurityCredential']}</req:SecurityCredential>
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
                      end_range_of_days=22):
        """
        Create Direct Debit Mandate
        
        Args:
            payer_msisdn: Payer phone number (MSISDN)
            payer_reference_number: Payer reference number for mandate
            frequency: Debit frequency (02=Daily, 03=Weekly, 05=Monthly, etc.)
            first_payment_date: First payment date (YYYYMMDD format or date object)
            expiry_date: Mandate expiry date (YYYYMMDD format or date object)
            payee_shortcode: Payee shortcode (defaults to TELEBIRR_SHORTCODE)
            payee_account_name: Payee account name (defaults to Flipstar)
            start_range_of_days: Start range of days for payment (default 1)
            end_range_of_days: End range of days for payment (default 22)
            
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
            <com:PayeeAccountName>{payee_account_name}</com:PayeeAccountName>
            <com:PayerAccountName></com:PayerAccountName>
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
          <req:PayerAccountName>{payer_account_name}</req:PayerAccountName>
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
    
    def initiate_debit(self, mandate_id, payer_reference_number, amount, 
                      currency='ETB', shortcode=None):
        """
        Initiate Direct Debit Transaction
        
        Args:
            mandate_id: Telebirr mandate ID
            payer_reference_number: Payer reference number
            amount: Amount to debit
            currency: Currency code (default ETB)
            shortcode: Shortcode for receiver party (defaults to TELEBIRR_SHORTCODE)
            
        Returns:
            dict: Response with success status and transaction ID
        """
        try:
            # Set default shortcode
            if shortcode is None:
                shortcode = self.shortcode
            
            # Build initiator (Organization Operator or SP Operator)
            initiator = {
                'IdentifierType': 14,  # SP Operator Username
                'Identifier': self.third_party_id,
                'SecurityCredential': self.third_party_password,
                'ShortCode': shortcode,
            }
            
            # Build receiver party (Payer Reference Number)
            receiver_party = {
                'IdentifierType': 53,  # Payer Reference Number
                'Identifier': payer_reference_number,
            }
            
            # Build body XML according to Telebirr documentation
            body_xml = f'''<req:TransactionRequest>
          <req:Parameters>
            <req:Parameter>
              <com:Key>MandateID</com:Key>
              <com:Value>{mandate_id}</com:Value>
            </req:Parameter>
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
        <req:Remark>Direct debit for mandate {mandate_id}</req:Remark>'''
            
            # Build SOAP envelope
            soap_envelope, originator_conversation_id, conversation_id = self._build_soap_envelope(
                command_id='InitTrans_Initiate Direct Debit Transaction',
                initiator=initiator,
                receiver_party=receiver_party,
                body_xml=body_xml
            )
            
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
    
    def cancel_mandate(self, mandate_id, payer_msisdn):
        """
        Cancel Direct Debit Mandate
        
        Args:
            mandate_id: Telebirr mandate ID
            payer_msisdn: Payer phone number (MSISDN)
            
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


# Singleton instance
telebirr_direct_debit_service = TelebirrDirectDebitService()
