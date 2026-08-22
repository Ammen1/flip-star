from django.core.management.base import BaseCommand

from api.integrations.telebirr.direct_debit import telebirr_direct_debit_service
from api.models.subscription import SubscriptionPlan


class Command(BaseCommand):
    help = 'Cancel Telebirr mandates by mandate_contract_id from SubscriptionPlan'

    def add_arguments(self, parser):
        parser.add_argument('mandate_contract_id', type=str, help='Mandate contract ID to cancel (e.g., 599941)')
        parser.add_argument('--force', action='store_true', help='Cancel without confirmation')

    def handle(self, *args, **options):
        mandate_contract_id = options['mandate_contract_id']
        force = options.get('force', False)

        self.stdout.write(f"Searching for subscriptions with mandate_contract_id: {mandate_contract_id}")

        subscriptions = SubscriptionPlan.objects.filter(mandate_contract_id=mandate_contract_id)

        if not subscriptions.exists():
            self.stdout.write(self.style.WARNING(f"No subscriptions found with mandate_contract_id: {mandate_contract_id}"))
            return

        self.stdout.write(f"Found {subscriptions.count()} subscription(s):")

        for sub in subscriptions:
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"ID: {sub.id}")
            self.stdout.write(f"User: {sub.user.username if sub.user else 'No user'}")
            self.stdout.write(f"Status: {sub.status}")
            self.stdout.write(f"Payment Method: {sub.payment_method}")
            self.stdout.write(f"Mandate Contract ID: {sub.mandate_contract_id}")
            self.stdout.write(f"MCT Contract No: {sub.mct_contract_no}")
            self.stdout.write(f"Mandate Status: {sub.mandate_status}")
            self.stdout.write(f"Telebirr Phone: {sub.telebirr_phone_number}")

        if not force:
            self.stdout.write(f"\n{'='*60}")
            response = input(f"Cancel Telebirr mandate {mandate_contract_id}? (yes/no): ")
            if response.lower() != 'yes':
                self.stdout.write(self.style.WARNING("Cancellation cancelled"))
                return

        sub = subscriptions.first()
        phone_number = sub.telebirr_phone_number

        if not phone_number:
            self.stdout.write(self.style.ERROR("No phone number found in subscription"))
            return

        normalized_phone = phone_number
        if phone_number.startswith('0'):
            normalized_phone = '251' + phone_number[1:]

        self.stdout.write(f"\nCancelling Telebirr mandate {mandate_contract_id} for phone {normalized_phone}...")

        result = telebirr_direct_debit_service.cancel_mandate(
            mandate_id=mandate_contract_id, payer_msisdn=normalized_phone,
        )

        if result.get('success'):
            self.stdout.write(self.style.SUCCESS(f"Successfully cancelled Telebirr mandate {mandate_contract_id}"))
            for sub in subscriptions:
                sub.mandate_status = 'cancelled'
                sub.save(update_fields=['mandate_status', 'updated_at'])
                self.stdout.write(f"  Updated subscription {sub.id} mandate_status to 'cancelled'")
        else:
            self.stdout.write(self.style.ERROR(f"Failed to cancel Telebirr mandate: {result.get('error')}"))
            self.stdout.write(self.style.WARNING("You may need to contact Telebirr support to cancel this mandate manually"))
