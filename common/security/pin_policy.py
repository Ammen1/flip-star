"""
PIN strength policy.

The product uses a 6-digit numeric PIN as the user's password everywhere
(registration, login, change-password, both forgot-password flows). Moving
to alphanumeric passwords would be a coordinated product/UX/mobile change
that locks out the existing user base, so that stays a follow-up, not
something this module does.

In the meantime, this rejects the PIN patterns an attacker would try first if
they got even one guess at a specific account: birthday-style sequential
digits, repeated digits, palindromes, and a small blocklist of well-known
weak PINs (from public PIN-frequency analyses). It also re-checks the basic
"6 digits" format defensively, so a single call to :func:`is_pin_too_weak`
is a complete check -- callers do not need a separate format check in front
of it.
"""

from __future__ import annotations

EXPLICIT_BLOCKLIST = {
    '123456', '654321', '111111', '000000', '121212', '112233',
    '123123', '159753', '789456', '147258', '987654', '246810',
    '135790', '102030', '123321', '456789', '987456',
}


def is_pin_too_weak(pin: str) -> tuple[bool, str]:
    """
    Returns ``(True, reason)`` if the PIN is too weak or malformed,
    otherwise ``(False, "")``.
    """
    if not pin or len(pin) != 6 or not pin.isdigit():
        return True, 'PIN must be exactly 6 digits.'

    if pin in EXPLICIT_BLOCKLIST:
        return True, 'This PIN is too common. Please choose a less predictable PIN.'

    if len(set(pin)) == 1:
        return True, 'PIN cannot be all the same digit.'

    digits = [int(c) for c in pin]
    diffs = {digits[i + 1] - digits[i] for i in range(5)}
    if diffs == {1} or diffs == {-1}:
        return True, 'PIN cannot be a sequential run of digits.'

    if pin == pin[::-1]:
        return True, 'PIN cannot be a palindrome.'

    return False, ''
