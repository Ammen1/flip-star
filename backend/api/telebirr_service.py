"""
Telebirr Payment Gateway Integration Service
Handles payment initiation, callback processing, and encryption/decryption
"""
import json
import base64
import hashlib
import hmac
import time
from datetime import datetime
from decimal import Decimal
import requests
from django.conf import settings
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend


class TelebirrService:
    """Telebirr Payment Gateway Service"""
    
    def __init__(self):
        self.base_url = getattr(settings, 'TELEBIRR_BASE_URL', 'https://developerportal.ethiotelebirr.et:38443/apiaccess/payment/gateway')
        self.fabric_app_id = getattr(settings, 'TELEBIRR_FABRIC_APP_ID', '')
        self.app_secret = getattr(settings, 'TELEBIRR_APP_SECRET', '')
        self.merchant_app_id = getattr(settings, 'TELEBIRR_MERCHANT_APP_ID', '')
        self.merchant_code = getattr(settings, 'TELEBIRR_MERCHANT_CODE', '')
        self.private_key = getattr(settings, 'TELEBIRR_PRIVATE_KEY', '')
        self.public_key = getattr(settings, 'TELEBIRR_PUBLIC_KEY', '')
        self.notify_url = getattr(settings, 'TELEBIRR_NOTIFY_URL', '')
        self.return_url = getattr(settings, 'TELEBIRR_RETURN_URL', '')
    
    def _generate_signature(self, data):
        """Generate RSA signature for payment request"""
        try:
            # Load private key
            private_key = serialization.load_pem_private_key(
                self.private_key.encode(),
                password=None,
                backend=default_backend()
            )
            
            # Convert data to JSON string
            message = json.dumps(data, separators=(',', ':'), sort_keys=True)
            
            # Sign the message
            signature = private_key.sign(
                message.encode('utf-8'),
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            
            # Base64 encode the signature
            return base64.b64encode(signature).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Signature generation failed: {str(e)}")
    
    def _verify_signature(self, data, signature):
        """Verify RSA signature from Telebirr callback"""
        try:
            # Load public key
            public_key = serialization.load_pem_public_key(
                self.public_key.encode(),
                backend=default_backend()
            )
            
            # Convert data to JSON string
            message = json.dumps(data, separators=(',', ':'), sort_keys=True)
            
            # Decode the signature
            signature_bytes = base64.b64decode(signature)
            
            # Verify the signature
            public_key.verify(
                signature_bytes,
                message.encode('utf-8'),
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return True
        except Exception as e:
            print(f"Signature verification failed: {str(e)}")
            return False
    
    def _generate_transaction_id(self):
        """Generate unique transaction ID"""
        timestamp = int(time.time() * 1000)
        return f"TX{timestamp}"
    
    def initiate_payment(self, amount, phone_number, user_id, package_id):
        """
        Initiate a Telebirr payment request
        
        Args:
            amount: Payment amount in ETB (Decimal or float)
            phone_number: Customer phone number (with country code, e.g., +251911234567)
            user_id: User ID for reference
            package_id: Coin package ID for reference
            
        Returns:
            dict: Payment initiation response with redirect URL
        """
        try:
            # Generate transaction ID
            transaction_id = self._generate_transaction_id()
            
            # Prepare payment data
            payment_data = {
                'appId': self.fabric_app_id,
                'appSecret': self.app_secret,
                'merchantAppId': self.merchant_app_id,
                'merchantCode': self.merchant_code,
                'nonce': str(int(time.time() * 1000)),
                'timestamp': str(int(time.time() * 1000)),
                'outTradeNo': transaction_id,
                'totalAmount': str(Decimal(str(amount))),
                'subject': 'Coin Purchase',
                'body': f'Purchase coins - User ID: {user_id}, Package ID: {package_id}',
                'notifyUrl': self.notify_url,
                'returnUrl': self.return_url,
                'timeoutExpress': '30m',  # Payment timeout
                'buyerId': phone_number,
            }
            
            # Generate signature
            signature = self._generate_signature(payment_data)
            payment_data['signature'] = signature
            
            # Make API request
            url = f"{self.base_url}/api/v1/order/create"
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            response = requests.post(url, json=payment_data, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('code') == 'SUCCESS' or result.get('success'):
                return {
                    'success': True,
                    'transaction_id': transaction_id,
                    'payment_url': result.get('paymentUrl') or result.get('redirectUrl'),
                    'out_trade_no': result.get('outTradeNo'),
                    'message': 'Payment initiated successfully'
                }
            else:
                return {
                    'success': False,
                    'error': result.get('message', 'Payment initiation failed'),
                    'code': result.get('code')
                }
                
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Payment initiation error: {str(e)}'
            }
    
    def process_callback(self, callback_data):
        """
        Process Telebirr payment callback (webhook)
        
        Args:
            callback_data: Dict containing callback data from Telebirr
            
        Returns:
            dict: Processed payment result
        """
        try:
            # Extract signature from callback
            signature = callback_data.get('signature')
            if not signature:
                return {
                    'success': False,
                    'error': 'Missing signature in callback'
                }
            
            # Prepare data for verification (exclude signature field)
            verify_data = {k: v for k, v in callback_data.items() if k != 'signature'}
            
            # Verify signature
            if not self._verify_signature(verify_data, signature):
                return {
                    'success': False,
                    'error': 'Invalid signature'
                }
            
            # Extract payment status
            trade_status = callback_data.get('tradeStatus') or callback_data.get('status')
            out_trade_no = callback_data.get('outTradeNo')
            transaction_id = callback_data.get('transactionId')
            total_amount = callback_data.get('totalAmount')
            
            # Determine if payment was successful
            is_success = trade_status in ['SUCCESS', 'TRADE_SUCCESS', 'success']
            
            return {
                'success': is_success,
                'transaction_id': out_trade_no,
                'telebirr_transaction_id': transaction_id,
                'amount': total_amount,
                'status': trade_status,
                'raw_data': callback_data
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Callback processing error: {str(e)}'
            }
    
    def query_payment_status(self, transaction_id):
        """
        Query payment status from Telebirr
        
        Args:
            transaction_id: Original transaction ID (outTradeNo)
            
        Returns:
            dict: Payment status information
        """
        try:
            # Prepare query data
            query_data = {
                'appId': self.fabric_app_id,
                'appSecret': self.app_secret,
                'merchantAppId': self.merchant_app_id,
                'merchantCode': self.merchant_code,
                'nonce': str(int(time.time() * 1000)),
                'timestamp': str(int(time.time() * 1000)),
                'outTradeNo': transaction_id,
            }
            
            # Generate signature
            signature = self._generate_signature(query_data)
            query_data['signature'] = signature
            
            # Make API request
            url = f"{self.base_url}/api/v1/order/query"
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            response = requests.post(url, json=query_data, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('code') == 'SUCCESS' or result.get('success'):
                trade_status = result.get('tradeStatus') or result.get('status')
                is_success = trade_status in ['SUCCESS', 'TRADE_SUCCESS', 'success']
                
                return {
                    'success': True,
                    'status': trade_status,
                    'is_paid': is_success,
                    'amount': result.get('totalAmount'),
                    'transaction_id': result.get('transactionId'),
                    'out_trade_no': result.get('outTradeNo')
                }
            else:
                return {
                    'success': False,
                    'error': result.get('message', 'Query failed')
                }
                
        except requests.RequestException as e:
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Query error: {str(e)}'
            }


# Singleton instance
telebirr_service = TelebirrService()
