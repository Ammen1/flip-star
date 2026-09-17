"""
TIMWE Master Aggregator syncOrderRelation endpoint (inbound).

The MA posts a SOAP request here whenever a subscription relationship is
created, removed or changed, and expects a response inside 30 seconds
(guide pp.10-17). One URL serves every event; ``updateType`` distinguishes
them.

Deliberately not an ``encrypted_endpoint``: FlipStar's E2E envelope is for our
own mobile client, and the MA speaks plain SOAP.

Two protections stand in for the authentication the guide does not define
(p.13 states the request has no header parameters at all):

* an optional source-IP allowlist, ``TIMWE_ALLOWED_IPS``
* a payload size cap and a DOCTYPE rejection in the parser

Until ``TIMWE_INTEGRATION_ENABLED`` is switched on, every request is parsed,
validated and recorded but no subscription is mutated. That kept the endpoint
observable during onboarding. OneVAS has since been removed, so this is the
only subscription channel over SMS.
"""

import logging

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from api.integrations.timwe.datasync import (
    SyncOrderRelationParseError,
    build_error_response,
    build_response,
    parse_sync_order_relation,
)
from api.integrations.timwe.errors import (
    SYNC_INTERNAL_ERROR,
    SYNC_INVALID_FORMAT,
    SYNC_OK,
    SYNC_ORDER_RELATION_ERRORS,
    SYNC_SERVICE_NOT_FOUND,
)
from api.models import TimweSyncOrderLog
from api.services.sms_subscription import resolve_subscriber
from api.services.subscription_tiers import resolve_tier
from common.security.client_ip import get_client_ip

logger = logging.getLogger(__name__)

SOAP_CONTENT_TYPE = 'text/xml; charset=utf-8'


#: Cap on what reaches the log, matching the slice stored on TimweSyncOrderLog.
#: The parser already refuses anything over 64 KiB, so this only bounds the
#: pathological case rather than truncating ordinary traffic.
LOG_PAYLOAD_LIMIT = 20000


def _log_payloads() -> bool:
    """Whether to write full SOAP bodies to the log."""
    return bool(getattr(settings, 'TIMWE_LOG_PAYLOADS', True))


def _truncate(text: str) -> str:
    if len(text) <= LOG_PAYLOAD_LIMIT:
        return text
    return f'{text[:LOG_PAYLOAD_LIMIT]}... [{len(text) - LOG_PAYLOAD_LIMIT} more chars]'


def _soap(body: str, status: int = 200) -> HttpResponse:
    """Build the SOAP response, logging it on the way out.

    Every return path in this module goes through here, so this one place
    covers all of them -- the allowlist rejection, the parse failure, the
    unmapped product, observation mode and the applied case alike.
    """
    if _log_payloads():
        logger.info(
            'TIMWE syncOrderRelation <-- response %s\n%s',
            status,
            _truncate(body),
        )
    return HttpResponse(body, status=status, content_type=SOAP_CONTENT_TYPE)


