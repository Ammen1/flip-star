"""SuperApp SMS Service - Dedicated SMS notifications for Telebirr SuperApp subscriptions"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SuperAppSMSService:
    """Service to send SMS notifications for SuperApp subscription events"""

    # Read from settings, which resolve through Vault -> environment -> .env,
    # rather than hardcoding the endpoint. See config/settings/base.py:445.
    ONEVAS_SMS_URL = settings.ONEVAS_SMS_URL  # Onevas SMS API endpoint

    def __init__(self):
        self.timeout = 10
        self.short_code = (
            settings.ONEVAS_SHORT_CODE if hasattr(settings, 'ONEVAS_SHORT_CODE') else '9286'
        )
        # Use the same ONEVAS_PRODUCTS configuration as Direct Debit
        self.ONEVAS_PRODUCTS = getattr(settings, 'ONEVAS_PRODUCTS', {})
        self.ONEVAS_APPLICATION_KEY = getattr(settings, 'ONEVAS_APPLICATION_KEY', '')
        self.ONEVAS_PRODUCT_NUMBER = getattr(settings, 'ONEVAS_PRODUCT_NUMBER', '')

    def _get_product_config(self, duration_type):
        """Get Onevas product configuration for a given duration type"""
        # Use tier-specific configuration if available, otherwise use default
        if duration_type and duration_type in self.ONEVAS_PRODUCTS:
            return self.ONEVAS_PRODUCTS[duration_type]
        else:
            # Fallback to default configuration
            return {
                'application_key': self.ONEVAS_APPLICATION_KEY,
                'product_id': self.ONEVAS_PRODUCT_NUMBER,
            }

    def _send_sms(self, phone_number, text, duration_type='weekly'):
        """
        Send SMS via Onevas API (same logic as Direct Debit)

        Args:
            phone_number: User's phone number (format: 2519...)
            text: SMS message content
            duration_type: Plan duration type (daily, weekly, monthly)

        Returns:
            bool: True if SMS sent successfully, False otherwise
        """
        try:
            config = self._get_product_config(duration_type)

            payload = {
                'application_key': config['application_key'],
                'phone_number': phone_number,
                'product_number': config['product_id'],
                'text': text,
            }

            logger.info(f'[SuperApp SMS] Sending SMS to {phone_number}')
            logger.info(f'[SuperApp SMS] Message: {text[:100]}...')
            logger.info(
                f"[SuperApp SMS] Using app_key: {config['application_key'][:10]}..., product: {config['product_id']}"
            )

            response = requests.post(
                self.ONEVAS_SMS_URL,
                json=payload,
                timeout=self.timeout,
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            )

            logger.info(f'[SuperApp SMS] Response status: {response.status_code}')
            logger.info(f'[SuperApp SMS] Response body: {response.text}')

            if response.status_code == 200:
                logger.info(f'[SuperApp SMS] SMS sent successfully to {phone_number}')
                return True
            else:
                logger.error(
                    f'[SuperApp SMS] Failed to send SMS. Status: {response.status_code}, Response: {response.text}'
                )
                return False

        except Exception as e:
            logger.error(f'[SuperApp SMS] Error sending SMS: {str(e)}')
            return False

    def send_subscription_success(self, phone_number, plan_name, amount, duration_type, end_date):
        """
        Send SMS when SuperApp subscription is successfully created (one-time payment)

        Args:
            phone_number: User's phone number
            plan_name: Name of the plan (e.g., "Weekly", "Monthly")
            amount: Subscription amount in ETB
            duration_type: Plan duration (daily, weekly, monthly)
            end_date: Date when subscription expires (for one-time payments)
        """
        duration_text = {'daily': '24 hours', 'weekly': '7 days', 'monthly': '30 days'}.get(
            duration_type, 'unknown period'
        )

        message = (
            f"Thank you for subscribing to the {plan_name} plan. "
            f"Amount: {amount} ETB. "
            f"Duration: {duration_text}. "
            f"Valid until: {end_date.strftime('%d-%m-%Y %H:%M') if end_date else 'N/A'}. "
            f"To renew, open the Telebirr SuperApp and subscribe again."
        )

        return self._send_sms(phone_number, message, duration_type)

    def send_subscription_renewal(
        self, phone_number, plan_name, amount, duration_type, next_renewal_date
    ):
        """
        Send SMS when SuperApp subscription is renewed

        Args:
            phone_number: User's phone number
            plan_name: Name of the plan
            amount: Subscription amount in ETB
            duration_type: Plan duration (daily, weekly, monthly)
            next_renewal_date: Date of next renewal
        """
        duration_text = {'daily': '24 hours', 'weekly': '7 days', 'monthly': '30 days'}.get(
            duration_type, 'unknown period'
        )

        message = (
            f"Your {plan_name} subscription has been renewed. "
            f"Amount charged: {amount} ETB. "
            f"Valid for {duration_text}. "
            f"Next renewal: {next_renewal_date.strftime('%d-%m-%Y') if next_renewal_date else 'N/A'}. "
            f"To cancel, send STOP to {self.short_code}."
        )

        return self._send_sms(phone_number, message, duration_type)

    def send_subscription_cancellation(self, phone_number, plan_name, duration_type):
        """
        Send SMS when SuperApp subscription is cancelled

        Args:
            phone_number: User's phone number
            plan_name: Name of the plan
            duration_type: Plan duration (daily, weekly, monthly)
        """
        message = (
            f'Your {plan_name} subscription has been cancelled. '
            f'Thank you for using FlipStar. '
            f'To resubscribe, open the Telebirr SuperApp, navigate to FlipStar service, and select Subscribe.'
        )

        return self._send_sms(phone_number, message, duration_type)

    def send_renewal_failed(self, phone_number, plan_name, amount, duration_type):
        """
        Send SMS when SuperApp subscription renewal fails (insufficient balance)

        Args:
            phone_number: User's phone number
            plan_name: Name of the plan
            amount: Subscription amount in ETB
            duration_type: Plan duration (daily, weekly, monthly)
        """
        message = (
            f'FlipStar: Your {plan_name} subscription renewal failed due to insufficient balance. '
            f'Required amount: {amount} ETB. '
            f'Please recharge and the renewal will be retried. '
            f'To cancel, send STOP to {self.short_code}.'
        )

        return self._send_sms(phone_number, message, duration_type)

    def send_subscription_expiry_warning(self, phone_number, plan_name, days_remaining):
        """
        Send SMS warning before subscription expires (for manual renewal plans)

        Args:
            phone_number: User's phone number
            plan_name: Name of the plan
            days_remaining: Days remaining before expiry
        """
        message = (
            f'FlipStar: Your {plan_name} subscription will expire in {days_remaining} day(s). '
            f'Please renew to continue enjoying FlipStar. '
            f'To renew, visit the app or send OK to {self.short_code}.'
        )

        return self._send_sms(phone_number, message, 'daily')


# Singleton instance
superapp_sms_service = SuperAppSMSService()
