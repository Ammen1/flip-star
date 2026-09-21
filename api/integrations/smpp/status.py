"""
Turning SMPP numbers into the names shown in logs and on the message row.

smpplib exposes the submit_sm_resp ``command_status`` values as
``SMPP_ESME_*`` constants (for example ``SMPP_ESME_RINVMSGLEN``, which a
gateway can return with value 1). Building the reverse map once keeps the
labels in one place instead of maintaining a second copy of the SMPP table.

These helpers are purely observational: they never change what is sent.
"""

import smpplib.consts

_STATUS_NAMES = None
_ENCODING_NAMES = None


def _status_names():
    """SMPP command_status value -> constant name, built once."""
    global _STATUS_NAMES
    if _STATUS_NAMES is None:
        _STATUS_NAMES = {
            value: name
            for name, value in vars(smpplib.consts).items()
            if name.startswith('SMPP_ESME_') and isinstance(value, int)
        }
    return _STATUS_NAMES


def status_label(code) -> str:
    """A readable label for a submit_sm_resp command_status.

    Returns ``SMPP_ESME_RINVMSGLEN (1)`` rather than the bare ``1`` that made
    every staging rejection look identical. ``None`` -- the gateway answered
    but its status could not be read -- is the plain ``rejected`` a
    pre-existing test and log line already use; an unknown number is labelled
    by the number so nothing is invented.
    """
    if code is None:
        return 'rejected'
    name = _status_names().get(code)
    if name is not None:
        return f'{name} ({code})'
    return f'status {code}'


def data_coding_label(code) -> str:
    """data_coding value -> constant name (e.g. ``SMPP_ENCODING_DEFAULT``)."""
    global _ENCODING_NAMES
    if _ENCODING_NAMES is None:
        _ENCODING_NAMES = {
            value: name
            for name, value in vars(smpplib.consts).items()
            if name.startswith('SMPP_ENCODING_') and isinstance(value, int)
        }
    name = _ENCODING_NAMES.get(code)
    return name if name is not None else str(code)
