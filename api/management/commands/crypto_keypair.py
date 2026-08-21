"""
Inspect, or explicitly rotate, the application's Redis-backed identity keypair.

Normal operation needs no operator action: the first process to boot
generates and stores the keypair (infrastructure/keys/service.py), and every
process after that just loads and validates it. This command exists for the
two things that state machine deliberately never does on its own:

    python manage.py crypto_keypair                    # show the current public key
    python manage.py crypto_keypair --rotate --confirm  # replace the keypair

Rotation is a separate, explicit administrative action -- not automatic --
because overwriting the private key invalidates the public key for anyone
who already has it (a client that encrypted to it, a counterparty that
verified a signature from it). The private key is never printed by this
command, in either mode.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from infrastructure.keys import KeyManagementError, key_manager, redis_store
from infrastructure.keys.service import generate_keypair

ALGORITHM = 'X25519'


class Command(BaseCommand):
    help = "Inspect, or explicitly rotate, the application's Redis-backed identity keypair."

    def add_arguments(self, parser):
        parser.add_argument(
            '--rotate', action='store_true',
            help='Generate a new keypair and overwrite the one currently in Redis.',
        )
        parser.add_argument(
            '--confirm', action='store_true',
            help='Required together with --rotate to actually perform the overwrite.',
        )

    def handle(self, *args, **options):
        if options['rotate']:
            self._rotate(confirmed=options['confirm'])
        else:
            self._show_status()

    def _show_status(self):
        try:
            key_manager.initialize()
        except KeyManagementError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.MIGRATE_HEADING('Cryptographic keypair'))
        self.stdout.write(f'  Algorithm  = {ALGORITHM}')
        self.stdout.write(f'  Public key = {key_manager.get_public_key()}')
        self.stdout.write('')
        self.stdout.write('The private key is never printed by this command.')
        self.stdout.write('To replace this keypair: python manage.py crypto_keypair --rotate --confirm')

    def _rotate(self, *, confirmed: bool):
        if not confirmed:
            self.stdout.write(self.style.WARNING(
                'This would generate a NEW keypair and overwrite the one in Redis, '
                'invalidating the current public key for anyone who already has it. '
                'Re-run with --rotate --confirm to actually do this.'
            ))
            return

        public_key, private_key = generate_keypair()
        redis_store.overwrite_both(public_key, private_key)
        key_manager.reset()
        key_manager.initialize()

        self.stdout.write(self.style.SUCCESS('Cryptographic keypair rotated.'))
        self.stdout.write(f'  New public key = {public_key}')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'Restart every application instance now. Each process caches the '
            'keypair in memory and will keep using the old one until it '
            'reloads from Redis.'
        ))
