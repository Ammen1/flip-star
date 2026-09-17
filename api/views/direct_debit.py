"""
Telebirr Direct Debit API Views

API endpoints for direct debit mandate management:
- Create mandate
- Activate mandate
- Cancel mandate
- List user mandates
- Webhook for async results
"""

import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.integrations.telebirr.direct_debit import telebirr_direct_debit_service
from api.models.contest import UserCoinBalance
from api.models.direct_debit import (
    B2CPaymentTransaction,
    DirectDebitMandate,
    DirectDebitTransaction,
)
from api.models.subscription import SubscriptionPayment, SubscriptionPlan, SubscriptionTier
from api.services.withdrawal_sms import (
    notify_failed as notify_withdrawal_failed,
)
from api.services.withdrawal_sms import (
    notify_paid as notify_withdrawal_paid,
)
from common.permissions.roles import HasAdminPermission
from common.security import encrypted_endpoint

logger = logging.getLogger(__name__)


def _parse_telebirr_soap_result(raw_body):
    """Extract the fields we care about from a Telebirr SOAP Result envelope.

    Telebirr sends ``Content-Type: text/xml`` with an ``<api:Result>`` SOAP
    envelope. DRF's ``request.data`` cannot parse this so we operate on the
    raw bytes/string with regex (the schema is fixed and small).
    """
    if isinstance(raw_body, bytes | bytearray):
        try:
            raw_body = raw_body.decode('utf-8', errors='replace')
        except Exception:
            raw_body = str(raw_body)
    text = raw_body or ''

    def _find(tag):
        m = re.search(
            rf'<(?:[a-zA-Z]+:)?{tag}>([^<]*)</(?:[a-zA-Z]+:)?{tag}>',
            text,
        )
        return m.group(1).strip() if m else None

    return {
        'ResultType': _find('ResultType'),
        'ResultCode': _find('ResultCode'),
        'ResultDesc': _find('ResultDesc'),
        'ConversationID': _find('ConversationID'),
        'OriginatorConversationID': _find('OriginatorConversationID'),
        'TransactionID': _find('TransactionID'),
        'MandateID': _find('MandateID'),
    }


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def create_direct_debit_mandate(request):
    """
    Create a direct debit mandate for subscription payment

    Request Body:
    {
        "tier_id": "uuid",
        "payer_msisdn": "251911234567",
        "frequency": "05"  // 02=Daily, 03=Weekly, 05=Monthly
    }
    """
    try:
        user = request.user
        tier_id = request.data.get('tier_id')
        payer_msisdn = request.data.get('payer_msisdn')
        frequency = request.data.get('frequency')

        # Validate required fields
        if not all([tier_id, payer_msisdn, frequency]):
            return Response(
                {'error': 'tier_id, payer_msisdn, and frequency are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get subscription tier
        try:
            tier = SubscriptionTier.objects.get(id=tier_id, is_active=True)
        except SubscriptionTier.DoesNotExist:
            return Response(
                {'error': 'Invalid subscription tier'}, status=status.HTTP_400_BAD_REQUEST
            )

        # Validate frequency matches tier duration
        frequency_map = {
            'daily': '02',
            'weekly': '03',
            'monthly': '05',
        }
        if tier.duration_type not in frequency_map:
            return Response(
                {
                    'error': 'This tier does not support direct debit (only tier-based subscriptions)'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        expected_frequency = frequency_map[tier.duration_type]
        if frequency != expected_frequency:
            return Response(
                {'error': f'Frequency must be {expected_frequency} for {tier.duration_type} tier'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate payer reference number
        payer_reference_number = f'FLP{user.id}{int(timezone.now().timestamp())}'

        # Calculate dates
        first_payment_date = timezone.now().date()
        expiry_date = first_payment_date + timedelta(days=365)  # 1 year expiry

        # Call Telebirr service to create mandate
        result = telebirr_direct_debit_service.create_mandate(
            payer_msisdn=payer_msisdn,
            payer_reference_number=payer_reference_number,
            frequency=frequency,
            first_payment_date=first_payment_date.strftime('%Y%m%d'),
            expiry_date=expiry_date.strftime('%Y%m%d'),
        )

        if not result.get('success'):
            return Response(
                {'error': result.get('error', 'Mandate creation failed')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Create mandate record. The synchronous Telebirr response is only an
        # acceptance ack; the real result (with the Telebirr-generated
        # MandateID) arrives later on the webhook. Until then, the mandate
        # stays in `pending_created` and cannot be activated/cancelled/debited.
        mandate = DirectDebitMandate.objects.create(
            user=user,
            tier=tier,
            payer_msisdn=payer_msisdn,
            payer_reference_number=payer_reference_number,
            payee_identifier_value=getattr(tier, 'short_code', '9286'),
            frequency=frequency,
            first_payment_date=first_payment_date,
            expiry_date=expiry_date,
            agreed_tc=True,
            originator_conversation_id=result.get('originator_conversation_id'),
            conversation_id=result.get('conversation_id'),
            status='pending_created',
        )

        return Response(
            {
                'success': True,
                'mandate_id': str(mandate.id),
                'payer_reference_number': payer_reference_number,
                'status': mandate.status,
                'message': 'Mandate created successfully. Please activate it to complete subscription.',
                'originator_conversation_id': result.get('originator_conversation_id'),
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        return Response(
            {'error': f'Failed to create mandate: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def activate_direct_debit_mandate(request):
    """
    Activate a direct debit mandate

    Request Body:
    {
        "mandate_id": "uuid",
        "payer_account_name": "John Doe"  // optional
    }
    """
    try:
        user = request.user
        mandate_id = request.data.get('mandate_id')
        payer_account_name = request.data.get('payer_account_name', '')

        # Validate required fields
        if not mandate_id:
            return Response({'error': 'mandate_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Get mandate
        try:
            mandate = DirectDebitMandate.objects.get(id=mandate_id, user=user)
        except DirectDebitMandate.DoesNotExist:
            return Response({'error': 'Mandate not found'}, status=status.HTTP_404_NOT_FOUND)

        # Telebirr requires the real MandateID (max 18 bytes) generated by
        # the Mobile Money system and delivered via the async result webhook.
        # Substituting payer_reference_number here would be rejected.
        if not mandate.mandate_id:
            return Response(
                {
                    'error': 'Mandate is not yet ready for activation. Telebirr has not returned the MandateID. Please retry shortly.'
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Atomically claim the mandate for activation: pending_active ->
        # activating. This is a single conditional UPDATE (auto-committed
        # immediately, no explicit transaction/lock), so two concurrent
        # activate requests can never both proceed -- Postgres serializes
        # the two UPDATEs at the row level, and only the first one finds
        # status still 'pending_active'. Nothing is held open while we then
        # talk to Telebirr below.
        claimed = DirectDebitMandate.objects.filter(id=mandate.id, status='pending_active').update(
            status='activating'
        )
        if claimed == 0:
            mandate.refresh_from_db()
            return Response(
                {'error': f'Mandate is in {mandate.status} status, cannot activate'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Call Telebirr service to activate mandate. No DB lock is held
        # across this call.
        try:
            result = telebirr_direct_debit_service.activate_mandate(
                mandate_id=mandate.mandate_id,
                payer_msisdn=mandate.payer_msisdn,
                agreed_tc=True,
                payer_account_name=payer_account_name,
            )
        except Exception as exc:
            # Unknown outcome (network error/timeout) -- we cannot tell
            # whether Telebirr actually processed this. Leave the mandate
            # in 'activating' rather than guessing; the async result
            # webhook (telebirr_direct_debit_webhook, which also accepts
            # 'activating' as a valid prior state) is the recovery path
            # once Telebirr's own record of the outcome arrives.
            logger.exception(
                'Telebirr activate_mandate call failed for mandate %s: %s', mandate.id, exc
            )
            return Response(
                {
                    'error': 'Activation request could not be confirmed. Please check mandate status shortly.'
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not result.get('success'):
            # Telebirr explicitly rejected the activation -- a known
            # outcome, safe to mark failed immediately.
            DirectDebitMandate.objects.filter(id=mandate.id, status='activating').update(
                status='failed', error_message=result.get('error') or ''
            )
            return Response(
                {'error': result.get('error', 'Mandate activation failed')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Success: finalize with a short locked transaction (no external
        # call inside it). Re-checking status under the lock makes this
        # idempotent against the recovery webhook finishing the same
        # transition first.
        subscription_plan = None
        with db_transaction.atomic():
            mandate = DirectDebitMandate.objects.select_for_update().get(id=mandate.id)
            if mandate.status == 'activating':
                mandate.payer_account_name = payer_account_name
                mandate.originator_conversation_id = result.get('originator_conversation_id')
                mandate.conversation_id = result.get('conversation_id')
                mandate.activate()

                # Create subscription plan from the tier persisted at mandate
                # creation time. (Previously this read mandate.subscription_plan.tier
                # which is always None at activation, so subscriptions were
                # never created.)
                tier = mandate.tier
                if tier:
                    subscription_plan = SubscriptionPlan.objects.create(
                        user=user,
                        tier=tier,
                        status='active',
                        duration_type=tier.duration_type,
                        start_date=timezone.now(),
                        end_date=timezone.now() + timedelta(days=tier.duration_days)
                        if tier.duration_days
                        else None,
                        next_renewal_date=timezone.now() + timedelta(days=tier.duration_days)
                        if tier.duration_days
                        else None,
                        auto_renew=True,
                        payment_method='telebirr_direct_debit',
                    )

                    # Link mandate to subscription
                    mandate.subscription_plan = subscription_plan
                    mandate.save()

                    # Create initial payment record
                    SubscriptionPayment.objects.create(
                        subscription=subscription_plan,
                        user=user,
                        amount=tier.price_etb,
                        currency='ETB',
                        status='pending',
                        payment_method='telebirr_direct_debit',
                        duration_type=tier.duration_type,
                        period_start=timezone.now(),
                        period_end=subscription_plan.end_date
                        or timezone.now() + timedelta(days=30),
                    )
            else:
                # Already finalized by the recovery webhook while we were
                # talking to Telebirr -- idempotent no-op, just report
                # current state.
                subscription_plan = mandate.subscription_plan

        return Response(
            {
                'success': True,
                'mandate_id': str(mandate.id),
                'status': mandate.status,
                'subscription_id': str(subscription_plan.id) if subscription_plan else None,
                'message': 'Mandate activated successfully. Subscription created.',
            }
        )

    except Exception as e:
        return Response(
            {'error': f'Failed to activate mandate: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def cancel_direct_debit_mandate(request):
    """
    Cancel a direct debit mandate

    Request Body:
    {
        "mandate_id": "uuid"
    }
    """
    try:
        user = request.user
        mandate_id = request.data.get('mandate_id')

        # Validate required fields
        if not mandate_id:
            return Response({'error': 'mandate_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Get mandate
        try:
            mandate = DirectDebitMandate.objects.get(id=mandate_id, user=user)
        except DirectDebitMandate.DoesNotExist:
            return Response({'error': 'Mandate not found'}, status=status.HTTP_404_NOT_FOUND)

        # Check if mandate is active
        if not mandate.is_active():
            return Response(
                {'error': f'Mandate is {mandate.status}, cannot cancel'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not mandate.mandate_id:
            return Response(
                {'error': 'Mandate has no Telebirr MandateID yet, cannot cancel.'},
                status=status.HTTP_409_CONFLICT,
            )

        # Atomically claim the mandate for cancellation: active ->
        # cancelling. Single conditional UPDATE, no lock held across the
        # Telebirr call below -- same pattern as activation above.
        claimed = DirectDebitMandate.objects.filter(id=mandate.id, status='active').update(
            status='cancelling'
        )
        if claimed == 0:
            mandate.refresh_from_db()
            return Response(
                {'error': f'Mandate is {mandate.status}, cannot cancel'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Call Telebirr service to cancel mandate. No DB lock held across
        # this call.
        try:
            result = telebirr_direct_debit_service.cancel_mandate(
                mandate_id=mandate.mandate_id, payer_msisdn=mandate.payer_msisdn
            )
        except Exception as exc:
            # Unknown outcome -- leave status as 'cancelling'. The async
            # result webhook (which also handles 'cancelling' as a valid
            # prior state) resolves it once Telebirr's own outcome is known.
            logger.exception(
                'Telebirr cancel_mandate call failed for mandate %s: %s', mandate.id, exc
            )
            return Response(
                {
                    'error': 'Cancellation request could not be confirmed. Please check mandate status shortly.'
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if not result.get('success'):
            # Telebirr explicitly rejected the cancellation -- known
            # outcome, safe to revert the claim back to active immediately.
            DirectDebitMandate.objects.filter(id=mandate.id, status='cancelling').update(
                status='active'
            )
            return Response(
                {'error': result.get('error', 'Mandate cancellation failed')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Success: finalize with a short locked transaction (no external
        # call inside it). Re-checking status under the lock makes this
        # idempotent against the recovery webhook finishing the same
        # transition first.
        with db_transaction.atomic():
            mandate = DirectDebitMandate.objects.select_for_update().get(id=mandate.id)
            if mandate.status == 'cancelling':
                mandate.cancel()

            if mandate.subscription_plan and mandate.subscription_plan.auto_renew:
                sp = mandate.subscription_plan
                sp.auto_renew = False
                sp.save()

        return Response(
            {
                'success': True,
                'mandate_id': str(mandate.id),
                'status': mandate.status,
                'message': 'Mandate cancelled successfully. Auto-renewal disabled.',
            }
        )

    except Exception as e:
        return Response(
            {'error': f'Failed to cancel mandate: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def list_user_mandates(request):
    """
    List all mandates for the authenticated user
    """
    try:
        user = request.user
        mandates = DirectDebitMandate.objects.filter(user=user).order_by('-created_at')

        mandate_data = []
        for mandate in mandates:
            mandate_data.append(
                {
                    'id': str(mandate.id),
                    'mandate_id': mandate.mandate_id,
                    'payer_msisdn': mandate.payer_msisdn,
                    'status': mandate.status,
                    'frequency': mandate.frequency,
                    'first_payment_date': mandate.first_payment_date,
                    'expiry_date': mandate.expiry_date,
                    'subscription_plan_id': str(mandate.subscription_plan.id)
                    if mandate.subscription_plan
                    else None,
                    'created_at': mandate.created_at,
                    'is_active': mandate.is_active(),
                }
            )

        return Response({'success': True, 'mandates': mandate_data})

    except Exception as e:
        return Response(
            {'error': f'Failed to list mandates: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@permission_classes([AllowAny])  # Telebirr calls this webhook
def telebirr_direct_debit_webhook(request):
    """Webhook endpoint for Telebirr async Result envelopes.

    Telebirr POSTs a SOAP Result envelope (``Content-Type: text/xml``). The
    previous version read ``request.data`` (JSON-only) which silently 400'd
    every real callback. We now parse the raw XML body and correlate by
    ``OriginatorConversationID``. We always return HTTP 200 so Telebirr
    does not retry-storm us; processing errors are logged.

    One-off payments are two-stage, matching what Telebirr actually sends:
    the FIRST callback only confirms the mandate/payment request was
    accepted (no TransactionID yet) -- this is where the real debit is
    actually requested via initiate_debit(), storing the resulting
    debit_conversation_id. Coins are only credited / the subscription only
    activated on the SECOND callback: the transaction-result webhook,
    correlated by debit_conversation_id (since its own
    OriginatorConversationID is the debit call's, not the original mandate
    call's) and carrying a real TransactionID. Crediting on the first
    callback -- as this function used to -- means coins can be handed out
    before Telebirr has even attempted to move money.

    Locked for the rest of this request. Telebirr callbacks are documented
    to retry, and this webhook has no signature verification (see
    docs/security.md), so a duplicate or truly concurrent delivery of the
    same callback is a real, expected case. select_for_update() blocks a
    second concurrent delivery on this mandate until the first commits; the
    status checks throughout (status == 'active' already, status ==
    'pending_created', etc.) are what stop a retry -- concurrent or
    sequential -- from re-crediting coins or re-running a transition that
    already ran.
    """
    raw_body = request.body or b''
    logger.warning(
        'Telebirr webhook hit: ct=%s len=%d body=%s',
        request.META.get('CONTENT_TYPE'),
        len(raw_body),
        raw_body[:4000],
    )

    try:
        # XML first (real Telebirr); JSON fallback for manual tests.
        parsed = _parse_telebirr_soap_result(raw_body)
        if not parsed.get('OriginatorConversationID') and isinstance(request.data, dict):
            tx = request.data.get('TransactionResult') or {}
            parsed = {
                'ResultType': request.data.get('ResultType'),
                'ResultCode': request.data.get('ResultCode'),
                'ResultDesc': request.data.get('ResultDesc'),
                'ConversationID': request.data.get('ConversationID'),
                'OriginatorConversationID': request.data.get('OriginatorConversationID'),
                # Accept the TransactionID either nested under
                # TransactionResult or at the top level.
                #
                # This used to read
                #   tx.get('TransactionID') if isinstance(tx, dict) else request.data.get('TransactionID')
                # whose else-branch was unreachable: `tx` is assigned
                # `request.data.get('TransactionResult') or {}` on the line
                # above, so it is ALWAYS a dict and isinstance() is always
                # true. A callback carrying a top-level TransactionID
                # therefore parsed as TransactionID=None.
                #
                # The consequence was not cosmetic. `new_mandate_id` below is
                # `MandateID or TransactionID`, and it is what distinguishes
                # Telebirr's transaction-result callback ("the debit
                # completed -- credit the coins") from the mandate-acceptance
                # callback ("now go initiate the debit"). With TransactionID
                # lost, a genuine transaction-result callback fell through to
                # the acceptance branch and re-issued initiate_debit for a
                # payment that had already succeeded, then marked the mandate
                # 'failed'. Reproduced end-to-end against real PostgreSQL:
                # the one-off payment never activated and the user was never
                # credited.
                #
                # Only this JSON branch is affected -- real Telebirr traffic
                # is XML and is handled by _parse_telebirr_soap_result above.
                'TransactionID': tx.get('TransactionID') or request.data.get('TransactionID'),
                'MandateID': request.data.get('MandateID'),
            }

        logger.info('Telebirr webhook parsed: %s', parsed)

        originator_conversation_id = parsed.get('OriginatorConversationID')
        result_code = parsed.get('ResultCode')
        result_type = parsed.get('ResultType')
        result_desc = parsed.get('ResultDesc') or ''
        # Telebirr returns the new MandateID either in <MandateID> or, for
        # InitTrans, the transaction id in <TransactionID>.
        new_mandate_id = parsed.get('MandateID') or parsed.get('TransactionID')

        if not originator_conversation_id:
            logger.warning('Telebirr webhook: no OriginatorConversationID found, ignoring')
            return Response({'success': True})

        with db_transaction.atomic():
            mandate = (
                DirectDebitMandate.objects.select_for_update()
                .filter(originator_conversation_id=originator_conversation_id)
                .first()
            )

            # The transaction-result callback for a one-off payment arrives
            # with a DIFFERENT OriginatorConversationID -- the debit call's,
            # not the original mandate call's -- so it only correlates via
            # debit_conversation_id.
            if not mandate:
                mandate = (
                    DirectDebitMandate.objects.select_for_update()
                    .filter(debit_conversation_id=originator_conversation_id)
                    .first()
                )
                if mandate:
                    logger.info(
                        'Telebirr webhook: matched mandate %s by debit_conversation_id', mandate.id
                    )

            if not mandate:
                logger.warning(
                    'Telebirr webhook: no mandate matched OriginatorConversationID=%s',
                    originator_conversation_id,
                )
                return Response({'success': True})

            is_success = result_code == '0' and (result_type == '0' or result_type is None)

            if is_success:
                # Persist the real MandateID as soon as we get it (max 18 bytes).
                if new_mandate_id and not mandate.mandate_id:
                    mandate.mandate_id = new_mandate_id[:18]
                    mandate.save(update_fields=['mandate_id'])

                if mandate.payment_type == 'one_off':
                    # A TransactionID present while still 'pending_created' is
                    # Telebirr's transaction-result callback -- the debit
                    # actually completed. Anything else at this stage is the
                    # mandate/payment-request acceptance callback.
                    if new_mandate_id and mandate.status == 'pending_created':
                        purchase_type = (mandate.metadata or {}).get('purchase_type', 'coins')

                        if purchase_type == 'subscription':
                            _activate_one_off_subscription(mandate)
                        else:
                            _credit_one_off_coins(mandate)
                    elif mandate.status == 'active':
                        # Already processed by an earlier delivery of this
                        # same callback -- re-running would double-pay.
                        logger.info(
                            'Telebirr webhook: one-off mandate %s already processed, ignoring duplicate callback',
                            mandate.id,
                        )
                    else:
                        # Mandate/payment-request acceptance callback:
                        # actually request the debit now. Coins/subscription
                        # are NOT touched here -- only on the transaction
                        # result callback above.
                        amount = mandate.metadata.get('amount', 10)
                        debit_result = telebirr_direct_debit_service.initiate_debit(
                            payer_reference_number=mandate.payer_reference_number,
                            amount=amount,
                            currency='ETB',
                            mandate_id=mandate.mandate_id or None,
                        )
                        if debit_result.get('success'):
                            if debit_result.get('originator_conversation_id'):
                                mandate.debit_conversation_id = debit_result.get(
                                    'originator_conversation_id'
                                )
                                mandate.save(update_fields=['debit_conversation_id'])
                            logger.info(
                                'Telebirr webhook: debit initiated for mandate %s, waiting for transaction result',
                                mandate.id,
                            )
                        else:
                            logger.error(
                                'Telebirr webhook: debit initiation failed for mandate %s: %s',
                                mandate.id,
                                debit_result.get('error'),
                            )
                            mandate.mark_failed(
                                f'Debit initiation failed: {debit_result.get("error")}'
                            )
                elif mandate.status == 'cancelling':
                    # Recovery path: confirms a cancellation that was
                    # claimed by cancel_direct_debit_mandate but whose
                    # synchronous outcome was never confirmed (e.g. the
                    # Telebirr HTTP call timed out after Telebirr had
                    # already processed it). See that view for the claim
                    # step this resolves.
                    mandate.cancel()
                    if mandate.subscription_plan and mandate.subscription_plan.auto_renew:
                        sp = mandate.subscription_plan
                        sp.auto_renew = False
                        sp.save()
                else:
                    # Handle recurring mandates. Each branch is guarded by the
                    # mandate's current status, so a repeated callback for a
                    # transition that already happened is a no-op rather than
                    # re-running side effects. 'activating' is included
                    # alongside 'pending_active' as a recovery path for
                    # activate_direct_debit_mandate's claim step above.
                    if mandate.status == 'pending_created':
                        mandate.status = 'pending_active'
                        mandate.save()
                    elif mandate.status in ('pending_active', 'activating'):
                        # Subscription creation for the recurring flow is
                        # intentionally NOT done here -- it belongs to
                        # activate_direct_debit_mandate (user-triggered),
                        # which already creates it with its own claim-then-
                        # finalize locking. Doing it here too would create a
                        # second, competing SubscriptionPlan if both this
                        # recovery path and that view fire for the same
                        # mandate. This just finalizes the status; that view
                        # (or its own recovery re-check) owns the rest.
                        mandate.activate()  # also sets activated_at and saves
            else:
                # Failure callback. If a one-off payment had already been
                # optimistically credited/activated by an earlier delivery
                # of a DIFFERENT (successful) callback for the same
                # correlation id, this later failure must undo it rather
                # than leave coins or an active subscription behind a
                # payment that ultimately failed.
                if mandate.payment_type == 'one_off' and mandate.status == 'active':
                    purchase_type = (mandate.metadata or {}).get('purchase_type', 'coins')
                    if purchase_type == 'subscription':
                        _rollback_one_off_subscription(mandate)
                    else:
                        _rollback_one_off_coins(mandate)

                if mandate.status == 'cancelling':
                    # Telebirr rejected the cancellation -- the mandate is
                    # still active, so revert the claim rather than marking
                    # it 'failed' (which would incorrectly kill a live
                    # subscription).
                    mandate.status = 'active'
                    mandate.save()
                else:
                    mandate.mark_failed(result_desc or f'ResultCode={result_code}')

        return Response({'success': True})

    except Exception as e:
        # Don't bubble 500s back to Telebirr; just log and ack.
        logger.exception('Telebirr webhook processing failed: %s', e)
        return Response({'success': True})


def _credit_one_off_coins(mandate):
    """Credit coins for a confirmed one-off Telebirr Direct Debit payment.
    Called only from inside telebirr_direct_debit_webhook's locked block."""
    from api.models import UserProfile

    try:
        if not mandate.user:
            logger.error('Telebirr webhook: mandate %s has no user, cannot add coins', mandate.id)
            mandate.mark_failed('No user on mandate')
            return
        profile = mandate.user.profile
        coins_to_add = mandate.metadata.get('coins', 100)
        balance, _ = UserCoinBalance.objects.get_or_create(user=mandate.user)
        balance.add_purchased(
            coins_to_add,
            transaction_type='purchase',
            payment_method='telebirr',
            description=f'One-off Direct Debit payment {mandate.id}',
        )
        profile.coins = balance.balance
        profile.save(update_fields=['coins'])
        mandate.status = 'active'
        mandate.save(update_fields=['status'])
        logger.info(
            'Telebirr webhook: credited %s coins to %s for mandate %s',
            coins_to_add,
            mandate.user.username,
            mandate.id,
        )
    except UserProfile.DoesNotExist:
        logger.error(
            'Telebirr webhook: UserProfile not found for %s, cannot add coins',
            mandate.user.username,
        )
        mandate.mark_failed('UserProfile not found')


def _rollback_one_off_coins(mandate):
    """Undo a coin credit for a one-off payment that was later reported
    failed. Called only from inside telebirr_direct_debit_webhook's locked
    block."""
    if not mandate.user:
        return
    try:
        balance = UserCoinBalance.objects.filter(user=mandate.user).first()
        if not balance:
            return
        coins_to_deduct = mandate.metadata.get('coins', 100)
        balance.spend_coins(
            coins_to_deduct, 'rollback', description=f'Rollback failed payment {mandate.id}'
        )
        profile = mandate.user.profile
        profile.coins = balance.balance
        profile.save(update_fields=['coins'])
        logger.warning(
            'Telebirr webhook: rolled back %s coins from %s for failed mandate %s',
            coins_to_deduct,
            mandate.user.username,
            mandate.id,
        )
    except Exception as exc:
        logger.exception(
            'Telebirr webhook: error rolling back coins for mandate %s: %s', mandate.id, exc
        )


def _activate_one_off_subscription(mandate):
    """Create/activate the SubscriptionPlan for a confirmed one-off
    subscription payment. Resolves or creates the user by phone for
    anonymous purchases. Called only from inside
    telebirr_direct_debit_webhook's locked block."""
    from django.db.models import Q

    from api.models import UserProfile

    try:
        if mandate.subscription_plan_id:
            # Already created by an earlier delivery of this callback.
            mandate.status = 'active'
            mandate.save(update_fields=['status'])
            return

        phone = mandate.payer_msisdn
        target_user = mandate.user
        is_new_user = False
        if not target_user:
            phone_variants = [phone]
            if phone.startswith('251') and len(phone) == 12:
                phone_variants += ['0' + phone[3:], '+' + phone]
            elif phone.startswith('0') and len(phone) == 10:
                phone_variants += ['251' + phone[1:], '+251' + phone[1:]]
            profile = UserProfile.objects.filter(Q(phone_number__in=phone_variants)).first()
            if profile:
                target_user = profile.user
                mandate.user = target_user
                mandate.save(update_fields=['user'])
            else:
                is_new_user = True

        tier = mandate.tier
        meta = mandate.metadata or {}
        duration_days = meta.get('duration_days') or (tier.duration_days if tier else None)
        duration_type = tier.duration_type if tier else meta.get('duration_type', 'daily')
        now = timezone.now()
        end_date = now + timedelta(days=duration_days) if duration_days else None

        if target_user:
            SubscriptionPlan.objects.filter(user=target_user, status='active').update(
                status='expired'
            )

        subscription_plan = SubscriptionPlan.objects.create(
            user=target_user,
            tier=tier,
            status='active',
            duration_type=duration_type,
            start_date=now,
            end_date=end_date,
            next_renewal_date=None,
            auto_renew=False,
            payment_method='telebirr',
            telebirr_phone_number=phone,
        )
        mandate.subscription_plan = subscription_plan
        mandate.save(update_fields=['subscription_plan'])

        if is_new_user:
            try:
                from api.services.otp import OTPService
                from api.services.sms.dispatch import queue_sms

                otp_code = OTPService.generate_otp()
                subscription_plan.setup_otp = otp_code
                subscription_plan.setup_otp_expires_at = now + timedelta(minutes=30)
                meta = subscription_plan.metadata or {}
                meta['is_new_user'] = True
                subscription_plan.metadata = meta
                subscription_plan.save(
                    update_fields=['setup_otp', 'setup_otp_expires_at', 'metadata']
                )

                message = f'You have successfully subscribed. Your OTP is: {otp_code}. Please use this to log in.'
                # Over TIMWE SMPP. This went through OnevasWebhookView.send_sms,
                # which has been removed along with the rest of OneVAS.
                queue_sms(phone_number=phone, text=message, purpose='otp_subscription_setup')
            except Exception:
                logger.exception(
                    'Telebirr webhook: failed to send setup OTP SMS for mandate %s', mandate.id
                )

        mandate.status = 'active'
        mandate.save(update_fields=['status'])
        logger.info(
            'Telebirr webhook: activated one-off subscription %s for mandate %s',
            subscription_plan.id,
            mandate.id,
        )
    except Exception as exc:
        logger.exception(
            'Telebirr webhook: error activating one-off subscription for mandate %s: %s',
            mandate.id,
            exc,
        )
        mandate.mark_failed(f'Subscription activation failed: {exc}')


def _rollback_one_off_subscription(mandate):
    """Cancel a subscription that was activated but later reported failed.
    Called only from inside telebirr_direct_debit_webhook's locked block."""
    try:
        subscription_plan = mandate.subscription_plan
        if subscription_plan and subscription_plan.status == 'active':
            subscription_plan.status = 'cancelled'
            subscription_plan.save(update_fields=['status'])
            logger.warning(
                'Telebirr webhook: cancelled subscription %s for failed mandate %s',
                subscription_plan.id,
                mandate.id,
            )
    except Exception as exc:
        logger.exception(
            'Telebirr webhook: error cancelling subscription for mandate %s: %s', mandate.id, exc
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def initiate_direct_debit(request):
    """
    Manually initiate a direct debit transaction (for testing or manual renewal)

    Request Body:
    {
        "mandate_id": "uuid",
        "amount": 100.00
    }
    """
    try:
        user = request.user
        mandate_id = request.data.get('mandate_id')
        amount = request.data.get('amount')

        # Validate required fields
        if not all([mandate_id, amount]):
            return Response(
                {'error': 'mandate_id and amount are required'}, status=status.HTTP_400_BAD_REQUEST
            )

        # Get mandate
        try:
            mandate = DirectDebitMandate.objects.get(id=mandate_id, user=user)
        except DirectDebitMandate.DoesNotExist:
            return Response({'error': 'Mandate not found'}, status=status.HTTP_404_NOT_FOUND)

        # Check if mandate is active
        if not mandate.is_active():
            return Response(
                {'error': f'Mandate is {mandate.status}, cannot initiate debit'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not mandate.mandate_id:
            return Response(
                {'error': 'Mandate has no Telebirr MandateID yet, cannot initiate debit.'},
                status=status.HTTP_409_CONFLICT,
            )

        # Create transaction record
        transaction = DirectDebitTransaction.objects.create(
            mandate=mandate, amount=Decimal(str(amount)), currency='ETB', status='pending'
        )

        # Call Telebirr service to initiate debit
        result = telebirr_direct_debit_service.initiate_debit(
            mandate_id=mandate.mandate_id,
            payer_reference_number=mandate.payer_reference_number,
            amount=amount,
            shortcode=mandate.payee_identifier_value,
        )

        if not result.get('success'):
            transaction.mark_failed(result.get('error'))
            return Response(
                {'error': result.get('error', 'Direct debit initiation failed')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Update transaction
        transaction.originator_conversation_id = result.get('originator_conversation_id')
        transaction.conversation_id = result.get('conversation_id')
        transaction.telebirr_transaction_id = result.get('transaction_id')
        transaction.save()

        return Response(
            {
                'success': True,
                'transaction_id': str(transaction.id),
                'status': transaction.status,
                'message': 'Direct debit initiated successfully',
            }
        )

    except Exception as e:
        return Response(
            {'error': f'Failed to initiate direct debit: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def create_one_off_coin_purchase(request):
    """
    Create a one-off payment for coin purchasing via Telebirr Direct Debit

    Request Body:
    {
        "amount": 10.00,
        "coins": 100
    }

    Returns:
    {
        "success": true,
        "mandate_id": "uuid",
        "originator_conversation_id": "S_X20260519...",
        "message": "One-off payment request accepted"
    }
    """
    try:
        user = request.user
        amount = request.data.get('amount')
        coins = request.data.get('coins', 100)

        # Validate required fields
        if not amount:
            return Response({'error': 'amount is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Get user's phone number from profile
        from api.models import UserProfile

        try:
            profile = user.profile
            payer_msisdn = profile.phone_number
            if not payer_msisdn:
                return Response(
                    {'error': 'Phone number not found in profile'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except UserProfile.DoesNotExist:
            return Response({'error': 'User profile not found'}, status=status.HTTP_404_NOT_FOUND)

        # Generate unique payer reference number
        payer_reference_number = f"COIN_{user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Call Telebirr service to create one-off payment
        result = telebirr_direct_debit_service.create_one_off_payment(
            payer_msisdn=payer_msisdn,
            payer_reference_number=payer_reference_number,
            frequency='01',
            first_payment_date=datetime.now().date(),
            expiry_date=datetime.now().date(),
        )

        if not result.get('success'):
            return Response(
                {'error': result.get('error', 'One-off payment request failed')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Create mandate record with payment_type='one_off'
        mandate = DirectDebitMandate.objects.create(
            user=user,
            payer_msisdn=payer_msisdn,
            payer_reference_number=payer_reference_number,
            payee_identifier_type=4,
            payee_identifier_value=telebirr_direct_debit_service.shortcode,
            payee_account_name=telebirr_direct_debit_service.payee_account_name,
            status='pending_created',
            payment_type='one_off',
            frequency='01',
            first_payment_date=datetime.now().date(),
            expiry_date=datetime.now().date(),
            agreed_tc=True,
            originator_conversation_id=result.get('originator_conversation_id'),
            conversation_id=result.get('conversation_id'),
            metadata={'coins': coins, 'amount': amount},
        )

        return Response(
            {
                'success': True,
                'mandate_id': str(mandate.id),
                'originator_conversation_id': result.get('originator_conversation_id'),
                'conversation_id': result.get('conversation_id'),
                'message': 'One-off payment request accepted successfully. Wait for payment confirmation.',
                'coins': coins,
                'amount': amount,
            }
        )

    except Exception as e:
        return Response(
            {'error': f'Failed to create one-off payment: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def create_one_off_subscription(request):
    """
    Create a ONE-OFF (non-recurring) subscription payment via Telebirr Direct Debit.

    The user pays ONCE for the selected period (daily / weekly / monthly). When the
    period ends the subscription simply expires and the user must renew manually by
    triggering this endpoint again (mimics the one-off coin purchase logic, but with
    the tier's respective frequency stored for reference).

    Works for both logged-in and anonymous callers (matching the old recurring flow):
    when anonymous, the user is resolved/created by phone number in the webhook.

    Request Body:
    {
        "tier_id": "uuid",
        "payer_msisdn": "251911234567"   # required if not logged in; else falls back to profile phone
    }
    """
    try:
        user = request.user if request.user.is_authenticated else None
        tier_id = request.data.get('tier_id')
        payer_msisdn = request.data.get('payer_msisdn')

        if not tier_id:
            return Response({'error': 'tier_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        from api.models import UserProfile

        if not payer_msisdn and user:
            try:
                payer_msisdn = user.profile.phone_number
            except UserProfile.DoesNotExist:
                payer_msisdn = None
        if not payer_msisdn:
            return Response(
                {'error': 'Phone number not found. Please provide payer_msisdn.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve subscription tier -- try UUID first, then fall back to
        # onevas_code / duration_type (mirrors the recurring create-mandate view).
        try:
            tier = SubscriptionTier.objects.get(id=tier_id)
        except (SubscriptionTier.DoesNotExist, ValueError):
            try:
                tier = SubscriptionTier.objects.get(onevas_code=str(tier_id))
            except SubscriptionTier.DoesNotExist:
                duration_type_map = {1: 'daily', 2: 'weekly', 3: 'monthly'}
                duration_type = duration_type_map.get(
                    int(tier_id) if str(tier_id).isdigit() else None
                )
                if duration_type:
                    tier = SubscriptionTier.objects.filter(
                        duration_type=duration_type, is_active=True
                    ).first()
                    if not tier:
                        return Response(
                            {'error': f'No active subscription tier found for {duration_type}'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                else:
                    return Response(
                        {'error': 'Invalid subscription tier'}, status=status.HTTP_400_BAD_REQUEST
                    )

        frequency_map = {'daily': '02', 'weekly': '03', 'monthly': '05'}
        if tier.duration_type not in frequency_map:
            return Response(
                {'error': 'This tier does not support Telebirr subscription'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        intended_frequency = frequency_map[tier.duration_type]

        user_ref = user.id if user else 'ANON'
        payer_reference_number = f"SUB_{user_ref}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Call Telebirr to create a one-off payment (frequency '01' = Once).
        # We charge once now; the intended recurring frequency is only stored
        # in metadata since this is a manual-renewal (non-recurring) flow.
        result = telebirr_direct_debit_service.create_one_off_payment(
            payer_msisdn=payer_msisdn,
            payer_reference_number=payer_reference_number,
            frequency='01',
            first_payment_date=datetime.now().date(),
            expiry_date=datetime.now().date(),
        )

        if not result.get('success'):
            return Response(
                {'error': result.get('error', 'Subscription payment request failed')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        mandate = DirectDebitMandate.objects.create(
            user=user,
            tier=tier,
            payer_msisdn=payer_msisdn,
            payer_reference_number=payer_reference_number,
            payee_identifier_type=4,
            payee_identifier_value=telebirr_direct_debit_service.shortcode,
            payee_account_name=telebirr_direct_debit_service.payee_account_name,
            status='pending_created',
            payment_type='one_off',
            frequency='01',
            first_payment_date=datetime.now().date(),
            expiry_date=datetime.now().date(),
            agreed_tc=True,
            originator_conversation_id=result.get('originator_conversation_id'),
            conversation_id=result.get('conversation_id'),
            metadata={
                'purchase_type': 'subscription',
                'tier_id': str(tier.id),
                'duration_type': tier.duration_type,
                'duration_days': tier.duration_days,
                'amount': str(tier.price_etb),
                'frequency': intended_frequency,
            },
        )

        logger.info(
            '[ONE-OFF SUB] Mandate created: %s (ref=%s)', mandate.id, payer_reference_number
        )

        return Response(
            {
                'success': True,
                'mandate_id': str(mandate.id),
                'originator_conversation_id': result.get('originator_conversation_id'),
                'conversation_id': result.get('conversation_id'),
                'message': 'One-off subscription payment request accepted. Wait for activation.',
                'tier': tier.name,
                'amount': str(tier.price_etb),
            }
        )

    except Exception as e:
        logger.exception('[ONE-OFF SUB] Failed to create subscription payment')
        return Response(
            {'error': f'Failed to create subscription payment: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def check_mandate_status(request):
    """
    Check the status of a one-off payment mandate.

    Query Parameters:
        mandate_id: The mandate UUID

    AllowAny + unguessable UUID: anonymous one-off purchasers have no auth
    token until the webhook creates their account, so they must be able to
    poll before that happens. If the caller IS authenticated, ownership is
    still enforced (or the mandate must still be unlinked to a user).
    """
    from django.db.models import Q

    try:
        mandate_id = request.GET.get('mandate_id')
        if not mandate_id:
            return Response({'error': 'mandate_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        qs = DirectDebitMandate.objects.filter(id=mandate_id)
        if request.user.is_authenticated:
            qs = qs.filter(Q(user=request.user) | Q(user__isnull=True))
        mandate = qs.first()
        if not mandate:
            return Response({'error': 'Mandate not found'}, status=status.HTTP_404_NOT_FOUND)

        purchase_type = (mandate.metadata or {}).get('purchase_type', 'coins')
        is_completed = mandate.status == 'active' and mandate.payment_type == 'one_off'
        # coins_added kept for backward-compat with the coin-purchase frontend
        coins_added = is_completed and purchase_type != 'subscription'
        subscription_active = is_completed and purchase_type == 'subscription'

        is_new_user = False
        if mandate.subscription_plan and mandate.subscription_plan.metadata:
            is_new_user = mandate.subscription_plan.metadata.get('is_new_user', False)

        return Response(
            {
                'success': True,
                'status': mandate.status,
                'coins_added': coins_added,
                'subscription_active': subscription_active,
                'completed': is_completed,
                'purchase_type': purchase_type,
                'payment_type': mandate.payment_type,
                'is_new_user': is_new_user,
            }
        )

    except Exception as e:
        return Response(
            {'error': f'Failed to check mandate status: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_b2c_payment(request):
    """
    Initiate a standalone Individual B2C Payment Transaction, tracked as its
    own B2CPaymentTransaction row (distinct from the withdrawal payout flow
    in api/views/wallet.py::request_withdrawal, which links a B2C payout
    directly to a WithdrawalRequest instead of creating one of these).

    Request Body:
    {
        "receiver_msisdn": "251911234567",
        "amount": 100.00,
        "currency": "ETB",
        "reason_type": "...",
        "remark": "...",
        "reference_data": {...},
        "initiator_type": "org_operator"
    }
    """
    try:
        receiver_msisdn = request.data.get('receiver_msisdn')
        amount = request.data.get('amount')
        currency = request.data.get('currency', 'ETB')
        reason_type = request.data.get('reason_type')
        remark = request.data.get('remark', '')
        reference_data = request.data.get('reference_data', {})
        initiator_type = request.data.get('initiator_type', 'org_operator')

        if not receiver_msisdn or not amount:
            return Response(
                {'error': 'receiver_msisdn and amount are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            amount_decimal = Decimal(str(amount))
            if amount_decimal <= 0:
                return Response(
                    {'error': 'Amount must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST
                )
        except (ValueError, TypeError):
            return Response({'error': 'Invalid amount format'}, status=status.HTTP_400_BAD_REQUEST)

        result = telebirr_direct_debit_service.initiate_b2c_payment(
            receiver_msisdn=receiver_msisdn,
            amount=amount_decimal,
            currency=currency,
            reason_type=reason_type,
            remark=remark,
            reference_data=reference_data,
            initiator_type=initiator_type,
        )

        if not result.get('success'):
            return Response(
                {'error': result.get('error', 'B2C payment initiation failed')},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        transaction = B2CPaymentTransaction.objects.create(
            payer=request.user,
            receiver_msisdn=receiver_msisdn,
            amount=amount_decimal,
            currency=currency,
            reason_type=reason_type or telebirr_direct_debit_service.b2c_reason_type,
            remark=remark,
            reference_data=reference_data,
            originator_conversation_id=result.get('originator_conversation_id') or '',
            conversation_id=result.get('conversation_id') or '',
            status='pending',
        )

        return Response(
            {
                'success': True,
                'transaction_id': str(transaction.id),
                'originator_conversation_id': result.get('originator_conversation_id'),
                'conversation_id': result.get('conversation_id'),
                'message': 'B2C payment initiated successfully',
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        return Response(
            {'error': f'Failed to initiate B2C payment: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_b2c_payments(request):
    """List the authenticated user's own B2CPaymentTransaction rows."""
    try:
        transactions = B2CPaymentTransaction.objects.filter(payer=request.user)

        status_filter = request.query_params.get('status')
        if status_filter:
            transactions = transactions.filter(status=status_filter)

        transactions = transactions.order_by('-created_at')

        return Response(
            {
                'success': True,
                'transactions': [
                    {
                        'id': str(t.id),
                        'receiver_msisdn': t.receiver_msisdn,
                        'amount': str(t.amount),
                        'currency': t.currency,
                        'reason_type': t.reason_type,
                        'remark': t.remark,
                        'status': t.status,
                        'telebirr_transaction_id': t.telebirr_transaction_id,
                        'created_at': t.created_at,
                        'completed_at': t.completed_at,
                    }
                    for t in transactions
                ],
            }
        )

    except Exception as e:
        return Response(
            {'error': f'Failed to list B2C payments: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([HasAdminPermission])
def query_mandate_from_telebirr(request):
    """
    Query mandate status directly from Telebirr for a given payer phone
    number. An ops/support diagnostic tool, not a self-service lookup --

    Master gates this behind bare IsAuthenticated with an arbitrary
    payer_msisdn query param, letting any logged-in user probe any phone
    number's mandate status. Gated behind HasAdminPermission instead, since
    nothing here scopes it to the caller's own phone number.

    Query params:
    - payer_msisdn: Payer phone number (required)
    - mandate_statuses: Optional comma-separated list of mandate status codes (e.g., '03,01')
    """
    payer_msisdn = request.query_params.get('payer_msisdn')
    mandate_statuses_param = request.query_params.get('mandate_statuses')

    if not payer_msisdn:
        return Response({'error': 'payer_msisdn is required'}, status=status.HTTP_400_BAD_REQUEST)

    mandate_statuses = mandate_statuses_param.split(',') if mandate_statuses_param else None

    logger.info(f'Querying mandate from Telebirr for payer_msisdn: {payer_msisdn}')

    try:
        result = telebirr_direct_debit_service.query_mandate_by_payer(
            payer_msisdn=payer_msisdn,
            mandate_statuses=mandate_statuses,
            debug=True,
        )
    except Exception as e:
        logger.error(f'Failed to query mandate from Telebirr: {e}')
        return Response(
            {'error': f'Failed to query mandate: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    if not result.get('success'):
        return Response({'error': result.get('error')}, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            'success': True,
            'message': result.get('message'),
            'response_code': result.get('response_code'),
            'conversation_id': result.get('conversation_id'),
            'response_text': result.get('response_text'),
        }
    )


query_mandate_from_telebirr.view_class.required_permission = 'view_payments'


@api_view(['POST'])
@permission_classes([AllowAny])  # Telebirr calls this webhook
def telebirr_b2c_webhook(request):
    """
    Webhook endpoint for Telebirr B2C payment result callbacks.

    Telebirr POSTs a SOAP Result envelope (Content-Type: text/xml) when a
    B2C payment completes -- the same envelope shape handled by
    telebirr_direct_debit_webhook above, reusing _parse_telebirr_soap_result.

    Three correlation paths, mirroring the three ways a B2C payment can start:
    1. Withdrawal-initiated payout (request_withdrawal): no
       B2CPaymentTransaction row exists, the WithdrawalRequest itself carries
       originator_conversation_id -- looked up and locked directly.
    2. Standalone B2C payment (initiate_b2c_payment): a real
       B2CPaymentTransaction row exists and is looked up and locked instead;
       any reference_data['withdrawal_id'] on it is then also updated.
    3. Winner-gift payout (api/views/crm.py::send_b2c_gift/send_b2c_bulk): a
       WinnerGiftTransaction row carries its own originator_conversation_id,
       looked up and locked the same way as the withdrawal-direct path.

    Locked for the rest of this request, same reasoning as
    telebirr_direct_debit_webhook: Telebirr retries callbacks and this
    endpoint has no signature verification, so select_for_update() plus a
    status check (only a 'processing' withdrawal / 'pending' transaction is
    ever transitioned) is what prevents a duplicate delivery from
    double-crediting a payout or double-refunding points. We always return
    200 so Telebirr does not retry-storm us.
    """
    from api.models import UserProfile
    from api.models.wallet import WithdrawalRequest

    raw_body = request.body or b''
    logger.info('Telebirr B2C webhook hit: len=%d body=%s', len(raw_body), raw_body[:4000])

    try:
        parsed = _parse_telebirr_soap_result(raw_body)
        originator_conversation_id = parsed.get('OriginatorConversationID')
        result_code = parsed.get('ResultCode')
        result_type = parsed.get('ResultType')
        result_desc = parsed.get('ResultDesc') or ''
        transaction_id = parsed.get('TransactionID')

        if not originator_conversation_id:
            logger.warning('Telebirr B2C webhook: no OriginatorConversationID found, ignoring')
            return Response({'success': True})

        is_success = result_code == '0' and (result_type == '0' or result_type is None)

        with db_transaction.atomic():
            transaction = (
                B2CPaymentTransaction.objects.select_for_update()
                .filter(originator_conversation_id=originator_conversation_id)
                .first()
            )

            if transaction:
                if transaction.status != 'pending':
                    logger.info(
                        'Telebirr B2C webhook: transaction %s already %s, ignoring duplicate callback',
                        transaction.id,
                        transaction.status,
                    )
                    return Response({'success': True})

                if is_success:
                    transaction.mark_success(transaction_id or '')
                else:
                    transaction.mark_failed(result_desc or f'ResultCode={result_code}')

                withdrawal_id = (transaction.reference_data or {}).get('withdrawal_id')
                if withdrawal_id:
                    withdrawal = (
                        WithdrawalRequest.objects.select_for_update()
                        .filter(pk=withdrawal_id)
                        .first()
                    )
                    if withdrawal and withdrawal.status == 'processing':
                        if is_success:
                            withdrawal.status = 'completed'
                            withdrawal.completed_at = timezone.now()
                            withdrawal.payout_reference = transaction_id or ''
                            withdrawal.telebirr_transaction_id = transaction_id or ''
                            withdrawal.save(
                                update_fields=[
                                    'status',
                                    'completed_at',
                                    'payout_reference',
                                    'telebirr_transaction_id',
                                ]
                            )
                            notify_withdrawal_paid(withdrawal)
                        else:
                            withdrawal.status = 'failed'
                            withdrawal.rejection_reason = (
                                f'B2C payment failed: {result_desc or f"ResultCode={result_code}"}'
                            )
                            withdrawal.save(update_fields=['status', 'rejection_reason'])
                            user_profile = UserProfile.objects.select_for_update().get(
                                user=withdrawal.user
                            )
                            user_profile.add_points(withdrawal.point_amount, total_field=None)
                            notify_withdrawal_failed(withdrawal, refunded=True)

                return Response({'success': True})

            # No B2CPaymentTransaction -- either a withdrawal-initiated
            # payout (WithdrawalRequest carries its own
            # originator_conversation_id) or a winner-gift payout
            # (WinnerGiftTransaction, api/views/crm.py::send_b2c_gift /
            # send_b2c_bulk, same story).
            from api.models.gift import WinnerGiftTransaction

            winner_gift = (
                WinnerGiftTransaction.objects.select_for_update()
                .filter(originator_conversation_id=originator_conversation_id)
                .first()
            )

            if winner_gift:
                if winner_gift.status != 'processing':
                    logger.info(
                        'Telebirr B2C webhook: winner gift %s already %s, ignoring duplicate callback',
                        winner_gift.id,
                        winner_gift.status,
                    )
                    return Response({'success': True})

                if is_success:
                    winner_gift.mark_success(transaction_id or '')
                    logger.info(
                        'Telebirr B2C webhook: winner gift %s marked success', winner_gift.id
                    )
                else:
                    winner_gift.mark_failed(result_desc or f'ResultCode={result_code}')
                    logger.info(
                        'Telebirr B2C webhook: winner gift %s failed: %s',
                        winner_gift.id,
                        result_desc,
                    )

                return Response({'success': True})

            # Neither of the above -- a withdrawal-initiated payout, which
            # correlates directly via the WithdrawalRequest's own
            # originator_conversation_id instead.
            withdrawal = (
                WithdrawalRequest.objects.select_for_update()
                .filter(originator_conversation_id=originator_conversation_id)
                .first()
            )

            if not withdrawal:
                logger.warning(
                    'Telebirr B2C webhook: no transaction, winner gift, or withdrawal matched OriginatorConversationID=%s',
                    originator_conversation_id,
                )
                return Response({'success': True})

            if withdrawal.status != 'processing':
                logger.info(
                    'Telebirr B2C webhook: withdrawal #%s status is %s (not processing), ignoring duplicate callback',
                    withdrawal.id,
                    withdrawal.status,
                )
                return Response({'success': True})

            if is_success:
                withdrawal.status = 'completed'
                withdrawal.completed_at = timezone.now()
                withdrawal.payout_reference = transaction_id or ''
                withdrawal.telebirr_transaction_id = transaction_id or ''
                withdrawal.save(
                    update_fields=[
                        'status',
                        'completed_at',
                        'payout_reference',
                        'telebirr_transaction_id',
                    ]
                )
                notify_withdrawal_paid(withdrawal)
                logger.info('Telebirr B2C webhook: withdrawal #%s marked completed', withdrawal.id)
            else:
                withdrawal.status = 'failed'
                withdrawal.rejection_reason = (
                    f'B2C payment failed: {result_desc or f"ResultCode={result_code}"}'
                )
                withdrawal.save(update_fields=['status', 'rejection_reason'])
                user_profile = UserProfile.objects.select_for_update().get(user=withdrawal.user)
                user_profile.add_points(withdrawal.point_amount, total_field=None)
                notify_withdrawal_failed(withdrawal, refunded=True)
                logger.info(
                    'Telebirr B2C webhook: withdrawal #%s failed, %s points refunded to %s',
                    withdrawal.id,
                    withdrawal.point_amount,
                    withdrawal.user.username,
                )

        return Response({'success': True})

    except Exception as e:
        logger.error('Telebirr B2C webhook exception: %s', str(e))
        logger.exception('Telebirr B2C webhook full traceback')
        # Don't bubble 500s back to Telebirr; just log and ack.
        return Response({'success': True})
