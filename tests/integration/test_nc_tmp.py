"""Temporary: decrypt the negative-control error to see what actually happened."""
import json
import pytest
from decimal import Decimal
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from api.models.contest import CoinPackage, UserCoinBalance
from common.security.e2e_encryption import decrypt_payload

pytestmark = pytest.mark.integration


def test_show_error(db, encrypted_client_keys):
    server_public, client_public, client_private = encrypted_client_keys
    u = User.objects.create_user(username='nc_user', password='x')
    p = CoinPackage.objects.create(name='S', price_etb=Decimal('10.00'),
                                   coin_amount=100, bonus_coins=20, is_active=True)
    api = APIClient()
    api.force_authenticate(user=u)
    r = api.post('/api/v1/coins/purchase/', {'package_id': p.id},
                 format='json', HTTP_X_CLIENT_PUBLIC_KEY=client_public)
    print('STATUS', r.status_code)
    body = json.loads(r.content)
    if 'encrypted' in body:
        body = json.loads(decrypt_payload(body['encrypted'], body['nonce'],
                                          server_public, body['checksum'], client_private))
    print('BODY', json.dumps(body)[:500])
    bal, _ = UserCoinBalance.objects.get_or_create(user=u)
    print('BALANCE', bal.balance)
