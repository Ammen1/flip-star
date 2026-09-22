import logging
import re
import string
import traceback
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, F, OuterRef, Prefetch, Q, Value
from django.db.models.functions import Greatest
from django.http import Http404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.models import (
    Block,
    Comment,
    Competition,
    Draft,
    Follow,
    ModerationAction,
    Notification,
    NotificationPreference,
    Quest,
    Reel,
    Report,
    SavedPost,
    Subscription,
    UserProfile,
    UserQuest,
    Vote,
    Winner,
)
from api.models.campaign import CampaignNotification
from api.serializers.core import (
    BlockSerializer,
    CommentSerializer,
    CompetitionSerializer,
    DraftSerializer,
    FollowSerializer,
    NotificationPreferenceSerializer,
    QuestSerializer,
    ReelSerializer,
    RegisterSerializer,
    ReportSerializer,
    SubscriptionSerializer,
    UserProfileSerializer,
    UserQuestSerializer,
    UserSerializer,
    WinnerSerializer,
)
from api.services.coin_purchase import insufficient_coins_payload
from api.services.subscription_access import (
    SUBSCRIPTION_REQUIRED_CODE,
    has_active_subscription,
    payment_pending_payload,
    subscription_required_payload,
)
from api.services.usernames import (
    is_duplicate_username_error,
)
from api.services.usernames import (
    is_taken as username_is_taken,
)
from api.services.usernames import (
    taken_payload as username_taken_payload,
)
from common.permissions import IsOwnerOrStaffOrReadOnly
from common.security import EncryptedPayloadMixin, encrypted_endpoint, is_pin_too_weak
from common.throttling import (
    LoginAnonThrottle,
    LoginUserThrottle,
    MediaRefreshAnonThrottle,
    MediaRefreshUserThrottle,
    OtpSendAnonThrottle,
    OtpSendUserThrottle,
    OtpVerifyAnonThrottle,
    OtpVerifyUserThrottle,
    PasswordResetAnonThrottle,
    PasswordResetUserThrottle,
    PhoneLookupAnonThrottle,
    PhoneLookupUserThrottle,
    ReportUserThrottle,
    check_and_increment_failure,
    clear_failures,
    is_blocked,
)
from common.validators import lookup_variants, normalize_ethiopian_phone

logger = logging.getLogger(__name__)


# ── OTP / Phone helpers ────────────────────────────────────────────────────
def _generate_otp():
    import secrets as _secrets

    return ''.join(_secrets.choice(string.digits) for _ in range(6))


def _normalize_ethiopian_phone(phone):
    """Normalize to 251XXXXXXXXX (no +; the stored and SMPP form). Returns None if invalid.

    Delegates to the shared validator so the client and the API enforce one
    rule. The previous implementation checked only length and the first
    character, so values like ``9abcdefgh`` and ``251abcdefghi`` were accepted
    and stored as phone numbers.
    """
    return normalize_ethiopian_phone(phone)


