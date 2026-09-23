"""
Whether coins can be bought with airtime right now.

Three separate things have to be true, and they fail in different ways:

* ``TIMWE_AIRTIME_PURCHASE_ENABLED`` -- the policy switch. Airtime purchase was
  turned off deliberately ("Ethio Telecom SIM cards are only accessible for SMS
  OTP verification"), so turning it on is a decision somebody makes per
  environment, never a default. It stays False in
  ``config/settings/base.py`` and is set to true only where it is wanted.
* ``TIMWE_CHARGING_ENABLED`` -- the master switch on the charging client. While
  it is off nothing is sent to TIMWE, whoever asks.
* the five settings ``chargeAmount`` cannot be built without
  (``TIMWE_CHARGE_URL``, ``TIMWE_SP_ID``, ``TIMWE_SP_PASSWORD``,
  ``TIMWE_SERVICE_ID``, ``TIMWE_CURRENCY``) plus a usable endpoint.

This exists so the answer is computed once. The purchase endpoint refuses when
it is false, and ``/wallet/config/`` tells the client the same thing -- so the
Buy Coins page offers airtime exactly when a purchase would work, rather than
offering a button that answers 403.

**Names, never values.** ``unavailable_reasons`` reports which settings are
missing so an operator can fix them; nothing here returns, logs or renders a
credential.
"""

from django.conf import settings


def policy_enabled() -> bool:
    """The environment's decision: may airtime be used to buy coins at all?"""
    return bool(getattr(settings, 'TIMWE_AIRTIME_PURCHASE_ENABLED', False))


def _client():
    from api.integrations.timwe.charge import TimweChargeService

    return TimweChargeService


def unavailable_reasons() -> list[str]:
    """Why airtime purchase is not available, as short machine-readable codes.

    Empty when it is available. Used for the operator-facing check on staging
    and by the tests; the client is told only true or false.
    """
    reasons = []
    if not policy_enabled():
        reasons.append('TIMWE_AIRTIME_PURCHASE_ENABLED is false')

    client = _client()
    if not client.charging_enabled():
        reasons.append('TIMWE_CHARGING_ENABLED is false')

    missing = client.missing_configuration()
    if missing:
        reasons.append(f'unset: {", ".join(missing)}')

    problem = client.endpoint_problem()
    if problem:
        reasons.append(problem)

    return reasons


def is_available() -> bool:
    """True when a coin purchase paid with airtime would actually be attempted.

    Deliberately stricter than the policy flag alone: switching the policy on
    in an environment that has no charging credentials would put an Airtime
    button in front of people that can only fail, which is worse than not
    offering it.
    """
    return not unavailable_reasons()
