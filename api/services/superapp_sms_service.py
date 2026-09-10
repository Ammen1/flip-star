"""SuperApp SMS Service - Dedicated SMS notifications for Telebirr SuperApp subscriptions"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class SuperAppSMSService:
    """Service to send SMS notifications for SuperApp subscription events.

    Every message goes over TIMWE SMPP. This used to carry OneVAS product keys
    and its SMS URL; OneVAS has been removed and none of them are read now.
    """

    def __init__(self):
        # The short code subscribers text -- TIMWE's, formerly OneVAS's.
        self.short_code = getattr(settings, 'SMS_SHORT_CODE', '') or '9286'

    def _send_sms(self, phone_number, text, duration_type='weekly'):
        """
        Queue an SMS for delivery over TIMWE SMPP.

        Args:
            phone_number: User's phone number (format: 2519...)
            text: SMS message content
            duration_type: Plan duration type. Unused -- it chose a OneVAS
                product -- and kept so the callers below need not change.

        Returns:
            bool: True if the message was recorded and queued. Queued, not
            delivered; SmsMessage.status carries the latter.
        """
        from api.services.sms.dispatch import SmsNotQueued, queue_sms

        try:
            queue_sms(
                phone_number=phone_number,
                text=text,
                purpose='superapp',
            )
        except SmsNotQueued as exc:
            logger.warning('[SuperApp SMS] Not queued for %s: %s', phone_number, exc)
            return False
        logger.info('[SuperApp SMS] Queued for %s', phone_number)
        return True

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
