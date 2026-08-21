"""
Ethio Telecom CRM Integration Service
Handles SOAP API calls to the PresentServiceGift endpoint (data-gift awards).

Distinct from Telebirr B2C (api/integrations/telebirr/direct_debit.py,
cash payouts) -- this is a separate Ethio Telecom CRM system used to grant
data-package gifts.
"""

import logging

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class CRMService:
    """Service for integrating with the Ethio Telecom CRM PresentServiceGift API"""

    VERSION = '1'

    @classmethod
    def get_endpoint(cls):
        return getattr(settings, 'CRM_ENDPOINT', '')

    @classmethod
    def get_service_number_a(cls):
        return getattr(settings, 'CRM_SERVICE_NUMBER_A', '')

    @classmethod
    def get_channel_id(cls):
        return getattr(settings, 'CRM_CHANNEL_ID', '')

    @classmethod
    def get_technical_channel_id(cls):
        return getattr(settings, 'CRM_TECHNICAL_CHANNEL_ID', '')

    @classmethod
    def get_tenant_id(cls):
        return getattr(settings, 'CRM_TENANT_ID', '')

    @classmethod
    def get_currency_id(cls):
        return getattr(settings, 'CRM_CURRENCY_ID', '1048')

    @classmethod
    def get_charge_code(cls):
        return getattr(settings, 'CRM_CHARGE_CODE', 'CC_GIFT_ONCE_OFF_FEE')

    @classmethod
    def get_offering_id(cls):
        return getattr(settings, 'CRM_OFFERING_ID', '')

    @classmethod
    def generate_transaction_id(cls) -> str:
        """Generate unique transaction ID in format YYYYMMDDHHMMSS"""
        return timezone.now().strftime('%Y%m%d%H%M%S')

    @classmethod
    def build_soap_request(
        cls,
        service_number_b: str,
        offering_id: str,
        charge_amount: float,
        access_user: str,
        access_pwd: str,
        transaction_id: str | None = None,
    ) -> str:
        """Build the PresentServiceGift SOAP request envelope."""
        if transaction_id is None:
            transaction_id = cls.generate_transaction_id()

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:han="http://soaif.huawei.com/mvas/handle/" xmlns:bas="http://crm.huawei.com/basetype/">
   <soapenv:Header/>
   <soapenv:Body>
      <han:PresentServiceGiftRequest>
         <han:RequestHeader>
            <bas:Version>{cls.VERSION}</bas:Version>
            <bas:TransactionId>{transaction_id}</bas:TransactionId>
            <bas:ChannelId>{cls.get_channel_id()}</bas:ChannelId>
            <bas:TechnicalChannelId>{cls.get_technical_channel_id()}</bas:TechnicalChannelId>
            <bas:TenantId>{cls.get_tenant_id()}</bas:TenantId>
            <bas:AccessUser>{access_user}</bas:AccessUser>
            <bas:AccessPwd>{access_pwd}</bas:AccessPwd>
         </han:RequestHeader>
         <han:PresentServiceGiftBody>
            <han:ServiceNumberA>{cls.get_service_number_a()}</han:ServiceNumberA>
            <han:FeeDeductionInfo>
               <han:DeductInfo>
                  <han:ChargeCode>{cls.get_charge_code()}</han:ChargeCode>
                  <han:ChargeAmt>{charge_amount}</han:ChargeAmt>
                  <han:CurrencyID>{cls.get_currency_id()}</han:CurrencyID>
               </han:DeductInfo>
            </han:FeeDeductionInfo>
            <han:ServiceNumberB>{service_number_b}</han:ServiceNumberB>
            <han:OfferingInfo>
               <han:OfferingId>
                  <han:OfferingId>{offering_id}</han:OfferingId>
               </han:OfferingId>
               <han:EffectiveMode>
                  <han:Mode>I</han:Mode>
               </han:EffectiveMode>
               <han:ActiveMode>
                  <han:Mode>A</han:Mode>
               </han:ActiveMode>
            </han:OfferingInfo>
         </han:PresentServiceGiftBody>
      </han:PresentServiceGiftRequest>
   </soapenv:Body>