def _source_allowed(request) -> bool:
    """
    Check the caller against ``TIMWE_ALLOWED_IPS``.

    An empty allowlist permits everything, because the MA's egress addresses
    are not in the integration guide and blocking by default would silently
    drop live subscription events. It is logged as a warning so the gap stays
    visible rather than becoming the accepted state.
    """
    allowed = [ip.strip() for ip in getattr(settings, 'TIMWE_ALLOWED_IPS', []) if ip.strip()]
    if not allowed:
        logger.warning(
            'TIMWE syncOrderRelation accepted without a source allowlist; '
            'set TIMWE_ALLOWED_IPS once TIMWE confirms its egress addresses.'
        )
        return True
    return get_client_ip(request) in allowed


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def timwe_sync_order_relation(request):
    """Receive one syncOrderRelation notification from the MA."""
    raw = request.body or b''

    # Read and logged before the allowlist check, so a request rejected by
    # source IP is still visible -- otherwise the one failure mode you most
    # need to see is the one that leaves no trace.
    if _log_payloads():
        logger.info(
            'TIMWE syncOrderRelation --> request from %s (%s, %d bytes)\n%s',
            get_client_ip(request),
            request.META.get('CONTENT_TYPE', ''),
            len(raw),
            _truncate(raw.decode('utf-8', errors='replace')),
        )

    if not _source_allowed(request):
        logger.warning('TIMWE syncOrderRelation rejected: source not in TIMWE_ALLOWED_IPS')
        return _soap(
            build_error_response(SYNC_INTERNAL_ERROR, 'Request rejected.'),
            status=403,
        )

    try:
        relation = parse_sync_order_relation(raw)
    except SyncOrderRelationParseError as exc:
        # Recorded even though it never became a usable relation: a malformed
        # request from the MA is the kind of thing that has to be evidenced
        # when raising it with them.
        TimweSyncOrderLog.objects.create(
            raw_payload=raw.decode('utf-8', errors='replace')[:20000],
            result_code=SYNC_INVALID_FORMAT,
            result_description=SYNC_ORDER_RELATION_ERRORS[SYNC_INVALID_FORMAT],
            error_message=str(exc),
        )
        logger.warning('TIMWE syncOrderRelation could not be parsed: %s', exc)
        return _soap(build_error_response(SYNC_INVALID_FORMAT, str(exc)))

    log = TimweSyncOrderLog.objects.create(
        event_type=relation.event_label,
        update_type=relation.update_type,
        msisdn=relation.msisdn,
        sp_id=relation.sp_id,
        product_id=relation.product_id,
        service_id=relation.service_id,
        transaction_id=relation.transaction_id,
        order_key=relation.order_key,
        keyword=relation.keyword,
        update_reason=relation.update_reason,
        update_time=relation.parsed_update_time(),
        expiry_time=relation.parsed_expiry_time(),
        raw_payload=raw.decode('utf-8', errors='replace')[:20000],
        extensions=relation.extensions,
    )

    # Product id first, then the subscriber's own SMS keyword. The ids stored
    # on the tiers came from OneVAS (since removed), and TIMWE has not always
    # quoted the same ones; a subscriber who texted '1' has said which plan
    # they want regardless of that.
    tier = resolve_tier(product_id=relation.product_id, keyword=relation.keyword)
    if tier is None:
        # 2032 is precisely this case: the service the product belongs to does
        # not exist on our side. Returning it tells the MA to stop rather than
        # retry a product we will never recognise.
        log.result_code = SYNC_SERVICE_NOT_FOUND
        log.result_description = SYNC_ORDER_RELATION_ERRORS[SYNC_SERVICE_NOT_FOUND]
        log.error_message = (
            f'No SubscriptionTier maps to productID {relation.product_id} '
            f'or keyword {relation.keyword!r}.'
        )
        log.save(update_fields=['result_code', 'result_description', 'error_message'])
        logger.warning(
            'TIMWE syncOrderRelation for an unmapped product',
            extra={
                'product_id': relation.product_id,
                'keyword': relation.keyword,
                'event': relation.event_label,
            },
        )
        return _soap(build_error_response(SYNC_SERVICE_NOT_FOUND))

    # The same lookup the subscription service uses, so the account attributed
    # on the log row is the one the plan will be attached to.
    user = resolve_subscriber(relation.msisdn)
    if user is not None:
        log.user = user

    if not getattr(settings, 'TIMWE_INTEGRATION_ENABLED', False):
        # Observation mode. Answering 0 is correct: the MA is telling us what
        # it already did, and a non-zero code would make it retry an event we
        # have successfully recorded.
        log.result_code = SYNC_OK
        log.result_description = 'Recorded; TIMWE integration not yet enabled.'
        log.save(update_fields=['user', 'result_code', 'result_description'])
        logger.info(
            'TIMWE syncOrderRelation recorded in observation mode',
            extra={'event': relation.event_label, 'product_id': relation.product_id},
        )
        return _soap(build_response(SYNC_OK, 'Accepted.'))

    try:
        applied, description = _apply_relation(relation, tier, user)
    except Exception:
        logger.exception('TIMWE syncOrderRelation failed while applying')
        log.result_code = SYNC_INTERNAL_ERROR
        log.result_description = SYNC_ORDER_RELATION_ERRORS[SYNC_INTERNAL_ERROR]
        log.save(update_fields=['user', 'result_code', 'result_description'])
        return _soap(build_error_response(SYNC_INTERNAL_ERROR))

    log.applied = applied
    log.result_code = SYNC_OK
    log.result_description = description
    log.save(update_fields=['user', 'applied', 'result_code', 'result_description'])
    return _soap(build_response(SYNC_OK, description))


