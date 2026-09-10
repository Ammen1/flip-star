"""
The setup OTP a new telebirr one-off subscriber gets goes out over TIMWE.

It was sent through OnevasWebhookView.send_sms. That view was deleted with the
rest of OneVAS, and the call sits inside a try/except that logs and carries
on -- so a reference left behind would not have failed loudly: the subscriber
would simply never get a code. This pins the replacement.

DirectDebitMandate.user is not nullable, so the "new user" branch this covers
is not reachable through the model today. The function is driven directly with
a stand-in mandate to exercise it anyway, since the code is there to run.
"""

from unittest.mock import MagicMock, patch

import pytest

from api.models.subscription import SubscriptionPlan
from api.views.direct_debit import _activate_one_off_subscription

pytestmark = pytest.mark.django_db

PHONE = '251911223344'


def _new_subscriber_mandate():
    mandate = MagicMock()
    mandate.subscription_plan_id = None
    mandate.user = None
    mandate.payer_msisdn = PHONE
    mandate.tier = None
    mandate.metadata = {'duration_days': 1, 'duration_type': 'daily'}
    return mandate


def test_a_new_subscriber_gets_the_setup_otp_over_timwe(monkeypatch):
    posted = []
    monkeypatch.setattr('requests.post', lambda *a, **kw: posted.append((a, kw)))

    with patch('api.services.sms.dispatch.queue_sms') as queued:
        _activate_one_off_subscription(_new_subscriber_mandate())

    queued.assert_called_once()
    sent = queued.call_args.kwargs
    assert sent['phone_number'] == PHONE
    assert sent['purpose'] == 'otp_subscription_setup'

    plan = SubscriptionPlan.objects.get(telebirr_phone_number=PHONE)
    assert plan.setup_otp
    assert plan.setup_otp in sent['text']
    assert posted == [], 'the setup OTP went over HTTP -- an old gateway is still in the path'
