"""
Check the TIMWE chargeAmount integration from inside a running pod.

Safe by default. With no flags it charges nothing: it reports which settings
are present (names, never secret values), builds a request to prove they are
consistent, and opens a TCP connection to the configured endpoint -- from the
pod, which is what matters. The host's network is not the pod's, and a
`telnet` from the node proves nothing about egress from a container.

    python manage.py timwe_charge_check

A real charge needs every one of --charge, --msisdn, --amount, --username and
--confirm. It goes through the same service as production, so it is recorded
as a TimweChargeTransaction and protected by an idempotency key:

    python manage.py timwe_charge_check --charge --msisdn 2519XXXXXXXX \\
        --amount 1 --username some_staff_user --confirm

The number is taken as input, never from source, and is masked in output.

Reconciliation -- never charges anything:

    python manage.py timwe_charge_check --reconcile [--hours 24]

lists every charge still needing a human: PENDING, TIMEOUT or UNKNOWN (the
subscriber may or may not have paid), and SUCCESS not yet applied (paid, but
the renewal or coins not yet delivered). Each row carries the reference code to
quote to TIMWE. It also summarises recent charging by purpose and outcome.
"""

import socket
import uuid
from urllib.parse import urlparse

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from api.integrations.timwe.charge import TimweChargeService
from api.integrations.timwe.errors import TimweConfigurationError, TimweError
from api.models.timwe import TimweChargeTransaction


def _mask(number):
    digits = ''.join(ch for ch in str(number) if ch.isdigit())
    return f'{digits[:5]}****{digits[-3:]}' if len(digits) > 6 else digits


