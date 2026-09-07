"""
Super Admin: organizations and their administrators.

Everything here is platform-level and gated on ``IsFlipstarUser`` (superuser or
FLIPSTAR realm). Organization users have their own surface in
``organization_campaigns.py`` and cannot reach any of this -- which is the
point: creating organizations, and deciding who administers them, is not
something an organization may do for itself.

Creating an administrator
-------------------------
``create_organization_admin`` builds an ordinary ``auth.User`` through
``create_user``, so the password is hashed by Django's normal machinery and
never stored or echoed in plaintext. Realm, role and organization are set from
the endpoint's own logic, not from the payload, so this is the only way an
account can acquire ORGANIZATION realm -- there is no self-service path.
"""

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from api.models.campaign import Campaign
from api.models.organization import Organization, UserRealm, UserRole
from api.services.realms import RealmValidationError, validate_profile
from common.permissions.realms import IsFlipstarUser

#: Fields Super Admin may set on an organization. An allowlist, so a payload
#: cannot reach anything else -- `created_by`, timestamps and the id are the
#: server's to decide.
ORGANIZATION_FIELDS = ('name', 'code', 'description', 'status', 'contact_email', 'contact_phone')


def serialize_organization(org, *, detail=False):
    data = {
        'id': org.id,
        'name': org.name,
        'code': org.code,
        'description': org.description,
        'status': org.status,
        'contact_email': org.contact_email,
        'contact_phone': org.contact_phone,
        'created_at': org.created_at,
    }
    if detail:
        # Counted in one grouped query by the caller rather than per status
        # here, so a details page is not five round trips.
        counts = Campaign.objects.filter(organization=org).aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='active')),
            completed=Count('id', filter=Q(status='completed')),
            draft=Count('id', filter=Q(status='draft')),
            submitted=Count('id', filter=Q(status='submitted')),
        )
        data['campaign_stats'] = counts
        data['admins'] = [
            {
                'id': profile.user_id,
                'username': profile.user.username,
                'email': profile.user.email,
                'role': profile.role,
                'is_active': profile.user.is_active,
            }
            for profile in org.members.select_related('user').order_by('user__username')
        ]
    return data


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------


