"""
DRF permissions for realm, role and organization ownership.

These sit alongside the existing classes in ``roles.py`` and follow the same
shape: a ``BasePermission`` subclass whose decisions come from a service layer
rather than from logic inlined in a view. The rules themselves live in
``api/services/realms.py``; this module only adapts them to DRF.

Object permissions are the important half
-----------------------------------------
``has_permission`` can only answer "may this kind of user reach this endpoint".
Organization isolation is a question about a specific row -- may THIS user see
THIS campaign -- so it is answered in ``has_object_permission``, and a view
that forgets to call ``check_object_permissions`` gets no isolation at all.
For list endpoints there is no object to check, which is why
``visible_campaigns`` filters the queryset instead: a permission class cannot
stop a list view from counting rows it should never have selected.
"""

from rest_framework.permissions import BasePermission

from api.services.realms import (
    can_access_campaign,
    can_create_campaign,
    can_modify_campaign,
    can_review_campaign,
    is_flipstar,
    is_organization_user,
)


class IsFlipstarUser(BasePermission):
    """Platform staff only."""

    message = 'This action is restricted to Flipstar staff.'

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return bool(user.is_superuser or is_flipstar(user))


class IsOrganizationUser(BasePermission):
    """Members of an organization only."""

    message = 'This action is restricted to organization accounts.'

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return is_organization_user(user)


class CanCreateCampaign(BasePermission):
    """May author a campaign.

    Requires a maker role in a realm that runs campaigns. Notably this does NOT
    pass every Flipstar account: staff are not automatically campaign authors,
    per the requirement that maker/checker be granted rather than assumed.
    Superusers still pass, matching their access everywhere else in the admin.
    """

    message = 'You do not have permission to create campaigns.'

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return can_create_campaign(user)


class CanAccessCampaign(BasePermission):
    """Read access to one campaign, scoped by organization.

    An organization user reaches their own organization's campaigns and
    nothing else -- not another organization's, and not the platform's.
    """

    message = 'You do not have access to this campaign.'

    def has_object_permission(self, request, view, obj) -> bool:
        return can_access_campaign(request.user, obj)


class CanModifyCampaign(BasePermission):
    """Edit or delete one campaign.

    Strictly narrower than access: being able to read an organization's
    campaigns does not imply being able to change them.
    """

    message = 'You do not have permission to modify this campaign.'

    def has_object_permission(self, request, view, obj) -> bool:
        return can_modify_campaign(request.user, obj)


class CanReviewCampaign(BasePermission):
    """Approve or reject one campaign.

    Carries the separation-of-duties rule: a checker who also authored or
    submitted the campaign is refused, so an approval step is never something
    the author can perform on their own work.
    """

    message = (
        'You cannot review this campaign. Reviewing requires the checker role, '
        'and a campaign cannot be approved by the person who created it.'
    )

    def has_object_permission(self, request, view, obj) -> bool:
        return can_review_campaign(request.user, obj)


__all__ = [
    'CanAccessCampaign',
    'CanCreateCampaign',
    'CanModifyCampaign',
    'CanReviewCampaign',
    'IsFlipstarUser',
    'IsOrganizationUser',
]
