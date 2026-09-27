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


@register()
def check_payment_tls_verification(app_configs, **kwargs):
    """Payment SOAP traffic with certificate verification turned off.

    Audit finding H-02. ``TELEBIRR_VERIFY_SSL`` used to default to False, so an
    environment that never set it -- which was every environment, since nothing
    in ``k8s/`` set it -- sent third-party credentials and payment instructions
    over a connection nobody authenticated. The default is now True, and this
    check exists so that turning it back off stays visible instead of becoming
    invisible again.

    Staging turns it off deliberately (the provider's UAT endpoint serves a
    private certificate), so this is a warning rather than an error. It is meant
    to be seen and left alone there, not silenced.
    """
    messages = []

    if getattr(settings, 'DEBUG', False):
        return messages

    if not getattr(settings, 'TELEBIRR_VERIFY_SSL', True):
        messages.append(
            CheckWarning(
                'Telebirr SOAP calls do not verify the server certificate.',
                hint=(
                    'TELEBIRR_VERIFY_SSL is false, so payment credentials and payout '
                    'instructions travel over a connection that is encrypted but not '
                    'authenticated -- an on-path party can read and alter them. This is '
                    "expected against the provider's UAT endpoint, which serves a private "
                    'certificate. It is not acceptable against a production gateway: '
                    'install the CA and remove the override. See '
                    'k8s/overlays/staging/patches/configmap-patch.yaml.'
                ),
                id=f'{PREFIX}.W004',
            )
        )

    if not getattr(settings, 'TIMWE_CHARGE_VERIFY_TLS', True):
        messages.append(
            CheckWarning(
                'TIMWE charging calls do not verify the server certificate.',
                hint=(
                    'TIMWE_CHARGE_VERIFY_TLS is false, so subscriber charging requests -- '
                    'which carry an MSISDN and take money -- are not authenticated in '
                    'transit. Install the MA certificate chain and remove the override.'
                ),
                id=f'{PREFIX}.W005',
            )
        )

    return messages
