"""
Report how configuration is currently being resolved.

Shows whether Vault is reachable, which source supplies each expected key, and
which required keys are missing. Never prints a secret value.

    python manage.py vault_status
    python manage.py vault_status --show-sources
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from infrastructure.secrets import default_provider as provider
from infrastructure.secrets.vault import VaultClient, VaultUnavailable

#: Keys the backend cannot run without in production.
REQUIRED_KEYS = [
    'SECRET_KEY',
    'ALLOWED_HOSTS',
    'DB_NAME',
    'DB_USER',
    'DB_PASSWORD',
    'DB_HOST',
]

#: Keys required only by a given integration. Absence disables that integration
#: rather than stopping the service.
INTEGRATION_KEYS = {
    'Telebirr direct debit': [
        'TELEBIRR_SOAP_URL',
        'TELEBIRR_THIRD_PARTY_ID',
        'TELEBIRR_THIRD_PARTY_PASSWORD',
        'TELEBIRR_SP_OPERATOR_ID',
        'TELEBIRR_SP_OPERATOR_CREDENTIAL',
    ],
    'Telebirr checkout': [
        'TELEBIRR_BASE_URL',
        'TELEBIRR_MERCHANT_CODE',
        'TELEBIRR_PRIVATE_KEY',
        'TELEBIRR_PUBLIC_KEY',
    ],
    'TIMWE SMS (SMPP)': [
        'TIMWE_SMPP_HOST',
        'TIMWE_SMPP_PORT',
        'TIMWE_SMPP_SYSTEM_ID',
        'TIMWE_SMPP_PASSWORD',
    ],
    'Object storage': [
        'ACCESS_KEY_ID',
        'SECRET_ACCESS_KEY',
        'STORAGE_BUCKET_NAME',
    ],
    'Web Push': [
        'VAPID_PUBLIC_KEY',
        'VAPID_PRIVATE_KEY',
    ],
}


class Command(BaseCommand):
    help = 'Report Vault connectivity and where each configuration key resolves from.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--show-sources',
            action='store_true',
            help='List the resolution source for every known key.',
        )

    def handle(self, *args, **options):
        summary = provider.describe()

        self.stdout.write(self.style.MIGRATE_HEADING('Secret resolution'))
        self.stdout.write(f'  Vault enabled  : {summary["vault_enabled"]}')
        self.stdout.write(f'  Vault required : {summary["vault_required"]}')
        self.stdout.write(f'  Precedence     : {summary["precedence"]} wins over the other')

        if summary['vault_enabled']:
            self.stdout.write(f'  Vault address  : {summary["vault_addr"]}')
            self.stdout.write(f'  Secret path    : {summary["vault_path"]}')
            self._report_connectivity()
            self.stdout.write(f'  Keys in Vault  : {summary["vault_key_count"]}')
        else:
            self.stdout.write(
                self.style.WARNING(
                    '  VAULT_ADDR is unset — resolving from environment and .env only.'
                )
            )

        self.stdout.write('')
        self._report_required()
        self._report_integrations()

        if options['show_sources']:
            self.stdout.write('')
            self._report_sources()

    # -- sections ------------------------------------------------------------

    def _report_connectivity(self):
        client = VaultClient.from_env()
        if client is None:  # pragma: no cover - guarded by caller
            return
        try:
            health = client.health()
        except VaultUnavailable as exc:
            self.stdout.write(self.style.ERROR(f'  Connectivity   : FAILED — {exc}'))
            return
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'  Connectivity   : FAILED — {exc}'))
            return

        state = 'OK' if health['authenticated'] else 'NOT AUTHENTICATED'
        style = self.style.SUCCESS if health['authenticated'] else self.style.ERROR
        self.stdout.write(style(f'  Connectivity   : {state} (auth: {health["auth_method"]})'))

    def _report_required(self):
        self.stdout.write(self.style.MIGRATE_HEADING('Required keys'))
        missing = []
        for key in REQUIRED_KEYS:
            source = provider.source_of(key)
            if source == 'unset':
                missing.append(key)
                self.stdout.write(self.style.ERROR(f'  {key:<32} MISSING'))
            else:
                self.stdout.write(f'  {key:<32} {source}')

        if missing:
            self.stdout.write(
                self.style.ERROR(
                    f'\n  {len(missing)} required key(s) missing. '
                    'Production will refuse to start.'
                )
            )

    def _report_integrations(self):
        self.stdout.write('')
        self.stdout.write(self.style.MIGRATE_HEADING('Integrations'))
        for name, keys in INTEGRATION_KEYS.items():
            resolved = [k for k in keys if provider.source_of(k) != 'unset']
            if len(resolved) == len(keys):
                self.stdout.write(self.style.SUCCESS(f'  {name:<26} configured'))
            elif resolved:
                absent = ', '.join(k for k in keys if provider.source_of(k) == 'unset')
                self.stdout.write(self.style.WARNING(f'  {name:<26} PARTIAL — missing: {absent}'))
            else:
                self.stdout.write(f'  {name:<26} not configured')

    def _report_sources(self):
        self.stdout.write(self.style.MIGRATE_HEADING('All known keys'))
        seen = set()
        for key in REQUIRED_KEYS + [k for keys in INTEGRATION_KEYS.values() for k in keys]:
            if key in seen:
                continue
            seen.add(key)
            self.stdout.write(f'  {key:<36} {provider.source_of(key)}')
