"""
Views for CRM Gift Integration and Telebirr B2C winner-gift payouts.

Two distinct gift rails, both admin-triggered:
- CRM (Ethio Telecom PresentServiceGift, data bundles) -- CRMGiftPackage/
  CRMGiftTransaction/CRMGiftAuditLog, resolved synchronously (the CRM SOAP
  call itself returns success/failure, there is no separate webhook).
- Telebirr B2C (cash) -- WinnerGiftPackage/WinnerGiftTransaction. Unlike the
  CRM rail, initiating a B2C payment only confirms Telebirr *accepted* the
  request; the transaction is left 'processing' here and only moved to
  'success'/'failed' by telebirr_b2c_webhook (api/views/direct_debit.py)
  once Telebirr's own async result callback arrives -- see that webhook's
  docstring and WinnerGiftTransaction's for why marking it done here (as
  master's own code does) would be crediting a payout before it happened.
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from api.integrations.telebirr.direct_debit import telebirr_direct_debit_service
from api.models.campaign_extended import (
    Campaign,
    Leaderboard,
    LeaderboardEntry,
    SelectedWinner,
    WinnerFrequencyRecord,
    WinnerSelection,
)
from api.models.crm import CRMGiftAuditLog, CRMGiftPackage, CRMGiftTransaction
from api.models.gift import GiftTransaction, WinnerGiftPackage, WinnerGiftTransaction
from api.serializers.crm import (
    AwardCRMGiftSerializer,
    CRMGiftAuditLogSerializer,
    CRMGiftPackageSerializer,
    CRMGiftTransactionSerializer,
)
from api.services.crm_service import CRMService
from common.permissions import HasAdminPermission


def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


def _normalize_local_phone(phone_number):
    """CRM/Telebirr B2C both expect local 09... format, not international 251..."""
    phone_number = phone_number.replace(' ', '').replace('-', '').replace('+', '')
    if phone_number.startswith('251'):
        return '0' + phone_number[3:]
    if not phone_number.startswith('0'):
        return '0' + phone_number
    return phone_number


def _user_can(user, permission):
    """Same check as common.permissions.HasAdminPermission, usable inline
    for scoping a queryset rather than gating a whole view."""
    if user.is_superuser:
        return True
    from api.models.subscription import AdminRole

    admin_role = AdminRole.objects.filter(user=user).first()
    return bool(admin_role and admin_role.has_permission(permission))


class CRMGiftPackageViewSet(viewsets.ModelViewSet):
    """Admin viewset for managing CRM gift packages"""
    permission_classes = [HasAdminPermission]
    required_permission = 'manage_gift_packages'
    serializer_class = CRMGiftPackageSerializer

    def get_queryset(self):
        queryset = CRMGiftPackage.objects.all()
        is_active = self.request.query_params.get('is_active')
        trigger_condition = self.request.query_params.get('trigger_condition')

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        if trigger_condition:
            queryset = queryset.filter(trigger_condition=trigger_condition)

        return queryset.order_by('name')

    @action(detail=False, methods=['get'])
    def active(self, request):
        packages = CRMGiftPackage.objects.filter(is_active=True).order_by('name')
        return Response(CRMGiftPackageSerializer(packages, many=True).data)

    @action(detail=False, methods=['get'])
    def by_trigger(self, request):
        trigger = request.query_params.get('trigger')
        if not trigger:
            return Response({'error': 'trigger parameter required'}, status=status.HTTP_400_BAD_REQUEST)

        packages = CRMGiftPackage.objects.filter(is_active=True, trigger_condition=trigger).order_by('name')
        return Response(CRMGiftPackageSerializer(packages, many=True).data)


class CRMGiftTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """Viewset for CRM gift transactions. Any authenticated user sees their
    own; an admin with 'view_gifts' sees everyone's -- not a blanket
    is_staff check, matching the AdminRole-scoped fix in api/views/admin.py."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CRMGiftTransactionSerializer

    def get_queryset(self):
        queryset = CRMGiftTransaction.objects.select_related('user', 'package')

        if not _user_can(self.request.user, 'view_gifts'):
            queryset = queryset.filter(user=self.request.user)

        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        user_id = self.request.query_params.get('user_id')
        if user_id and _user_can(self.request.user, 'view_gifts'):
            queryset = queryset.filter(user_id=user_id)

        return queryset.order_by('-created_at')

    @action(detail=False, methods=['get'])
    def my_transactions(self, request):
        transactions = CRMGiftTransaction.objects.filter(
            user=request.user,
        ).select_related('package').order_by('-created_at')
        return Response(CRMGiftTransactionSerializer(transactions, many=True).data)

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        if not _user_can(request.user, 'award_gifts'):
            return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

        transaction = self.get_object()
        if transaction.status != 'failed':
            return Response({'error': 'Can only retry failed transactions'}, status=status.HTTP_400_BAD_REQUEST)

        success, message, response_data = CRMService.send_gift(
            service_number_b=transaction.phone_number,
            offering_id=transaction.offering_id,
            charge_amount=float(transaction.charge_amount),
            access_user=getattr(settings, 'CRM_ACCESS_USER', ''),
            access_pwd=getattr(settings, 'CRM_ACCESS_PASSWORD', ''),
        )

        if success:
            transaction.mark_success(response_data.get('ret_code', '0'), message)
        else:
            transaction.mark_failed(response_data.get('ret_code', 'ERROR'), message)

        CRMGiftAuditLog.objects.create(
            transaction=transaction, action='retry', performed_by=request.user,
            details=f'Retried transaction: {message}', ip_address=_get_client_ip(request),
        )

        return Response(CRMGiftTransactionSerializer(transaction).data)


