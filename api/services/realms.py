"""
Realm, role and organization ownership rules.

Every question of the form "may this user do this to this campaign?" is
answered here, so that no view has to reimplement it and no two views can
disagree. Views call these; they do not re-derive the rules.

The rule that matters most
--------------------------
An organization user's campaigns are decided by their account, never by their
request. ``organization_for_new_campaign`` returns the owner from the
authenticated user and there is deliberately no code path that reads an
organization id from a request body -- which is what stops:

    POST /campaigns/  {"organization_id": <someone else's>}

from working. A caller supplying that field is not rejected with an error
about it; the field simply has no effect, because nothing reads it.

Reading a missing role
----------------------
``role`` is nullable and most users have none. Everything here treats a
missing role as "cannot act", never as "unrestricted" -- the failure mode of
the opposite reading is an ordinary member approving campaigns.
"""

from api.models.organization import UserRealm, UserRole


class RealmValidationError(ValueError):
    """A realm/role/organization combination that must not be stored."""


# ---------------------------------------------------------------------------
# Reading a user's realm
# ---------------------------------------------------------------------------


def profile_of(user):
    """The user's profile, or None.

    Every account gets one from a post_save signal, but an anonymous request
    or a half-created fixture may not, and a missing profile must read as "no
    privileges" rather than raising.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return None
    return getattr(user, 'profile', None)


def realm_of(user):
    """The user's realm, or None when there is no profile to ask."""
    profile = profile_of(user)
    return getattr(profile, 'realm', None) if profile else None


def role_of(user):
    """The user's role, or None. None means "no role", which grants nothing."""
    profile = profile_of(user)
    return getattr(profile, 'role', None) if profile else None


def organization_of(user):
    """The organization a user belongs to, or None."""
    profile = profile_of(user)
    return getattr(profile, 'organization', None) if profile else None


def is_flipstar(user):
    return realm_of(user) == UserRealm.FLIPSTAR


def is_organization_user(user):
    return realm_of(user) == UserRealm.ORGANIZATION


def is_member(user):
    return realm_of(user) == UserRealm.MEMBER


def is_maker(user):
    return role_of(user) == UserRole.MAKER


def can_author(user):
    """May create, edit and submit campaigns.

    An organization admin runs their organization, which includes authoring
    its campaigns -- so ADMIN carries maker rights. Kept separate from
    ``is_maker`` so that "holds the MAKER role" remains an exact question:
    separation of duties at approval time asks who authored, not who may.
    """
    return is_maker(user) or is_org_admin(user)


def is_checker(user):
    return role_of(user) == UserRole.CHECKER


def is_org_admin(user):
    """Runs an organization.

    Note what this is NOT: Django's ``is_staff``. An organization admin
    administers one organization; a staff account administers the platform.
    Conflating them would give every organization admin the run of the site.
    """
    return role_of(user) == UserRole.ADMIN


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

#: Which roles each realm may carry. Absence from a realm's set means the
#: combination is refused, not merely discouraged.
#:
#: MEMBER holds the empty set: maker and checker are approval responsibilities
#: over campaigns and money, and an ordinary app user has no standing to carry
#: either. If the business ever needs a member-level approver, add it here --
#: one line, one place -- rather than special-casing a view.
ALLOWED_ROLES = {
    UserRealm.FLIPSTAR: {UserRole.ADMIN, UserRole.MAKER, UserRole.CHECKER, None},
    UserRealm.ORGANIZATION: {UserRole.ADMIN, UserRole.MAKER, UserRole.CHECKER, None},
    UserRealm.MEMBER: {None},
}


def validate_profile(realm, role, organization):
    """Check a realm/role/organization triple, raising on anything invalid.

    Called from UserProfile.clean() so both the admin and any ModelForm get it,
    and from the service functions that change these values. The database
    constraint covers the realm/organization half independently -- validation
    is the readable error, the constraint is the guarantee.
    """
    if realm not in dict(UserRealm.choices):
        raise RealmValidationError(f'Unknown realm {realm!r}.')

    normalised_role = role or None
    if normalised_role is not None and normalised_role not in dict(UserRole.choices):
        raise RealmValidationError(f'Unknown role {role!r}.')

    allowed = ALLOWED_ROLES.get(realm, {None})
    if normalised_role not in allowed:
        names = ', '.join(sorted(r for r in allowed if r)) or 'no role'
        raise RealmValidationError(
            f'A {realm} account may not hold the {normalised_role} role. Allowed: {names}.'
        )

    # The invariant the whole ownership model rests on: an organization user
    # with no organization could neither be scoped to anything nor excluded
    # from anything.
    if realm == UserRealm.ORGANIZATION and organization is None:
        raise RealmValidationError('An ORGANIZATION account must belong to an organization.')

    # And the converse. A member or staff account carrying an organization
    # would be silently inside that organization's data scope.
    if realm != UserRealm.ORGANIZATION and organization is not None:
        raise RealmValidationError(f'A {realm} account must not belong to an organization.')


# ---------------------------------------------------------------------------
# Campaign ownership
# ---------------------------------------------------------------------------


