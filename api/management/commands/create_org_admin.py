"""
Create an organization and its administrator in one step.

Why a command rather than the API
---------------------------------
The API endpoint for this is Super-Admin-only, which is correct -- appointing
organization administrators is a platform act. But that leaves a chicken and
egg on a fresh install: there is no organization to log into and no UI path to
the first one. This command is the way in, run by whoever has shell access.

Idempotent
----------
Re-running with the same values updates rather than duplicating: the
organization is matched on its code, the user on their username. So it is safe
to run again after a failed attempt, and safe to use to reset a forgotten
password.

Passwords
---------
``--password`` has no default, deliberately -- the same reasoning as
create_superadmin, where a defaulted literal once created accounts with a
password published in this repository. The password is hashed by create_user
and never printed back.
"""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models.organization import Organization, UserRealm, UserRole


class Command(BaseCommand):
    help = 'Create an organization and an ORGANIZATION-realm administrator for it.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--org-name', required=True, help='Organization name, e.g. "ABC Company".'
        )
        parser.add_argument(
            '--org-code',
            required=True,
            help='Short unique code, e.g. ABC. Upper-cased automatically.',
        )
        parser.add_argument(
            '--username', required=True, help='Login username for the administrator.'
        )
        parser.add_argument(
            '--password', required=True, help='Login password. Hashed, never stored in plain text.'
        )
        parser.add_argument('--email', default='', help='Optional email address.')
        parser.add_argument(
            '--role',
            default=UserRole.ADMIN,
            choices=[choice[0] for choice in UserRole.choices],
            help='Role within the organization (default: ADMIN).',
        )
        parser.add_argument(
            '--status',
            default='active',
            choices=['active', 'pending', 'suspended'],
            help='Organization status (default: active). A suspended organization cannot be edited by its own admin.',
        )

    def handle(self, *args, **options):
        org_name = options['org_name'].strip()
        org_code = options['org_code'].strip().upper()
        username = options['username'].strip()
        password = options['password']
        email = (options['email'] or '').strip()
        role = options['role']
        status = options['status']

        if not password:
            raise CommandError('--password is required.')

        # Everything below is one transaction, so a rejected realm/role
        # combination rolls the organization and the user back with it rather
        # than leaving either half-created.
        with transaction.atomic():
            organization, org_created = Organization.objects.update_or_create(
                code=org_code,
                defaults={'name': org_name, 'status': status},
            )

            user = User.objects.filter(username__iexact=username).first()
            if user is None:
                user = User.objects.create_user(username=username, email=email, password=password)
                user_created = True
            else:
                # Re-running is how a forgotten password gets reset, so the
                # password is applied either way.
                user.set_password(password)
                if email:
                    user.email = email
                user.save()
                user_created = False

            profile = user.profile
            profile.realm = UserRealm.ORGANIZATION
            profile.role = role
            profile.organization = organization
            # full_clean runs the realm/role/organization rules from
            # api/services/realms.py. Surfaced as a CommandError so an operator
            # gets the reason rather than a traceback.
            try:
                profile.full_clean()
            except ValidationError as exc:
                raise CommandError('; '.join(exc.messages)) from exc
            profile.save(update_fields=['realm', 'role', 'organization'])

        self.stdout.write(
            self.style.SUCCESS(
                f'{"Created" if org_created else "Updated"} organization '
                f'{organization.name} ({organization.code}), status={organization.status}'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'{"Created" if user_created else "Updated"} user {user.username} '
                f'-- realm=ORGANIZATION role={role}'
            )
        )
        self.stdout.write('')
        self.stdout.write('Sign in at the admin dashboard with that username and password.')
        self.stdout.write(
            'The account is not staff, so it lands on the organization dashboard '
            'rather than the Super Admin console.'
        )
