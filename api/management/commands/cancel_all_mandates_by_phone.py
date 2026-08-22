from django.core.management.base import BaseCommand

from api.integrations.telebirr.direct_debit import telebirr_direct_debit_service
from api.models.subscription import SubscriptionPlan


class Command(BaseCommand):
    help = 'Cancel all active Telebirr mandates for a phone number'

    def add_arguments(self, parser):
        parser.add_argument('phone_number', type=str, help='Phone number to search (e.g., 0911528271)')

    def handle(self, *args, **options):
        phone_number = options['phone_number']

        normalized_phone = phone_number
        if phone_number.startswith('0'):
            normalized_phone = '251' + phone_number[1:]

        self.stdout.write(f"Searching for active Telebirr mandates with phone: {phone_number} (normalized: {normalized_phone})")

        subscriptions = SubscriptionPlan.objects.filter(
            telebirr_phone_number__in=[phone_number, normalized_phone],
            mandate_contract_id__isnull=False,
            mandate_status='active',
        )

        if not subscriptions.exists():
            self.stdout.write(self.style.WARNING(f"No active Telebirr mandates found for phone: {phone_number}"))
            return

        self.stdout.write(f"Found {subscriptions.count()} active mandate(s):")

        for sub in subscriptions:
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"ID: {sub.id}")
            self.stdout.write(f"User: {sub.user.username if sub.user else 'No user'}")
            self.stdout.write(f"Status: {sub.status}")
            self.stdout.write(f"Mandate Contract ID: {sub.mandate_contract_id}")
            self.stdout.write(f"MCT Contract No: {sub.mct_contract_no}")
            self.stdout.write(f"Mandate Status: {sub.mandate_status}")

        self.stdout.write(f"\n{'='*60}")
        response = input(f"Cancel {subscriptions.count()} active mandate(s)? (yes/no): ")

        if response.lower() != 'yes':
            self.stdout.write(self.style.WARNING("Cancellation cancelled"))
            return

        cancelled_count = 0
        failed_count = 0

        for sub in subscriptions:
            self.stdout.write(f"\nCancelling mandate {sub.mandate_contract_id}...")

            result = telebirr_direct_debit_service.cancel_mandate(
                mandate_id=sub.mandate_contract_id, payer_msisdn=normalized_phone,
            )

            if result.get('success'):
                self.stdout.write(self.style.SUCCESS("  Successfully cancelled via Telebirr"))
                sub.mandate_status = 'cancelled'
                sub.save(update_fields=['mandate_status', 'updated_at'])
                cancelled_count += 1
            else:
                self.stdout.write(self.style.ERROR(f"  Failed to cancel via Telebirr: {result.get('error')}"))
                failed_count += 1

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS(f"Cancelled {cancelled_count} mandate(s)"))
        if failed_count > 0:
            self.stdout.write(self.style.WARNING(f"Failed to cancel {failed_count} mandate(s) via Telebirr"))
