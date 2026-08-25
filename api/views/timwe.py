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
validated and recorded but no subscription is mutated. That keeps the endpoint
observable during onboarding without letting it grant subscriptions in
parallel with the OneVAS webhooks that are still live.
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
from api.models import SubscriptionTier, TimweSyncOrderLog
from common.security.client_ip import get_client_ip

logger = logging.getLogger(__name__)

SOAP_CONTENT_TYPE = 'text/xml; charset=utf-8'


def _soap(body: str, status: int = 200) -> HttpResponse:
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
    if not _source_allowed(request):
        logger.warning('TIMWE syncOrderRelation rejected: source not in TIMWE_ALLOWED_IPS')
        return _soap(
            build_error_response(SYNC_INTERNAL_ERROR, 'Request rejected.'),
            status=403,
        )

    raw = request.body or b''

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

    tier = SubscriptionTier.objects.filter(product_id=relation.product_id).first()
    if tier is None:
        # 2032 is precisely this case: the service the product belongs to does
        # not exist on our side. Returning it tells the MA to stop rather than
        # retry a product we will never recognise.
        log.result_code = SYNC_SERVICE_NOT_FOUND
        log.result_description = SYNC_ORDER_RELATION_ERRORS[SYNC_SERVICE_NOT_FOUND]
        log.error_message = f'No SubscriptionTier maps to productID {relation.product_id}.'
        log.save(update_fields=['result_code', 'result_description', 'error_message'])
        logger.warning(
            'TIMWE syncOrderRelation for an unmapped product',
            extra={'product_id': relation.product_id, 'event': relation.event_label},
        )
        return _soap(build_error_response(SYNC_SERVICE_NOT_FOUND))

    user = _resolve_user(relation.msisdn)
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


def _resolve_user(msisdn: str):
    """Find the FlipStar account behind an MSISDN, or None."""
    if not msisdn:
        return None

    from api.models import SubscriptionPlan, UserProfile

    profile = UserProfile.objects.filter(phone_number=msisdn).select_related('user').first()
    if profile is not None:
        return profile.user

    plan = (
        SubscriptionPlan.objects.filter(onevas_phone_number=msisdn).select_related('user').first()
    )
    return plan.user if plan is not None else None


def _apply_relation(relation, tier, user):
    """
    Apply a subscription change.

    Left unimplemented on purpose. The live subscription lifecycle currently
    belongs to OnevasWebhookView, and adding a second path that grants and
    cancels the same SubscriptionPlan rows would be exactly the parallel
    implementation this migration is meant to avoid. At cutover this function
    takes over that logic and the OneVAS view is deleted in the same change.

    Reached only when TIMWE_INTEGRATION_ENABLED is true, which stays false
    until TIMWE supplies credentials and the WEB subscription flow.
    """
    raise NotImplementedError(
        'TIMWE subscription application is wired at cutover, when '
        'OnevasWebhookView is removed. See docs/integrations.md.'
    )
