"""
Organizations, and the realm/role vocabulary that decides what an account is.

Why realm lives on UserProfile and not on User
----------------------------------------------
This project uses Django's built-in ``auth.User`` -- there is no
``AUTH_USER_MODEL`` override -- so fields cannot be added to it. ``UserProfile``
is the existing one-to-one extension every other per-user attribute already
uses (coins, points, xp, streak), and it is created by a post_save signal on
User, so every account has one. Realm, role and organization go there for the
same reason, rather than introducing a second user table.

Realm and role are different questions
--------------------------------------
    realm  -- what KIND of account this is. Every user has exactly one.
    role   -- what RESPONSIBILITY the user carries inside that realm.
              Optional; most users have none.

A MEMBER is not "a user without a role"; they are an end user of the app, and
that stays true whether or not they are ever given one. Conflating the two is
how an ordinary member ends up able to approve campaigns.
"""

from django.contrib.auth.models import User
from django.db import models


class UserRealm(models.TextChoices):
    """What kind of account this is.

    FLIPSTAR      platform staff. Operates the product itself.
    MEMBER        an end user of the app. The overwhelming majority, and the
                  safe default -- see the migration for why existing accounts
                  land here rather than being promoted by inference.
    ORGANIZATION  acts on behalf of a company running campaigns. Must be
                  attached to an Organization; enforced in validation and by a
                  database constraint.
    """

    FLIPSTAR = 'FLIPSTAR', 'Flipstar'
    MEMBER = 'MEMBER', 'Member'
    ORGANIZATION = 'ORGANIZATION', 'Organization'


class UserRole(models.TextChoices):
    """An optional responsibility within a realm.

    ADMIN    runs an organization: creates campaigns, manages its content,
             and holds the maker rights needed to do so. Distinct from
             Django's is_staff, which is platform administration -- an
             organization admin administers one organization, not the site.
    MAKER    authors and submits campaigns.
    CHECKER  reviews them.

    Deliberately nullable. "No role" is the normal state, not a gap to be
    filled, and code should read a missing role as "cannot act", never as
    "unrestricted".
    """

    ADMIN = 'ADMIN', 'Administrator'
    MAKER = 'MAKER', 'Maker'
    CHECKER = 'CHECKER', 'Checker'


class Organization(models.Model):
    """A company whose users run campaigns on the platform.

    Campaigns belong to an organization, and that ownership is what scopes
    every read and write an organization user is allowed to perform. It is
    therefore never accepted from a request body -- see
    api/services/realms.py.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
    ]

    name = models.CharField(max_length=200, unique=True)
    # A short stable handle, unique like the name. Useful in URLs, exports and
    # support conversations, where a renamed organization would otherwise
    # break every prior reference.
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text='Short unique identifier, e.g. ABC-CO. Stable across renames.',
    )
    contact_email = models.EmailField(blank=True, default='')
    contact_phone = models.CharField(max_length=32, blank=True, default='')
    description = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # SET_NULL rather than CASCADE: removing the staff member who registered an
    # organization must not delete the organization, its users or its campaigns.
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='organizations_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return self.name

    @property
    def is_active(self):
        return self.status == 'active'
