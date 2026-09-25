"""
Telebirr H5 / SuperApp Payment Gateway (Fabric) Integration Service.

Implements the documented InApp H5 flow:
  1. applyFabricToken   POST /payment/v1/token
  2. preOrder (create)  POST /payment/v1/merchant/preOrder  -> prepay_id
  3. build rawRequest   (signed string handed to js_fun_start_pay on the H5 page)
  4. notify (webhook)    SP -> our notify_url (verify sign with SP public key)
  5. queryOrder         POST /payment/v1/merchant/queryOrder

Request signing follows the "RequestSignatureProcess":
  - flatten top-level + biz_content fields (excluding sign/sign_type/etc.)
  - sort keys alphabetically (ascii)
  - join as key=value with '&'
  - sign with RSA-PSS, SHA-256 digest, MGF1(SHA-256) -> i.e. SHA256withRSAandMGF1
"""

import base64
import json
import logging
import time
import uuid

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from django.conf import settings

logger = logging.getLogger(__name__)

# Fields that never participate in the signature string.
_EXCLUDE_FIELDS = {
    'sign',
    'sign_type',
    'header',
    'refund_info',
    'openType',
    'raw_request',
    'biz_content',
    'wallet_reference_data',
}


class TelebirrService:
    """Telebirr H5 (Fabric) Payment Gateway Service."""

    def __init__(self):
        self.base_url = getattr(settings, 'TELEBIRR_H5_BASE_URL', '').rstrip('/')
        self.fabric_app_id = getattr(settings, 'TELEBIRR_FABRIC_APP_ID', '')
        self.app_secret = getattr(settings, 'TELEBIRR_APP_SECRET', '')
        self.merchant_app_id = getattr(settings, 'TELEBIRR_MERCHANT_APP_ID', '')
        self.merchant_code = getattr(settings, 'TELEBIRR_MERCHANT_CODE', '')
        self.private_key_pem = getattr(settings, 'TELEBIRR_PRIVATE_KEY', '')
        self.public_key_pem = getattr(settings, 'TELEBIRR_PUBLIC_KEY', '')
        self.notify_url = getattr(settings, 'TELEBIRR_NOTIFY_URL', '')
        self.redirect_url = getattr(settings, 'TELEBIRR_REDIRECT_URL', '')
        self.timeout = 30
        # https testbed certs are not always chain-trusted; mirror the demo's
        # rejectUnauthorized:false. Override with TELEBIRR_VERIFY_SSL=true.
        self.verify_ssl = getattr(settings, 'TELEBIRR_VERIFY_SSL', False)

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------
    @staticmethod
    def create_timestamp():
        """UTC timestamp in seconds (string)."""
        return str(int(time.time()))

    @staticmethod
    def create_nonce_str():
        """Random 32-char alphanumeric nonce."""
        return uuid.uuid4().hex

    def create_merchant_order_id(self):
        """Millisecond epoch as merchant order id (alphanumeric)."""
        return str(int(time.time() * 1000))

    def _build_sign_origin_str(self, request_object):
        """Flatten + sort + join request fields into the string to be signed."""
        field_map = {}
        for key, value in request_object.items():
            if key in _EXCLUDE_FIELDS:
                continue
            field_map[key] = value
        biz = request_object.get('biz_content')
        if isinstance(biz, dict):
            for key, value in biz.items():
                if key in _EXCLUDE_FIELDS:
                    continue
                field_map[key] = value
        return '&'.join(f'{k}={field_map[k]}' for k in sorted(field_map.keys()))

    def _load_private_key(self):
        if not self.private_key_pem:
            raise ValueError('TELEBIRR_PRIVATE_KEY is not configured')
        return serialization.load_pem_private_key(
            self.private_key_pem.encode(), password=None, backend=default_backend()
        )

    def _load_public_key(self):
        if not self.public_key_pem:
            raise ValueError('TELEBIRR_PUBLIC_KEY is not configured')
        return serialization.load_pem_public_key(
            self.public_key_pem.encode(), backend=default_backend()
        )

    def _sign_string(self, text):
        """RSA-PSS / SHA256withRSAandMGF1 signature, base64 encoded."""
        private_key = self._load_private_key()
        signature = private_key.sign(
            text.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=hashes.SHA256().digest_size,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode('utf-8')

    def sign_request_object(self, request_object):
        """Public helper: sign a request/raw-request map."""
        return self._sign_string(self._build_sign_origin_str(request_object))

    def verify_signature(self, data, signature):
        """Verify an SP signature over a flattened request map (PSS/MGF1-SHA256)."""
        try:
            origin = self._build_sign_origin_str(data)
            self._load_public_key().verify(
                base64.b64decode(signature),
                origin.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=hashes.SHA256().digest_size,
                ),
                hashes.SHA256(),
            )
            return True
        except (InvalidSignature, ValueError, Exception) as exc:
            logger.warning('Telebirr signature verification failed: %s', exc)
            return False

    # ------------------------------------------------------------------
    # Step 1: apply fabric token
    # ------------------------------------------------------------------
    def apply_fabric_token(self):
        """Fetch a fabric token. Returns the response dict (contains 'token')."""
        url = f'{self.base_url}/payment/v1/token'
        # The app key is a credential and does not belong in a log line; the
        # URL alone says which environment was called.
        logger.info('[TELEBIRR] Applying fabric token. URL: %s', url)
        resp = requests.post(
            url,
            headers={
                'Content-Type': 'application/json',
                'X-APP-Key': self.fabric_app_id,
            },
            json={'appSecret': self.app_secret},
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        # Status only. This response *is* the fabric token -- see this
        # method's own docstring -- so logging its body wrote a live
        # credential into the log on every H5 checkout. What is useful when
        # this fails is the status and whether a token came back, and both
        # survive without printing it.
        logger.info(
            '[TELEBIRR] Fabric token response status=%s has_token=%s',
            resp.status_code,
            bool(resp.text and 'token' in resp.text),
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Step 3: create order (preOrder) -> rawRequest
    # ------------------------------------------------------------------
    def _build_pre_order_request(
        self, title, amount, merch_order_id, notify_url=None, redirect_url=None, trade_type='InApp'
    ):
        req = {
            'timestamp': self.create_timestamp(),
            'nonce_str': self.create_nonce_str(),
            'method': 'payment.preorder',
            'version': '1.0',
        }
        biz = {
            'notify_url': notify_url or self.notify_url,
            'redirect_url': redirect_url or self.redirect_url,
            'trade_type': trade_type,
            'appid': self.merchant_app_id,
            'merch_code': self.merchant_code,
            'merch_order_id': merch_order_id,
            'title': title,
            'total_amount': str(amount),
            'trans_currency': 'ETB',
            'business_type': 'BuyGoods',
            'timeout_express': '120m',
            'payee_identifier': self.merchant_code,
            'payee_identifier_type': '04',
            'payee_type': '3000',
        }
        req['biz_content'] = biz
        req['sign'] = self.sign_request_object(req)
        req['sign_type'] = 'SHA256WithRSA'
        return req

    def _build_pre_order_request_ondemand(
        self, title, amount, merch_order_id, notify_url=None, redirect_url=None, trade_type='InApp'
    ):
        """Build preOrder request for on-demand coin purchases (without payee fields)."""
        req = {
            'timestamp': self.create_timestamp(),
            'nonce_str': self.create_nonce_str(),
            'method': 'payment.preorder',
            'version': '1.0',
        }
        biz = {
            'notify_url': notify_url or self.notify_url,
            'redirect_url': redirect_url or self.redirect_url,
            'trade_type': trade_type,
            'appid': self.merchant_app_id,
            'merch_code': self.merchant_code,
            'merch_order_id': merch_order_id,
            'title': title,
            'total_amount': str(amount),
            'trans_currency': 'ETB',
            'business_type': 'BuyGoods',
            'timeout_express': '120m',
        }
        req['biz_content'] = biz
        req['sign'] = self.sign_request_object(req)
        req['sign_type'] = 'SHA256WithRSA'
        return req

    def _build_raw_request(self, prepay_id):
        """Build the signed rawRequest string handed to js_fun_start_pay."""
        fields = {
            'appid': self.merchant_app_id,
            'merch_code': self.merchant_code,
            'nonce_str': self.create_nonce_str(),
            'prepay_id': prepay_id,
            'timestamp': self.create_timestamp(),
        }
        sign = self.sign_request_object(fields)
        return '&'.join(
            [
                f"appid={fields['appid']}",
                f"merch_code={fields['merch_code']}",
                f"nonce_str={fields['nonce_str']}",
                f"prepay_id={fields['prepay_id']}",
                f"timestamp={fields['timestamp']}",
                f'sign={sign}',
                'sign_type=SHA256WithRSA',
            ]
        )

    def create_order(
        self,
        title,
        amount,
        merch_order_id=None,
        notify_url=None,
        redirect_url=None,
        trade_type='InApp',
    ):
        """
        Create a prepaid order and return the signed rawRequest for the H5 page.

        Returns dict:
          { success, merch_order_id, prepay_id, raw_request }  on success
          { success: False, error, code, raw }                 on failure
        """
        merch_order_id = merch_order_id or self.create_merchant_order_id()
        try:
            token_result = self.apply_fabric_token()
            fabric_token = token_result.get('token')
            if not fabric_token:
                return {
                    'success': False,
                    'error': 'Failed to obtain fabric token',
                    'raw': token_result,
                }

            req_obj = self._build_pre_order_request(
                title,
                amount,
                merch_order_id,
                notify_url=notify_url,
                redirect_url=redirect_url,
                trade_type=trade_type,
            )
            url = f'{self.base_url}/payment/v1/merchant/preOrder'
            logger.info(f'[TELEBIRR] preOrder request: {json.dumps(req_obj, indent=2)}')
            resp = requests.post(
                url,
                headers={
                    'Content-Type': 'application/json',
                    'X-APP-Key': self.fabric_app_id,
                    'Authorization': fabric_token,
                },
                json=req_obj,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
            logger.info(f'[TELEBIRR] preOrder response status: {resp.status_code}')
            # Body withheld: this exchange carries the fabric token in its
            # Authorization header, and a failing response commonly echoes
            # the request back. The status and the parsed outcome below are
            # what diagnosing this actually needs.
            logger.info('[TELEBIRR] preOrder response body withheld (status %s)', resp.status_code)
            resp.raise_for_status()
            result = resp.json()

            if result.get('result') == 'SUCCESS' and result.get('biz_content'):
                prepay_id = result['biz_content'].get('prepay_id')
                return {
                    'success': True,
                    'merch_order_id': result['biz_content'].get('merch_order_id', merch_order_id),
                    'prepay_id': prepay_id,
                    'raw_request': self._build_raw_request(prepay_id),
                }
            return {
                'success': False,
                'error': result.get('msg', 'preOrder failed'),
                'code': result.get('code'),
                'raw': result,
            }
        except requests.RequestException as exc:
            logger.error('Telebirr preOrder network error: %s', exc)
            return {'success': False, 'error': f'Network error: {exc}'}
        except Exception as exc:
            logger.error('Telebirr preOrder error: %s', exc)
            return {'success': False, 'error': str(exc)}

    def create_order_ondemand(
        self,
        title,
        amount,
        merch_order_id=None,
        notify_url=None,
        redirect_url=None,
        trade_type='InApp',
    ):
        """
        Create a prepaid order for on-demand coin purchases (without payee fields).

        Returns dict:
          { success, merch_order_id, prepay_id, raw_request }  on success
          { success: False, error, code, raw }                 on failure
        """
        merch_order_id = merch_order_id or self.create_merchant_order_id()
        try:
            token_result = self.apply_fabric_token()
            fabric_token = token_result.get('token')
            if not fabric_token:
                return {
                    'success': False,
                    'error': 'Failed to obtain fabric token',
                    'raw': token_result,
                }

            req_obj = self._build_pre_order_request_ondemand(
                title,
                amount,
                merch_order_id,
                notify_url=notify_url,
                redirect_url=redirect_url,
                trade_type=trade_type,
            )
            url = f'{self.base_url}/payment/v1/merchant/preOrder'
            logger.info(f'[TELEBIRR] preOrder request (ondemand): {json.dumps(req_obj, indent=2)}')
            resp = requests.post(
                url,
                headers={
                    'Content-Type': 'application/json',
                    'X-APP-Key': self.fabric_app_id,
                    'Authorization': fabric_token,
                },
                json=req_obj,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
            logger.info(f'[TELEBIRR] preOrder response status (ondemand): {resp.status_code}')
            # Body withheld: this exchange carries the fabric token in its
            # Authorization header, and a failing response commonly echoes
            # the request back. The status and the parsed outcome below are
            # what diagnosing this actually needs.
            logger.info(
                '[TELEBIRR] preOrder response body (ondemand) withheld (status %s)',
                resp.status_code,
            )
            resp.raise_for_status()
            result = resp.json()

            if result.get('result') == 'SUCCESS' and result.get('biz_content'):
                prepay_id = result['biz_content'].get('prepay_id')
                return {
                    'success': True,
                    'merch_order_id': result['biz_content'].get('merch_order_id', merch_order_id),
                    'prepay_id': prepay_id,
                    'raw_request': self._build_raw_request(prepay_id),
                }
            return {
                'success': False,
                'error': result.get('msg', 'preOrder failed'),
                'code': result.get('code'),
                'raw': result,
            }
        except requests.RequestException as exc:
            logger.error('Telebirr preOrder network error (ondemand): %s', exc)
            return {'success': False, 'error': f'Network error: {exc}'}
        except Exception as exc:
            logger.error('Telebirr preOrder error (ondemand): %s', exc)
            return {'success': False, 'error': str(exc)}

    # ------------------------------------------------------------------
    # queryOrder
    # ------------------------------------------------------------------
    def query_order(self, merch_order_id):
        """Query an order's status by merchant order id."""
        try:
            token_result = self.apply_fabric_token()
            fabric_token = token_result.get('token')
            if not fabric_token:
                return {'success': False, 'error': 'Failed to obtain fabric token'}

            req = {
                'timestamp': self.create_timestamp(),
                'nonce_str': self.create_nonce_str(),
                'method': 'payment.queryorder',
                'version': '1.0',
                'biz_content': {
                    'appid': self.merchant_app_id,
                    'merch_code': self.merchant_code,
                    'merch_order_id': merch_order_id,
                },
            }
            req['sign'] = self.sign_request_object(req)
            req['sign_type'] = 'SHA256WithRSA'

            url = f'{self.base_url}/payment/v1/merchant/queryOrder'
            resp = requests.post(
                url,
                headers={
                    'Content-Type': 'application/json',
                    'X-APP-Key': self.fabric_app_id,
                    'Authorization': fabric_token,
                },
                json=req,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
            resp.raise_for_status()
            result = resp.json()

            if result.get('result') == 'SUCCESS' and result.get('biz_content'):
                biz = result['biz_content']
                order_status = biz.get('order_status')
                trade_status = biz.get('trade_status')
                return {
                    'success': True,
                    'is_paid': order_status == 'PAY_SUCCESS',
                    'trade_status': trade_status,
                    'order_status': order_status,
                    'merch_order_id': biz.get('merch_order_id'),
                    'payment_order_id': biz.get('payment_order_id'),
                    'total_amount': biz.get('total_amount'),
                    'raw': result,
                }
            return {
                'success': False,
                'error': result.get('msg', 'queryOrder failed'),
                'code': result.get('code'),
                'raw': result,
            }
        except requests.RequestException as exc:
            logger.error('Telebirr queryOrder network error: %s', exc)
            return {'success': False, 'error': f'Network error: {exc}'}
        except Exception as exc:
            logger.error('Telebirr queryOrder error: %s', exc)
            return {'success': False, 'error': str(exc)}

    # ------------------------------------------------------------------
    # auth token (auto-login)
    # ------------------------------------------------------------------
    def request_auth_token(self, access_token):
        """
        Request auth token from Telebirr to get user info for auto-login.

        access_token: Token provided by SuperApp to H5 app

        Returns dict:
          { success, open_id, identityId, identifier, nickName, status, raw } on success
          { success: False, error, code, raw } on failure
        """
        try:
            token_result = self.apply_fabric_token()
            fabric_token = token_result.get('token')
            if not fabric_token:
                return {
                    'success': False,
                    'error': 'Failed to obtain fabric token',
                    'raw': token_result,
                }

            req = {
                'timestamp': self.create_timestamp(),
                'nonce_str': self.create_nonce_str(),
                'method': 'payment.authtoken',
                'version': '1.0',
                'biz_content': {
                    'access_token': access_token,
                    'trade_type': 'InApp',
                    'appid': self.merchant_app_id,
                    'resource_type': 'OpenId',
                },
            }
            req['sign'] = self.sign_request_object(req)
            req['sign_type'] = 'SHA256WithRSA'

            url = f'{self.base_url}/payment/v1/auth/authToken'
            resp = requests.post(
                url,
                headers={
                    'Content-Type': 'application/json',
                    'X-APP-Key': self.fabric_app_id,
                    'Authorization': fabric_token,
                },
                json=req,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
            resp.raise_for_status()
            result = resp.json()

            if result.get('result') == 'SUCCESS' and result.get('biz_content'):
                biz = result['biz_content']
                # Production SuperApp does not return 'identifier' (phone number) field
                # Only returns identityId and walletIdentityId which are NOT phone numbers
                identifier = biz.get('identifier')
                return {
                    'success': True,
                    'open_id': biz.get('open_id'),
                    'identityId': biz.get('identityId'),
                    'identityType': biz.get('identityType'),
                    'walletIdentityId': biz.get('walletIdentityId'),
                    'identifier': identifier,  # Phone number (MSISDN) - None in production
                    'nickName': biz.get('nickName'),
                    'status': biz.get('status'),
                    'raw': result,
                }
            return {
                'success': False,
                'error': result.get('msg', 'authToken failed'),
                'code': result.get('code'),
                'raw': result,
            }
        except requests.RequestException as exc:
            logger.error('Telebirr authToken network error: %s', exc)
            return {'success': False, 'error': f'Network error: {exc}'}
        except Exception as exc:
            logger.error('Telebirr authToken error: %s', exc)
            return {'success': False, 'error': str(exc)}

    # ------------------------------------------------------------------
    # notify (async webhook) verification
    # ------------------------------------------------------------------
    def verify_notify(self, notify_data):
        """
        Verify and parse an async payment notification.

        notify_data: dict of the POSTed callback body.
        Returns: { verified, is_paid, merch_order_id, payment_order_id,
                   trade_status, total_amount, trans_id, raw }
        """
        signature = notify_data.get('sign')
        verify_payload = {k: v for k, v in notify_data.items() if k not in ('sign', 'sign_type')}
        verified = bool(signature) and self.verify_signature(verify_payload, signature)
        trade_status = notify_data.get('trade_status')
        return {
            'verified': verified,
            'is_paid': trade_status == 'Completed',
            'merch_order_id': notify_data.get('merch_order_id'),
            'payment_order_id': notify_data.get('payment_order_id'),
            'trade_status': trade_status,
            'total_amount': notify_data.get('total_amount'),
            'trans_id': notify_data.get('trans_id'),
            'raw': notify_data,
        }


# Singleton instance
telebirr_service = TelebirrService()
