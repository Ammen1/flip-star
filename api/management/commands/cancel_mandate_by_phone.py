from django.core.management.base import BaseCommand

from api.integrations.telebirr.direct_debit import telebirr_direct_debit_service
from api.models.direct_debit import DirectDebitMandate


class Command(BaseCommand):
    help = 'Cancel all active Direct Debit mandates by phone number'

    def add_arguments(self, parser):
        parser.add_argument('phone_number', type=str, help='Phone number to search (e.g., 0911528271)')

    def handle(self, *args, **options):
        phone_number = options['phone_number']

        normalized_phone = phone_number
        if phone_number.startswith('0'):
            normalized_phone = '251' + phone_number[1:]

        self.stdout.write(f"Searching for Direct Debit mandates with phone: {phone_number} (normalized: {normalized_phone})")

        mandates = DirectDebitMandate.objects.filter(payer_msisdn__in=[phone_number, normalized_phone])

        if not mandates.exists():
            self.stdout.write(self.style.WARNING(f"No Direct Debit mandates found for phone: {phone_number}"))
            return

        self.stdout.write(f"Found {mandates.count()} mandate(s):")

        for mandate in mandates:
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"ID: {mandate.id}")
            self.stdout.write(f"User: {mandate.user.username if mandate.user else 'No user'}")
            self.stdout.write(f"Mandate ID (Telebirr): {mandate.mandate_id or 'N/A'}")
            self.stdout.write(f"Status: {mandate.status}")
            self.stdout.write(f"Payment Type: {mandate.payment_type}")
            self.stdout.write(f"Payer MSISDN: {mandate.payer_msisdn}")
            self.stdout.write(f"Payer Reference: {mandate.payer_reference_number}")
            self.stdout.write(f"Frequency: {mandate.get_frequency_display()}")
            self.stdout.write(f"Start Date: {mandate.first_payment_date}")
            self.stdout.write(f"Expiry Date: {mandate.expiry_date}")
            self.stdout.write(f"Created: {mandate.created_at}")
            self.stdout.write(f"Is Active: {mandate.is_active()}")

        self.stdout.write(f"\n{'='*60}")
        response = input(f"Cancel {mandates.count()} mandate(s)? (yes/no): ")

        if response.lower() != 'yes':
            self.stdout.write(self.style.WARNING("Cancellation cancelled"))
            return

        cancelled_count = 0
        failed_count = 0

        for mandate in mandates:
            self.stdout.write(f"\nCancelling mandate {mandate.id}...")

            if not mandate.mandate_id:
                self.stdout.write(self.style.WARNING("  Skipping Telebirr call - no Telebirr mandate_id; cancelling locally"))
                mandate.cancel()
                cancelled_count += 1
                continue

            if mandate.status == 'cancelled':
                self.stdout.write(self.style.WARNING("  Skipping - already cancelled"))
                continue

            result = telebirr_direct_debit_service.cancel_mandate(
                mandate_id=mandate.mandate_id, payer_msisdn=mandate.payer_msisdn,
            )

            if result.get('success'):
                self.stdout.write(self.style.SUCCESS("  Successfully cancelled via Telebirr"))
            else:
                self.stdout.write(self.style.ERROR(f"  Failed to cancel via Telebirr: {result.get('error')}"))
                self.stdout.write(self.style.WARNING("  Cancelling locally anyway, to stop future local debit attempts"))
            # Cancelled locally either way -- a failed Telebirr call must not
            # leave the mandate active on our side and eligible for the next
            # scheduled debit; see process_telebirr_mandate_deductions.
            mandate.cancel()
            cancelled_count += 1

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS(f"Cancelled {cancelled_count} mandate(s)"))
        if failed_count > 0:
            self.stdout.write(self.style.WARNING(f"Failed to cancel {failed_count} mandate(s) via Telebirr (cancelled locally)"))
