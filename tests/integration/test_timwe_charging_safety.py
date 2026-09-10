"""
Deploying the charging code must never be what starts charging.

These pin the activation rules rather than the charging logic:

* both switches default off, and nothing in the deployment turns them on;
* the master switch holds at the lowest level -- the one function that sends
  a chargeAmount -- so no caller can get around it;
* the guide's ``http://IP:Port/...`` template and the SMPP gateway's address
  are refused as the charging endpoint;
* the verification commands an operator runs after a deploy send nothing.
"""

import ast
import re
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from api.integrations.timwe.charge import TimweChargeService
from api.integrations.timwe.errors import TimweChargingDisabled, TimweConfigurationError
from api.models.timwe import TimweChargeTransaction
from api.services.timwe_charging import request_charge

pytestmark = pytest.mark.django_db

BACKEND = Path(__file__).resolve().parents[2]
POST = 'api.integrations.timwe.charge.requests.post'
CONNECT = 'api.management.commands.timwe_charge_check.socket.create_connection'

SWITCHES = (
    'TIMWE_CHARGING_ENABLED',
    'TIMWE_SUBSCRIPTION_RENEWAL_ENABLED',
    'TIMWE_AIRTIME_PURCHASE_ENABLED',
)

CONFIG = {
    'TIMWE_CHARGE_URL': 'http://ma.test:8080/AmountChargingService/services/AmountCharging',
    'TIMWE_SP_ID': '300263',
    'TIMWE_SP_PASSWORD': 'charging-password-for-tests',
    'TIMWE_SERVICE_ID': '30026300007331',
    'TIMWE_CURRENCY': 'ETB',
    'TIMWE_CHARGE_TIMEOUT': 60,
    'TIMWE_SMPP_HOST': '10.175.206.42',
    'TIMWE_SMPP_PORT': 6986,
    'TIMWE_SMPP_PASSWORD': 'smpp-password-for-tests',
    # Off, as in every deployment.
    'TIMWE_CHARGING_ENABLED': False,
    'TIMWE_SUBSCRIPTION_RENEWAL_ENABLED': False,
    'TIMWE_AIRTIME_PURCHASE_ENABLED': False,
}


@pytest.fixture(autouse=True)
def configured(settings):
    for key, value in CONFIG.items():
        setattr(settings, key, value)
    return settings


@pytest.fixture
def user():
    u = User.objects.create_user(username='payer', password='x')
    u.profile.phone_number = '251912345678'
    u.profile.save(update_fields=['phone_number'])
    return u


# ─── off by default, and nothing turns them on ───────────────────────────────