class CRMGiftAwardViewSet(viewsets.ViewSet):
    """Viewset for awarding CRM (data) and Telebirr B2C (cash) gifts to users"""
    permission_classes = [HasAdminPermission]
    required_permission = 'award_gifts'

    def _check_and_create_crm_transaction(self, *, user, phone_number, package, trigger_source, campaign_id):
        if package.max_awards_per_user > 0:
            awards_count = CRMGiftTransaction.objects.filter(user=user, package=package, status='success').count()
            if awards_count >= package.max_awards_per_user:
                return None, f'User has already received this package {awards_count} times (max: {package.max_awards_per_user})'

        return CRMGiftTransaction.objects.create(
            user=user, phone_number=phone_number, package=package, offering_id=package.offering_id,
            transaction_id=CRMService.generate_transaction_id(), charge_amount=package.charge_amount,
            trigger_source=trigger_source, campaign_id=campaign_id, status='pending',
        ), None

    @action(detail=False, methods=['post'])
    def award(self, request):
        """Award a CRM (data) gift package to a user"""
        serializer = AwardCRMGiftSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_id = serializer.validated_data['user_id']
        package_id = serializer.validated_data['package_id']
        trigger_source = serializer.validated_data.get('trigger_source', 'manual')
        campaign_id = serializer.validated_data.get('campaign_id')

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        phone_number = getattr(getattr(user, 'profile', None), 'phone_number', None)
        if not phone_number:
            return Response({'error': 'User has no phone number'}, status=status.HTTP_400_BAD_REQUEST)
        phone_number = _normalize_local_phone(phone_number)

        try:
            package = CRMGiftPackage.objects.get(id=package_id, is_active=True)
        except CRMGiftPackage.DoesNotExist:
            return Response({'error': 'Package not found or inactive'}, status=status.HTTP_404_NOT_FOUND)

        if user.profile.level < package.min_level:
            return Response(
                {'error': f'User level {user.profile.level} below required level {package.min_level}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        transaction, error = self._check_and_create_crm_transaction(
            user=user, phone_number=phone_number, package=package,
            trigger_source=trigger_source, campaign_id=campaign_id,
        )
        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)

        success, message, response_data = CRMService.send_gift(
            service_number_b=phone_number, offering_id=package.offering_id,
            charge_amount=float(package.charge_amount),
            access_user=getattr(settings, 'CRM_ACCESS_USER', ''),
            access_pwd=getattr(settings, 'CRM_ACCESS_PASSWORD', ''),
        )

        if success:
            transaction.mark_success(response_data.get('ret_code', '0'), message)
        else:
            transaction.mark_failed(response_data.get('ret_code', 'ERROR'), message)

        CRMGiftAuditLog.objects.create(
            transaction=transaction, action='award', performed_by=request.user,
            details=f'Awarded {package.name} to {user.username}: {message}', ip_address=_get_client_ip(request),
        )

        return Response(
            CRMGiftTransactionSerializer(transaction).data,
            status=status.HTTP_201_CREATED if success else status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=False, methods=['post'])
    def award_by_phone(self, request):
        """Award a CRM (data) gift by phone number (for external integrations)"""
        phone_number = request.data.get('phone_number')
        offering_id = request.data.get('offering_id')
        charge_amount = request.data.get('charge_amount')
        trigger_source = request.data.get('trigger_source', 'external_api')

        if not all([phone_number, offering_id, charge_amount]):
            return Response(
                {'error': 'phone_number, offering_id, and charge_amount are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        phone_number = _normalize_local_phone(phone_number)
        user = User.objects.filter(profile__phone_number=phone_number).first()

        transaction = CRMGiftTransaction.objects.create(
            user=user, phone_number=phone_number, offering_id=offering_id,
            transaction_id=CRMService.generate_transaction_id(), charge_amount=charge_amount,
            trigger_source=trigger_source, status='pending',
        )

        success, message, response_data = CRMService.send_gift(
            service_number_b=phone_number, offering_id=offering_id, charge_amount=float(charge_amount),
            access_user=getattr(settings, 'CRM_ACCESS_USER', ''),
            access_pwd=getattr(settings, 'CRM_ACCESS_PASSWORD', ''),
        )

        if success:
            transaction.mark_success(response_data.get('ret_code', '0'), message)
        else:
            transaction.mark_failed(response_data.get('ret_code', 'ERROR'), message)

        CRMGiftAuditLog.objects.create(
            transaction=transaction, action='award',
            performed_by=request.user if request.user.is_authenticated else None,
            details=f'External award to {phone_number}: {message}', ip_address=_get_client_ip(request),
        )

        return Response(
            CRMGiftTransactionSerializer(transaction).data,
            status=status.HTTP_201_CREATED if success else status.HTTP_400_BAD_REQUEST,
        )

    def _resolve_current_winners(self, selection_type, campaign_id):
        """Winners of the most recent formal WinnerSelection for this type,
        falling back to the current period's Leaderboard if none exists yet.
        Returns a list of (user, extra) or a SelectedWinner queryset, plus
        the WinnerSelection used (or None for the leaderboard fallback)."""
        selection_query = WinnerSelection.objects.filter(selection_type=selection_type).select_related('campaign')
        if campaign_id:
            selection_query = selection_query.filter(campaign_id=campaign_id)
        latest_selection = selection_query.order_by('-created_at').first()

        if latest_selection:
            winners = SelectedWinner.objects.filter(selection=latest_selection).select_related('user', 'selection')
            return list(winners), latest_selection

        now = timezone.now()
        period_start, _period_end = _period_bounds(selection_type, now)

        leaderboard_query = Leaderboard.objects.filter(period_type=selection_type, period_start=period_start)
        if campaign_id:
            leaderboard_query = leaderboard_query.filter(campaign_id=campaign_id)
        latest_leaderboard = leaderboard_query.order_by('-created_at').first()

        if not latest_leaderboard:
            return [], None

        entries = LeaderboardEntry.objects.filter(leaderboard=latest_leaderboard).select_related('user').order_by('rank')
        return list(entries), None

    @action(detail=False, methods=['post'])
    def award_campaign_winners(self, request):
        """Award CRM (data) gifts to campaign winners by selection type (daily, weekly, monthly, grand)"""
        selection_type = request.data.get('selection_type')
        campaign_id = request.data.get('campaign_id')
        package_id = request.data.get('package_id')

        if not all([selection_type, package_id]):
            return Response({'error': 'selection_type and package_id are required'}, status=status.HTTP_400_BAD_REQUEST)

        valid_types = ['daily', 'weekly', 'monthly', 'grand']
        if selection_type not in valid_types:
            return Response({'error': f'Invalid selection_type. Must be one of: {", ".join(valid_types)}'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            package = CRMGiftPackage.objects.get(id=package_id, is_active=True)
        except CRMGiftPackage.DoesNotExist:
            return Response({'error': 'Package not found or inactive'}, status=status.HTTP_404_NOT_FOUND)

        winners, latest_selection = self._resolve_current_winners(selection_type, campaign_id)
        if not winners:
            return Response({'error': f'No winners found for selection_type={selection_type}'}, status=status.HTTP_404_NOT_FOUND)

        results = {'total_winners': len(winners), 'successful': 0, 'failed': 0, 'skipped': 0, 'errors': []}

        for winner in winners:
            user = winner.user
            phone_number = getattr(getattr(user, 'profile', None), 'phone_number', None)
            if not phone_number:
                results['skipped'] += 1
                results['errors'].append({'user': user.username, 'reason': 'No phone number'})
                continue
            phone_number = _normalize_local_phone(phone_number)

            if user.profile.level < package.min_level:
                results['skipped'] += 1
                results['errors'].append({'user': user.username, 'reason': f'Level {user.profile.level} below required {package.min_level}'})
                continue

            is_eligible, current_wins, max_wins = WinnerFrequencyRecord.check_frequency_eligibility(
                user, selection_type, latest_selection.campaign if latest_selection else None,
            )
            if not is_eligible:
                results['skipped'] += 1
                results['errors'].append({
                    'user': user.username,
                    'reason': f'Already won {selection_type} {current_wins} times (max: {max_wins}) in this period',
                })
                continue

            transaction, error = self._check_and_create_crm_transaction(
                user=user, phone_number=phone_number, package=package,
                trigger_source=f'campaign_{selection_type}',
                campaign_id=campaign_id or (latest_selection.campaign_id if latest_selection else None),
            )
            if error:
                results['skipped'] += 1
                results['errors'].append({'user': user.username, 'reason': error})
                continue

            success, message, response_data = CRMService.send_gift(
                service_number_b=phone_number, offering_id=package.offering_id,
                charge_amount=float(package.charge_amount),
                access_user=getattr(settings, 'CRM_ACCESS_USER', ''),
                access_pwd=getattr(settings, 'CRM_ACCESS_PASSWORD', ''),
            )

            if success:
                transaction.mark_success(response_data.get('ret_code', '0'), message)
                results['successful'] += 1
                WinnerFrequencyRecord.record_win(
                    user=user, winner_type=selection_type,
                    campaign=latest_selection.campaign if latest_selection else None, selection=latest_selection,
                )
            else:
                transaction.mark_failed(response_data.get('ret_code', 'ERROR'), message)
                results['failed'] += 1
                results['errors'].append({'user': user.username, 'reason': message})

            CRMGiftAuditLog.objects.create(
                transaction=transaction, action='award', performed_by=request.user,
                details=f'Campaign winner award ({selection_type}): {message}', ip_address=_get_client_ip(request),
            )

        return Response(results)

    def _initiate_b2c_winner_gift(self, *, user, winner_type, amount, gift_package):
        """Create a WinnerGiftTransaction and initiate its B2C payment.
        Left 'processing' on a successful initiation -- see module
        docstring for why 'success' is only ever set by the webhook."""
        phone_number = getattr(getattr(user, 'profile', None), 'phone_number', None)
        if not phone_number:
            return None, 'No phone number'
        phone_number = _normalize_local_phone(phone_number)

        transaction = WinnerGiftTransaction.objects.create(
            winner=user, winner_type=winner_type, gift_package=gift_package, amount=amount,
            payment_method='telebirr_b2c', receiver_msisdn=phone_number, status='processing',
        )

        try:
            result = telebirr_direct_debit_service.initiate_b2c_payment(
                receiver_msisdn=phone_number, amount=amount, currency='ETB',
                reason_type='Winner gift payout', remark=f'{winner_type.capitalize()} Winner Gift',
                reference_data={'winner_gift_transaction_id': str(transaction.id)},
                initiator_type='org_operator',
            )
        except Exception as e:
            transaction.mark_failed(str(e))
            return transaction, str(e)

        if result.get('success'):
            transaction.originator_conversation_id = result.get('originator_conversation_id') or ''
            transaction.conversation_id = result.get('conversation_id') or ''
            transaction.save(update_fields=['originator_conversation_id', 'conversation_id', 'updated_at'])
            return transaction, None

        transaction.mark_failed(result.get('error', 'Unknown error'))
        return transaction, result.get('error', 'Unknown error')

    @action(detail=False, methods=['post'])
    def send_b2c_gift(self, request):
        """Initiate a Telebirr B2C cash gift to a single winner. Only
        initiates the payout -- telebirr_b2c_webhook confirms completion."""
        user_id = request.data.get('user_id')
        amount = request.data.get('amount', 1000)
        winner_type = request.data.get('winner_type', 'weekly')

        if not user_id:
            return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if not user.profile.is_telebirr_user():
            return Response({'error': 'User is not a Telebirr user'}, status=status.HTTP_400_BAD_REQUEST)

        gift_package, _created = WinnerGiftPackage.objects.get_or_create(
            winner_type=winner_type,
            defaults={'gift_type': 'cash', 'payment_method': 'telebirr_b2c', 'amount': Decimal(str(amount)), 'is_active': True},
        )

        transaction, error = self._initiate_b2c_winner_gift(
            user=user, winner_type=winner_type, amount=Decimal(str(amount)), gift_package=gift_package,
        )
        if transaction is None:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
        if error:
            return Response({'success': False, 'error': error}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': True,
            'transaction_id': str(transaction.id),
            'status': transaction.status,
            'message': 'B2C gift payout initiated -- awaiting Telebirr confirmation',
        })

    @action(detail=False, methods=['post'])
    def send_b2c_bulk(self, request):
        """Initiate Telebirr B2C cash gifts to all winners of a type."""
        winner_type = request.data.get('winner_type', 'weekly')
        amount = request.data.get('amount', 1000)

        valid_types = ['daily', 'weekly', 'monthly', 'grand']
        if winner_type not in valid_types:
            return Response({'error': f'Invalid winner_type. Must be one of: {", ".join(valid_types)}'}, status=status.HTTP_400_BAD_REQUEST)

        winners, _latest_selection = self._resolve_current_winners(winner_type, None)

        results = {'total_winners': len(winners), 'initiated': 0, 'failed': 0, 'skipped': 0, 'errors': []}

        gift_package, _created = WinnerGiftPackage.objects.get_or_create(
            winner_type=winner_type,
            defaults={'gift_type': 'cash', 'payment_method': 'telebirr_b2c', 'amount': Decimal(str(amount)), 'is_active': True},
        )

        for winner in winners:
            user = winner.user
            if not user.profile.is_telebirr_user():
                results['skipped'] += 1
                results['errors'].append({'user': user.username, 'reason': 'Not a Telebirr user'})
                continue

            transaction, error = self._initiate_b2c_winner_gift(
                user=user, winner_type=winner_type, amount=Decimal(str(amount)), gift_package=gift_package,
            )
            if transaction is None or error:
                results['failed'] += 1
                results['errors'].append({'user': user.username, 'reason': error})
                continue
            results['initiated'] += 1

        return Response(results)

    @action(detail=False, methods=['get'])
    def campaign_winners(self, request):
        """Real-time-scored campaign winners for a selection type/period,
        kept in sync with the frontend leaderboard's own calculation."""
        selection_type = request.query_params.get('selection_type')
        campaign_id = request.query_params.get('campaign_id')
        date_filter = request.query_params.get('date')

        if not selection_type:
            return Response({'error': 'selection_type parameter is required'}, status=status.HTTP_400_BAD_REQUEST)

        valid_types = ['daily', 'weekly', 'monthly', 'grand']
        if selection_type not in valid_types:
            return Response({'error': f'Invalid selection_type. Must be one of: {", ".join(valid_types)}'}, status=status.HTTP_400_BAD_REQUEST)

        from datetime import datetime

        from api.models.campaign_extended import PostScore
        from api.models.core import Comment, Vote
        from api.services.scoring.engine import CampaignScoringEngine

        now = timezone.now()
        target_dt = now
        if date_filter:
            try:
                parsed_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
                target_dt = timezone.make_aware(datetime.combine(parsed_date, datetime.min.time()), timezone.get_current_timezone())
            except ValueError:
                return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        period_start, period_end = _period_bounds(selection_type, target_dt)
        start_date = period_start.date()

        campaign_filter = {'campaign_id': campaign_id} if campaign_id else {}
        if selection_type == 'daily':
            posts_qs = PostScore.objects.filter(created_at__date=start_date, **campaign_filter).exclude(moderation_status='rejected')
        elif selection_type == 'monthly':
            posts_qs = PostScore.objects.filter(created_at__year=target_dt.year, created_at__month=target_dt.month, **campaign_filter).exclude(moderation_status='rejected')
        else:  # weekly, grand
            posts_qs = PostScore.objects.filter(created_at__gte=period_start, **campaign_filter).exclude(moderation_status='rejected')

        user_ids = list(posts_qs.values_list('user_id', flat=True).distinct())
        if not user_ids:
            return Response({
                'selection_type': selection_type, 'campaign_id': campaign_id, 'date_filter': date_filter,
                'count': 0, 'winners': [], 'message': f'No participants found for {selection_type} period',
            })

        likes_weight, comments_weight, shares_weight, gifts_weight = 1.0, 2.0, 3.0, 5.0
        if campaign_id:
            try:
                campaign = Campaign.objects.get(id=campaign_id)
                engine = CampaignScoringEngine(campaign)
                config = engine.type_config
                engagement_weights = config.get('phase1_qualification', {}) if campaign.campaign_type == 'grand' else config.get('engagement', {})
                likes_weight = engagement_weights.get('likes_weight', 1.0)
                comments_weight = engagement_weights.get('comments_weight', 2.0)
                shares_weight = engagement_weights.get('shares_weight', 3.0)
                gifts_weight = engagement_weights.get('gifts_weight', 5.0)
            except Campaign.DoesNotExist:
                pass

        entries_data = []
        for user in User.objects.filter(id__in=user_ids):
            reel_ids = list(posts_qs.filter(user=user).values_list('reel_id', flat=True))
            if not reel_ids:
                continue

            total_likes = Vote.objects.filter(reel_id__in=reel_ids).count()
            total_comments = Comment.objects.filter(reel_id__in=reel_ids).count()
            total_shares = 0
            total_gifters = GiftTransaction.objects.filter(reel_id__in=reel_ids).count()

            calculated_score = (
                total_likes * likes_weight + total_comments * comments_weight
                + total_shares * shares_weight + total_gifters * gifts_weight
            )

            entries_data.append({
                'user_id': user.id, 'username': user.username,
                'phone_number': getattr(getattr(user, 'profile', None), 'phone_number', None),
                'total_score': float(calculated_score), 'post_count': len(reel_ids),
                'likes_count': total_likes, 'comments_count': total_comments, 'gifts_count': total_gifters,
            })

        entries_data.sort(key=lambda x: x['total_score'], reverse=True)
        limits = {'daily': 50, 'weekly': 10, 'monthly': 5, 'grand': 3}
        entries_data = entries_data[:limits.get(selection_type, 50)]

        winners_data = []
        for idx, entry in enumerate(entries_data):
            user = User.objects.get(id=entry['user_id'])
            winners_data.append({
                'id': f'rt-{entry["user_id"]}', 'user_id': entry['user_id'], 'username': entry['username'],
                'phone_number': entry['phone_number'], 'rank': idx + 1, 'final_score': entry['total_score'],
                'selection_method': 'Real-time Leaderboard', 'campaign_id': campaign_id,
                'campaign_title': Campaign.objects.get(id=campaign_id).title if campaign_id else 'All Campaigns',
                'selection_type': selection_type, 'selection_date': now, 'created_at': now, 'is_from_realtime': True,
                'post_count': entry['post_count'], 'likes_count': entry['likes_count'],
                'comments_count': entry['comments_count'], 'gifts_count': entry['gifts_count'],
                'is_telebirr_user': user.profile.is_telebirr_user() if hasattr(user, 'profile') else False,
            })

        return Response({
            'selection_type': selection_type, 'campaign_id': campaign_id, 'date_filter': date_filter,
            'count': len(winners_data), 'winners': winners_data, 'source': 'realtime_calculation',
            'period_start': period_start, 'period_end': period_end,
        })


class CRMGiftAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Viewset for CRM audit logs (admin only)"""
    permission_classes = [HasAdminPermission]
    required_permission = 'view_gifts'
    serializer_class = CRMGiftAuditLogSerializer

    def get_queryset(self):
        queryset = CRMGiftAuditLog.objects.select_related('transaction', 'performed_by')

        transaction_id = self.request.query_params.get('transaction_id')
        if transaction_id:
            queryset = queryset.filter(transaction_id=transaction_id)

        action_filter = self.request.query_params.get('action')
        if action_filter:
            queryset = queryset.filter(action=action_filter)

        return queryset.order_by('-created_at')


def _period_bounds(selection_type, at):
    """(period_start, period_end) for a daily/weekly/monthly/grand tier at
    the given instant. Shared by campaign_winners, award_campaign_winners's
    leaderboard fallback, and send_b2c_bulk's winner lookup."""
    from datetime import timedelta

    if selection_type == 'daily':
        period_start = at.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=1)
    elif selection_type == 'weekly':
        period_start = (at - timedelta(days=at.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=7)
    elif selection_type == 'monthly':
        period_start = at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_end = (period_start + timedelta(days=32)).replace(day=1)
    else:  # grand
        period_end = at
        period_start = at - timedelta(days=180)
    return period_start, period_end
