from rest_framework import serializers

from api.models.crm import CRMGiftAuditLog, CRMGiftPackage, CRMGiftTransaction


class CRMGiftPackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CRMGiftPackage
        fields = [
            'id', 'name', 'offering_id', 'description', 'charge_amount',
            'min_level', 'min_coins', 'trigger_condition', 'is_active',
            'max_awards_per_user', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class CRMGiftTransactionSerializer(serializers.ModelSerializer):
    package_name = serializers.CharField(source='package.name', read_only=True, default=None)
    username = serializers.CharField(source='user.username', read_only=True, default=None)

    class Meta:
        model = CRMGiftTransaction
        fields = [
            'id', 'user', 'username', 'phone_number', 'package', 'package_name',
            'offering_id', 'transaction_id', 'charge_amount', 'status',
            'response_message', 'response_code', 'trigger_source', 'campaign_id',
            'created_at', 'completed_at',
        ]
        read_only_fields = [
            'user', 'transaction_id', 'status', 'response_message',
            'response_code', 'created_at', 'completed_at',
        ]


class AwardCRMGiftSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(help_text='User ID to award gift to')
    package_id = serializers.IntegerField(help_text='CRM Package ID to award')
    trigger_source = serializers.CharField(required=False, allow_blank=True, help_text='Source of the award (e.g., campaign_123)')
    campaign_id = serializers.IntegerField(required=False, allow_null=True)


class CRMGiftAuditLogSerializer(serializers.ModelSerializer):
    performed_by_username = serializers.CharField(source='performed_by.username', read_only=True, default=None)

    class Meta:
        model = CRMGiftAuditLog
        fields = ['id', 'transaction', 'action', 'performed_by', 'performed_by_username', 'details', 'ip_address', 'created_at']
        read_only_fields = ['created_at']
