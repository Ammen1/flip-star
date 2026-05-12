"""Onevas charging service for on-demand subscription purchases"""
import requests
import logging
from django.conf import settings
from datetime import datetime

logger = logging.getLogger(__name__)


class OnevasChargingService:
    """Service to handle Onevas charging API requests"""
    
    ONEVAS_CHARGING_URL = "https://onevas.et/api/v1/charging"
    
    def __init__(self):
        self.timeout = 30  # 30 seconds timeout for charging requests
    
    def initiate_charging(self, phone_number, product_number, application_key):
        """
        Initiate a charging request to Onevas
        
        Args:
            phone_number: User's phone number (format: 2519...)
            product_number: Onevas product number
            application_key: Onevas application key
        
        Returns:
            dict: Response from Onevas API
        """
        payload = {
            "application_key": application_key,
            "phone_number": phone_number,
            "product_number": product_number
        }
        
        try:
            logger.info(f"[Onevas Charging] Initiating charging request for {phone_number}")
            response = requests.post(
                self.ONEVAS_CHARGING_URL,
                json=payload,
                timeout=self.timeout,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            )
            
            logger.info(f"[Onevas Charging] Response status: {response.status_code}")
            
            return {
                'status_code': response.status_code,
                'success': response.status_code == 200,
                'data': response.json() if response.content else None,
                'text': response.text
            }
            
        except requests.exceptions.Timeout:
            logger.error(f"[Onevas Charging] Request timeout for {phone_number}")
            return {
                'status_code': None,
                'success': False,
                'error': 'timeout',
                'message': 'Request timed out'
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"[Onevas Charging] Request failed: {str(e)}")
            return {
                'status_code': None,
                'success': False,
                'error': 'request_exception',
                'message': str(e)
            }
    
    def parse_charging_response(self, response_data):
        """
        Parse Onevas charging response to determine status
        
        Args:
            response_data: Response from Onevas API
        
        Returns:
            tuple: (status, error_message)
        """
        if not response_data.get('success'):
            return 'failed', response_data.get('message', 'Charging request failed')
        
        data = response_data.get('data', {})
        
        # Check for insufficient balance response
        if data.get('error') == 'insufficient_balance' or data.get('code') == 'INSUFFICIENT_BALANCE':
            return 'insufficient_balance', 'Insufficient airtime balance'
        
        # Check for successful charging
        if data.get('success') or data.get('status') == 'success':
            return 'success', None
        
        # Default to failed
        return 'failed', data.get('message', 'Charging failed')
    
    def get_transaction_status(self, transaction_id):
        """
        Check the status of a charging transaction
        
        Args:
            transaction_id: Onevas transaction ID
        
        Returns:
            dict: Transaction status from Onevas
        """
        # Note: Onevas may not have a status check endpoint
        # This is a placeholder for future implementation
        return {
            'status': 'unknown',
            'message': 'Status check not implemented yet'
        }


# Singleton instance
onevas_charging_service = OnevasChargingService()
