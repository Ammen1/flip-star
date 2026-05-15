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
from zeep import Client
from zeep.transports import Transport
from requests import Session


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
        
        # Initialize SOAP client
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize SOAP client"""
        try:
            session = Session()
            session.verify = False  # Disable SSL verification for testing (enable in production)
            transport = Transport(session=session)
            self.client = Client(self.soap_url, transport=transport)
        except Exception as e:
            print(f"Failed to initialize SOAP client: {str(e)}")
    
    def _generate_originator_conversation_id(self):
        """Generate unique originator conversation ID"""
        return f"S_X{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    def _generate_timestamp(self):
        """Generate timestamp in YYYYMMDDHHMMSS format"""
        return datetime.now().strftime('%Y%m%d%H%M%S')
    
    def _build_soap_envelope(self, command_id, initiator, receiver_party, body_data):
        """
        Build SOAP envelope for Telebirr Direct Debit API
        
        Args:
            command_id: SOAP command ID
            initiator: Initiator identifier dict (IdentifierType, Identifier, SecurityCredential)
            receiver_party: Receiver party dict (IdentifierType, Identifier)
            body_data: Body data dict specific to the operation
            
        Returns:
            dict: SOAP request envelope
        """
        originator_conversation_id = self._generate_originator_conversation_id()
        timestamp = self._generate_timestamp()
        
        envelope = {
            'Header': {
                'Version': '1.0',
                'CommandID': command_id,
                'OriginatorConversationID': originator_conversation_id,
                'Caller': {
                    'CallerType': self.caller_type,
                    'ThirdPartyID': self.third_party_id,
                    'Password': self.third_party_password,
                    'ResultURL': self.result_url,
                },
                'KeyOwner': '1',
                'Timestamp': timestamp,
            },
            'Body': {
                'Identity': {
                    'Initiator': initiator,
                    'ReceiverParty': receiver_party,
                },
                **body_data
            }
        }
        
        return envelope, originator_conversation_id
    
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
            
            # Build body data
            body_data = {
                'CreateDirectDebitMandateByPayerRequest': {
                    'Payee': {
                        'IdentifierType': 4,  # Shortcode
                        'IdentifierValue': payee_shortcode,
                    },
                    'DirectDebitMandateInfo': {
                        'PayerReferenceNumber': payer_reference_number,
                        'AgreedTC': '1',  # User agreed to TC
                        'PayeeAccountName': payee_account_name,
                        'PayerAccountName': '',  # Optional, filled during activation
                        'FirstPaymentDate': first_payment_date,
                        'Frequency': frequency,
                        'StartRangeOfDays': str(start_range_of_days),
                        'EndRangeOfDays': str(end_range_of_days),
                        'ExpiryDate': expiry_date,
                    }
                }
            }
            
            # Build SOAP envelope
            envelope, originator_conversation_id = self._build_soap_envelope(
                command_id='CreateDirectDebitMandateByCustomer',
                initiator=initiator,
                receiver_party=receiver_party,
                body_data=body_data
            )
            
            # Call SOAP API
            if self.client is None:
                self._init_client()
            
            # Make actual SOAP call
            try:
                response = self.client.service.Request(envelope)
                # Parse response
                response_code = response.Body.ResponseCode
                response_desc = response.Body.ResponseDesc
                conversation_id = response.Header.ConversationID
                
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
            except Exception as soap_error:
                print(f"SOAP call failed: {str(soap_error)}")
                return {
                    'success': False,
                    'error': f'SOAP call failed: {str(soap_error)}'
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
            
            # Build body data
            body_data = {
                'ActivateDirectDebitMandateRequest': {
                    'MandateID': mandate_id,
                    'AgreedTC': '1' if agreed_tc else '0',
                    'PayerAccountName': payer_account_name,
                }
            }
            
            # Build SOAP envelope
            envelope, originator_conversation_id = self._build_soap_envelope(
                command_id='ActivateCustomerDirectDebitMandate',
                initiator=initiator,
                receiver_party=receiver_party,
                body_data=body_data
            )
            
            # Call SOAP API
            if self.client is None:
                self._init_client()
            
            # Make actual SOAP call
            try:
                response = self.client.service.Request(envelope)
                # Parse response
                response_code = response.Body.ResponseCode
                response_desc = response.Body.ResponseDesc
                conversation_id = response.Header.ConversationID
                
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
            except Exception as soap_error:
                print(f"SOAP call failed: {str(soap_error)}")
                return {
                    'success': False,
                    'error': f'SOAP call failed: {str(soap_error)}'
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
            
            # Build transaction parameters
            parameters = [
                {'Key': 'MandateID', 'Value': mandate_id},
                {'Key': 'Amount', 'Value': str(amount)},
                {'Key': 'Currency', 'Value': currency},
            ]
            
            # Build body data
            body_data = {
                'TransactionRequest': {
                    'Parameters': {
                        'Parameter': parameters
                    }
                },
                'Remark': f'Direct debit for mandate {mandate_id}'
            }
            
            # Build SOAP envelope
            envelope, originator_conversation_id = self._build_soap_envelope(
                command_id='InitTrans_Initiate Direct Debit Transaction',
                initiator=initiator,
                receiver_party=receiver_party,
                body_data=body_data
            )
            
            # Call SOAP API
            if self.client is None:
                self._init_client()
            
            # Make actual SOAP call
            try:
                response = self.client.service.Request(envelope)
                # Parse response
                response_code = response.Body.ResponseCode
                response_desc = response.Body.ResponseDesc
                conversation_id = response.Header.ConversationID
                
                if response_code == '0':
                    # Extract transaction ID if present
                    transaction_id = None
                    if hasattr(response.Body, 'TransactionResult'):
                        transaction_id = response.Body.TransactionResult.TransactionID
                    
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
            except Exception as soap_error:
                print(f"SOAP call failed: {str(soap_error)}")
                return {
                    'success': False,
                    'error': f'SOAP call failed: {str(soap_error)}'
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
            
            # Build body data
            body_data = {
                'CancelDirectDebitMandateByPayerRequest': {
                    'MandateID': mandate_id,
                }
            }
            
            # Build SOAP envelope
            envelope, originator_conversation_id = self._build_soap_envelope(
                command_id='CancelCustomerDirectDebitMandateByPayer',
                initiator=initiator,
                receiver_party=receiver_party,
                body_data=body_data
            )
            
            # Call SOAP API
            if self.client is None:
                self._init_client()
            
            # Make actual SOAP call
            try:
                response = self.client.service.Request(envelope)
                # Parse response
                response_code = response.Body.ResponseCode
                response_desc = response.Body.ResponseDesc
                conversation_id = response.Header.ConversationID
                
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
            except Exception as soap_error:
                print(f"SOAP call failed: {str(soap_error)}")
                return {
                    'success': False,
                    'error': f'SOAP call failed: {str(soap_error)}'
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