@api_view(['POST'])
@permission_classes([AllowAny])
@encrypted_endpoint
def register(request):
    username = request.data.get('username')
    if username_is_taken(username):
        return Response(username_taken_payload(), status=status.HTTP_409_CONFLICT)

    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        try:
            user = serializer.save()
        except IntegrityError as e:
            if is_duplicate_username_error(e):
                return Response(username_taken_payload(), status=status.HTTP_409_CONFLICT)
            raise
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {'user': UserSerializer(user).data, 'token': token.key}, status=status.HTTP_201_CREATED
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
@encrypted_endpoint
def login(request):
    if is_blocked(request, 'login', 6):
        return Response(
            {
                'error': 'Too many failed login attempts. Please try again in 10 minutes.',
                'attempts_remaining': 0,
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        return Response(
            {'error': 'Username and password required'}, status=status.HTTP_400_BAD_REQUEST
        )

    # Try to find user by username or email
    user = None
    try:
        # First try username
        user = User.objects.get(username=username)
        print(f'[LOGIN] Found user by username: {user.username} (id={user.id})')
    except User.DoesNotExist:
        # Then try email
        try:
            user = User.objects.get(email=username)
            print(f'[LOGIN] Found user by email: {user.username} (id={user.id})')
        except User.DoesNotExist:
            print(f'[LOGIN] User not found: {username}')
            pass

    if user:
        print(f'[LOGIN] User found: {user.username}, checking password...')
        print(f'[LOGIN] User has usable password: {user.has_usable_password()}')

        if user.check_password(password):
            clear_failures(request, 'login')
            token, _ = Token.objects.get_or_create(user=user)
            print(f'[LOGIN] Success - user: {user.username}')
            try:
                from api.models.admin import SystemLog

                ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
                if ip and ',' in ip:
                    ip = ip.split(',')[0].strip()
                SystemLog.objects.create(
                    log_type='security',
                    message=f'Successful login: {user.username}',
                    user=user,
                    ip_address=ip or None,
                    endpoint='/api/auth/login/',
                    details={'username': user.username, 'is_staff': user.is_staff},
                )
            except Exception:  # noqa: S110 – best-effort audit log; must not surface to the caller
                pass
            return Response({'user': UserSerializer(user).data, 'token': token.key})
        else:
            remaining = check_and_increment_failure(request, 'login', 6, 600)
            print(f'[LOGIN] Password check FAILED for user: {user.username}')
            if not user.has_usable_password():
                print('[LOGIN] User has no usable password, this might be a migration issue')
            try:
                from api.models.admin import SystemLog

                ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
                if ip and ',' in ip:
                    ip = ip.split(',')[0].strip()
                SystemLog.objects.create(
                    log_type='security',
                    message=f'Failed login attempt: {username}',
                    ip_address=ip or None,
                    endpoint='/api/auth/login/',
                    details={'attempted_username': username},
                )
            except Exception:  # noqa: S110 – best-effort audit log; must not surface to the caller
                pass
            if remaining == 0:
                return Response(
                    {
                        'error': 'Too many failed login attempts. Please try again in 10 minutes.',
                        'attempts_remaining': 0,
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            return Response(
                {'error': 'Invalid credentials', 'attempts_remaining': remaining},
                status=status.HTTP_401_UNAUTHORIZED,
            )
    else:
        remaining = check_and_increment_failure(request, 'login', 6, 600)
        print(f'[LOGIN] User not found for: {username}')
        try:
            from api.models.admin import SystemLog

            ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
            if ip and ',' in ip:
                ip = ip.split(',')[0].strip()
            SystemLog.objects.create(
                log_type='security',
                message=f'Login attempt with unknown user: {username}',
                ip_address=ip or None,
                endpoint='/api/auth/login/',
                details={'attempted_username': username},
            )
        except Exception:  # noqa: S110 – best-effort audit log; must not surface to the caller
            pass
        if remaining == 0:
            return Response(
                {
                    'error': 'Too many failed login attempts. Please try again in 10 minutes.',
                    'attempts_remaining': 0,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return Response(
            {'error': 'Invalid credentials', 'attempts_remaining': remaining},
            status=status.HTTP_401_UNAUTHORIZED,
        )


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetAnonThrottle, PasswordResetUserThrottle])
@encrypted_endpoint
def reset_password(request):
    """Reset password for a user by email - temporary fix for password hash issues"""
    email = request.data.get('email')
    new_password = request.data.get('new_password')

    if not email or not new_password:
        return Response(
            {'error': 'Email and new_password required'}, status=status.HTTP_400_BAD_REQUEST
        )

    too_weak, reason = is_pin_too_weak(new_password)
    if too_weak:
        return Response({'error': reason}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=email)
        user.set_password(new_password)
        user.save()
        # Invalidate any existing auth tokens so old sessions on other
        # devices/browsers cannot continue after a password reset -- same
        # invalidation change_password already does below.
        Token.objects.filter(user=user).delete()
        print(f'[RESET] Password reset for user: {user.username}')
        return Response({'message': 'Password reset successful. You can now login.'})
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([AllowAny])
def privacy_policy(request):
    """Return the FlipStar privacy policy content."""
    policy_content = {
        'version': '2.1',
        'effective_date': 'May 2026',
        'data_controller': 'Ethio telecom and SkykinTechnologies PLC',
        'data_jurisdiction': 'Federal Democratic Republic of Ethiopia',
        'hosting': 'Ethio telecom InfraCloud (in-country)',
        'data_collected': {
            'account_identity': 'Ethio telecom mobile number, full name',
            'subscription_billing': 'Subscription plan, billing timestamps, payment status, telebirr transaction references',
            'platform_activity': 'Uploads (Flips), votes, comments, shares, gifts sent/received, coins, points balance, login timestamps',
            'content_data': 'Videos, photos, captions, hashtags, content moderation results',
            'prize_identity': 'National ID or passport number (only for prize winners)',
            'device_technical': 'Device type, OS version, app version, IP address (stripped from content before storage)',
        },
        'data_usage': [
            'Service provision - account management, subscription processing, feature access',
            'Billing & payments - subscription charges, coin purchases, prize delivery via telebirr',
            'Platform operations - Engagement Score calculation, leaderboards, competition prizes',
            'SMS notifications - subscription confirmation, auto-renewal alerts, prize notifications',
            'Content moderation - AI and manual review for brand safety and legal compliance',
            'Promotion & marketing - user name, photos, and video images may be used for promotional purposes',
            'Fraud prevention - detecting botting, vote manipulation, self-gifting',
            'Support - responding to enquiries via in-app support, SMS, email, WhatsApp, Telegram',
        ],
        'data_storage_security': {
            'in_country_hosting': 'Exclusively on Ethio telecom InfraCloud within Ethiopia',
            'encrypted_storage': 'Mobile phone number stored in encrypted form, never displayed publicly',
            'metadata_stripping': 'All personal metadata (GPS, device info) automatically stripped from uploads',
            'secure_transactions': 'Financial transactions processed through secure telebirr infrastructure',
            'access_controls': 'Only authorised personnel on need-to-know basis',
        },
        'data_sharing': {
            'ethio_telecom': 'Billing, subscriber verification, prize delivery, SMS notifications',
            'skykin_technologies': 'Platform operation, content hosting, app maintenance, moderation',
            'law_enforcement': 'When required by Ethiopian law or court order',
            'third_parties': 'No selling, renting, or sharing with unrelated third parties for marketing',
        },
        'user_generated_content': {
            'licence': 'Non-exclusive, royalty-free, worldwide licence to host, store, reproduce, and promote content',
            'promotional_use': 'Name, initials, photos, and video images may be used for promotional purposes',
            'ownership': 'Users retain ownership of original content',
            'moderation': 'All competition content reviewed for brand safety before rewards',
        },
        'metadata_location': {
            'automatic_removal': 'All personal metadata (GPS, device info) automatically removed from uploads',
            'location_inference': 'Approximate location may be inferred from network registration for verification only',
        },
        'cookies_tracking': {
            'session_cookies': 'Used on web portal to maintain logged-in session',
            'functional_storage': 'App stores session tokens and preferences locally',
            'analytics': 'Basic usage analytics aggregated and not linked to individuals',
            'no_third_party_trackers': 'No third-party advertising trackers or data selling',
        },
        'user_rights': {
            'access': 'Request copy of personal data',
            'correction': 'Request correction of inaccurate data',
            'deletion': 'Request deletion of account and data (subject to legal obligations)',
            'unsubscription': 'Cancel subscription via SMS (STOP1/STOP2/STOP3), App, or telebirr',
            'objection': 'Object to promotional use of data',
        },
        'contact_channels': {
            'in_app_support': 'Profile → Help & Support → Contact Us',
            'email': 'support@flipstar.et',
            'ethio_telecom_email': '994@ethionet.et',
            'sms': '9286',
            'whatsapp': '+251 99 400 0000',
            'telegram': 'https://t.me/ethio_telecom',
        },
        'data_retention': {
            'digital_coins': 'Valid while account active; expire 30 days after unsubscription',
            'earned_points': 'Forfeited after 180 days of account inactivity',
            'unclaimed_prizes': 'Expire 30 days after winner notification',
            'account_data': 'Retained while active; deleted upon verified deletion request',
            'transaction_records': 'Retained as required by Ethiopian financial regulations',
        },
        'children_privacy': {
            'age_restriction': '18 years and above only',
            'no_under_18': 'Do not knowingly collect data from under 18',
            'report_underage': 'Contact support@flipstar.et if under 18 has registered',
        },
        'governing_law': 'Federal Democratic Republic of Ethiopia (FDRE)',
    }
    return Response(policy_content)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def change_password(request):
    """Change password for authenticated user"""
    current_password = request.data.get('current_password')
    new_password = request.data.get('new_password')

    if not current_password or not new_password:
        return Response(
            {'error': 'current_password and new_password required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # App uses 6-digit numeric PIN as the password.
    too_weak, reason = is_pin_too_weak(new_password)
    if too_weak:
        return Response({'error': reason}, status=status.HTTP_400_BAD_REQUEST)

    user = request.user
    if not user.check_password(current_password):
        return Response(
            {'error': 'Current password is incorrect'}, status=status.HTTP_400_BAD_REQUEST
        )

    user.set_password(new_password)
    user.save()

    # Delete old token to force re-login
    Token.objects.filter(user=user).delete()

    return Response({'message': 'Password changed successfully. Please login again.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def delete_account(request):
    """Delete authenticated user's account, removing stored media files first.

    Deleting the User row cascades to Reel/Message rows in the DB, but a
    cascade never touches the storage backend -- without deleting each
    FileField explicitly first, every photo/video/thumbnail this user ever
    uploaded is orphaned in S3/local storage forever.
    """
    from api.models.messaging import Message

    user = request.user
    username = user.username

    deleted_summary = {
        'reels': Reel.objects.filter(user=user).count(),
        'messages_sent': Message.objects.filter(sender=user).count(),
    }

    profile = getattr(user, 'profile', None)
    if profile:
        for file_field_name in ('profile_photo', 'avatar'):
            file_field = getattr(profile, file_field_name, None)
            if file_field:
                try:
                    file_field.delete(save=False)
                except Exception as exc:
                    print(
                        f'[DELETE ACCOUNT] Failed to delete profile file {file_field_name}: {exc}'
                    )

    for reel in Reel.objects.filter(user=user).only('media', 'image', 'thumbnail'):
        for file_field_name in ('media', 'image', 'thumbnail'):
            file_field = getattr(reel, file_field_name, None)
            if file_field:
                try:
                    file_field.delete(save=False)
                except Exception as exc:
                    print(
                        f'[DELETE ACCOUNT] Failed to delete reel file {file_field_name} for reel {reel.id}: {exc}'
                    )

    for message in Message.objects.filter(sender=user).exclude(media='').only('media'):
        if message.media:
            try:
                message.media.delete(save=False)
            except Exception as exc:
                print(f'[DELETE ACCOUNT] Failed to delete message media {message.id}: {exc}')

    # Delete authentication token
    try:
        Token.objects.filter(user=user).delete()
    except Exception:  # noqa: S110 – token deletion is best-effort during account deletion
        pass

    # Delete user (this cascades to related objects)
    user.delete()

    return Response(
        {
            'message': f'Account {username} has been deleted successfully.',
            'deleted_summary': deleted_summary,
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def download_data(request):
    """Generate and return user's data as JSON"""
    user = request.user
    from api.models import Comment, Follow, Reel, UserProfile

    try:
        profile = UserProfile.objects.get(user=user)
    except UserProfile.DoesNotExist:
        profile = None

    # Collect user data
    user_data = {
        'user': {
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'date_joined': user.date_joined.isoformat(),
        },
        'profile': {
            'bio': profile.bio if profile else None,
            'phone_number': profile.phone_number if profile else None,
            'level': profile.level if profile else 1,
            'xp': profile.xp if profile else 0,
        }
        if profile
        else None,
        'reels': list(
            Reel.objects.filter(user=user).values('id', 'caption', 'hashtags', 'created_at')
        ),
        'comments': list(Comment.objects.filter(user=user).values('id', 'text', 'created_at')),
        'followers': list(Follow.objects.filter(following=user).values('follower__username')),
        'following': list(Follow.objects.filter(follower=user).values('following__username')),
    }

    return Response(user_data)


# ── OTP-less Login for SMS Subscribers ─────────────────────────────────────────


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([LoginAnonThrottle, LoginUserThrottle])
@encrypted_endpoint
def login_with_phone(request):
    """OTP-less login for users with active SMS subscriptions"""
    from api.models.subscription import SubscriptionPlan as UserSubscription

    phone = request.data.get('phone', '').strip()
    password = request.data.get('password', '').strip()

    print(f'[LOGIN WITH PHONE DEBUG] login_with_phone called - phone: {phone}')

    if not phone or not password:
        print('[LOGIN WITH PHONE DEBUG] Missing phone or password')
        return Response(
            {'error': 'Phone and password required'}, status=status.HTTP_400_BAD_REQUEST
        )

    # Normalize phone number
    phone = _normalize_ethiopian_phone(phone)
    print(f'[LOGIN WITH PHONE DEBUG] Normalized phone: {phone}')
    if not phone:
        print('[LOGIN WITH PHONE DEBUG] Invalid phone format')
        return Response(
            {'error': 'Invalid Ethiopian phone number'}, status=status.HTTP_400_BAD_REQUEST
        )

    # 1. Check active SMS subscription (primary path)
    print('[LOGIN WITH PHONE DEBUG] Checking for SMS subscription')
    sms_subscription = UserSubscription.objects.filter(
        onevas_phone_number=phone, status='active', subscription_source='sms'
    ).first()

    if sms_subscription and sms_subscription.user:
        user = sms_subscription.user
        print(f'[LOGIN WITH PHONE DEBUG] Found via subscription, user: {user.username}')
        if user.check_password(password):
            token, _ = Token.objects.get_or_create(user=user)
            return Response({'user': UserSerializer(user).data, 'token': token.key})
        if not user.has_usable_password():
            return _pin_not_set_response(phone)
        return Response({'error': 'Invalid password'}, status=status.HTTP_401_UNAUTHORIZED)

    if sms_subscription and not sms_subscription.user:
        return Response(
            {
                'error': 'User account not created yet',
                'requires_registration': True,
                'phone': phone,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 2. Fallback: find user by UserProfile.phone_number (registered via subscription OTP)
    print('[LOGIN WITH PHONE DEBUG] No subscription found, checking UserProfile.phone_number')
    try:
        profile = UserProfile.objects.get(phone_number=phone)
        user = profile.user
        print(f'[LOGIN WITH PHONE DEBUG] Found via UserProfile: {user.username}')
        if user.check_password(password):
            token, _ = Token.objects.get_or_create(user=user)
            return Response({'user': UserSerializer(user).data, 'token': token.key})
        if not user.has_usable_password():
            return _pin_not_set_response(phone)
        return Response({'error': 'Invalid password'}, status=status.HTTP_401_UNAUTHORIZED)
    except UserProfile.DoesNotExist:
        pass

    print('[LOGIN WITH PHONE DEBUG] Phone not found anywhere')
    return Response(
        {'error': 'No account found for this phone number. Please subscribe and register first.'},
        status=status.HTTP_400_BAD_REQUEST,
    )


# ── Phone OTP Registration ─────────────────────────────────────────────────


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([OtpSendAnonThrottle, OtpSendUserThrottle])
@encrypted_endpoint
def send_phone_otp(request):
    """Step 1 of registration: validate Ethiopian phone and send a 6-digit OTP by SMS (TIMWE)."""
    from api.services.otp import OTPService

    phone_raw = request.data.get('phone', '').strip()
    print(f'[OTP DEBUG] send_phone_otp called with phone_raw: {phone_raw}')

    if not phone_raw:
        print('[OTP DEBUG] No phone number provided')
        return Response({'error': 'Phone number required'}, status=status.HTTP_400_BAD_REQUEST)

    phone = _normalize_ethiopian_phone(phone_raw)
    print(f'[OTP DEBUG] Normalized phone: {phone}')

    if not phone:
        print('[OTP DEBUG] Invalid phone number format')
        return Response(
            {'error': 'Invalid Ethiopian phone number. Use format 09XXXXXXXX or +251XXXXXXXXX'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if UserProfile.objects.filter(phone_number=phone).exists():
        print(f'[OTP DEBUG] Phone {phone} already registered')
        return Response(
            {'error': 'This phone number is already registered'}, status=status.HTTP_400_BAD_REQUEST
        )

    print(f'[OTP DEBUG] Calling OTPService.send_otp for phone: {phone}')
    success, message = OTPService.send_otp(phone)
    print(f'[OTP DEBUG] OTPService result - success: {success}, message: {message}')

    if success:
        # In dev/local mode return the OTP code so frontend can show it (SMS not required)
        from django.conf import settings as _settings

        dev_code = None
        if _settings.DEBUG:
            from django.core.cache import cache as _cache

            _data = _cache.get(f'otp:{phone}')
            if _data:
                dev_code = _data.get('code')
                # i want to add on response otp number
        resp = {'message': message, 'phone': phone, 'otp': dev_code}
        if dev_code:
            resp['dev_code'] = dev_code
        return Response(resp)
    else:
        return Response({'error': message}, status=status.HTTP_429_TOO_MANY_REQUESTS)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([OtpVerifyAnonThrottle, OtpVerifyUserThrottle])
@encrypted_endpoint
def verify_phone_otp(request):
    """Step 2: verify the OTP entered by the user."""
    from api.services.otp import OTPService

    phone = request.data.get('phone', '').strip()
    code = request.data.get('code', '').strip()
    print(f'[OTP DEBUG] verify_phone_otp called - phone: {phone}, code: {code}')

    if not phone or not code:
        print('[OTP DEBUG] verify_phone_otp failed - missing phone or code')
        return Response({'error': 'Phone and code required'}, status=status.HTTP_400_BAD_REQUEST)

    # send_phone_otp stores the code under the normalized number (251XXXXXXXXX),
    # so verification has to normalize too or the lookup misses and every code
    # reads as "expired or not found". forgot_password_phone_verify already
    # does this; these two endpoints were missed.
    normalized = _normalize_ethiopian_phone(phone)
    if not normalized:
        return Response(
            {'error': 'Invalid Ethiopian phone number'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    phone = normalized

    # Verify OTP using OTPService
    print('[OTP DEBUG] Calling OTPService.verify_otp')
    success, message = OTPService.verify_otp(phone, code)
    print(f'[OTP DEBUG] OTPService.verify_otp result - success: {success}, message: {message}')

    if success:
        return Response({'message': message, 'phone': phone})
    else:
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([OtpSendAnonThrottle, OtpSendUserThrottle])
def send_login_otp(request):
    """Send an OTP for passwordless login of an existing user (including
    Telebirr SuperApp users who registered via subscription, not the phone
    registration flow above)."""
    from django.conf import settings as _settings
    from django.core.cache import cache

    from api.services.otp import OTPService
    from api.views.subscription import mask_phone_number

    phone_raw = request.data.get('phone', '').strip()
    if not phone_raw:
        return Response({'error': 'Phone number required'}, status=status.HTTP_400_BAD_REQUEST)

    phone = _normalize_ethiopian_phone(phone_raw)
    if not phone:
        return Response(
            {'error': 'Invalid Ethiopian phone number. Use format 09XXXXXXXX or +251XXXXXXXXX'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Unlike send_phone_otp (registration), an existing user is exactly who
    # this endpoint is for -- do not reject on UserProfile match.
    user_exists = UserProfile.objects.filter(phone_number=phone).exists()

    # No credential of any kind goes with the code. This used to resolve a
    # OneVAS application key and product number from the subscriber's tier;
    # OneVAS has been removed and TIMWE needs neither. Anything the caller
    # sends in the body besides the phone is ignored, as before.
    success, message = OTPService.send_otp(phone, action='login')

    if not success:
        return Response({'error': message}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    resp = {'message': message, 'phone': mask_phone_number(phone), 'user_exists': user_exists}
    if _settings.DEBUG:
        cached = cache.get(f'otp:{phone}')
        if cached:
            resp['dev_code'] = cached.get('code')
    return Response(resp)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([OtpVerifyAnonThrottle, OtpVerifyUserThrottle])
def login_with_otp(request):
    """Passwordless login for an existing user, verified by OTP. Falls back
    to an active Telebirr SuperApp subscription (telebirr_phone_number) when
    no UserProfile has claimed this number yet -- the user paid through
    Telebirr but never went through phone registration."""
    from api.models.subscription import SubscriptionPlan as UserSubscription
    from api.services.otp import OTPService

    phone_raw = request.data.get('phone', '').strip()
    code = request.data.get('code', '').strip()
    if not phone_raw or not code:
        return Response({'error': 'Phone and code required'}, status=status.HTTP_400_BAD_REQUEST)

    phone = _normalize_ethiopian_phone(phone_raw)
    if not phone:
        return Response({'error': 'Invalid phone number'}, status=status.HTTP_400_BAD_REQUEST)

    success, message = OTPService.verify_otp(phone, code)
    if not success:
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = UserProfile.objects.get(phone_number=phone).user
    except UserProfile.DoesNotExist:
        phone_values = lookup_variants(phone)
        subscription = (
            UserSubscription.objects.filter(
                telebirr_phone_number__in=phone_values,
                payment_method='telebirr',
                status='active',
            )
            .filter(Q(end_date__isnull=True) | Q(end_date__gt=timezone.now()))
            .first()
        )
        if not (subscription and subscription.user):
            return Response(
                {'error': 'No account found. Please register first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = subscription.user

    token, _created = Token.objects.get_or_create(user=user)
    return Response({'token': token.key, 'user': UserSerializer(user).data})


@api_view(['POST'])
@permission_classes([AllowAny])
@encrypted_endpoint
def register_with_phone(request):
    """Step 3: create account after phone verified. Password must be exactly 6 digits."""
    from django.db import transaction

    from api.models.subscription import SubscriptionHistory, SubscriptionPayment
    from api.models.subscription import SubscriptionPlan as UserSubscription

    phone = request.data.get('phone', '').strip()
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '').strip()
    email = request.data.get('email', '').strip()
    skip_otp = request.data.get('skip_otp', False)  # Allow skipping OTP for SMS subscribers

    print(
        f'[REGISTRATION DEBUG] register_with_phone called - phone: {phone}, username: {username}, email: {email}, skip_otp: {skip_otp}'
    )

    if not phone or not username or not password:
        print('[REGISTRATION DEBUG] Missing required fields')
        return Response(
            {'error': 'phone, username, and password are required'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    too_weak, reason = is_pin_too_weak(password)
    if too_weak:
        print(f'[REGISTRATION DEBUG] Weak/invalid password: {reason}')
        return Response({'error': reason}, status=status.HTTP_400_BAD_REQUEST)

    # Normalize before any lookup. The verification marker, UserProfile.phone_number
    # and SubscriptionPlan.onevas_phone_number all store the 251XXXXXXXXX form, so
    # a caller sending 09XXXXXXXX would otherwise miss every one of them.
    # Idempotent: an already-normalized number passes through unchanged.
    normalized = _normalize_ethiopian_phone(phone)
    if not normalized:
        print(f'[REGISTRATION DEBUG] Invalid phone format: {phone}')
        return Response(
            {'error': 'Invalid Ethiopian phone number. Use format 09XXXXXXXX or +251XXXXXXXXX'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    phone = normalized

    # Check if user has active SMS subscription (OTP-less flow)
    print(f'[REGISTRATION DEBUG] Checking for SMS subscription for phone: {phone}')
    sms_subscription = UserSubscription.objects.filter(
        onevas_phone_number=phone, status='active', subscription_source='sms', user__isnull=True
    ).first()

    if sms_subscription:
        print('[REGISTRATION DEBUG] Found active SMS subscription, skipping OTP')
        skip_otp = True  # Skip OTP verification for SMS subscribers
    else:
        print('[REGISTRATION DEBUG] No SMS subscription found, will check OTP verification')

    if not skip_otp:
        # Require OTP verification for the app-first flow.
        #
        # This used to read a verified row from the `api_phoneotp` table, but
        # migrations 0051 and 0054 dropped that table while send/verify moved to
        # the cache-backed OTPService -- so this path raised
        # "no such table: api_phoneotp" for every caller.
        #
        # verify_phone_otp now leaves a short-lived marker instead. It is
        # single-use: consuming it here stops one verification being replayed to
        # register several accounts.
        print('[REGISTRATION DEBUG] Requiring OTP verification')
        from api.services.otp import OTPService

        if not OTPService.is_verified(phone):
            print(f'[REGISTRATION DEBUG] No valid verification marker for {phone}')
            return Response(
                {'error': 'Phone not verified. Please complete OTP step first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        print('[REGISTRATION DEBUG] Verification marker found')

    # Case-insensitive: 'Ammen' and 'ammen' are the same name here, because
    # gift delivery resolves recipients with username__iexact and would match
    # both. See api/services/usernames.py.
    if username_is_taken(username):
        print(f'[REGISTRATION DEBUG] Username already taken: {username}')
        return Response(username_taken_payload(), status=status.HTTP_409_CONFLICT)
    if UserProfile.objects.filter(phone_number=phone).exists():
        print(f'[REGISTRATION DEBUG] Phone number already registered: {phone}')
        return Response(
            {'error': 'Phone number already registered'}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        print('[REGISTRATION DEBUG] Creating user account...')
        user = User.objects.create_user(username=username, password=password, email=email or '')
        profile = user.profile
        profile.phone_number = phone
        profile.save()
        print(f'[REGISTRATION DEBUG] User created successfully: {user.username} (ID: {user.id})')

        if not skip_otp:
            # Burn the marker so the same verification cannot register again.
            from api.services.otp import OTPService

            OTPService.consume_verification(phone)
            print('[REGISTRATION DEBUG] Verification marker consumed')

        # Link any SMS subscriptions to the new user
        with transaction.atomic():
            # Link active SMS subscriptions
            sms_subs = UserSubscription.objects.filter(
                onevas_phone_number=phone,
                status='active',
                subscription_source='sms',
                user__isnull=True,
            )
            sms_count = sms_subs.count()
            print(f'[REGISTRATION DEBUG] Found {sms_count} SMS subscriptions to link')

            for sub in sms_subs:
                # Link subscription to user
                sub.user = user
                sub.save()

                # Update payment records
                SubscriptionPayment.objects.filter(subscription=sub, user__isnull=True).update(
                    user=user
                )

                # Update history records
                SubscriptionHistory.objects.filter(subscription=sub, user__isnull=True).update(
                    user=user
                )

                # Update user trial status
                profile.is_trial_user = False
                profile.save()
                print(f'[REGISTRATION DEBUG] Linked subscription {sub.id} to user {user.username}')

        token, _ = Token.objects.get_or_create(user=user)
        print(
            f'[REGISTRATION DEBUG] Registration successful - token generated for user: {user.username}'
        )
        return Response(
            {'user': UserSerializer(user).data, 'token': token.key}, status=status.HTTP_201_CREATED
        )
    except Exception as e:
        print(f'[REGISTRATION DEBUG] Registration failed with error: {str(e)}')
        import traceback

        print(f'[REGISTRATION DEBUG] Traceback: {traceback.format_exc()}')
        # A duplicate that slipped past the pre-check: two requests passed it
        # before either wrote, and the database constraint caught the second.
        # That is the constraint doing its job, so it is reported as the same
        # ordinary 409 the pre-check returns -- not as a failure.
        if is_duplicate_username_error(e):
            return Response(username_taken_payload(), status=status.HTTP_409_CONFLICT)

        # Everything else: logged in full, described in general. `str(e)` here
        # put database constraint text, table names and column names in front
        # of the customer.
        logger.exception('[REGISTRATION] Failed for phone=%s', phone)
        return Response(
            {'error': 'We could not create your account. Please try again.'},
            status=status.HTTP_400_BAD_REQUEST,
        )


# ── Forgot Password (email-based) ──────────────────────────────────────────


@api_view(['POST'])
@permission_classes([AllowAny])
@encrypted_endpoint
def login_with_subscription_otp(request):
    """Login with subscription OTP and create user account with password"""
    from api.models import UserProfile
    from api.models.subscription import SubscriptionPlan as UserSubscription

    phone = request.data.get('phone', '').strip()
    username = request.data.get('username', '').strip()
    otp = request.data.get('otp', '').strip()
    password = request.data.get('password', '').strip()

    print(
        f'[SUBSCRIPTION LOGIN DEBUG] Login attempt - phone: {phone}, username: {username}, otp: {otp}'
    )

    # Validate inputs - username is optional for existing users (will be checked after finding subscription)
    if not phone or not otp or not password:
        return Response(
            {'error': 'phone, otp, and password are required'}, status=status.HTTP_400_BAD_REQUEST
        )

    too_weak, reason = is_pin_too_weak(password)
    if too_weak:
        return Response({'error': reason}, status=status.HTTP_400_BAD_REQUEST)

    # Normalize phone
    phone = _normalize_ethiopian_phone(phone)
    if not phone:
        return Response(
            {'error': 'Invalid Ethiopian phone number'}, status=status.HTTP_400_BAD_REQUEST
        )

    # Find subscription with matching OTP (works for both SMS and app subscriptions)
    print(f'[SUBSCRIPTION LOGIN DEBUG] Searching for subscription with phone: {phone}, otp: {otp}')
    phone_values = lookup_variants(phone)
    subscription = (
        UserSubscription.objects.filter(
            Q(onevas_phone_number__in=phone_values) | Q(telebirr_phone_number__in=phone_values),
            setup_otp=otp,
            status='active',
        )
        .order_by('-start_date')
        .first()
    )

    if not subscription:
        # Debug: Try to find any subscription with this phone
        all_subs = UserSubscription.objects.filter(
            Q(onevas_phone_number__in=phone_values) | Q(telebirr_phone_number__in=phone_values)
        )
        print('[SUBSCRIPTION LOGIN DEBUG] No matching subscription found')
        print(
            f'[SUBSCRIPTION LOGIN DEBUG] All subscriptions with phone {phone}: {all_subs.count()}'
        )
        for sub in all_subs:
            print(
                f'[SUBSCRIPTION LOGIN DEBUG]   - ID: {sub.id}, OTP: {sub.setup_otp}, Status: {sub.status}, Source: {sub.subscription_source}, User: {sub.user}'
            )
        return Response(
            {'error': 'Invalid OTP or no active subscription found'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    print(f'[SUBSCRIPTION LOGIN DEBUG] Subscription found: ID {subscription.id}')

    # Check if subscription already has a user (existing user renewal/login)
    if subscription.user:
        print(
            f'[SUBSCRIPTION LOGIN DEBUG] Subscription already has user: {subscription.user.username}'
        )

        user = subscription.user
        if user.has_usable_password():
            # Existing PIN: this path is a login, so the submitted PIN must
            # match. First-time SuperApp/USSD accounts have no usable password
            # and fall through to set their PIN after OTP verification.
            if not user.check_password(password):
                return Response({'error': 'Invalid password'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            user.set_password(password)
            user.save(update_fields=['password'])

            profile, _created = UserProfile.objects.get_or_create(user=user)
            if not profile.phone_number:
                profile.phone_number = phone
                profile.save(update_fields=['phone_number'])

        # Clear OTP after successful login
        subscription.setup_otp = None
        subscription.save()

        print(f'[SUBSCRIPTION LOGIN DEBUG] User logged in successfully: {user.username}')

        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {'user': UserSerializer(user).data, 'token': token.key, 'message': 'Login successful'},
            status=status.HTTP_200_OK,
        )

    # No user yet - create new account (SMS-first flow)
    print('[SUBSCRIPTION LOGIN DEBUG] No user linked, creating new account')

    # Username is required for new users
    if not username:
        return Response(
            {'error': 'Username is required for new accounts'}, status=status.HTTP_400_BAD_REQUEST
        )

    # Same rule as every other place a username is claimed.
    if username_is_taken(username):
        return Response(username_taken_payload(), status=status.HTTP_409_CONFLICT)

    # Create user account
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                password=password,
                email=f'{username}@flipstar.app',  # Placeholder email
            )

            # Create profile (use get_or_create in case profile already exists)
            profile, created = UserProfile.objects.get_or_create(
                user=user, defaults={'phone_number': phone}
            )
            if not created:
                # Profile already exists, update phone number if different
                profile.phone_number = phone
                profile.save()

            # Link subscription to user
            subscription.user = user
            subscription.setup_otp = None  # Clear OTP after use
            subscription.save()

            print(f'[SUBSCRIPTION LOGIN DEBUG] User created: {username}, subscription linked')

        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                'user': UserSerializer(user).data,
                'token': token.key,
                'message': 'Account created successfully',
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        # Same two cases as register_with_phone: a duplicate the constraint
        # caught is a 409 the customer can act on, and anything else is logged
        # in full but described in general. The traceback stays in the log --
        # it was never something to return.
        if is_duplicate_username_error(e):
            return Response(username_taken_payload(), status=status.HTTP_409_CONFLICT)

        logger.exception('[SUBSCRIPTION LOGIN] Account creation failed')
        return Response(
            {'error': 'We could not create your account. Please try again.'},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([OtpSendAnonThrottle, OtpSendUserThrottle])
def resend_subscription_otp(request):
    """Resend the subscription setup OTP via SMS for an active subscription
    (login_with_subscription_otp's companion -- lets a customer get a fresh
    OTP without re-subscribing). Always returns a generic success regardless
    of whether a matching subscription exists, to avoid phone enumeration."""
    from django.conf import settings as _settings
    from django.core.cache import cache

    from api.models.subscription import SubscriptionPlan as UserSubscription
    from api.services.otp import OTPService
    from api.services.sms.dispatch import SmsNotQueued, queue_sms
    from api.views.subscription import WEB_APP_LINK, mask_phone_number

    phone_raw = request.data.get('phone', '').strip()
    if not phone_raw:
        return Response({'error': 'Phone number required'}, status=status.HTTP_400_BAD_REQUEST)

    phone = _normalize_ethiopian_phone(phone_raw)
    if not phone:
        return Response(
            {'error': 'Invalid Ethiopian phone number'}, status=status.HTTP_400_BAD_REQUEST
        )

    cooldown_key = f'resend_sub_otp:{phone}'
    if cache.get(cooldown_key):
        return Response(
            {'error': 'Please wait before requesting another OTP.'},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    subscription = (
        UserSubscription.objects.filter(
            Q(onevas_phone_number=phone) | Q(telebirr_phone_number=phone),
            status='active',
            end_date__gt=timezone.now(),
        )
        .order_by('-start_date')
        .first()
    )

    safe_response = {
        'message': 'If an active subscription exists, a new OTP has been sent via SMS.',
        'phone': mask_phone_number(phone),
    }

    if not subscription or not subscription.tier:
        return Response(safe_response)

    tier = subscription.tier
    otp_code = OTPService.generate_otp()
    subscription.setup_otp = otp_code
    subscription.setup_otp_expires_at = timezone.now() + timedelta(minutes=30)
    if not subscription.onevas_phone_number:
        subscription.onevas_phone_number = phone
    subscription.save()

    stop_keywords = {'daily': 'STOP1', 'weekly': 'STOP2', 'monthly': 'STOP3', 'ondemand': 'STOP'}
    stop_keyword = stop_keywords.get(tier.duration_type, 'STOP')

    token = subscription.generate_subscription_token(expires_hours=24)
    existing_user = '&existing_user=true' if subscription.user else ''
    message = (
        f'Dear valued customer, here is your new OTP for your {tier.name} Flipstar '
        f'subscription: {otp_code}. To access your premium service, please click on '
        f'{WEB_APP_LINK}?subscription_tp=true&token={token}{existing_user} and enter this OTP. '
        f'To cancel your subscription at any time, please send {stop_keyword} to {tier.short_code}.'
    )

    # Straight onto the TIMWE SMS queue. This went through
    # OnevasWebhookView.send_sms, which already queued the same way -- OneVAS
    # has been removed, so nothing on the OTP path goes near that class now.
    # queue_sms normalises the number itself.
    try:
        queue_sms(phone_number=phone, text=message, purpose='otp_subscription_resend')
    except SmsNotQueued:
        return Response(
            {'error': 'Failed to send OTP SMS. Please try again.'},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    cache.set(cooldown_key, True, timeout=60)

    resp = dict(safe_response)
    if _settings.DEBUG:
        resp['dev_code'] = otp_code
    return Response(resp)


@api_view(['POST'])
@permission_classes([AllowAny])
@encrypted_endpoint
def dev_create_subscription(request):
    """DEV ONLY: Create a fake active subscription with OTP for local testing without TIMWE."""
    from django.conf import settings as _s

    if not _s.DEBUG:
        return Response({'error': 'Only available in DEBUG mode'}, status=403)
    from api.models.subscription import SubscriptionPlan as UserSubscription
    from api.models.subscription import SubscriptionTier

    phone_raw = request.data.get('phone', '').strip()
    phone = _normalize_ethiopian_phone(phone_raw)
    if not phone:
        return Response({'error': 'Invalid phone number'}, status=400)
    tier = SubscriptionTier.objects.first()
    if not tier:
        return Response(
            {'error': 'No subscription tiers found. Run seed_subscription_tiers first.'}, status=400
        )
    from api.services.otp import OTPService

    otp_code = OTPService.generate_otp()
    # Cancel any existing unlinked subscription for this phone
    UserSubscription.objects.filter(onevas_phone_number=phone, user__isnull=True).delete()
    UserSubscription.objects.create(
        tier=tier,
        onevas_phone_number=phone,
        status='active',
        subscription_source='sms',
        setup_otp=otp_code,
        user=None,
    )
    reg_url = f'http://localhost/?subscription_tp=true&phone={phone}&otp={otp_code}'
    return Response(
        {
            'message': 'Test subscription created',
            'phone': phone,
            'otp': otp_code,
            'tier': tier.name,
            'registration_url': reg_url,
        }
    )


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PhoneLookupAnonThrottle, PhoneLookupUserThrottle])
@encrypted_endpoint
def check_phone_account(request):
    """Check if a phone number has an existing account"""
    from api.models import UserProfile

    phone = request.data.get('phone', '').strip()
    if not phone:
        return Response({'has_account': False}, status=status.HTTP_400_BAD_REQUEST)

    # Normalize phone number
    phone = _normalize_ethiopian_phone(phone)
    if not phone:
        return Response({'has_account': False}, status=status.HTTP_400_BAD_REQUEST)

    # Check if phone number has a profile
    has_account = UserProfile.objects.filter(phone_number=phone).exists()

    return Response({'has_account': has_account})


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetAnonThrottle, PasswordResetUserThrottle])
@encrypted_endpoint
def forgot_password_request(request):
    """Send 6-digit reset code to the user's email."""
    from api.models.auth import PasswordResetToken

    email = request.data.get('email', '').strip()
    if not email:
        return Response({'error': 'Email required'}, status=status.HTTP_400_BAD_REQUEST)
    SAFE = {'message': 'If an account with that email exists, a reset code has been sent.'}
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response(SAFE)
    code = _generate_otp()
    PasswordResetToken.objects.filter(user=user).delete()
    PasswordResetToken.objects.create(
        user=user, code=code, expires_at=timezone.now() + timedelta(minutes=15)
    )
    try:
        from django.conf import settings
        from django.core.mail import send_mail

        send_mail(
            subject='FlipStar — Password Reset Code',
            message=(
                f'Your FlipStar password reset code is: {code}\n\n'
                'This code expires in 15 minutes.\n'
                'If you did not request a reset, please ignore this email.'
            ),
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@flipstar.app'),
            recipient_list=[email],
            fail_silently=True,
        )
        print(f'[PWD-RESET] Code sent to {email}')
    except Exception as exc:
        print(f'[PWD-RESET] Email error: {exc} — dev code: {code}')
    return Response(SAFE)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetAnonThrottle, PasswordResetUserThrottle])
@encrypted_endpoint
def forgot_password_confirm(request):
    """Verify reset code and set new 6-digit password."""
    from api.models.auth import PasswordResetToken

    email = request.data.get('email', '').strip()
    code = request.data.get('code', '').strip()
    new_password = request.data.get('new_password', '').strip()
    if not email or not code or not new_password:
        return Response(
            {'error': 'email, code, and new_password required'}, status=status.HTTP_400_BAD_REQUEST
        )
    too_weak, reason = is_pin_too_weak(new_password)
    if too_weak:
        return Response({'error': reason}, status=status.HTTP_400_BAD_REQUEST)
    try:
        user = User.objects.get(email=email)
        token_obj = PasswordResetToken.objects.get(user=user, code=code, used=False)
    except (User.DoesNotExist, PasswordResetToken.DoesNotExist):
        return Response(
            {'error': 'Invalid or expired reset code'}, status=status.HTTP_400_BAD_REQUEST
        )
    if timezone.now() > token_obj.expires_at:
        token_obj.delete()
        return Response(
            {'error': 'Code expired. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST
        )
    user.set_password(new_password)
    user.save()
    token_obj.used = True
    token_obj.save()
    return Response({'message': 'Password reset successful. You can now log in.'})


# ── Phone PIN reset: who may reset ─────────────────────────────────────────
#
# A PIN reset is for a subscriber. Anyone else is told why, and how to
# subscribe -- where this used to answer "if an account exists, you will
# receive a code" and leave a non-subscriber waiting for an SMS that was never
# going to come.
#
# This tells a caller whether a number has an account. send_login_otp already
# does (``user_exists``), so nothing new is disclosed, and both endpoints are
# throttled.

PIN_RESET_USER_NOT_FOUND_CODE = 'USER_NOT_FOUND'


def _subscribe_hint():
    """How to subscribe: the routes the subscription page offers."""
    from django.conf import settings as _settings

    short_code = getattr(_settings, 'SMS_SHORT_CODE', '') or '9286'
    return (
        f'To subscribe, send 1 (Daily), 2 (Weekly) or 3 (Monthly) to {short_code} '
        'to pay with airtime, or subscribe with telebirr through the SuperApp or USSD.'
    )


#: A subscriber who has an account but has never chosen a PIN. Distinguished
#: from a wrong PIN because the two need opposite things from the user: one
#: should try again, the other has nothing to try.
PIN_NOT_SET_CODE = 'pin_not_set'


def _pin_not_set_response(phone):
    """Tell a subscriber who has no PIN where to get one.

    Subscribing by telebirr USSD push creates the account with
    ``password=None`` (see api/views/subscription.py) -- there is no
    registration step in that flow, and nothing ever asks for a PIN. Such a
    subscriber typing their number and any PIN used to be told "Invalid
    password", which is false: there is no password to get wrong. They would
    then try to register and be told the number was already taken, leaving no
    route forward at all.

    The route that does work is the PIN reset: it sends an OTP to this number
    and sets a PIN on the existing account. This response names it so the
    client can take them straight there.
    """
    return Response(
        {
            'code': PIN_NOT_SET_CODE,
            'error': 'You have not set a PIN yet. Set one to finish signing in.',
            'requires_pin_setup': True,
            'phone': phone,
        },
        status=status.HTTP_403_FORBIDDEN,
    )


def _pin_reset_account(phone):
    """The account a PIN reset for ``phone`` applies to, or why there is none.

    Returns ``(user, None)`` when the number belongs to an account with an
    active subscription, and ``(None, response)`` otherwise. "Active" is
    ``has_active_subscription`` -- the same rule that gates posting.
    """
    profile = UserProfile.objects.select_related('user').filter(phone_number=phone).first()
    if profile is None:
        return None, Response(
            {
                'code': PIN_RESET_USER_NOT_FOUND_CODE,
                'error': 'No FlipStar account is registered with this phone number.',
                'subscribe_hint': _subscribe_hint(),
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    if not has_active_subscription(profile.user):
        return None, Response(
            {
                'code': SUBSCRIPTION_REQUIRED_CODE,
                'error': 'This account does not have an active subscription.',
                'subscribe_hint': _subscribe_hint(),
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return profile.user, None


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetAnonThrottle, PasswordResetUserThrottle])
@encrypted_endpoint
def forgot_password_phone_request(request):
    """Send a 6-digit PIN reset code by SMS (TIMWE) to a subscriber's phone."""
    from api.services.otp import OTPService

    phone = _normalize_ethiopian_phone((request.data.get('phone') or '').strip())
    if not phone:
        return Response(
            {'error': 'Invalid Ethiopian phone number'}, status=status.HTTP_400_BAD_REQUEST
        )

    _user, refusal = _pin_reset_account(phone)
    if refusal is not None:
        return refusal

    success, message = OTPService.send_otp(phone, action='password_reset')
    if success:
        return Response({'message': message, 'phone': phone})
    return Response({'error': message}, status=status.HTTP_429_TOO_MANY_REQUESTS)


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([PasswordResetAnonThrottle, PasswordResetUserThrottle])
@encrypted_endpoint
def forgot_password_phone_verify(request):
    """Verify the reset code and set a new 6-digit PIN."""
    from api.services.otp import OTPService

    phone = (request.data.get('phone') or '').strip()
    code = (request.data.get('code') or '').strip()
    new_password = (request.data.get('new_password') or '').strip()

    if not phone or not code or not new_password:
        return Response(
            {'error': 'phone, code, and new_password required'}, status=status.HTTP_400_BAD_REQUEST
        )

    too_weak, reason = is_pin_too_weak(new_password)
    if too_weak:
        return Response({'error': reason}, status=status.HTTP_400_BAD_REQUEST)

    phone = _normalize_ethiopian_phone(phone)
    if not phone:
        return Response(
            {'error': 'Invalid Ethiopian phone number'}, status=status.HTTP_400_BAD_REQUEST
        )

    # Checked again here, not just when the code was requested: the OTP cache
    # is shared with login, and /auth/send-login-otp/ gives a code to any
    # number. Without this, that code would reset the PIN of an account the
    # request step turned away.
    user, refusal = _pin_reset_account(phone)
    if refusal is not None:
        return refusal

    success, message = OTPService.verify_otp(phone, code)
    if not success:
        return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.save()
    return Response({'message': 'Password reset successful. You can now log in.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_post(request):
    """Publish a photo or video post: the endpoint web and mobile upload to.

    The request stores the original and records the post; it does not process
    it. No FFmpeg runs here any more -- no duration probe, no frame grab --
    so the answer comes as soon as the bytes are safely in object storage.
    The post is returned as PROCESSING, the worker produces the video ladder
    or optimised images, and the post becomes READY (and appears in feeds)
    when that is done. See api/services/media_pipeline.py.

    Retry-safe: send an Idempotency-Key header (or a client_upload_id field)
    and a repeated submission -- a timeout followed by a retry, a double tap
    on Post -- returns the post it already created, 200 instead of 201, with
    no second charge.
    """
    return _create_post_from_upload(request, request.FILES.get('file'))


#: How many posts one status request may ask about.
PROCESSING_STATUS_MAX_IDS = 20


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def processing_posts(request):
    """Where the requesting user's uploads are in processing -- all of them in
    one request, for the web app's upload indicator.

      ?ids=12,13   those posts (any status), so the client sees each one reach
                   READY or FAILED. Posts that are not the user's, or no longer
                   exist, are simply absent.
      (no ids)     the user's posts still PROCESSING from the last day, so an
                   indicator can be rebuilt on a device that lost its list.

    Each row: id, processing_status, processing_progress (0-100, the worker's
    real progress; 100 once READY), processing_error (a code, never an
    exception), media_type, queued -- true while no worker has started -- and
    created_at. One small query; nothing is signed or serialised beyond these.
    """
    from api.models import MediaStatus
    from api.serializers.core import ReelSerializer

    posts = Reel.objects.filter(user=request.user)
    raw = (request.query_params.get('ids') or '').strip()
    if raw:
        ids = []
        for part in raw.split(',')[:PROCESSING_STATUS_MAX_IDS]:
            part = part.strip()
            if part.isascii() and part.isdigit() and len(part) <= 10:
                ids.append(int(part))
        posts = posts.filter(pk__in=ids)
    else:
        posts = posts.filter(
            processing_status=MediaStatus.PROCESSING,
            created_at__gte=timezone.now() - timedelta(days=1),
        )
    posts = posts.only(
        'id',
        'media',
        'image',
        'original_media',
        'original_image',
        'processing_status',
        'processing_progress',
        'processing_error',
        'processing_started_at',
        'created_at',
    ).order_by('-created_at')[:PROCESSING_STATUS_MAX_IDS]

    describe = ReelSerializer()
    rows = [
        {
            'id': post.pk,
            'processing_status': post.processing_status,
            'processing_progress': describe.get_processing_progress(post),
            'processing_error': post.processing_error or None,
            'media_type': describe.get_media_type(post),
            'queued': post.processing_status == MediaStatus.PROCESSING
            and post.processing_started_at is None,
            'created_at': post.created_at,
        }
        for post in posts
    ]
    return Response({'posts': rows})


def moderation_visible(queryset, user):
    """What moderation lets `user` see: nothing hidden by a moderator, and
    nothing from a banned, shadowbanned or temporarily banned account --
    except, for a signed-in user, their own posts. The feed's rule
    (ReelViewSet); anything else that hands out a post's media applies it
    too, so the two cannot drift apart."""
    now = timezone.now()
    ban_over = Q(user__profile__ban_expires_at__isnull=True) | Q(
        user__profile__ban_expires_at__lte=now
    )
    if user is not None and getattr(user, 'is_authenticated', False):
        return queryset.filter(
            Q(is_hidden=False)
            & (
                Q(user=user)
                | (Q(user__is_active=True) & Q(user__profile__is_shadowbanned=False) & ban_over)
            )
        )
    return queryset.filter(
        is_hidden=False, user__is_active=True, user__profile__is_shadowbanned=False
    ).filter(ban_over)


MEDIA_REFRESH_MAX_IDS = 20
MEDIA_REFRESH_MAX_FAILURES = 5


def _ids_from(values, limit):
    out = []
    for value in values if isinstance(values, list | tuple) else []:
        text = str(value).strip()
        if text.isascii() and text.isdigit() and len(text) <= 10 and int(text) not in out:
            out.append(int(text))
        if len(out) >= limit:
            break
    return out


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([MediaRefreshAnonThrottle, MediaRefreshUserThrottle])
def refresh_post_media(request):
    """The media to load now for posts a client already has.

    A client holds on to media URLs -- in a feed left open, in its feed
    caches -- and where the bucket is private those URLs are signed and stop
    working after S3_QUERYSTRING_EXPIRE. This answers with the posts' media
    signed now, the same fields the feed carries (reel_media_payload).

        {"ids": [12, 13],
         "failures": [{"id": 12, "url": "<the URL that did not load>",
                       "error": "4", "surface": "reels"}]}

    A failure is diagnosed (api/services/media_availability.py) and logged as
    `media.unavailable` with its reason; that post's answer carries
    `media_check: {"reason", "repairing"}` and leaves out any rendition
    storage says is missing. At most 20 ids and 5 failures; posts the caller
    may not see (moderation, or still processing and not theirs) are left
    out. Never an original under source/.
    """
    from django.conf import settings

    from api.services.media_availability import check_failure, media_payload

    data = request.data if hasattr(request.data, 'get') else {}
    failures = {}
    raw_failures = data.get('failures')
    for failure in raw_failures if isinstance(raw_failures, list) else []:
        if not isinstance(failure, dict):
            continue
        ids = _ids_from([failure.get('id')], 1)
        if ids and ids[0] not in failures and len(failures) < MEDIA_REFRESH_MAX_FAILURES:
            failures[ids[0]] = failure
    ids = _ids_from([*failures, *(data.get('ids') or [])], MEDIA_REFRESH_MAX_IDS)
    if not ids:
        return Response({'posts': [], 'expires_in': None})

    posts = moderation_visible(
        Reel.objects.filter(pk__in=ids).select_related('user', 'user__profile'), request.user
    ).visible_to(request.user)
    by_id = {post.pk: post for post in posts}

    rows = []
    for pk in ids:
        post = by_id.get(pk)
        if post is None:
            continue
        if pk in failures:
            payload, check = check_failure(post, failures[pk], request)
        else:
            payload, check = media_payload(post, request), None
        rows.append({'id': pk, **payload, 'media_check': check})

    signed = bool(getattr(settings, 'AWS_QUERYSTRING_AUTH', False)) and bool(
        getattr(settings, 'S3_BUCKET_NAME', '')
    )
    return Response(
        {
            'posts': rows,
            # How long the URLs above work, for a client deciding when to ask
            # again; null when they do not expire.
            'expires_in': getattr(settings, 'AWS_QUERYSTRING_EXPIRE', 3600) if signed else None,
        }
    )


class _PostNeedsCoins(Exception):
    def __init__(self, message, available):
        super().__init__(message)
        self.available = available


def _post_payload(reel, request):
    return ReelSerializer(reel, context={'request': request, 'followed_user_ids': set()}).data


def _reset_media(reel, source, intake):
    """Point a post at a new original and forget everything derived from the
    old one, so nothing of the replaced media is served. Not saved here."""
    from api.models import MediaStatus
    from api.services.media_pipeline import VIDEO

    is_video = intake.kind == VIDEO
    reel.media = source if is_video else None
    reel.image = None if is_video else source
    reel.original_media = source if is_video else ''
    reel.original_image = '' if is_video else source
    for field in (
        'media_360',
        'media_480',
        'image_small',
        'image_medium',
        'image_webp',
        'image_small_webp',
        'image_medium_webp',
        'blurhash',
    ):
        setattr(reel, field, '')
    reel.thumbnail = None
    reel.duration = None
    reel.source_size = intake.size
    reel.processed_size = None
    reel.source_deleted_at = None
    reel.processing_status = MediaStatus.PROCESSING
    reel.processing_error = ''
    reel.processing_failed = False
    reel.processed = False
    reel.processed_at = None
    reel.processing_task_id = ''
    reel.processing_started_at = None
    reel.processing_progress = 0
    # Skip a version: a run of the old media still in flight (a forced
    # re-process) writes where the new media never will, and is discarded.
    reel.media_version += 1


def _remove_replaced_media(reel_id, source_keys):
    """After the replacement commits, remove the replaced original: nothing
    refers to it and nothing will ever process it again. The replaced media's
    processed files stay until the new media is READY -- the worker removes
    every earlier version then -- so they are never gone before their
    replacement exists."""
    from django.db import transaction

    if not source_keys:
        return

    def _send():
        from api.tasks.media import delete_post_media

        delete_post_media.delay(reel_id, source_keys, [])

    transaction.on_commit(_send, robust=True)


def _video_subscription_refusal(user):
    """The 403 for a video from someone without a subscription, or None.

    Posting a video is subscriber-only. The client checks too, but that check
    is a courtesy: the status can lapse between opening the page and pressing
    Publish, and the endpoint is reachable directly.

    403 with a machine-readable `code` rather than a generic error, so the
    client can tell this apart from a real failure and keep the user's video
    and caption instead of discarding the draft.

    A short-code subscriber whose period has just run out is renewed here
    rather than turned away: the backend charges TIMWE once for the next
    period (when renewal is switched on) and the post goes through on a
    confirmed charge. See api/services/subscription_renewal.py.
    """
    if has_active_subscription(user):
        return None
    from api.services.subscription_renewal import (
        PAYMENT_PENDING,
        check_and_renew_subscription,
    )

    renewal = check_and_renew_subscription(user)
    if renewal.has_subscription:
        return None
    if renewal.state == PAYMENT_PENDING:
        return Response(
            payment_pending_payload(
                'Your subscription renewal payment is being confirmed. Please try again shortly.'
            ),
            status=status.HTTP_403_FORBIDDEN,
        )
    return Response(subscription_required_payload(), status=status.HTTP_403_FORBIDDEN)


def _create_post_from_upload(request, upload_file, overlay_text=None):
    """Everything /posts/create/ and POST /reels/ share, so the rules for
    publishing -- subscription, price, category, validation -- cannot depend
    on which endpoint a client happens to call."""
    import logging

    from django.db import IntegrityError, transaction

    from api.models import MediaStatus
    from api.models.contest import UserCoinBalance
    from api.models.wallet import WalletConfig
    from api.services.feed_filters import (
        InvalidCategory,
        invalid_category_response,
        resolve_category,
    )
    from api.services.media_pipeline import (
        VIDEO,
        MediaRejected,
        StorageUnavailable,
        discard_source,
        existing_post,
        queue_processing,
        read_client_upload_id,
        store_source,
        validate_upload,
    )

    log = logging.getLogger(__name__)
    user = request.user

    try:
        client_upload_id = read_client_upload_id(request)
        already = existing_post(user, client_upload_id)
        if already is not None:
            return Response(_post_payload(already, request), status=status.HTTP_200_OK)
        intake = validate_upload(upload_file)
    except MediaRejected as exc:
        return exc.response()

    is_video = intake.kind == VIDEO
    caption = request.data.get('caption', '')
    hashtags = request.data.get('hashtags', '')

    # The category the person picked. It used to be dropped here, so every
    # post from web and mobile was uncategorised and never appeared under an
    # Explore category. Resolved exactly as Explore filters (an id, or a slug
    # for older clients); unknown or inactive is a 400, never silently none.
    raw_category = request.data.get('category')
    if str(raw_category or '').strip().lower() in ('null', 'undefined', 'none'):
        raw_category = None
    try:
        category = resolve_category(raw_category)
    except InvalidCategory as exc:
        return invalid_category_response(exc.value)

    if is_video:
        refusal = _video_subscription_refusal(user)
        if refusal is not None:
            return refusal

    campaign = None
    is_campaign_post = False
    campaign_id = request.data.get('campaign_id')
    if campaign_id:
        from api.models.campaign import Campaign

        campaign = Campaign.objects.filter(id=campaign_id).first()
        is_campaign_post = campaign is not None

    # The price of posting (api/services/post_pricing.py). The long-video
    # difference is charged by the worker once it has measured the video
    # (api/tasks/media.py _charge_long_video): deciding it here meant running
    # ffprobe inside the request, and would mean trusting a duration the
    # client sent.
    from api.services import post_pricing

    config = WalletConfig.get_config()
    cost = post_pricing.base_cost(config, is_campaign_post=is_campaign_post)

    try:
        source = store_source(user, upload_file, intake)
    except StorageUnavailable:
        return Response(
            {
                'error': 'We could not save your upload. Please try again.',
                'code': 'storage_unavailable',
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        with transaction.atomic():
            if cost and cost > 0:
                balance, _ = UserCoinBalance.objects.get_or_create(user=user)
                try:
                    balance.spend_coins(
                        cost,
                        'post_create' if not is_campaign_post else 'campaign_post_create',
                        description=f'Create {"campaign" if is_campaign_post else "non-campaign"} post',
                    )
                except ValueError as exc:
                    raise _PostNeedsCoins(str(exc), balance.balance) from exc

            reel = Reel.objects.create(
                user=user,
                caption=caption,
                hashtags=hashtags,
                overlay_text=overlay_text or '',
                category=category,
                campaign=campaign,
                is_campaign_post=is_campaign_post,
                # The original is recorded twice on purpose: media/image mark
                # the post's type for code that asks, original_* is what the
                # worker reads. Neither is served -- the key is private and the
                # serializer does not resolve source/ keys.
                media=source if is_video else None,
                image=None if is_video else source,
                original_media=source if is_video else '',
                original_image='' if is_video else source,
                source_size=intake.size,
                processing_status=MediaStatus.PROCESSING,
                processed=False,
                client_upload_id=client_upload_id,
            )
            UserProfile.objects.filter(user=user).update(xp=F('xp') + 25)
            queue_processing(reel.pk)
    except _PostNeedsCoins as exc:
        discard_source(source)
        return Response(
            insufficient_coins_payload(cost, exc.available, message=str(exc)),
            status=status.HTTP_400_BAD_REQUEST,
        )
    except IntegrityError:
        # The same submission id arrived twice at once and the other request
        # won: this upload is surplus, and its post is the other one.
        discard_source(source)
        already = existing_post(user, client_upload_id)
        if already is not None:
            return Response(_post_payload(already, request), status=status.HTTP_200_OK)
        log.exception('[CREATE_POST] integrity error user=%s', user.pk)
        return Response(
            {'error': 'We could not create your post. Please try again.', 'code': 'post_failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except Exception:
        discard_source(source)
        # The detail is for the logs. A traceback in the response told anyone
        # who asked about the code, the paths and the database.
        log.exception('[CREATE_POST] failed user=%s', user.pk)
        return Response(
            {'error': 'We could not create your post. Please try again.', 'code': 'post_failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # A brand-new post: no comments, votes, likes or saves to count.
    reel.comment_count_db = 0
    reel.votes_count_db = 0
    reel.is_liked_db = False
    reel.is_saved_db = False
    log.info(
        '[CREATE_POST] reel=%s user=%s kind=%s bytes=%s category=%s',
        reel.pk,
        user.pk,
        intake.kind,
        intake.size,
        category.pk if category else None,
    )
    return Response(_post_payload(reel, request), status=status.HTTP_201_CREATED)


class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        profile = request.user.profile
        user = request.user

        # Update user fields
        if 'username' in request.data:
            user.username = request.data['username']
        if 'email' in request.data:
            user.email = request.data['email']
        if 'first_name' in request.data:
            user.first_name = request.data['first_name']
        if 'last_name' in request.data:
            user.last_name = request.data['last_name']
        user.save()

        # Update profile fields
        if 'bio' in request.data:
            profile.bio = request.data['bio']
        if 'profile_photo' in request.FILES:
            profile.profile_photo = request.FILES['profile_photo']
        profile.save()

        return Response(
            {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'bio': profile.bio,
                'profile_photo': profile.profile_photo.url if profile.profile_photo else None,
            }
        )

    @action(detail=False, methods=['post'])
    def update_privacy(self, request):
        profile = request.user.profile

        # Update privacy settings
        if 'privateAccount' in request.data:
            profile.is_private = request.data['privateAccount']
        if 'showActivity' in request.data:
            profile.show_activity = request.data['showActivity']
        if 'allowMessages' in request.data:
            profile.allow_messages = request.data['allowMessages']

        profile.save()

        return Response(
            {
                'privateAccount': profile.is_private,
                'showActivity': profile.show_activity,
                'allowMessages': profile.allow_messages,
                'message': 'Privacy settings updated successfully',
            }
        )

    @action(detail=False, methods=['get'])
    def me(self, request):
        profile = request.user.profile
        serializer = self.get_serializer(profile)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def add_xp(self, request):
        profile = request.user.profile
        xp = request.data.get('xp', 0)
        profile.xp += xp
        profile.level = (profile.xp // 1000) + 1
        profile.save()
        return Response(UserProfileSerializer(profile).data)

    @action(detail=False, methods=['post'])
    def daily_checkin(self, request):
        profile = request.user.profile
        now = timezone.now()

        if profile.last_checkin:
            if (now - profile.last_checkin).days == 1:
                profile.streak += 1
            elif (now - profile.last_checkin).days > 1:
                profile.streak = 1
        else:
            profile.streak = 1

        profile.last_checkin = now
        profile.xp += 50
        profile.save()

        return Response({'streak': profile.streak, 'xp': profile.xp, 'level': profile.level})


class DraftViewSet(viewsets.ModelViewSet):
    """Unpublished reels-in-progress. Always scoped to the requesting user --
    there is no read-only public access, unlike ReelViewSet."""

    queryset = Draft.objects.all()
    serializer_class = DraftSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user).order_by('-created_at')

    def create(self, request):
        serializer = DraftSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        try:
            draft = self.get_queryset().get(pk=pk)
        except Draft.DoesNotExist:
            return Response({'error': 'Draft not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = DraftSerializer(
            draft, data=request.data, partial=True, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        try:
            draft = self.get_queryset().get(pk=pk)
        except Draft.DoesNotExist:
            return Response({'error': 'Draft not found'}, status=status.HTTP_404_NOT_FOUND)

        # Delete files from storage -- the DB row cascading away on
        # draft.delete() never touches the storage backend on its own.
        for file_field_name in ('image', 'media', 'audio_file'):
            file_field = getattr(draft, file_field_name, None)
            if file_field:
                file_field.delete(save=False)
        draft.delete()
        return Response({'message': 'Draft deleted'})


def engagement_response(reel, **extra):
    """The response every engagement endpoint returns.

    Carries the four counts read back from the database plus the resulting
    leaderboard score, so a client never computes the score itself and never
    has to guess which spelling of "comments" a given endpoint used.

    The score is included on ordinary posts too, weighted by the defaults. It
    simply has no leaderboard to appear on -- which is the honest answer, and
    cheaper than making every caller branch on whether a post is in a campaign.
    """
    from api.services.scoring.leaderboard import campaign_for_reel, reel_engagement_payload

    payload = reel_engagement_payload(reel, campaign_for_reel(reel))
    payload.update(extra)
    # Retained because existing clients read it; same number as `likes`.
    payload['votes'] = payload['likes']
    return payload


class ReelViewSet(viewsets.ModelViewSet):
    queryset = Reel.objects.all()
    serializer_class = ReelSerializer
    # Reads are open to anyone; writes require authentication and, for
    # object-level actions (update/destroy/save/...), ownership or staff.
    # get_permissions() below still narrows further for specific actions
    # (e.g. vote/comments/share only need auth, not ownership) -- this is
    # the fail-closed default for anything it doesn't explicitly cover.
    permission_classes = [IsOwnerOrStaffOrReadOnly]

    def get_object(self):
        """For detail lookups (retrieve/update/delete) always use the full queryset
        so a reel the user marked 'not interested' still resolves instead of 404."""
        from django.shortcuts import get_object_or_404

        pk = self.kwargs.get('pk')
        queryset = Reel.objects.select_related('user', 'user__profile').annotate(
            comment_count_db=Count('comments', distinct=True),
        )
        if self.request.user.is_authenticated:
            try:
                queryset = queryset.annotate(
                    is_liked_db=Exists(
                        Vote.objects.filter(user=self.request.user, reel=OuterRef('pk'))
                    ),
                    is_saved_db=Exists(
                        SavedPost.objects.filter(user=self.request.user, reel=OuterRef('pk'))
                    ),
                )
            except Exception:  # noqa: S110 – annotation failure must not crash the retrieve
                pass
        # A post whose media is still processing (or failed) exists only for
        # its author until it is READY; anyone else gets the same 404 as for a
        # post that does not exist.
        if not self.request.user.is_staff:
            queryset = queryset.visible_to(self.request.user)
        obj = get_object_or_404(queryset, pk=pk)
        self.check_object_permissions(self.request, obj)
        return obj

    def perform_create(self, serializer):
        """Generate thumbnail for video uploads using FFmpeg"""
        # Check if user is banned before allowing content creation
        if self.request.user.is_authenticated:
            profile = getattr(self.request.user, 'profile', None)
            if profile:
                # Check for permanent ban
                if not self.request.user.is_active:
                    from rest_framework.exceptions import PermissionDenied

                    raise PermissionDenied('Your account has been permanently banned.')
                # Check for temp ban
                if profile.ban_expires_at and profile.ban_expires_at > timezone.now():
                    from rest_framework.exceptions import PermissionDenied

                    raise PermissionDenied(
                        f'Your account is temporarily banned until {profile.ban_expires_at.strftime("%Y-%m-%d %H:%M")}.'
                    )
        instance = serializer.save()

        # Generate thumbnail if video is uploaded
        if instance.media and not instance.thumbnail:
            try:
                import os
                import subprocess

                from django.conf import settings

                media_path = instance.media.path
                if not media_path or not os.path.exists(media_path):
                    return instance

                # Generate thumbnail filename
                thumbnail_dir = os.path.join(settings.MEDIA_ROOT, 'thumbnails')
                os.makedirs(thumbnail_dir, exist_ok=True)
                thumbnail_path = os.path.join(thumbnail_dir, f'{instance.id}.jpg')

                # Use FFmpeg to extract thumbnail at 1 second
                subprocess.run(  # noqa: S603 – args are fully hardcoded; no user input reaches ffmpeg
                    [  # noqa: S607 – 'ffmpeg' is a fixed system binary, not user-controlled
                        'ffmpeg',
                        '-i',
                        media_path,
                        '-ss',
                        '00:00:01',
                        '-vframes',
                        '1',
                        '-vf',
                        'scale=320:-2',
                        thumbnail_path,
                        '-y',
                    ],
                    check=True,
                    capture_output=True,
                )

                # Save thumbnail path to model
                instance.thumbnail.name = f'thumbnails/{instance.id}.jpg'
                instance.save(update_fields=['thumbnail'])
            except Exception as e:
                print(f'[REELS] Thumbnail generation failed for reel {instance.id}: {e}')

        return instance

    def get_queryset(self):
        try:
            from api.models import Comment

            # Prefetch recent comments to avoid N+1 queries in serializer
            recent_comments_prefetch = Prefetch(
                'comments',
                queryset=Comment.objects.select_related('user').order_by('-created_at')[:10],
                to_attr='prefetched_comments',
            )

            queryset = (
                Reel.objects.select_related('user', 'user__profile')
                .prefetch_related(recent_comments_prefetch, 'gifts_received')
                .annotate(
                    comment_count_db=Count('comments', distinct=True),
                    votes_count_db=Count('reel_votes', distinct=True),
                )
                .order_by('-created_at')
            )

            # Filter out hidden/banned content (moderation)
            # - is_hidden: Content removed by moderation
            # - is_shadowbanned: User shadowbanned (content hidden from others, but visible to owner)
            # - is_active=False: User permanently banned
            # - ban_expires_at > now: User temporarily banned
            # Signed-in users still see their own content. The same rule
            # guards POST /posts/media/ (moderation_visible).
            queryset = moderation_visible(queryset, self.request.user)

            # Skip NotInterested filter to prevent crashes - it's causing performance issues
            # If needed, can be re-enabled later with optimization

            # Annotate is_liked / is_saved for the current user to avoid N+1
            if self.request.user.is_authenticated:
                try:
                    queryset = queryset.annotate(
                        is_liked_db=Exists(
                            Vote.objects.filter(user=self.request.user, reel=OuterRef('pk'))
                        ),
                        is_saved_db=Exists(
                            SavedPost.objects.filter(user=self.request.user, reel=OuterRef('pk'))
                        ),
                    )
                except Exception as e:
                    print(
                        f'[REELS] Auth annotation failed: {e} - falling back to unannotated queryset'
                    )

            # Filter by user
            user_id = self.request.query_params.get('user', None)
            if user_id:
                queryset = queryset.filter(user_id=user_id)

            # Media still processing, or failed, has nothing to serve. Its
            # author sees it on their own profile (?user=<self>) with its
            # status; every feed lists READY posts alone.
            own_profile = (
                self.request.user.is_authenticated
                and user_id
                and str(user_id) == str(self.request.user.pk)
            )
            queryset = queryset.visible_to(self.request.user) if own_profile else queryset.ready()

            # Filter saved posts (requires authentication)
            saved = self.request.query_params.get('saved', None)
            if saved == 'true' and self.request.user.is_authenticated:
                try:
                    saved_post_ids = SavedPost.objects.filter(user=self.request.user).values_list(
                        'reel_id', flat=True
                    )
                    queryset = queryset.filter(id__in=saved_post_ids)
                except Exception as e:
                    print(f'[REELS] Saved filter failed: {e}')

            return queryset
        except Exception as e:
            print(f'[REELS] get_queryset failed: {e} - returning empty queryset')
            return Reel.objects.none()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        # Pre-compute the set of user IDs the current user follows — turns
        # N per-reel "am I following this author?" queries into one.
        if self.request.user.is_authenticated:
            try:
                context['followed_user_ids'] = set(
                    Follow.objects.filter(follower=self.request.user).values_list(
                        'following_id', flat=True
                    )
                )
            except Exception:
                context['followed_user_ids'] = set()
        else:
            context['followed_user_ids'] = set()
        return context

    def retrieve(self, request, *args, **kwargs):
        """Wrap retrieve so any serializer error returns a useful 500 body instead of crashing."""
        import traceback as _tb

        try:
            return super().retrieve(request, *args, **kwargs)
        except Http404:
            raise
        except Exception as e:
            tb = _tb.format_exc()
            print(f'[REELS RETRIEVE] ERROR pk={kwargs.get("pk")}: {type(e).__name__}: {e}\n{tb}')
            # The traceback stays in the log; it used to be returned too.
            return Response(
                {'error': 'This post could not be loaded.', 'code': 'post_unavailable'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def list(self, request, *args, **kwargs):
        """Override list to return empty results instead of 500 on errors"""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            print(f'[REELS LIST] Error: {e}')
            traceback.print_exc()
            return Response(
                {'count': 0, 'next': None, 'previous': None, 'results': []},
                status=status.HTTP_200_OK,
            )

    def get_permissions(self):
        if self.action in [
            'create',
            'update',
            'partial_update',
            'destroy',
            'vote',
            'comments',
            'share',
            'share_with',
        ]:
            self.permission_classes = [IsAuthenticated]  # Require auth for modifying operations
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        """POST /reels/ -- the same publishing path as /posts/create/.

        This used to be a second implementation: it ran FFmpeg in the request,
        stored the upload publicly, charged nothing and skipped the subscriber
        check that /posts/create/ enforces, so the price and the rules of
        posting depended on which endpoint a client called. It now hands off
        to the shared implementation, and keeps only what was particular to
        it: the file may arrive as `file`, `media` or `image`, and
        `overlay_text` is stored.
        """
        upload_file = (
            request.FILES.get('file') or request.FILES.get('media') or request.FILES.get('image')
        )
        return _create_post_from_upload(
            request, upload_file, overlay_text=request.data.get('overlay_text', '')
        )

    @action(detail=True, methods=['post'])
    def vote(self, request, pk=None):
        from api.models import Notification
        from api.services.campaign_charges import InsufficientCoins, charge_engagement

        reel = self.get_object()

        # The vote and the charge commit together or not at all. Previously the
        # rollback was a manual vote.delete() after the charge failed, which
        # left a window where a crash between the two kept an unpaid vote.
        try:
            with transaction.atomic():
                vote, created = Vote.objects.get_or_create(user=request.user, reel=reel)
                if created:
                    charge_engagement(request.user, reel, 'like')
                    # F() rather than `reel.votes += 1`: two concurrent likes
                    # both read the same value and one increment is lost.
                    Reel.objects.filter(pk=reel.pk).update(votes=F('votes') + 1)
                    reel.refresh_from_db(fields=['votes'])
        except InsufficientCoins as exc:
            return Response(
                insufficient_coins_payload(exc.required, exc.available, message=exc.message),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if created:
            # Create notification for reel owner (don't notify self)
            if reel.user != request.user:
                Notification.objects.create(
                    recipient=reel.user,
                    sender=request.user,
                    notification_type='like',
                    reel=reel,
                    message=f'{request.user.username} liked your post',
                )

            return Response({'has_voted': True, 'is_liked': True, 'votes': reel.votes})
        else:
            # Unlike. The like path above already used F(); this one did
            # `reel.votes -= 1; reel.save()`, which is the same lost-update bug
            # in reverse -- and worse, a bare save() rewrites every column from
            # a snapshot taken before the read, so an unlike could silently
            # roll back a share or a view that landed in between.
            #
            # The delete and the decrement commit together: a decrement without
            # its delete would drift the count below the rows that justify it.
            with transaction.atomic():
                deleted, _ = Vote.objects.filter(pk=vote.pk).delete()
                if deleted:
                    Reel.objects.filter(pk=reel.pk).update(votes=Greatest(F('votes') - 1, Value(0)))
            reel.refresh_from_db(fields=['votes'])

            # Delete notification when unliked
            if reel.user != request.user:
                Notification.objects.filter(
                    recipient=reel.user, sender=request.user, notification_type='like', reel=reel
                ).delete()

            return Response({'has_voted': False, 'is_liked': False, 'votes': reel.votes})

    @action(detail=True, methods=['post'])
    def save(self, request, pk=None):
        reel = self.get_object()
        saved_post, created = SavedPost.objects.get_or_create(user=request.user, reel=reel)

        if created:
            return Response({'saved': True, 'message': 'Post saved'})
        else:
            saved_post.delete()
            return Response({'saved': False, 'message': 'Post unsaved'})

    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        """Increment share count for a reel"""
        from api.services.campaign_charges import InsufficientCoins, charge_engagement

        reel = self.get_object()

        # once=True: sharing has no uniqueness constraint of its own, so every
        # double-tap, retry and refresh used to deduct again. The prior
        # CoinTransaction is the ledger that makes a repeat free.
        try:
            with transaction.atomic():
                charged = charge_engagement(request.user, reel, 'share', once=True)
                Reel.objects.filter(pk=reel.pk).update(shares=F('shares') + 1)
        except InsufficientCoins as exc:
            return Response(
                insufficient_coins_payload(exc.required, exc.available, message=exc.message),
                status=status.HTTP_400_BAD_REQUEST,
            )

        reel.refresh_from_db(fields=['shares'])
        return Response(engagement_response(reel, coins_charged=charged))

    @action(detail=True, methods=['post'], url_path='share-with')
    def share_with(self, request, pk=None):
        """Send this post to one or more users as a direct message.

        Composes what already exists -- Conversation, Message and the same
        charge_engagement the `share` action uses -- rather than adding a
        parallel notion of sharing. The client previously did this itself:
        for each recipient it created a conversation, posted a message with a
        "[POST_ID:n]" marker in the text, then called `share` again. That is
        three round trips per recipient and it produced two defects this
        endpoint exists to fix.

        The first is the share count. `share` was called once per recipient,
        so sending to five people counted five shares for one action. Here the
        count moves once, after the sends succeed, no matter how many
        recipients there were.

        The second is atomicity. A client that failed halfway left some
        recipients messaged and the rest not, with no way to tell which. The
        whole send is one transaction.

        Body: {"user_ids": [2, 7, 9]}
        """
        from api.models.messaging import Conversation, Message
        from api.services.campaign_charges import InsufficientCoins, charge_engagement

        reel = self.get_object()

        raw_ids = request.data.get('user_ids')
        if raw_ids is None and request.data.get('user_id') is not None:
            # Single-recipient spelling, so the simple case stays simple.
            raw_ids = [request.data.get('user_id')]

        if not isinstance(raw_ids, list | tuple) or not raw_ids:
            return Response(
                {'error': 'user_ids must be a non-empty list of user IDs.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # A share sheet is a scrollable list; a request naming hundreds of
        # recipients is not a user tapping avatars, so it is refused rather
        # than served as a fan-out primitive.
        if len(raw_ids) > 20:
            return Response(
                {'error': 'Cannot share with more than 20 users at once.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            wanted = {int(value) for value in raw_ids}
        except (TypeError, ValueError):
            return Response(
                {'error': 'user_ids must contain integers.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Sending a post to yourself has no meaning here -- it would create a
        # conversation with one participant. Dropped rather than rejected, so
        # selecting yourself among five people still sends to the other four.
        wanted.discard(request.user.id)
        if not wanted:
            return Response(
                {'error': 'Choose at least one other user to share with.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        recipients = list(User.objects.filter(id__in=wanted, is_active=True))
        found_ids = {user.id for user in recipients}
        missing = sorted(wanted - found_ids)
        if not recipients:
            return Response(
                {
                    'error': 'None of the selected users could be found.',
                    'invalid_user_ids': missing,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            with transaction.atomic():
                # Charged once for the action, not once per recipient, and
                # once=True keeps a retry free -- the same rule `share` uses.
                charged = charge_engagement(request.user, reel, 'share', once=True)

                for recipient in recipients:
                    conversation = Conversation.between(request.user, recipient)
                    if conversation is None:
                        conversation = Conversation.objects.create()
                        conversation.participants.add(request.user, recipient)

                    Message.objects.create(
                        conversation=conversation,
                        sender=request.user,
                        # The post travels as a reference. Text is left empty
                        # so the recipient's card renders from the live post
                        # rather than from a caption frozen at send time.
                        text='',
                        media_type=Message.MEDIA_POST,
                        shared_reel=reel,
                    )
                    Conversation.objects.filter(pk=conversation.pk).update(
                        last_message_at=timezone.now()
                    )

                # Once, after the sends -- not once per recipient.
                Reel.objects.filter(pk=reel.pk).update(shares=F('shares') + 1)
        except InsufficientCoins as exc:
            return Response(
                insufficient_coins_payload(exc.required, exc.available, message=exc.message),
                status=status.HTTP_400_BAD_REQUEST,
            )

        reel.refresh_from_db(fields=['shares'])
        return Response(
            engagement_response(
                reel,
                coins_charged=charged,
                shared=True,
                recipient_ids=sorted(found_ids),
                invalid_user_ids=missing,
            )
        )

    @action(detail=True, methods=['get', 'post'])
    def comments(self, request, pk=None):
        reel = self.get_object()

        if request.method == 'GET':
            # Use the extended serializer so nested CommentReply rows come back
            # with each Comment. Without this, the frontend comment-sheet refetch
            # drops every reply on re-open.
            from api.serializers.extended import CommentSerializer as ExtendedCommentSerializer

            comments = (
                Comment.objects.filter(reel=reel)
                .select_related('user', 'user__profile')
                .prefetch_related('replies', 'replies__user', 'replies__user__profile')
            )
            serializer = ExtendedCommentSerializer(
                comments, many=True, context={'request': request}
            )
            return Response(serializer.data)
        elif request.method == 'POST':
            if not request.user.is_authenticated:
                return Response(
                    {'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED
                )

            text = request.data.get('text', '').strip()
            if not text:
                return Response(
                    {'error': 'Comment text is required'}, status=status.HTTP_400_BAD_REQUEST
                )

            from api.services.campaign_charges import InsufficientCoins, charge_engagement

            # Comment first, then charge, both in one block. The old order
            # deducted before the comment existed and outside any transaction,
            # so a failure in between charged the user for nothing.
            try:
                with transaction.atomic():
                    comment = Comment.objects.create(user=request.user, reel=reel, text=text)
                    charge_engagement(request.user, reel, 'comment')
            except InsufficientCoins as exc:
                return Response(
                    insufficient_coins_payload(exc.required, exc.available, message=exc.message),
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Notification is created automatically by signal in signals.py

            serializer = CommentSerializer(comment, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """Delete a reel - only owner can delete"""
        import traceback as _tb

        from django.db import connection, transaction

        try:
            # Check authentication first
            if not request.user.is_authenticated:
                return Response(
                    {'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED
                )

            reel = self.get_object()
            print(
                f'[REEL DELETE] User: {request.user.username}, Reel: {reel.id}, Owner: {reel.user.username}'
            )

            # Check ownership
            if reel.user != request.user and not request.user.is_staff:
                return Response(
                    {'error': 'You can only delete your own posts'},
                    status=status.HTTP_403_FORBIDDEN,
                )

            reel_id = reel.id
            # The private original and the processed versions are not in the
            # media/image columns the deletes below touch; they are removed by
            # a task once the delete has committed.
            source_keys = [
                key
                for key in (reel.original_media, reel.original_image)
                if key and key.startswith('source/')
            ]

            def _remove_files_after_commit():
                from api.tasks.media import delete_post_media

                transaction.on_commit(
                    lambda: delete_post_media.delay(reel_id, source_keys), robust=True
                )

            # Try Django ORM delete first (uses model CASCADE rules) - safest path
            try:
                with transaction.atomic():
                    # Delete media files from storage before ORM delete
                    try:
                        if reel.media:
                            reel.media.delete(save=False)
                    except Exception as _e:
                        print(f'[REEL DELETE] media file delete skipped: {_e}')
                    try:
                        if reel.image:
                            reel.image.delete(save=False)
                    except Exception as _e:
                        print(f'[REEL DELETE] image file delete skipped: {_e}')
                    reel.delete()
                    _remove_files_after_commit()
                print(f'[REEL DELETE] Successfully deleted reel {reel_id} via ORM')
                return Response(status=status.HTTP_204_NO_CONTENT)
            except Exception as orm_err:
                print(f'[REEL DELETE] ORM delete failed, falling back to raw SQL: {orm_err}')

            # Fallback: raw SQL cascade delete
            with transaction.atomic():
                with connection.cursor() as cur:

                    def _safe(sql, params, critical=False):
                        """Execute SQL using a savepoint so optional-table failures don't abort the txn."""
                        sid = transaction.savepoint()
                        try:
                            cur.execute(sql, params)
                            transaction.savepoint_commit(sid)
                            return True
                        except Exception as _e:
                            transaction.savepoint_rollback(sid)
                            if critical:
                                print(f'[REEL DELETE] CRITICAL step failed: {_e}')
                                raise
                            print(f'[REEL DELETE] optional step skipped ({_e})')
                            return False

                    # 1. Notifications linked to comments on this reel
                    _safe(
                        """DELETE FROM api_notification
                        WHERE comment_id IN (SELECT id FROM api_comment WHERE reel_id=%s)""",
                        [reel_id],
                    )
                    # 2. CommentLikes / CommentReplies (optional tables)
                    _safe(
                        'DELETE FROM api_commentlike WHERE comment_id IN (SELECT id FROM api_comment WHERE reel_id=%s)',
                        [reel_id],
                    )
                    _safe(
                        'DELETE FROM api_commentreply WHERE comment_id IN (SELECT id FROM api_comment WHERE reel_id=%s)',
                        [reel_id],
                    )
                    # 3. Comments
                    _safe('DELETE FROM api_comment WHERE reel_id=%s', [reel_id])
                    # 4. Votes
                    _safe('DELETE FROM api_vote WHERE reel_id=%s', [reel_id])
                    # 5. Saved posts
                    _safe('DELETE FROM api_savedpost WHERE reel_id=%s', [reel_id])
                    # 6. Notifications (direct reel ref)
                    _safe('DELETE FROM api_notification WHERE reel_id=%s', [reel_id])
                    # 7. Not-interested flags
                    _safe('DELETE FROM api_notinterested WHERE reel_id=%s', [reel_id])
                    # 8. Reports
                    _safe('DELETE FROM api_report WHERE reported_reel_id=%s', [reel_id])
                    # 9. Winners
                    _safe('DELETE FROM api_winner WHERE reel_id=%s', [reel_id])
                    # 10. Optional related tables
                    for sql_opt in [
                        'DELETE FROM api_moderationaction WHERE reel_id=%s',
                        'DELETE FROM api_campaignentry WHERE reel_id=%s',
                        'DELETE FROM api_postscore WHERE reel_id=%s',
                        'DELETE FROM api_postboost WHERE reel_id=%s',
                        'DELETE FROM api_contestpostscore WHERE reel_id=%s',
                        'DELETE FROM api_gifttocreator WHERE reel_id=%s',
                        'DELETE FROM api_grandfinaleentry WHERE reel_id=%s',
                        'DELETE FROM api_grandfinalistentry WHERE reel_id=%s',
                        'DELETE FROM api_fraudalert WHERE reel_id=%s',
                        'DELETE FROM api_contestscore WHERE reel_id=%s',
                        'DELETE FROM api_mastercampaignparticipant WHERE reel_id=%s',
                    ]:
                        _safe(sql_opt, [reel_id])
                    # 11. Clear file columns then delete the reel row (CRITICAL)
                    _safe(
                        "UPDATE api_reel SET media='', image='' WHERE id=%s",
                        [reel_id],
                        critical=True,
                    )
                    _safe('DELETE FROM api_reel WHERE id=%s', [reel_id], critical=True)
                    _remove_files_after_commit()

            print(f'[REEL DELETE] Successfully deleted reel {reel_id}')
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Http404:
            raise
        except Exception as e:
            tb = _tb.format_exc()
            print(f'[REEL DELETE] Error: {type(e).__name__}: {e}\n{tb}')
            # The exception stays in the log. Its text -- a database error, a
            # storage path -- used to be returned to the client too.
            return Response(
                {
                    'error': 'We could not delete this post. Please try again.',
                    'code': 'delete_failed',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def partial_update(self, request, *args, **kwargs):
        """Edit a post: caption, hashtags and/or its media. Owner only.

        Replacement media goes through the same pipeline as a new post: the
        file's real type is checked, the original is stored privately, video
        is subscriber-only, and the post is PROCESSING until the new media is
        encoded. It used to publish the raw upload as-is -- metadata and all --
        and left the previous video's smaller renditions and thumbnail in
        place, so feeds went on serving the old video to anyone on a slow
        connection.
        """
        import logging

        from django.db import transaction

        from api.models import MediaStatus
        from api.services.media_pipeline import (
            SOURCE_PREFIX,
            VIDEO,
            MediaRejected,
            StorageUnavailable,
            discard_source,
            queue_processing,
            read_client_upload_id,
            store_source,
            validate_upload,
        )

        log = logging.getLogger(__name__)
        reel = self.get_object()
        if reel.user != request.user:
            return Response(
                {'error': 'You can only edit your own posts'}, status=status.HTTP_403_FORBIDDEN
            )

        new_file = (
            request.FILES.get('file') or request.FILES.get('media') or request.FILES.get('image')
        )
        intake = None
        client_upload_id = ''
        if new_file:
            try:
                client_upload_id = read_client_upload_id(request)
            except MediaRejected as exc:
                return exc.response()
            # The same replacement again -- a retry after the answer was lost.
            # It has been applied; answering 409 "still processing" to it
            # would tell the person their edit failed when it did not.
            if client_upload_id and reel.client_upload_id == client_upload_id:
                return Response(self.get_serializer(reel).data)
            # A worker is encoding this post's current media; swapping the
            # original under it would race its result.
            if reel.processing_status == MediaStatus.PROCESSING:
                return Response(
                    {
                        'error': 'This post is still being processed. '
                        'You can change its media once it is ready.',
                        'code': 'post_processing',
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            try:
                intake = validate_upload(new_file)
            except MediaRejected as exc:
                return exc.response()
            if intake.kind == VIDEO:
                refusal = _video_subscription_refusal(request.user)
                if refusal is not None:
                    return refusal

        source = None
        if intake is not None:
            try:
                source = store_source(request.user, new_file, intake)
            except StorageUnavailable:
                return Response(
                    {
                        'error': 'We could not save your upload. Please try again.',
                        'code': 'storage_unavailable',
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        replaced_sources = [
            key
            for key in (reel.original_media, reel.original_image)
            if key and key.startswith(SOURCE_PREFIX)
        ]
        try:
            with transaction.atomic():
                if 'caption' in request.data:
                    reel.caption = request.data['caption']
                if 'hashtags' in request.data:
                    reel.hashtags = request.data['hashtags']
                if source:
                    _reset_media(reel, source, intake)
                    if client_upload_id:
                        # Remembered so a retry of this edit is recognised.
                        reel.client_upload_id = client_upload_id
                reel.save()
                if source:
                    queue_processing(reel.pk)
                    _remove_replaced_media(reel.pk, replaced_sources)
        except Exception:
            discard_source(source)
            log.exception('[REEL UPDATE] failed reel=%s', reel.pk)
            return Response(
                {
                    'error': 'We could not update your post. Please try again.',
                    'code': 'update_failed',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(self.get_serializer(reel).data)


class QuestViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
    queryset = Quest.objects.filter(is_active=True)
    serializer_class = QuestSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        quest = self.get_object()
        user_quest, _ = UserQuest.objects.get_or_create(user=request.user, quest=quest)

        if not user_quest.completed:
            user_quest.completed = True
            user_quest.completed_at = timezone.now()
            user_quest.save()

            profile = request.user.profile
            profile.xp += quest.xp_reward
            profile.save()

        return Response(UserQuestSerializer(user_quest).data)


class SubscriptionViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user)

    @action(detail=False, methods=['post'])
    def upgrade(self, request):
        plan = request.data.get('plan')
        subscription = request.user.subscription
        subscription.plan = plan
        subscription.expires_at = timezone.now() + timedelta(days=30)
        subscription.save()
        return Response(SubscriptionSerializer(subscription).data)


class NotificationPreferenceViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return NotificationPreference.objects.filter(user=self.request.user)

    @action(detail=False, methods=['get', 'put', 'patch'])
    def me(self, request):
        try:
            prefs = request.user.notification_prefs
            if request.method in ['PUT', 'PATCH']:
                serializer = self.get_serializer(prefs, data=request.data, partial=True)
                if serializer.is_valid():
                    serializer.save()
                    return Response(serializer.data)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            serializer = self.get_serializer(prefs)
            return Response(serializer.data)
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f'Error in notification preferences me: {e}')
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CompetitionViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
    queryset = Competition.objects.filter(is_active=True)
    serializer_class = CompetitionSerializer
    permission_classes = [AllowAny]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsAuthenticated]
        return super().get_permissions()

    @action(detail=True, methods=['post'])
    def determine_winner(self, request, pk=None):
        competition = self.get_object()

        if competition.is_active:
            return Response(
                {'error': 'Competition is still active'}, status=status.HTTP_400_BAD_REQUEST
            )

        # Get top voted reel during competition period
        top_reel = (
            Reel.objects.filter(
                created_at__gte=competition.start_date, created_at__lte=competition.end_date
            )
            .order_by('-votes')
            .first()
        )

        if not top_reel:
            return Response({'error': 'No submissions found'}, status=status.HTTP_404_NOT_FOUND)

        # Create winner
        winner, created = Winner.objects.get_or_create(
            competition=competition,
            user=top_reel.user,
            defaults={'reel': top_reel, 'votes_received': top_reel.votes},
        )

        serializer = WinnerSerializer(winner)
        return Response(serializer.data)


class WinnerViewSet(EncryptedPayloadMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Winner.objects.all()
    serializer_class = WinnerSerializer
    permission_classes = [AllowAny]

    @action(detail=False, methods=['get'])
    def latest(self, request):
        winners = Winner.objects.all()[:10]
        serializer = self.get_serializer(winners, many=True)
        return Response(serializer.data)


def _follow_user_id_param(value, name):
    """A user id taken from the query string, or a refusal.

    These values land in a filter on an integer column, so anything
    non-numeric raises ValueError deep inside the ORM -- past any handler that
    could describe it -- and surfaces as an unhandled 500.

    The usual source is a client interpolating an id it does not have yet,
    arriving literally as ``?follower=undefined``. That is a malformed
    request, not a server fault, so it is answered as one. A well-formed id
    that matches nothing still returns an empty list, which is the honest
    answer to "who does user 999 follow".
    """
    from rest_framework.exceptions import ValidationError

    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({name: f'Expected a numeric user id, got {value!r}.'}) from None


class FollowViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
    serializer_class = FollowSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_permissions(self):
        if self.action == 'suggestions':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Follow.objects.none()

        # Handle query params for getting followers/following of any user
        following_id = self.request.query_params.get('following')
        follower_id = self.request.query_params.get('follower')

        if following_id:
            # Get users who follow the user with following_id (i.e., following_id is being followed)
            return Follow.objects.filter(
                following_id=_follow_user_id_param(following_id, 'following')
            )
        elif follower_id:
            # Get users who the follower_id follows (i.e., follower_id is the follower)
            return Follow.objects.filter(follower_id=_follow_user_id_param(follower_id, 'follower'))
        else:
            # Default: return who the current user is following
            return Follow.objects.filter(follower=self.request.user)

    @action(detail=False, methods=['post'])
    def toggle(self, request):
        following_id = request.data.get('following_id')
        if not following_id:
            return Response({'error': 'following_id required'}, status=400)

        try:
            following = User.objects.get(id=following_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

        if following == request.user:
            return Response({'error': 'Cannot follow yourself'}, status=400)

        follow, created = Follow.objects.get_or_create(follower=request.user, following=following)

        if not created:
            follow.delete()
            return Response({'following': False})

        return Response({'following': True})

    @action(detail=False, methods=['get'])
    def suggestions(self, request):
        # Instagram-style suggestion algorithm (2026)
        # Signals: mutual connections, activity/interests, contacts, location, profile interactions

        privileged_exclusion = {'is_staff': False, 'is_superuser': False}

        if request.user.is_authenticated:
            # Get users the current user follows
            following_ids = Follow.objects.filter(follower=request.user).values_list(
                'following_id', flat=True
            )

            # Get mutual connections (transitive property: if A follows B, and B follows C, suggest C to A)
            mutual_connections = set()
            for following_id in following_ids:
                # Get users that the people you follow also follow
                their_following = Follow.objects.filter(follower_id=following_id).values_list(
                    'following_id', flat=True
                )
                mutual_connections.update(their_following)

            # Get users who liked/commented on posts the current user engaged with
            from api.models import Comment, Vote

            engaged_posts = Vote.objects.filter(user=request.user).values_list('reel_id', flat=True)
            engaged_posts = list(engaged_posts) + list(
                Comment.objects.filter(user=request.user).values_list('reel_id', flat=True)
            )

            # Get users who engaged with the same posts (activity-based signal)
            activity_based_users = set()
            for post_id in engaged_posts[:50]:  # Limit to last 50 engaged posts
                other_voters = (
                    Vote.objects.filter(reel_id=post_id)
                    .exclude(user=request.user)
                    .values_list('user_id', flat=True)
                )
                activity_based_users.update(other_voters)

            # Combine all candidate users with scores
            candidate_scores = {}

            # Mutual connections get highest weight
            for user_id in mutual_connections:
                candidate_scores[user_id] = candidate_scores.get(user_id, 0) + 5

            # Activity-based users get medium weight
            for user_id in activity_based_users:
                candidate_scores[user_id] = candidate_scores.get(user_id, 0) + 3

            # Exclude: self, already following, staff/superuser
            exclude_ids = set(following_ids) | {request.user.id}

            # Filter candidates
            valid_candidates = (
                User.objects.filter(**privileged_exclusion)
                .exclude(id__in=exclude_ids)
                .filter(id__in=candidate_scores.keys())
            )

            # Sort by score, then randomize within same score for variety
            sorted_candidates = sorted(
                valid_candidates, key=lambda u: (-candidate_scores.get(u.id, 0), u.id)
            )

            # Take top 10
            suggestions = sorted_candidates[:10]
        else:
            # For non-authenticated users, suggest random users (excluding staff/superuser)
            suggestions = User.objects.filter(**privileged_exclusion).order_by('?')[:10]

        serializer = UserSerializer(suggestions, many=True, context={'request': request})
        return Response(serializer.data)


class BlockViewSet(EncryptedPayloadMixin, viewsets.ModelViewSet):
    serializer_class = BlockSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return Block.objects.filter(blocker=self.request.user).select_related(
                'blocker', 'blocked'
            )
        return Block.objects.none()

    @action(detail=False, methods=['post'])
    def block(self, request):
        blocked_id = request.data.get('blocked_id')
        if not blocked_id:
            return Response({'error': 'blocked_id required'}, status=400)

        try:
            blocked = User.objects.get(id=blocked_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

        if blocked == request.user:
            return Response({'error': 'Cannot block yourself'}, status=400)

        # Create block
        block, created = Block.objects.get_or_create(blocker=request.user, blocked=blocked)

        if not created:
            return Response({'error': 'Already blocked'}, status=400)

        return Response({'blocked': True})

    @action(detail=False, methods=['get'])
    def unblock(self, request):
        blocked_id = request.query_params.get('blocked_id')
        if not blocked_id:
            return Response({'error': 'blocked_id required'}, status=400)

        try:
            block = Block.objects.get(blocker=request.user, blocked_id=blocked_id)
            block.delete()
            return Response({'unblocked': True})
        except Block.DoesNotExist:
            return Response({'error': 'Block not found'}, status=404)


class UserSearchViewSet(EncryptedPayloadMixin, viewsets.ViewSet):
    """Search users for mentions"""

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def search(self, request):
        """Search users by username for mentions"""
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response({'results': []})

        # Search users who allow mentions and are not blocked by current user
        blocked_ids = Block.objects.filter(blocker=request.user).values_list(
            'blocked_id', flat=True
        )

        users = (
            User.objects.filter(username__icontains=query)
            .exclude(id=request.user.id)
            .exclude(id__in=blocked_ids)
            .select_related('profile')
            .filter(profile__allow_mentions=True)[:10]
        )

        serializer = UserSerializer(users, many=True, context={'request': request})
        return Response({'results': serializer.data})


@api_view(['GET'])
@permission_classes([AllowAny])
@encrypted_endpoint
def search(request):
    query = request.GET.get('q', '')
    if not query:
        return Response({'users': [], 'posts': [], 'hashtags': []})

    # Search users
    users = User.objects.filter(username__icontains=query)[:10]

    # Search posts by caption or hashtags
    posts = Reel.objects.ready().filter(caption__icontains=query) | Reel.objects.ready().filter(
        hashtags__icontains=query
    )
    posts = posts.distinct()[:20]

    # Extract unique hashtags - only scan reels that match, not ALL reels
    hashtags = set()
    for post in Reel.objects.ready().filter(hashtags__icontains=query).only('hashtags')[:100]:
        for tag in post.get_hashtags_list():
            if query.lower() in tag.lower():
                hashtags.add(tag)

    from api.serializers.core import build_feed_context

    feed_ctx = build_feed_context(request)
    return Response(
        {
            'users': UserSerializer(users, many=True, context={'request': request}).data,
            'posts': ReelSerializer(posts, many=True, context=feed_ctx).data,
            'hashtags': list(hashtags)[:10],
        }
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_user_notifications(request):
    """Get all notifications for the authenticated user"""
    try:
        # Get general notifications (likes, comments, follows) - with select_related to avoid N+1
        notifications = (
            Notification.objects.filter(recipient=request.user)
            .select_related('sender', 'sender__profile', 'reel', 'comment')
            .order_by('-created_at')[:50]
        )

        # Get campaign notifications
        campaign_notifications = (
            CampaignNotification.objects.filter(user=request.user)
            .select_related('campaign')
            .order_by('-created_at')[:50]
        )

        result = []

        # Add general notifications
        for notif in notifications:
            sender_data = None
            if notif.sender:
                profile_photo = None
                try:
                    pf = notif.sender.profile.profile_photo
                    if pf and pf.name:
                        profile_photo = pf.name if pf.name.startswith('http') else pf.url
                except Exception:  # noqa: S110 – profile photo fetch is best-effort in notification list
                    pass
                sender_data = {
                    'id': notif.sender.id,
                    'username': notif.sender.username,
                    'first_name': notif.sender.first_name,
                    'last_name': notif.sender.last_name,
                    'profile_photo': profile_photo,
                }

            reel_data = None
            if notif.reel:
                try:
                    # Never a private original under source/ (a post
                    # that is still processing has no served media yet).
                    from api.services.media_pipeline import served_url as _safe_url

                    reel_data = {
                        'id': notif.reel.id,
                        'media': _safe_url(notif.reel.media),
                        'image': _safe_url(notif.reel.image),
                    }
                except Exception:
                    reel_data = {'id': notif.reel.id, 'media': None, 'image': None}

            result.append(
                {
                    'id': notif.id,
                    'type': 'general',
                    'sender': sender_data,
                    'notification_type': notif.notification_type,
                    'message': notif.message,
                    'read': notif.is_read,
                    'timestamp': notif.created_at.isoformat() if notif.created_at else None,
                    'reel_id': notif.reel.id if notif.reel else None,
                    'reel': reel_data,
                    'comment_id': notif.comment.id if notif.comment else None,
                    'comment': notif.comment.text if notif.comment else None,
                }
            )

        # Add campaign notifications
        for notif in campaign_notifications:
            result.append(
                {
                    'id': notif.id,
                    'type': 'campaign',
                    'message': notif.message,
                    'notification_type': notif.notification_type,
                    'read': notif.is_read,
                    'timestamp': notif.created_at.isoformat() if notif.created_at else None,
                    'campaign_id': notif.campaign.id if notif.campaign else None,
                }
            )

        # Sort all notifications by timestamp
        result.sort(key=lambda x: x['timestamp'] or '', reverse=True)

        return Response(result)
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f'Error fetching notifications: {str(e)}', exc_info=True)
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def mark_notifications_read(request):
    """Mark notifications as read"""
    notification_ids = request.data.get('notification_ids', [])
    if notification_ids:
        # Mark specific notifications as read
        Notification.objects.filter(id__in=notification_ids, recipient=request.user).update(
            is_read=True
        )
    else:
        # Mark all notifications as read
        Notification.objects.filter(recipient=request.user).update(is_read=True)

    return Response({'message': 'Notifications marked as read'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_unread_notification_count(request):
    """Return count of unread notifications for the bell badge"""
    try:
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'unread_count': count})
    except Exception:
        return Response({'unread_count': 0})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def mark_single_notification_read(request, notification_id):
    """Mark a single notification as read"""
    try:
        Notification.objects.filter(id=notification_id, recipient=request.user).update(is_read=True)
        return Response({'message': 'Marked as read'})
    except Exception as e:
        return Response({'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([ReportUserThrottle])
@encrypted_endpoint
def create_report(request):
    """Create a new report for inappropriate content"""
    try:
        data = request.data.copy()
        print(f'[REPORT] Received report data: {data}')

        # Map legacy field names sent by frontend (reported_reel -> reported_reel_id)
        if 'reported_reel' in data and 'reported_reel_id' not in data:
            data['reported_reel_id'] = data.pop('reported_reel')
        if 'reported_user' in data and 'reported_user_id' not in data:
            data['reported_user_id'] = data.pop('reported_user')
        if 'reported_comment' in data and 'reported_comment_id' not in data:
            data['reported_comment_id'] = data.pop('reported_comment')

        # Auto-set target_type
        if 'reported_reel_id' in data and data['reported_reel_id']:
            data['target_type'] = 'reel'
        elif 'reported_comment_id' in data and data['reported_comment_id']:
            data['target_type'] = 'comment'
        elif 'reported_user_id' in data and data['reported_user_id']:
            data['target_type'] = 'user'

        # Auto-set priority based on report type
        high_priority_types = ['self_harm', 'violence', 'hate_speech']
        report_type = data.get('report_type', '')
        if report_type in high_priority_types:
            data['priority'] = 'critical'
        elif report_type in ['harassment', 'scam']:
            data['priority'] = 'high'
        else:
            data['priority'] = 'medium'

        print(f'[REPORT] Data after processing: {data}')
        serializer = ReportSerializer(data=data)
        if serializer.is_valid():
            report = serializer.save(reported_by=request.user)
            print(f'[REPORT] Report created successfully: ID {report.id}')

            # Auto-set reported_user from reel owner if not provided
            if report.reported_reel and not report.reported_user:
                report.reported_user = report.reported_reel.user
                report.save(update_fields=['reported_user'])
                print(f'[REPORT] Auto-set reported_user to reel owner: {report.reported_user.id}')

            # Auto-flag if target has 5+ pending reports
            if report.reported_reel:
                count = Report.objects.filter(
                    reported_reel=report.reported_reel, status='pending'
                ).count()
                if count >= 5:
                    report.priority = 'critical'
                    report.save(update_fields=['priority'])

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        print(f'[REPORT] Validation errors: {serializer.errors}')
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        print(f'[REPORT] Error creating report: {e}')
        import traceback as tb

        tb.print_exc()
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_reports_list(request):
    """Get all reports for admin dashboard"""
    if not request.user.is_staff:
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    status_filter = request.query_params.get('status', None)
    report_type = request.query_params.get('type', None)

    reports = Report.objects.all().order_by('-created_at')

    if status_filter:
        reports = reports.filter(status=status_filter)
    if report_type:
        reports = reports.filter(report_type=report_type)

    serializer = ReportSerializer(reports, many=True)
    return Response(serializer.data)


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def admin_report_detail(request, report_id):
    """Get or update a specific report"""
    if not request.user.is_staff:
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    try:
        report = Report.objects.get(id=report_id)
    except Report.DoesNotExist:
        return Response({'error': 'Report not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = ReportSerializer(report)
        return Response(serializer.data)

    elif request.method == 'PUT':
        serializer = ReportSerializer(report, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save(reviewed_by=request.user)
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def _create_moderation_notification(
    user, action_type, target_type, reason, report_id=None, moderator=None
):
    """Create a notification for a moderation action taken on a user's content or account"""
    if not user:
        return

    action_messages = {
        'warning': f'Your account has received a warning due to a report. Reason: {reason}',
        'content_removed': f'Your content has been removed due to a report. Reason: {reason}',
        'shadowban': f'Your account has been shadow banned - your content is now hidden from other users. Reason: {reason}',
        'temp_ban': f'Your account has been temporarily banned. Reason: {reason}',
        'permanent_ban': f'Your account has been permanently banned due to severe violations. Reason: {reason}',
    }

    message = action_messages.get(
        action_type, f'Moderation action taken: {action_type}. Reason: {reason}'
    )
    if report_id:
        message += f' (Report #{report_id})'

    Notification.objects.create(
        recipient=user,
        sender=moderator or user,  # System notification
        notification_type='moderation',
        message=message,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_moderate_report(request, report_id):
    """Take a moderation action on a report (warn, remove content, ban user, etc.)"""
    if not request.user.is_staff:
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)
    try:
        report = Report.objects.select_related('reported_user', 'reported_reel').get(id=report_id)
    except Report.DoesNotExist:
        return Response({'error': 'Report not found'}, status=status.HTTP_404_NOT_FOUND)

    action_taken = request.data.get('action_taken')
    reason_details = request.data.get('reason_details', '')

    if not action_taken:
        return Response({'error': 'action_taken is required'}, status=status.HTTP_400_BAD_REQUEST)

    ModerationAction.objects.create(
        report=report,
        moderator=request.user,
        action_taken=action_taken,
        reason_details=reason_details,
    )

    # Execute the action based on type
    print(f'[MODERATION] Executing action: {action_taken}')
    # Fallback: if reported_user is not set but reported_reel is, get the reel owner
    if not report.reported_user and report.reported_reel:
        report.reported_user = report.reported_reel.user
        report.save(update_fields=['reported_user'])
        print(f'[MODERATION] Auto-set reported_user from reel owner: {report.reported_user.id}')

    if action_taken == 'warning':
        # Send warning notification to user
        if report.reported_user:
            print(f'[MODERATION] Sending warning to user {report.reported_user.id}')
            _create_moderation_notification(
                user=report.reported_user,
                action_type='warning',
                target_type=report.target_type,
                reason=reason_details or 'Violation of community guidelines',
                report_id=report.id,
                moderator=request.user,
            )
            print('[MODERATION] Warning notification sent')
        else:
            print('[MODERATION] No reported_user found for warning')

    elif action_taken == 'content_removed':
        # Soft-delete the reel (mark as hidden instead of deleting)
        if report.reported_reel:
            print(f'[MODERATION] Hiding reel {report.reported_reel.id}')
            report.reported_reel.is_hidden = True
            report.reported_reel.save(update_fields=['is_hidden'])
            print('[MODERATION] Reel hidden successfully')
            # Notify the user
            if report.reported_user:
                _create_moderation_notification(
                    user=report.reported_user,
                    action_type='content_removed',
                    target_type='reel',
                    reason=reason_details or 'Content violates community guidelines',
                    report_id=report.id,
                    moderator=request.user,
                )
                print('[MODERATION] Content removal notification sent')
        else:
            print('[MODERATION] No reported_reel found for content_removed')

    elif action_taken == 'shadowban':
        # Shadow ban the user - content hidden from others but visible to self
        if report.reported_user:
            print(f'[MODERATION] Shadowbanning user {report.reported_user.id}')
            profile = getattr(report.reported_user, 'profile', None)
            if profile:
                print('[MODERATION] Profile found, setting is_shadowbanned=True')
                profile.is_shadowbanned = True
                profile.save(update_fields=['is_shadowbanned'])
                print('[MODERATION] Shadowban saved successfully')
                _create_moderation_notification(
                    user=report.reported_user,
                    action_type='shadowban',
                    target_type=report.target_type,
                    reason=reason_details or 'Repeated violations of community guidelines',
                    report_id=report.id,
                    moderator=request.user,
                )
                print('[MODERATION] Shadowban notification sent')
            else:
                print(f'[MODERATION] No profile found for user {report.reported_user.id}')
        else:
            print('[MODERATION] No reported_user found for shadowban')

    elif action_taken == 'temp_ban':
        # Temporary ban - set expiration (default 72 hours)
        if report.reported_user:
            print(f'[MODERATION] Temporarily banning user {report.reported_user.id}')
            profile = getattr(report.reported_user, 'profile', None)
            if profile:
                # Default to 72 hours from now, can be customized
                ban_duration_hours = 72
                profile.ban_expires_at = timezone.now() + timedelta(hours=ban_duration_hours)
                print(f'[MODERATION] Setting ban_expires_at to {profile.ban_expires_at}')
                profile.save(update_fields=['ban_expires_at'])
                print('[MODERATION] Temp ban saved successfully')
                _create_moderation_notification(
                    user=report.reported_user,
                    action_type='temp_ban',
                    target_type=report.target_type,
                    reason=reason_details
                    or f'Temporary ban for {ban_duration_hours} hours due to violations',
                    report_id=report.id,
                    moderator=request.user,
                )
                print('[MODERATION] Temp ban notification sent')
            else:
                print(f'[MODERATION] No profile found for user {report.reported_user.id}')
        else:
            print('[MODERATION] No reported_user found for temp_ban')

    elif action_taken == 'permanent_ban':
        # Permanent ban - deactivate account
        if report.reported_user:
            print(f'[MODERATION] Permanently banning user {report.reported_user.id}')
            report.reported_user.is_active = False
            report.reported_user.save(update_fields=['is_active'])
            print('[MODERATION] Permanent ban saved successfully')
            _create_moderation_notification(
                user=report.reported_user,
                action_type='permanent_ban',
                target_type=report.target_type,
                reason=reason_details or 'Severe or repeated violations of community guidelines',
                report_id=report.id,
                moderator=request.user,
            )
            print('[MODERATION] Permanent ban notification sent')
        else:
            print('[MODERATION] No reported_user found for permanent_ban')

    elif action_taken == 'no_action':
        # No action taken - just resolve the report
        print('[MODERATION] No action taken, just resolving report')
        pass

    # Mark report resolved
    report.status = 'resolved'
    report.reviewed_by = request.user
    report.resolution_notes = reason_details
    report.resolved_at = timezone.now()
    report.save(update_fields=['status', 'reviewed_by', 'resolution_notes', 'resolved_at'])

    return Response({'success': True, 'action': action_taken})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def admin_undo_moderation_action(request, action_id):
    """Undo a moderation action"""
    if not request.user.is_staff:
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)
    try:
        moderation_action = ModerationAction.objects.select_related(
            'report', 'report__reported_user', 'report__reported_reel'
        ).get(id=action_id)
    except ModerationAction.DoesNotExist:
        return Response({'error': 'Moderation action not found'}, status=status.HTTP_404_NOT_FOUND)

    action_to_undo = moderation_action.action_taken
    report = moderation_action.report
    print(f'[MODERATION] Undoing action: {action_to_undo}')

    # Undo the action based on type
    if action_to_undo == 'content_removed':
        # Restore the reel (unhide it)
        if report.reported_reel:
            print(f'[MODERATION] Restoring reel {report.reported_reel.id}')
            report.reported_reel.is_hidden = False
            report.reported_reel.save(update_fields=['is_hidden'])
            print('[MODERATION] Reel restored successfully')
            # Notify the user
            if report.reported_user:
                _create_moderation_notification(
                    user=report.reported_user,
                    action_type='content_restored',
                    target_type='reel',
                    reason='Your content has been restored after review',
                    report_id=report.id,
                    moderator=request.user,
                )
                print('[MODERATION] Content restoration notification sent')
        else:
            print('[MODERATION] No reported_reel found for content_removed undo')

    elif action_to_undo == 'shadowban':
        # Remove shadowban
        if report.reported_user:
            print(f'[MODERATION] Removing shadowban from user {report.reported_user.id}')
            profile = getattr(report.reported_user, 'profile', None)
            if profile:
                print('[MODERATION] Profile found, setting is_shadowbanned=False')
                profile.is_shadowbanned = False
                profile.save(update_fields=['is_shadowbanned'])
                print('[MODERATION] Shadowban removed successfully')
                _create_moderation_notification(
                    user=report.reported_user,
                    action_type='shadowban_removed',
                    target_type=report.target_type,
                    reason='Your shadowban has been removed after review',
                    report_id=report.id,
                    moderator=request.user,
                )
                print('[MODERATION] Shadowban removal notification sent')
            else:
                print(f'[MODERATION] No profile found for user {report.reported_user.id}')
        else:
            print('[MODERATION] No reported_user found for shadowban undo')

    elif action_to_undo == 'temp_ban':
        # Remove temp ban
        if report.reported_user:
            print(f'[MODERATION] Removing temp ban from user {report.reported_user.id}')
            profile = getattr(report.reported_user, 'profile', None)
            if profile:
                print('[MODERATION] Profile found, clearing ban_expires_at')
                profile.ban_expires_at = None
                profile.save(update_fields=['ban_expires_at'])
                print('[MODERATION] Temp ban removed successfully')
                _create_moderation_notification(
                    user=report.reported_user,
                    action_type='temp_ban_removed',
                    target_type=report.target_type,
                    reason='Your temporary ban has been removed after review',
                    report_id=report.id,
                    moderator=request.user,
                )
                print('[MODERATION] Temp ban removal notification sent')
            else:
                print(f'[MODERATION] No profile found for user {report.reported_user.id}')
        else:
            print('[MODERATION] No reported_user found for temp_ban undo')

    elif action_to_undo == 'permanent_ban':
        # Reactivate account
        if report.reported_user:
            print(f'[MODERATION] Reactivating user {report.reported_user.id}')
            report.reported_user.is_active = True
            report.reported_user.save(update_fields=['is_active'])
            print('[MODERATION] Account reactivated successfully')
            _create_moderation_notification(
                user=report.reported_user,
                action_type='account_reactivated',
                target_type=report.target_type,
                reason='Your account has been reactivated after review',
                report_id=report.id,
                moderator=request.user,
            )
            print('[MODERATION] Account reactivation notification sent')
        else:
            print('[MODERATION] No reported_user found for permanent_ban undo')

    elif action_to_undo == 'warning':
        # Warning is just a notification, nothing to undo
        print('[MODERATION] Warning has no effect to undo, but will notify user')
        if report.reported_user:
            _create_moderation_notification(
                user=report.reported_user,
                action_type='warning_cleared',
                target_type=report.target_type,
                reason='Your warning has been cleared after review',
                report_id=report.id,
                moderator=request.user,
            )
            print('[MODERATION] Warning cleared notification sent')

    elif action_to_undo == 'no_action':
        # No action was taken, nothing to undo
        print('[MODERATION] No action was taken, nothing to undo')
        return Response({'error': 'No action to undo'}, status=status.HTTP_400_BAD_REQUEST)

    # Mark the moderation action as undone
    moderation_action.undone = True
    moderation_action.undone_by = request.user
    moderation_action.undone_at = timezone.now()
    moderation_action.save(update_fields=['undone', 'undone_by', 'undone_at'])

    return Response({'success': True, 'undone_action': action_to_undo})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_reports_stats(request):
    """Get report statistics for admin dashboard"""
    if not request.user.is_staff:
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    from django.db.models import Count

    total_reports = Report.objects.count()
    pending_reports = Report.objects.filter(status='pending').count()
    reviewing_reports = Report.objects.filter(status='reviewing').count()
    resolved_reports = Report.objects.filter(status='resolved').count()
    dismissed_reports = Report.objects.filter(status='dismissed').count()

    reports_by_type = Report.objects.values('report_type').annotate(count=Count('id'))

    return Response(
        {
            'total_reports': total_reports,
            'pending_reports': pending_reports,
            'reviewing_reports': reviewing_reports,
            'resolved_reports': resolved_reports,
            'dismissed_reports': dismissed_reports,
            'reports_by_type': list(reports_by_type),
        }
    )


# Deepest page the explorer feed serves; see get_trending_reels.
TRENDING_MAX_OFFSET = 1000


@api_view(['GET'])
@permission_classes([AllowAny])
@encrypted_endpoint
def get_trending_reels(request):
    """Trending posts for the Explore page, filtered by category and time.

    Query parameters, all optional:
      category    all | trending | <category id> | <category slug>
      time_range  24h | 7d (default) | 30d
      limit       page size, 1-50 (default 20)
      offset      rows to skip, for infinite scroll (default 0)

    Two defects here both looked like "the category filter does nothing":
      - an unknown slug skipped the filter and returned every post;
      - offset was never read, so every scroll request returned page one
        again, and the client -- de-duplicating by id -- appended nothing.
    An unknown category is now a 400 (api/services/feed_filters.py), and pages
    are slices of one deterministic order, so page two continues page one
    within the same category and window.

    A failure is a 500, not an empty 200: an empty list rendered as "nothing
    here yet", indistinguishable from a category that has no posts.

    Performance: one annotated SELECT -- select_related plus Exists-based
    is_liked / is_saved and DB-side counts -- so the serializer never falls into
    per-row queries; Reel's (category, -created_at) index serves the filter.
    """
    import logging

    from api.models.boost import BoostCampaign
    from api.serializers.core import build_feed_context
    from api.services.feed_filters import (
        InvalidCategory,
        bounded_int,
        invalid_category_response,
        resolve_category,
        window_start,
    )

    try:
        category = resolve_category(request.GET.get('category'))
    except InvalidCategory as exc:
        return invalid_category_response(exc.value)

    limit = bounded_int(request.GET.get('limit'), default=20, low=1, high=50)
    offset = bounded_int(request.GET.get('offset'), default=0, low=0, high=TRENDING_MAX_OFFSET + 1)
    if offset > TRENDING_MAX_OFFSET:
        # A deep offset makes the database walk every earlier row. Nobody
        # scrolls a thousand trending posts, so the feed ends there.
        return Response([])

    try:
        # READY only: a post still processing has no media to show yet.
        queryset = Reel.objects.ready().filter(
            created_at__gte=window_start(request.GET.get('time_range', '7d'), timezone.now())
        )
        if category is not None:
            queryset = queryset.filter(category=category)

        # An active boost lifts a post in Trending.
        #
        # Nothing read the boost state before this: `is_boosted` was set when a
        # campaign started and never consulted by any feed, `injection_ratio`
        # was configured and used nowhere, and boost/eligible/ was served but
        # called by no client. A user paid coins and got no visibility at all.
        #
        # The condition matches get_eligible_boosts exactly rather than
        # restating it -- status, an end time in the future, and budget left --
        # so "boosted" cannot come to mean two different things depending on
        # which code path asks.
        active_boost = BoostCampaign.objects.filter(
            reel=OuterRef('pk'),
            status='active',
            end_time__gt=timezone.now(),
            coins_remaining__gt=0,
        )

        queryset = queryset.select_related('user', 'user__profile').annotate(
            comment_count_db=Count('comments', distinct=True),
            votes_count_db=Count('reel_votes', distinct=True),
            has_active_boost=Exists(active_boost),
        )
        if request.user.is_authenticated:
            queryset = queryset.annotate(
                is_liked_db=Exists(Vote.objects.filter(user=request.user, reel=OuterRef('pk'))),
                is_saved_db=Exists(
                    SavedPost.objects.filter(user=request.user, reel=OuterRef('pk'))
                ),
            )
        # Boosted first, then the existing order untouched. Ranking within each
        # group is unchanged, so an unboosted feed looks exactly as it did.
        # `-id` comes last so rows that tie on everything else still have one
        # fixed order; without it, offset pages can repeat or skip posts that
        # share a vote count and a timestamp.
        queryset = queryset.order_by('-has_active_boost', '-votes', '-created_at', '-id')[
            offset : offset + limit
        ]

        serializer = ReelSerializer(queryset, many=True, context=build_feed_context(request))
        return Response(serializer.data)
    except Exception:
        logging.getLogger(__name__).exception('[TRENDING] explorer trending failed')
        return Response(
            {'error': 'Could not load trending posts.', 'code': 'trending_failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([AllowAny])
@encrypted_endpoint
def get_categories(request):
    """Return all active categories for the frontend."""
    try:
        from api.models import Category
        from api.serializers.core import CategorySerializer

        categories = Category.objects.filter(is_active=True).order_by('order', 'name')
        serializer = CategorySerializer(categories, many=True)
        return Response(serializer.data)
    except Exception as e:
        print(f'[CATEGORIES] Error: {str(e)}')
        import traceback

        traceback.print_exc()
        return Response([], status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
@encrypted_endpoint
def get_trending_hashtags(request):
    """Return top hashtags ranked by (post_count + weighted_votes) in the time window."""
    from collections import defaultdict
    from datetime import timedelta

    time_range = request.GET.get('time_range', '7d')
    limit = min(int(request.GET.get('limit', 15)), 30)

    now = timezone.now()
    if time_range == '24h':
        threshold = now - timedelta(hours=24)
    elif time_range == '30d':
        threshold = now - timedelta(days=30)
    else:
        threshold = now - timedelta(days=7)

    rows = (
        Reel.objects.ready()
        .filter(
            created_at__gte=threshold,
            hashtags__isnull=False,
        )
        .exclude(hashtags='')
        .values_list('hashtags', 'votes')
    )

    tag_posts = defaultdict(int)
    tag_score = defaultdict(float)

    for hashtags_str, votes in rows:
        tags = re.findall(r'#?(\w+)', hashtags_str or '')
        for tag in tags:
            t = tag.lower()
            if len(t) < 2:
                continue
            tag_posts[t] += 1
            tag_score[t] += 1 + (votes or 0) * 0.05

    ranked = sorted(tag_score.keys(), key=lambda t: tag_score[t], reverse=True)[:limit]

    result = [{'tag': t, 'posts': tag_posts[t], 'score': round(tag_score[t])} for t in ranked]
    return Response(result)


@api_view(['GET'])
@permission_classes([AllowAny])
@encrypted_endpoint
def get_reels_by_hashtag(request):
    """Get reels that contain a specific hashtag"""
    from django.db.models import Count, Q

    hashtag = request.GET.get('tag', '').strip().lower()
    if not hashtag:
        return Response({'error': 'Tag parameter required'}, status=status.HTTP_400_BAD_REQUEST)

    # Remove # if present
    if hashtag.startswith('#'):
        hashtag = hashtag[1:]

    limit = min(int(request.GET.get('limit', 30)), 50)

    # Search in both hashtags field and caption — annotate the same way
    # ReelViewSet does so the serializer never falls into N+1 fallbacks.
    queryset = (
        Reel.objects.ready()
        .filter(
            Q(hashtags__icontains=f'#{hashtag}')
            | Q(hashtags__icontains=hashtag)
            | Q(caption__icontains=f'#{hashtag}')
        )
        .select_related('user', 'user__profile')
        .annotate(
            comment_count_db=Count('comments', distinct=True),
            votes_count_db=Count('reel_votes', distinct=True),
        )
    )
    if request.user.is_authenticated:
        queryset = queryset.annotate(
            is_liked_db=Exists(Vote.objects.filter(user=request.user, reel=OuterRef('pk'))),
            is_saved_db=Exists(SavedPost.objects.filter(user=request.user, reel=OuterRef('pk'))),
        )
    queryset = queryset.order_by('-votes', '-created_at')[:limit]

    from api.serializers.core import build_feed_context

    serializer = ReelSerializer(queryset, many=True, context=build_feed_context(request))
    return Response({'hashtag': hashtag, 'count': len(serializer.data), 'results': serializer.data})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def mark_not_interested(request):
    """Mark a reel as not interested to hide from user's feed"""
    reel_id = request.data.get('reel_id')
    if not reel_id:
        return Response({'error': 'reel_id required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        reel = Reel.objects.get(id=reel_id)
    except Reel.DoesNotExist:
        return Response({'error': 'Reel not found'}, status=status.HTTP_404_NOT_FOUND)

    from api.models import NotInterested

    NotInterested.objects.get_or_create(user=request.user, reel=reel)

    return Response({'message': 'Marked as not interested', 'reel_id': reel_id})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def undo_not_interested(request):
    """Undo marking a reel as not interested"""
    reel_id = request.data.get('reel_id')
    if not reel_id:
        return Response({'error': 'reel_id required'}, status=status.HTTP_400_BAD_REQUEST)

    from api.models import NotInterested

    NotInterested.objects.filter(user=request.user, reel_id=reel_id).delete()

    return Response({'message': 'Removed from not interested', 'reel_id': reel_id})


@api_view(['POST'])
@permission_classes([AllowAny])
@encrypted_endpoint
def track_view(request, reel_id):
    """Increment view count for a reel. Uses F() for atomic DB increment."""
    from django.db.models import F

    try:
        updated = Reel.objects.filter(id=reel_id).update(view_count=F('view_count') + 1)
        if not updated:
            return Response({'error': 'Reel not found'}, status=status.HTTP_404_NOT_FOUND)
        view_count = Reel.objects.filter(id=reel_id).values_list('view_count', flat=True).first()
        return Response({'view_count': view_count})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== NOTIFICATION SETTINGS ====================


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_notification_settings(request):
    """Get notification settings for the authenticated user"""
    try:
        # Get or create notification preferences
        notification_prefs, created = NotificationPreference.objects.get_or_create(
            user=request.user,
            defaults={
                'likes': True,
                'comments': True,
                'follows': True,
                'messages': True,
                'email_notifications': True,
                'push_notifications': True,
            },
        )

        return Response(
            {
                'likes': notification_prefs.likes,
                'comments': notification_prefs.comments,
                'follows': notification_prefs.follows,
                'messages': notification_prefs.messages,
                'email_notifications': notification_prefs.email_notifications,
                'push_notifications': notification_prefs.push_notifications,
            }
        )
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def update_notification_settings(request):
    """Update notification settings for the authenticated user"""
    try:
        # Get or create notification preferences
        notification_prefs, created = NotificationPreference.objects.get_or_create(
            user=request.user
        )

        # Update fields from request data
        update_fields = [
            'likes',
            'comments',
            'follows',
            'messages',
            'email_notifications',
            'push_notifications',
        ]
        for field in update_fields:
            if field in request.data:
                setattr(notification_prefs, field, request.data[field])

        notification_prefs.save()

        return Response(
            {
                'message': 'Notification settings updated successfully',
                'settings': {
                    'likes': notification_prefs.likes,
                    'comments': notification_prefs.comments,
                    'follows': notification_prefs.follows,
                    'messages': notification_prefs.messages,
                    'email_notifications': notification_prefs.email_notifications,
                    'push_notifications': notification_prefs.push_notifications,
                },
            }
        )
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== PRIVACY SETTINGS ====================


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def get_privacy_settings(request):
    """Get privacy settings for the authenticated user"""
    try:
        profile = request.user.profile
        return Response(
            {
                'privateAccount': profile.is_private,
                'showActivity': profile.show_activity,
                'allowMessages': profile.allow_messages,
            }
        )
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
@encrypted_endpoint
def update_privacy_settings(request):
    """Update privacy settings for the authenticated user"""
    try:
        profile = request.user.profile

        # Map frontend field names to model field names
        field_mapping = {
            'privateAccount': 'is_private',
            'showActivity': 'show_activity',
            'allowMessages': 'allow_messages',
        }

        for frontend_field, model_field in field_mapping.items():
            if frontend_field in request.data:
                setattr(profile, model_field, request.data[frontend_field])

        profile.save()

        return Response(
            {
                'message': 'Privacy settings updated successfully',
                'settings': {
                    'privateAccount': profile.is_private,
                    'showActivity': profile.show_activity,
                    'allowMessages': profile.allow_messages,
                },
            }
        )
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