class Command(BaseCommand):
    help = 'Verify TIMWE chargeAmount configuration and connectivity; optionally charge once.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--charge', action='store_true', help='Perform ONE real charge. Costs money.'
        )
        parser.add_argument('--msisdn', help='Number to charge. Must be approved for testing.')
        parser.add_argument('--amount', help='Whole-currency amount. Use the minimum.')
        parser.add_argument(
            '--username', help='Account the charge is attributed to (recorded on the row).'
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Required with --charge. No confirmation, no charge.',
        )
        parser.add_argument(
            '--reconcile',
            action='store_true',
            help='List pending, ambiguous and unapplied charges for reconciliation. Charges nothing.',
        )
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='With --reconcile: the window the summary covers. Default 24.',
        )

    def handle(self, *args, **options):
        if options['reconcile']:
            if options['charge']:
                raise CommandError('--reconcile never charges; do not combine it with --charge.')
            self._reconcile(hours=max(1, options['hours']))
            return

        ok = self._check_configuration()
        if ok:
            ok = self._check_request_builds() and ok
            ok = self._check_connectivity() and ok

        if not options['charge']:
            self.stdout.write('')
            self.stdout.write(
                'No charge made. Re-run with --charge --msisdn --amount --username --confirm '
                'to charge once.'
            )
            if not ok:
                raise CommandError('Checks failed; fix the items above before charging.')
            return

        if not ok:
            raise CommandError('Refusing to charge: the checks above did not pass.')
        self._charge_once(options)

    # -- checks --------------------------------------------------------------

    def _check_configuration(self):
        self.stdout.write(self.style.MIGRATE_HEADING('Configuration'))
        missing = TimweChargeService.missing_configuration()
        for name, present in (
            ('TIMWE_CHARGE_URL', bool(TimweChargeService.get_endpoint())),
            ('TIMWE_SP_ID', bool(TimweChargeService.get_sp_id())),
            ('TIMWE_SP_PASSWORD', bool(TimweChargeService.get_sp_account_password())),
            ('TIMWE_SERVICE_ID', bool(TimweChargeService.get_service_id())),
            ('TIMWE_CURRENCY', bool(TimweChargeService.get_currency())),
        ):
            # Presence only. The password is never printed, and neither is the
            # SP ID -- it is half of the digest input.
            mark = self.style.SUCCESS('set') if present else self.style.ERROR('MISSING')
            self.stdout.write(f'  {name:22} {mark}')

        from django.conf import settings

        for flag in (
            'TIMWE_CHARGING_ENABLED',
            'TIMWE_SUBSCRIPTION_RENEWAL_ENABLED',
            'TIMWE_AIRTIME_PURCHASE_ENABLED',
        ):
            on = bool(getattr(settings, flag, False))
            mark = self.style.WARNING('ON') if on else 'off'
            self.stdout.write(f'  {flag:34} {mark}')

        endpoint = TimweChargeService.get_endpoint()
        if endpoint:
            self.stdout.write(f'  endpoint               {endpoint}')
        currency = TimweChargeService.get_currency()
        if currency:
            self.stdout.write(f'  currency               {currency}')

        try:
            timeout = TimweChargeService.get_timeout()
            self.stdout.write(f'  TIMWE_CHARGE_TIMEOUT   {timeout}s')
        except TimweConfigurationError as exc:
            self.stdout.write(self.style.ERROR(f'  {exc}'))
            return False

        ok = True
        # Reported whatever else is missing: a placeholder or SMPP address is
        # the mistake to catch before anyone sets the remaining values.
        problem = TimweChargeService.endpoint_problem()
        if problem:
            self.stdout.write(self.style.ERROR(f'  {problem}'))
            ok = False

        # A warning, not a refusal: TIMWE may confirm the two are the same. The
        # point is that nobody assumes it. Compared, never printed.
        smpp_password = getattr(settings, 'TIMWE_SMPP_PASSWORD', '') or ''
        if smpp_password and TimweChargeService.get_sp_account_password() == smpp_password:
            self.stdout.write(
                self.style.WARNING(
                    '  TIMWE_SP_PASSWORD is the same as the SMPP password. Confirm with TIMWE '
                    'that AmountCharging uses it -- they are separate credentials.'
                )
            )

        if missing:
            self.stdout.write(
                self.style.ERROR(
                    '  TIMWE_CHARGE_URL and the charging credentials come from TIMWE. '
                    'They are not the SMPP host or password.'
                )
            )
            ok = False
        return ok

    def _check_request_builds(self):
        """Build a request without sending it, to prove the values agree."""
        self.stdout.write(self.style.MIGRATE_HEADING('Request'))
        try:
            TimweChargeService.build_soap_request(
                msisdn='251900000000',
                amount=1,
                description='configuration check',
                reference_code='CHECK',
            )
        except (TimweError, TimweConfigurationError) as exc:
            self.stdout.write(self.style.ERROR(f'  cannot build a request: {exc}'))
            return False
        self.stdout.write(self.style.SUCCESS('  builds cleanly (not sent)'))
        return True

    def _check_connectivity(self):
        """Open and close a TCP connection. No HTTP, so nothing is charged."""
        self.stdout.write(self.style.MIGRATE_HEADING('Connectivity (from this pod)'))
        parsed = urlparse(TimweChargeService.get_endpoint())
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if not host:
            self.stdout.write(self.style.ERROR('  TIMWE_CHARGE_URL has no host.'))
            return False
        try:
            with socket.create_connection((host, port), timeout=10):
                pass
        except OSError as exc:
            self.stdout.write(self.style.ERROR(f'  {host}:{port} unreachable: {exc}'))
            return False
        self.stdout.write(self.style.SUCCESS(f'  {host}:{port} reachable'))
        return True

    # -- reconciliation ------------------------------------------------------

    def _reconcile(self, *, hours):
        """Report what needs a human. Reads only; nothing here can charge."""
        from datetime import timedelta

        from django.db.models import Avg, Count, Q
        from django.utils import timezone

        needs_attention = (
            TimweChargeTransaction.objects.filter(
                Q(status__in=('pending', 'timeout', 'unknown'))
                | Q(
                    status='success',
                    fulfilled_at__isnull=True,
                    purpose__in=(
                        TimweChargeTransaction.PURPOSE_SUBSCRIPTION_RENEWAL,
                        TimweChargeTransaction.PURPOSE_COIN_PURCHASE,
                    ),
                )
            )
            .select_related('user')
            .order_by('created_at')
        )

        self.stdout.write(self.style.MIGRATE_HEADING('Needs reconciliation (nothing is charged)'))
        rows = list(needs_attention)
        if not rows:
            self.stdout.write(self.style.SUCCESS('  nothing pending, ambiguous or unapplied'))
        for row in rows:
            state = 'PAID, NOT APPLIED' if row.status == 'success' else row.status.upper()
            self.stdout.write(
                f'  {row.id}  {row.purpose or "-":20} user={row.user_id} '
                f'{int(row.amount)} {row.currency}  ref={row.reference_code}  '
                f'{row.created_at:%Y-%m-%d %H:%M}  {state}  '
                f'timwe_error={row.error_code or "-"}  msisdn={row.masked_msisdn}'
            )

        since = timezone.now() - timedelta(hours=hours)
        recent = TimweChargeTransaction.objects.filter(created_at__gte=since)
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING(f'Last {hours}h by purpose and status'))
        summary = recent.values('purpose', 'status').annotate(n=Count('id')).order_by('purpose')
        for line in summary:
            self.stdout.write(f'  {line["purpose"] or "-":20} {line["status"]:8} {line["n"]}')
        latency = recent.exclude(duration_ms__isnull=True).aggregate(avg=Avg('duration_ms'))['avg']
        self.stdout.write(f'  average latency     {int(latency) if latency else "-"} ms')
        codes = (
            recent.exclude(error_code='')
            .values('error_code')
            .annotate(n=Count('id'))
            .order_by('-n')[:5]
        )
        for code in codes:
            self.stdout.write(f'  timwe error {code["error_code"]:8} {code["n"]}')

    # -- the one real charge -------------------------------------------------

    def _charge_once(self, options):
        from api.services.timwe_charging import ChargeRefused, request_charge, user_message

        for flag in ('msisdn', 'amount', 'username'):
            if not options[flag]:
                raise CommandError(f'--{flag} is required with --charge.')
        if not options['confirm']:
            raise CommandError('Refusing to charge without --confirm. This costs real money.')
        if not TimweChargeService.charging_enabled():
            raise CommandError(
                'Not charged: TIMWE_CHARGING_ENABLED is off. Switch it on only once TIMWE has '
                'confirmed the AmountCharging endpoint, the charging credentials and the '
                'authentication mode.'
            )

        user = User.objects.filter(username=options['username']).first()
        if user is None:
            raise CommandError(f'No user named {options["username"]!r}.')

        key = f'staging-check-{uuid.uuid4().hex}'
        self.stdout.write(self.style.MIGRATE_HEADING('Charging once'))
        self.stdout.write(f'  msisdn          {_mask(options["msisdn"])}')
        self.stdout.write(f'  amount          {options["amount"]}')
        self.stdout.write(f'  idempotency key {key}')

        try:
            result = request_charge(
                user=user,
                msisdn=options['msisdn'],
                amount=options['amount'],
                description='FlipStar staging charge check',
                idempotency_key=key,
                purpose=TimweChargeTransaction.PURPOSE_MANUAL_CHECK,
            )
        except (ChargeRefused, TimweConfigurationError) as exc:
            raise CommandError(f'Not charged: {exc}') from exc

        row = result.transaction
        style = self.style.SUCCESS if result.succeeded else self.style.WARNING
        self.stdout.write(style(f'  status          {row.status}'))
        self.stdout.write(f'  outcome         {row.outcome}')
        self.stdout.write(f'  reference_code  {row.reference_code}')
        self.stdout.write(f'  http_status     {row.http_status}')
        self.stdout.write(f'  timwe error     {row.error_code or "-"}')
        self.stdout.write(f'  duration        {row.duration_ms} ms')
        self.stdout.write(f'  message         {row.error_message or "-"}')
        self.stdout.write('')
        self.stdout.write(f'  user would see: {user_message(result)}')
        if result.is_ambiguous:
            self.stdout.write(
                self.style.WARNING(
                    '  AMBIGUOUS -- do not charge again. Reconcile reference_code with TIMWE.'
                )
            )
