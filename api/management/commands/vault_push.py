"""
Load secrets from a .env file into Vault.

The one-time migration step. Reads a dotenv file, filters out non-secret
bootstrap keys, and writes the rest to the configured KV v2 path.

Dry run by default; never prints a secret value.

    python manage.py vault_push --env-file .env
    python manage.py vault_push --env-file .env --confirm
    python manage.py vault_push --env-file .env --confirm --merge
"""

from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from infrastructure.secrets.provider import BOOTSTRAP_KEYS
from infrastructure.secrets.vault import VaultClient, VaultUnavailable

#: Keys never written to Vault: they configure Vault itself, select the settings
#: module, or are host-specific rather than secret.
EXCLUDED_KEYS = BOOTSTRAP_KEYS | {
    'DEBUG',
    'DJANGO_ENV',
    'USE_LOCMEM_CACHE',
    'USE_DOCKER_DB',
}

#: Matches `KEY=value`, tolerating `export ` prefixes and inline quotes.
_LINE = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$')


def parse_dotenv(path: Path) -> dict[str, str]:
    """Parse a dotenv file into a mapping. Ignores comments and blank lines."""
    values: dict[str, str] = {}

    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue

        match = _LINE.match(line)
        if not match:
            continue

        key, value = match.group(1), match.group(2).strip()

        # Strip a single layer of matching quotes.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]

        values[key] = value

    return values


class Command(BaseCommand):
    help = 'Write secrets from a .env file into the configured Vault path.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--env-file',
            default='.env',
            help='Path to the dotenv file to read (default: .env).',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Actually write. Without this the command only reports.',
        )
        parser.add_argument(
            '--merge',
            action='store_true',
            help='Merge with existing Vault contents instead of replacing them.',
        )
        parser.add_argument(
            '--include-empty',
            action='store_true',
            help='Also write keys whose value is blank (skipped by default).',
        )

    def handle(self, *args, **options):
        env_path = Path(options['env_file'])
        if not env_path.is_file():
            raise CommandError(f'No such file: {env_path}')

        client = VaultClient.from_env()
        if client is None:
            raise CommandError(
                'VAULT_ADDR is not set, so there is no Vault to write to.\n'
                'Set VAULT_ADDR and either VAULT_TOKEN or '
                'VAULT_ROLE_ID + VAULT_SECRET_ID.'
            )

        parsed = parse_dotenv(env_path)
        if not parsed:
            raise CommandError(f'{env_path} contained no KEY=value pairs.')

        excluded = sorted(k for k in parsed if k in EXCLUDED_KEYS)
        blank = sorted(
            k for k in parsed
            if k not in EXCLUDED_KEYS and not parsed[k] and not options['include_empty']
        )
        payload = {
            k: v for k, v in parsed.items()
            if k not in EXCLUDED_KEYS and (v or options['include_empty'])
        }

        mode = 'WRITE' if options['confirm'] else 'DRY RUN'
        self.stdout.write(self.style.MIGRATE_HEADING(f'vault_push [{mode}]'))
        self.stdout.write(f'  Source        : {env_path}')
        self.stdout.write(f'  Destination   : {client.addr} {client.mount_point}/{client.path}')
        self.stdout.write(f'  Strategy      : {"merge" if options["merge"] else "replace"}')
        self.stdout.write('')
        self.stdout.write(f'  Parsed keys   : {len(parsed)}')
        self.stdout.write(f'  To write      : {len(payload)}')
        self.stdout.write(f'  Excluded      : {len(excluded)}')
        self.stdout.write(f'  Blank skipped : {len(blank)}')

        if excluded:
            self.stdout.write('')
            self.stdout.write('  Excluded (bootstrap / non-secret):')
            for key in excluded:
                self.stdout.write(f'    - {key}')

        if blank:
            self.stdout.write('')
            self.stdout.write('  Skipped (empty value, use --include-empty to write):')
            for key in blank:
                self.stdout.write(f'    - {key}')

        self.stdout.write('')
        self.stdout.write('  Keys to write:')
        for key in sorted(payload):
            self.stdout.write(f'    + {key}')

        if not options['confirm']:
            self.stdout.write('')
            self.stdout.write(
                self.style.WARNING('Dry run - nothing written. Re-run with --confirm.')
            )
            return

        if options['merge']:
            try:
                existing = client.load_or_raise()
            except VaultUnavailable:
                existing = {}
            merged = {**existing, **payload}
        else:
            merged = payload

        try:
            client.write(merged)
        except VaultUnavailable as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError(f'Vault write failed: {exc}') from exc

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Wrote {len(merged)} secrets to {client.mount_point}/{client.path}.'
            )
        )
        self.stdout.write('')
        self.stdout.write('Next steps:')
        self.stdout.write('  1. python manage.py vault_status      # verify resolution')
        self.stdout.write('  2. Remove the secret entries from docker-compose.yml')
        self.stdout.write('  3. Delete the local .env once confirmed working')