</soapenv:Envelope>'''

    @classmethod
    def parse_soap_response(cls, response_text: str) -> tuple[bool, str, dict]:
        """Parse a PresentServiceGift SOAP response."""
        import xml.etree.ElementTree as ET

        try:
            # response_text is our own outbound call's response from the
            # configured CRM_ENDPOINT (an internal Ethio Telecom host), not
            # attacker-supplied input -- not routing through defusedxml,
            # which isn't otherwise a dependency of this project.
            root = ET.fromstring(response_text)  # noqa: S314
            namespaces = {
                'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
                'han': 'http://soaif.huawei.com/mvas/handle/',
                'bas': 'http://crm.huawei.com/basetype/',
            }

            response_header = root.find('.//han:ResponseHeader', namespaces)
            if response_header is None:
                return False, 'Invalid response format', {}

            ret_code = response_header.find('bas:RetCode', namespaces)
            ret_msg = response_header.find('bas:RetMsg', namespaces)
            if ret_code is None or ret_msg is None:
                return False, 'Missing response code or message', {}

            code = ret_code.text
            message = ret_msg.text

            transaction_id = None
            request_header = response_header.find('bas:RequestHeader', namespaces)
            if request_header is not None:
                trans_id_elem = request_header.find('bas:TransactionId', namespaces)
                if trans_id_elem is not None:
                    transaction_id = trans_id_elem.text

            success = code == '0'
            return success, message, {'ret_code': code, 'ret_msg': message, 'transaction_id': transaction_id}

        except ET.ParseError as e:
            logger.error('Failed to parse CRM SOAP response: %s', e)
            return False, f'XML parsing error: {str(e)}', {}
        except Exception as e:
            logger.error('Error parsing CRM SOAP response: %s', e)
            return False, f'Error: {str(e)}', {}

    @classmethod
    def send_gift(
        cls,
        service_number_b: str,
        offering_id: str,
        charge_amount: float,
        access_user: str,
        access_pwd: str,
    ) -> tuple[bool, str, dict]:
        """Send a gift package to a user via the CRM PresentServiceGift API."""
        transaction_id = cls.generate_transaction_id()
        soap_request = cls.build_soap_request(
            service_number_b=service_number_b, offering_id=offering_id, charge_amount=charge_amount,
            access_user=access_user, access_pwd=access_pwd, transaction_id=transaction_id,
        )

        logger.info(
            'Sending CRM gift request: transaction_id=%s, service_number_b=%s, offering_id=%s',
            transaction_id, service_number_b, offering_id,
        )

        try:
            headers = {
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': 'http://soaif.huawei.com/mvas/handle/PresentServiceGift',
            }
            response = requests.post(cls.get_endpoint(), data=soap_request, headers=headers, timeout=30)

            if response.status_code != 200:
                logger.error('CRM request failed with status %s: %s', response.status_code, response.text[:500])
                return False, f'HTTP {response.status_code}: {response.text[:200]}', {}

            success, message, response_data = cls.parse_soap_response(response.text)
            if success:
                logger.info('CRM gift successful: transaction_id=%s', transaction_id)
            else:
                logger.error('CRM gift failed: transaction_id=%s, message=%s', transaction_id, message)

            response_data['transaction_id'] = transaction_id
            response_data['service_number_b'] = service_number_b
            response_data['offering_id'] = offering_id
            response_data['charge_amount'] = charge_amount
            return success, message, response_data

        except requests.exceptions.Timeout:
            logger.error('CRM request timeout: transaction_id=%s', transaction_id)
            return False, 'Request timeout', {'transaction_id': transaction_id}
        except requests.exceptions.RequestException as e:
            logger.error('CRM request error: transaction_id=%s, error=%s', transaction_id, e)
            return False, f'Request error: {str(e)}', {'transaction_id': transaction_id}
        except Exception as e:
            logger.error('Unexpected CRM error: transaction_id=%s, error=%s', transaction_id, e)
            return False, f'Unexpected error: {str(e)}', {'transaction_id': transaction_id}
