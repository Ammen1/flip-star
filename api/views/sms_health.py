"""
Operational state of the SMS gateway.

Read-only and side-effect free: it reports what the SMPP session is doing, it
does not send a message. A health check that sent a real SMS would bill a
subscriber every time a probe ran.

Staff-only, because the answer names the gateway host and describes the link.
Credentials never appear -- SmppClient.health() has no access to the password
and SmppSettings.describe() redacts the system_id.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from api.models.sms import SmsMessage, SmsStatus


@api_view(['GET'])
@permission_classes([IsAdminUser])
def sms_health(request):
    """Gateway state plus a short delivery summary."""
    from api.services.sms import get_gateway

    try:
        gateway = get_gateway()
        transport = gateway.health()
    except Exception as exc:
        # A misconfigured provider is exactly what this endpoint exists to
        # surface, so it is reported rather than raised.
        transport = {'error': str(exc), 'configured': False}

    counts = {
        status.value: SmsMessage.objects.filter(status=status.value).count() for status in SmsStatus
    }

    return Response(
        {
            'transport': transport,
            'messages': counts,
            # The oldest thing still waiting -- a queue that stops draining
            # shows up here before anyone reports a missing OTP.
            'oldest_queued': (
                SmsMessage.objects.filter(status=SmsStatus.QUEUED)
                .order_by('created_at')
                .values_list('created_at', flat=True)
                .first()
            ),
        }
    )