def _apply_relation(relation, tier, user):
    """
    Apply one subscription change announced by the MA.

    Returns ``(applied, description)``. ``applied`` says whether subscription
    state actually changed, which the caller records on the log row -- a
    duplicate or a no-op is a successful request that changed nothing, and the
    two must stay distinguishable when reconciling against TIMWE's own records.

    The work itself lives in ``api/services/sms_subscription.py``. This
    function decides *whether* to act; that module decides *what* acting means
    -- free trials, renewals, payment records and the message the subscriber
    gets -- with the same rules the removed OneVAS webhook applied.

    Reached only when TIMWE_INTEGRATION_ENABLED is true.
    """
    from api.services import sms_subscription

    # The MA retries on anything other than result 0, and a retried subscribe
    # must not produce a second subscription. transactionID is the MA's own
    # identifier for the event, so it is the right idempotency key. The current
    # log row is still applied=False at this point, so it cannot match itself.
    if (
        relation.transaction_id
        and TimweSyncOrderLog.objects.filter(
            transaction_id=relation.transaction_id, applied=True
        ).exists()
    ):
        return False, 'Already applied; duplicate transactionID.'

    metadata = {
        'source': 'timwe',
        'product_id': relation.product_id,
        'service_id': relation.service_id,
        'transaction_id': relation.transaction_id,
        'order_key': relation.order_key,
        'keyword': relation.keyword,
    }

    if relation.is_subscribe:
        if not relation.msisdn:
            # userID/type said this is not a mobile subscriber, so there is no
            # number to bill, to text, or to key the plan on.
            return False, 'No MSISDN on the notification; nothing to subscribe.'

        result = sms_subscription.subscribe(
            phone_number=relation.msisdn,
            tier=tier,
            payment_method='timwe',
            metadata=metadata,
            # Already resolved by the caller and recorded on the log row.
            user=user,
        )

        # The SMS is the point of the SMS channel: without it the subscriber
        # has been charged and has no way into what they paid for. Sent outside
        # the subscription transaction, and never allowed to fail the request --
        # a non-zero result makes the MA retry a charge we have already applied.
        try:
            renewed = result.action == 'renewed'
            if renewed:
                # A period charged again, not a new subscription: no OTP, so
                # the code the subscriber already holds keeps working.
                message = sms_subscription.build_renewal_message(tier=tier, plan=result.plan)
            else:
                message = sms_subscription.build_welcome_message(
                    tier=tier,
                    result=result,
                    phone_number=relation.msisdn,
                    base_url=settings.TIMWE_SUBSCRIPTION_LINK_BASE,
                )
            sms_subscription.send_subscription_sms(
                relation.msisdn,
                message,
                tier,
                purpose='subscription_renewal' if renewed else 'subscription_welcome',
                # The MA's own id for this event: a retried notification finds
                # the message already queued instead of sending a second one.
                idempotency_key=(
                    f'timwe-sub:{relation.transaction_id}' if relation.transaction_id else None
                ),
            )
        except Exception:
            logger.exception(
                'TIMWE subscription applied but the SMS failed',
                extra={'plan_id': str(result.plan.id)},
            )

        logger.info(
            'TIMWE subscription %s',
            result.action,
            extra={'product_id': relation.product_id, 'tier': tier.name},
        )
        return True, f'Subscription {result.action}.'

    if relation.is_unsubscribe:
        cancelled = sms_subscription.unsubscribe(
            phone_number=relation.msisdn,
            duration_type=tier.duration_type,
            reason='Unsubscribed via TIMWE',
            metadata={**metadata, 'update_reason': relation.update_reason},
            user=user,
        )
        if not cancelled:
            # Deliberately not 2031 ("subscription relationship does not
            # exist"). The MA is reporting something it has already done;
            # answering with an error makes it retry a cancellation we can
            # never satisfy. Recorded, and reconciled from the log. No SMS
            # either: nothing changed, and a second "you are cancelled" for a
            # subscription that was already gone is a message about our
            # bookkeeping, not about them.
            return False, 'No active subscription to cancel.'

        # A subscriber who texts STOP otherwise gets no confirmation at all:
        # the app cannot tell them and the MA's notification comes to us. Sent
        # outside the cancellation, and never allowed to fail the request -- a
        # non-zero result makes the MA retry a cancellation already applied.
        try:
            sms_subscription.send_subscription_sms(
                relation.msisdn,
                sms_subscription.build_cancellation_message(
                    tier=tier,
                    # The keyword that started it is the one that starts it
                    # again, and the MA quotes it on the way out.
                    subscribe_keyword=sms_subscription.subscribe_keyword_for(tier),
                ),
                tier,
                purpose='subscription_cancelled',
                idempotency_key=(
                    f'timwe-unsub:{relation.transaction_id}' if relation.transaction_id else None
                ),
            )
        except Exception:
            logger.exception(
                'TIMWE subscription cancelled but the SMS failed',
                extra={'product_id': relation.product_id},
            )

        logger.info(
            'TIMWE subscription cancelled',
            extra={'product_id': relation.product_id, 'count': len(cancelled)},
        )
        return True, 'Subscription cancelled.'

    # updateType 3 (Update) carries product metadata rather than a state
    # change: nothing we hold is affected, so it is recorded and acknowledged.
    return False, 'Update recorded; no subscription change required.'