def _declared_default(name):
    """The default in config/settings/base.py, read from source -- not from a test override."""
    tree = ast.parse((BACKEND / 'config' / 'settings' / 'base.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, 'id', None) == 'config'
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == name
        ):
            for keyword in node.keywords:
                if keyword.arg == 'default':
                    return ast.literal_eval(keyword.value)
    raise AssertionError(f'{name} is not declared in config/settings/base.py')


@pytest.mark.parametrize('name', SWITCHES)
def test_every_charging_switch_defaults_off(name):
    assert _declared_default(name) is False


def test_nothing_in_the_deployment_turns_charging_on():
    """A deploy picks these files up. None of them may flip a switch."""
    enabling = re.compile(
        r'(TIMWE_(?:CHARGING|SUBSCRIPTION_RENEWAL|AIRTIME_PURCHASE)_ENABLED)\s*[:=]\s*["\']?(true|1|yes|on)\b',
        re.IGNORECASE,
    )
    candidates = [BACKEND / '.env.example', BACKEND / 'docker-compose.yml']
    for folder in ('k8s', 'argocd', '.github'):
        root = BACKEND / folder
        if root.exists():
            candidates += [
                p
                for p in root.rglob('*')
                if p.is_file() and p.suffix in ('.yaml', '.yml', '.env', '.json', '')
            ]
    offenders = []
    for path in candidates:
        if not path.exists():
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        for match in enabling.finditer(text):
            offenders.append(f'{path.relative_to(BACKEND)}: {match.group(0)}')
    assert not offenders, 'A deployment file enables TIMWE charging:\n  ' + '\n  '.join(offenders)


# ─── the master switch, at the lowest level ──────────────────────────────────


def test_the_client_sends_nothing_with_the_master_switch_off():
    """Whoever calls execute() -- the switch is checked where the request is sent."""
    with patch(POST) as posted, pytest.raises(TimweChargingDisabled):
        TimweChargeService.execute(
            msisdn='251912345678', amount=3, description='d', reference_code='R1'
        )
    posted.assert_not_called()


def test_the_service_records_nothing_with_the_master_switch_off(user):
    with patch(POST) as posted, pytest.raises(TimweChargingDisabled):
        request_charge(
            user=user, msisdn='251912345678', amount=3, description='d', idempotency_key='k'
        )
    posted.assert_not_called()
    assert not TimweChargeTransaction.objects.exists()


def test_there_is_no_way_to_charge_around_the_ledger():
    """The old charge() wrapper recorded nothing and guarded nothing."""
    assert not hasattr(TimweChargeService, 'charge')


# ─── the endpoint is TIMWE's to supply ───────────────────────────────────────


@pytest.mark.parametrize(
    'url',
    [
        'http://IP:Port/AmountChargingService/services/AmountCharging',
        'http://ip:port/AmountChargingService/services/AmountCharging',
        'http://<IP>:<Port>/AmountChargingService/services/AmountCharging',
    ],
)
def test_the_documentation_placeholder_is_refused(settings, user, url):
    settings.TIMWE_CHARGE_URL = url
    settings.TIMWE_CHARGING_ENABLED = True

    assert 'placeholder' in TimweChargeService.endpoint_problem()
    with pytest.raises(TimweConfigurationError, match='placeholder'):
        TimweChargeService.ensure_configured()
    with patch(POST) as posted, pytest.raises(TimweConfigurationError):
        request_charge(
            user=user, msisdn='251912345678', amount=3, description='d', idempotency_key='k'
        )
    posted.assert_not_called()
    assert not TimweChargeTransaction.objects.exists()


@pytest.mark.parametrize(
    'url',
    [
        'http://10.175.206.42:6986/AmountChargingService/services/AmountCharging',
        'http://10.175.206.42:6986',
    ],
)
def test_the_smpp_gateway_is_refused_as_the_charge_endpoint(settings, url):
    settings.TIMWE_CHARGE_URL = url

    assert 'SMPP gateway' in TimweChargeService.endpoint_problem()
    with pytest.raises(TimweConfigurationError, match='SMPP gateway'):
        TimweChargeService.ensure_configured()


def test_the_same_host_on_another_port_is_allowed(settings):
    """TIMWE may serve charging from the SMPP box; only the SMPP port itself is refused."""
    settings.TIMWE_CHARGE_URL = (
        'http://10.175.206.42:8080/AmountChargingService/services/AmountCharging'
    )

    assert TimweChargeService.endpoint_problem() == ''


@pytest.mark.parametrize('url', ['ftp://ma.test/x', 'ma.test:8080/x', 'http:///x'])
def test_a_malformed_endpoint_is_refused(settings, url):
    settings.TIMWE_CHARGE_URL = url

    assert TimweChargeService.endpoint_problem()


# ─── verifying a deployment sends nothing ─────────────────────────────────────


def test_the_post_deploy_check_reports_the_switches_off_and_sends_nothing():
    out = StringIO()
    with patch(POST) as posted, patch(CONNECT):
        call_command('timwe_charge_check', stdout=out)

    posted.assert_not_called()
    report = out.getvalue()
    for switch in SWITCHES:
        assert re.search(rf'{switch}\s+off', report), report
    assert 'No charge made' in report


def test_a_charge_from_the_command_is_refused_while_the_switch_is_off(user):
    with (
        patch(POST) as posted,
        patch(CONNECT),
        pytest.raises(CommandError, match='TIMWE_CHARGING_ENABLED is off'),
    ):
        call_command(
            'timwe_charge_check',
            '--charge',
            '--msisdn',
            '251912345678',
            '--amount',
            '1',
            '--username',
            user.username,
            '--confirm',
            stdout=StringIO(),
        )
    posted.assert_not_called()
    assert not TimweChargeTransaction.objects.exists()


def test_the_check_names_a_placeholder_url_and_does_not_connect(settings):
    settings.TIMWE_CHARGE_URL = 'http://IP:Port/AmountChargingService/services/AmountCharging'

    out = StringIO()
    with patch(CONNECT) as connect, pytest.raises(CommandError):
        call_command('timwe_charge_check', stdout=out)

    connect.assert_not_called()
    assert 'placeholder' in out.getvalue()


def test_a_charging_password_equal_to_the_smpp_one_is_flagged_never_printed(settings):
    settings.TIMWE_SP_PASSWORD = settings.TIMWE_SMPP_PASSWORD

    out = StringIO()
    with patch(CONNECT):
        call_command('timwe_charge_check', stdout=out)

    report = out.getvalue()
    assert 'same as the SMPP password' in report
    assert settings.TIMWE_SMPP_PASSWORD not in report


def test_reconciliation_cannot_be_combined_with_a_charge():
    with pytest.raises(CommandError, match='never charges'):
        call_command('timwe_charge_check', '--reconcile', '--charge', stdout=StringIO())


def test_reconciliation_with_the_switches_off_sends_nothing():
    out = StringIO()
    with patch(POST) as posted, patch(CONNECT) as connect:
        call_command('timwe_charge_check', '--reconcile', stdout=out)

    posted.assert_not_called()
    connect.assert_not_called()
    assert 'nothing pending, ambiguous or unapplied' in out.getvalue()
