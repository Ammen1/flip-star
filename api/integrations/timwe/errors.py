"""
Error codes defined by the TIMWE Master Aggregator integration guide.

Two disjoint sets, because the two APIs run in opposite directions:

``SYNC_ORDER_RELATION_ERRORS``
    Numeric codes *we* return to the MA from the syncOrderRelation endpoint
    (guide p.17). ``"0"`` means the subscription relationship was applied
    successfully; anything else tells the MA what went wrong on our side.

``CHARGE_AMOUNT_ERRORS``
    ``SVC``/``POL`` codes the MA returns to *us* from chargeAmount (guide
    pp.22-24). Grouped here so the caller can distinguish "retry later"
    (an MA-side fault) from "this will never succeed" (bad credentials, or a
    subscriber who cannot be billed).
"""

from __future__ import annotations

SYNC_OK = '0'

SYNC_INVALID_FORMAT = '1211'
SYNC_RELATION_EXISTS = '2030'
SYNC_RELATION_NOT_FOUND = '2031'
SYNC_SERVICE_NOT_FOUND = '2032'
SYNC_SERVICE_ABNORMAL = '2033'
SYNC_SERVICE_NOT_SUBSCRIBABLE = '2034'
SYNC_INTERNAL_ERROR = '2500'

SYNC_ORDER_RELATION_ERRORS = {
    SYNC_OK: 'Success',
    SYNC_INVALID_FORMAT: 'The field format is incorrect or the value is invalid.',
    SYNC_RELATION_EXISTS: 'The subscription relationship already exists.',
    SYNC_RELATION_NOT_FOUND: 'The subscription relationship does not exist.',
    SYNC_SERVICE_NOT_FOUND: 'The service does not exist.',
    SYNC_SERVICE_ABNORMAL: 'The service is unavailable.',
    SYNC_SERVICE_NOT_SUBSCRIBABLE: 'The service is unavailable.',
    SYNC_INTERNAL_ERROR: 'An internal system error occurred.',
}

CHARGE_TIMEOUT = 'SVC0001'
CHARGE_INVALID_INPUT = 'SVC0002'
CHARGE_AUTH_FAILED = 'SVC0901'
CHARGE_FAILED = 'SVC0270'
CHARGE_AMOUNT_OUT_OF_RANGE = 'POL0910'

CHARGE_AMOUNT_ERRORS = {
    CHARGE_TIMEOUT: 'Waiting for response timed out; an internal MA service is abnormal.',
    CHARGE_INVALID_INPUT: 'A required charging field is blank or invalid.',
    CHARGE_AUTH_FAILED: 'Authentication or authorisation failed at the MA.',
    CHARGE_FAILED: 'MDSP charge failed; an internal MA service is abnormal.',
    CHARGE_AMOUNT_OUT_OF_RANGE: 'Amount is outside the permitted transaction range.',
}

#: MA-side faults. The request was well-formed and the credentials were
#: accepted, so the same call may succeed later.
CHARGE_RETRYABLE = frozenset({CHARGE_TIMEOUT, CHARGE_FAILED})

#: Faults that will keep failing until a human changes configuration. Retrying
#: these burns the subscriber's patience and our rate limit for nothing.
CHARGE_PERMANENT = frozenset({CHARGE_INVALID_INPUT, CHARGE_AUTH_FAILED, CHARGE_AMOUNT_OUT_OF_RANGE})


class TimweError(Exception):
    """A TIMWE call failed."""


class TimweConfigurationError(TimweError):
    """Required TIMWE credentials or endpoints are absent."""


class TimweAmountError(TimweError):
    """
    An amount cannot be represented on the wire without losing money.

    The MA does not support a decimal point and caps the field at four
    characters (guide p.21), so 3.50 has no faithful representation. Refusing
    is the only safe option: silently sending ``3`` under-bills, and ``4``
    over-bills.
    """