def organization_for_new_campaign(user, requested_organization_id=None):
    """The organization a campaign created by ``user`` must belong to.

    Derived from the account. Returns None for a Flipstar user, which is what
    a platform-owned campaign looks like.

    This function is the reason an organization user cannot choose their own
    owner: callers take the answer from here, and for such a user nothing
    reads an organization id out of request data.

    ``requested_organization_id`` is honoured ONLY for platform staff, so that
    Super Admin can create a campaign on an organization's behalf from the
    dashboard. For an organization user it is ignored entirely -- their own
    organization is returned whatever the request said, which is what stops
    one organization creating campaigns under another.
    """
    # Super Admin picking an organization from the create-campaign form.
    #
    # This is the ONE place an organization id from a request is honoured, and
    # it is gated on being platform staff. The organization-user branch below
    # never consults it, so the parameter is inert for them. That asymmetry is
    # the point: one endpoint serves both, and only one of them may choose.
    if requested_organization_id is not None and (
        getattr(user, 'is_superuser', False) or is_flipstar(user)
    ):
        from api.models.organization import Organization

        try:
            return Organization.objects.get(pk=requested_organization_id)
        except Organization.DoesNotExist as exc:
            raise RealmValidationError('The selected organization does not exist.') from exc

    if is_organization_user(user):
        organization = organization_of(user)
        if organization is None:
            # Should be unreachable -- validation and the database constraint
            # both forbid it -- but an ownerless campaign is worse than a
            # refused request, so this is checked rather than assumed.
            raise RealmValidationError(
                'This account is an organization account but has no organization.'
            )
        return organization

    if is_flipstar(user):
        return None

    raise RealmValidationError('This account may not create campaigns.')


def can_create_campaign(user):
    """Who may create a campaign at all.

    Requires a maker role in either realm that runs campaigns. A Flipstar
    account without a role gets nothing here by default -- per the requirement
    that not every staff member is automatically a campaign author -- while
    superusers keep the blanket access the rest of the admin surface gives
    them.
    """
    if getattr(user, 'is_superuser', False):
        return True

    # Backward compatibility, deliberately kept.
    #
    # This endpoint was guarded by IsAdminUser (is_staff) before realms
    # existed, and the admin dashboard's Create Campaign button still calls
    # it. Every pre-existing account migrates to realm=MEMBER, so checking
    # realm alone would refuse every staff admin who is not also a superuser
    # -- breaking a working screen for reasons invisible from it.
    #
    # This is a compatibility bridge, not the intended end state. Once staff
    # accounts carry FLIPSTAR + MAKER, drop this branch so that campaign
    # authorship is granted explicitly rather than inherited from is_staff.
    if getattr(user, 'is_staff', False):
        return True

    if not (is_flipstar(user) or is_organization_user(user)):
        return False
    return can_author(user)


def can_review_campaign(user, campaign):
    """Who may approve or reject a submitted campaign.

    Three conditions, all required:

      * a checker role -- makers author, checkers review
      * the campaign is inside the user's own scope
      * the reviewer is not the author (separation of duties)

    The last is the one worth stating plainly: a maker who is also a checker
    must not be able to wave through their own campaign, because an approval
    step that the author can perform is not an approval step.
    """
    if not is_checker(user):
        return False
    if not can_access_campaign(user, campaign):
        return False
    return not is_own_work(user, campaign)


def is_own_work(user, campaign):
    """True when this user authored or submitted the campaign."""
    user_id = getattr(user, 'id', None)
    return user_id is not None and user_id in {
        campaign.created_by_id,
        campaign.submitted_by_id,
    }


def can_access_campaign(user, campaign):
    """Whether ``user`` may see this campaign at all.

    Organization isolation lives here. An organization user sees their own
    organization's campaigns and nothing else; platform campaigns
    (organization NULL) are not theirs either.
    """
    if getattr(user, 'is_superuser', False):
        return True
    if is_flipstar(user):
        return True
    if is_organization_user(user):
        organization = organization_of(user)
        return organization is not None and campaign.organization_id == organization.id
    return False


def can_modify_campaign(user, campaign):
    """Whether ``user`` may edit or delete this campaign.

    Access plus authorship rights: being able to read an organization's
    campaigns does not imply being able to change them.
    """
    if getattr(user, 'is_superuser', False):
        return True
    if not can_access_campaign(user, campaign):
        return False
    return can_author(user) or is_flipstar(user)


def visible_campaigns(user, queryset):
    """Narrow a campaign queryset to what ``user`` is allowed to see.

    Filtering the queryset rather than checking objects one at a time is what
    keeps list endpoints from leaking another organization's campaigns through
    pagination counts, search results or analytics aggregates.
    """
    if getattr(user, 'is_superuser', False) or is_flipstar(user):
        return queryset
    if is_organization_user(user):
        organization = organization_of(user)
        if organization is None:
            return queryset.none()
        return queryset.filter(organization=organization)
    # Members do not administer campaigns. Public browsing of campaigns goes
    # through the existing public endpoints, which are unchanged.
    return queryset.none()


__all__ = [
    'ALLOWED_ROLES',
    'RealmValidationError',
    'can_access_campaign',
    'can_create_campaign',
    'can_modify_campaign',
    'can_review_campaign',
    'can_author',
    'is_checker',
    'is_flipstar',
    'is_org_admin',
    'is_maker',
    'is_member',
    'is_organization_user',
    'is_own_work',
    'organization_for_new_campaign',
    'organization_of',
    'profile_of',
    'realm_of',
    'role_of',
    'validate_profile',
    'visible_campaigns',
]
