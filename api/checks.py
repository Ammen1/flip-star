"""Deployment configuration checks, run by ``manage.py check``.

These are settings whose absence is not a code fault and does not stop the
process starting, but does stop a documented business rule from working. The
Daily Sprint's data prize is the motivating case: ``DATA_PRIZE_OFFERING_ID``
was never configured, so every one of the twenty daily winners' bundles
failed with "No data package configured" -- and the only place that said so
was a delivery attempt hours after the win, in a log nobody was reading.

A check here surfaces it at deploy time instead, which is when it can still
be fixed before a campaign closes.

Warnings, not errors: an environment that does not run campaigns (a
developer's laptop, a CI run) should not fail ``manage.py check`` for want of
an Ethio Telecom OfferingId.
"""

from django.conf import settings
from django.core.checks import Warning as CheckWarning
from django.core.checks import register

#: Prefix for this app's check ids, so ``SILENCED_SYSTEM_CHECKS`` can name
#: one precisely.
PREFIX = 'flipstar'


@register()
def check_data_prize_provisioning(app_configs, **kwargs):
    """The Daily Sprint's 1 GB data prize needs an OfferingId to provision."""
    messages = []

    offering = getattr(settings, 'DATA_PRIZE_OFFERING_ID', '') or getattr(
        settings, 'CRM_OFFERING_ID', ''
    )
    if not offering:
        messages.append(
            CheckWarning(
                'No data package is configured for Daily Sprint prizes.',
                hint=(
                    'Set DATA_PRIZE_OFFERING_ID to the 1 GB package OfferingId from '
                    'Ethio Telecom (or CRM_OFFERING_ID as a fallback). Until it is set, '
                    'every daily data prize fails with "No data package configured". '
                    'Failures are recorded and retryable, so nothing is lost -- but '
                    'nothing is delivered either.'
                ),
                id=f'{PREFIX}.W001',
            )
        )

    if not getattr(settings, 'DATA_PRIZE_PROVISIONING_NUMBER', ''):
        messages.append(
            CheckWarning(
                'No provisioning number is configured for data prizes.',
                hint=(
                    'Set DATA_PRIZE_PROVISIONING_NUMBER to the number the bundle is '
                    'sent from (ServiceNumberA). The business requirement names '
                    '0911227833.'
                ),
                id=f'{PREFIX}.W002',
            )
        )

    return messages


@register()
def check_webhook_allowlist(app_configs, **kwargs):
    """The unsigned Telebirr webhooks are open to the internet by default."""
    if getattr(settings, 'TELEBIRR_WEBHOOK_ALLOWED_IPS', None):
        return []

    # Only worth saying in a deployment that is actually reachable. A
    # DEBUG environment is a developer's machine.
    if getattr(settings, 'DEBUG', False):
        return []

    return [
        CheckWarning(
            'The Telebirr SOAP webhooks accept a callback from any address.',
            hint=(
                'The B2C, direct-debit and USSD result envelopes carry no signature, '
                'so a forged callback naming a guessed OriginatorConversationID could '
                'settle a payout as succeeded. Set TELEBIRR_WEBHOOK_ALLOWED_IPS to '
                "Telebirr's egress addresses, and allow-list the same range at the "
                'ingress. See api/services/webhook_allowlist.py.'
            ),
            id=f'{PREFIX}.W003',
        )
    ]