@api_view(['GET', 'POST'])
@permission_classes([IsFlipstarUser])
def organization_list_create(request):
    """List organizations, or create one."""
    if request.method == 'GET':
        queryset = Organization.objects.all()

        search = (request.query_params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))

        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        queryset = queryset.annotate(
            _members=Count('members', distinct=True),
            _campaigns=Count('campaigns', distinct=True),
        )

        return Response(
            {
                'count': queryset.count(),
                'results': [
                    {
                        **serialize_organization(org),
                        'member_count': org._members,
                        'campaign_count': org._campaigns,
                    }
                    for org in queryset
                ],
            }
        )

    payload = {field: request.data.get(field) for field in ORGANIZATION_FIELDS}
    if not (payload.get('name') or '').strip():
        return Response({'error': 'name is required.'}, status=status.HTTP_400_BAD_REQUEST)
    if not (payload.get('code') or '').strip():
        return Response({'error': 'code is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        org = Organization.objects.create(
            name=payload['name'].strip(),
            code=payload['code'].strip().upper(),
            description=payload.get('description') or '',
            status=payload.get('status') or 'pending',
            contact_email=payload.get('contact_email') or '',
            contact_phone=payload.get('contact_phone') or '',
            created_by=request.user,
        )
    except IntegrityError:
        # name and code are both unique; the database is the arbiter rather
        # than a pre-check, which would race two simultaneous creates.
        return Response(
            {'error': 'An organization with that name or code already exists.'},
            status=status.HTTP_409_CONFLICT,
        )

    return Response(serialize_organization(org, detail=True), status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH'])
@permission_classes([IsFlipstarUser])
def organization_detail(request, organization_id):
    """One organization, with its admins and campaign statistics."""
    try:
        org = Organization.objects.get(pk=organization_id)
    except Organization.DoesNotExist:
        return Response({'error': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(serialize_organization(org, detail=True))

    changed = []
    for field in ORGANIZATION_FIELDS:
        if field in request.data:
            value = request.data[field]
            setattr(org, field, value.strip().upper() if field == 'code' and value else value)
            changed.append(field)

    if changed:
        try:
            org.save(update_fields=[*changed, 'updated_at'])
        except IntegrityError:
            return Response(
                {'error': 'An organization with that name or code already exists.'},
                status=status.HTTP_409_CONFLICT,
            )

    return Response(serialize_organization(org, detail=True))


@api_view(['GET'])
@permission_classes([IsFlipstarUser])
def organization_campaigns(request, organization_id):
    """Campaigns belonging to one organization.

    Super Admin only. An organization user reads its own campaigns through
    /organization/campaigns/, which scopes by account rather than by an id in
    the URL.
    """
    try:
        org = Organization.objects.get(pk=organization_id)
    except Organization.DoesNotExist:
        return Response({'error': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

    campaigns = Campaign.objects.filter(organization=org).order_by('-created_at')
    return Response(
        {
            'organization': {'id': org.id, 'name': org.name, 'code': org.code},
            'count': campaigns.count(),
            'results': [
                {
                    'id': c.id,
                    'title': c.title,
                    'status': c.status,
                    'campaign_type': c.campaign_type,
                    'total_entries': c.total_entries,
                    'created_at': c.created_at,
                }
                for c in campaigns[:200]
            ],
        }
    )


# ---------------------------------------------------------------------------
# Organization administrators
# ---------------------------------------------------------------------------


@api_view(['POST'])
@permission_classes([IsFlipstarUser])
def create_organization_admin(request, organization_id):
    """Create an administrator account for an organization.

    The account is an ordinary auth.User: ``create_user`` hashes the password,
    and nothing here stores or returns it. Realm, role and organization are set
    by this endpoint, never taken from the payload -- a request cannot make
    itself an organization admin, and cannot attach an account to a different
    organization than the one in the URL.

    The user and the profile move together in one transaction. A signal creates
    the profile on user creation, so a failure while assigning realm would
    otherwise leave a live account with a MEMBER profile and a password its
    intended owner was told to use.
    """
    try:
        org = Organization.objects.get(pk=organization_id)
    except Organization.DoesNotExist:
        return Response({'error': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

    if org.status == 'suspended':
        return Response(
            {'error': 'Cannot add an administrator to a suspended organization.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    username = (request.data.get('username') or '').strip()
    email = (request.data.get('email') or '').strip()
    password = request.data.get('password') or ''
    role = request.data.get('role') or UserRole.ADMIN

    if not username:
        return Response({'error': 'username is required.'}, status=status.HTTP_400_BAD_REQUEST)
    if not password:
        return Response({'error': 'password is required.'}, status=status.HTTP_400_BAD_REQUEST)

    if role not in dict(UserRole.choices):
        return Response({'error': f'Unknown role {role!r}.'}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(username__iexact=username).exists():
        return Response(
            {'error': 'That username is already taken.'}, status=status.HTTP_409_CONFLICT
        )
    if email and User.objects.filter(email__iexact=email).exists():
        return Response(
            {'error': 'That email is already registered.'}, status=status.HTTP_409_CONFLICT
        )

    # Checked before the account exists, so an invalid combination cannot
    # leave a half-configured user behind.
    try:
        validate_profile(UserRealm.ORGANIZATION, role, org)
    except RealmValidationError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            user = User.objects.create_user(username=username, email=email, password=password)
            profile = user.profile
            profile.realm = UserRealm.ORGANIZATION
            profile.role = role
            profile.organization = org
            profile.save(update_fields=['realm', 'role', 'organization'])
    except IntegrityError:
        return Response(
            {'error': 'That username is already taken.'}, status=status.HTTP_409_CONFLICT
        )

    # The password is not echoed back. It was supplied by the caller and is
    # now a hash; returning it would put a live credential in a response body,
    # a log and a browser history for no benefit.
    return Response(
        {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'realm': UserRealm.ORGANIZATION,
            'role': role,
            'organization': {'id': org.id, 'name': org.name, 'code': org.code},
        },
        status=status.HTTP_201_CREATED,
    )
