"""
How many SMS a message actually costs to send.

Length in characters is not what a gateway bills. A message is encoded as
GSM-7 if every character fits that alphabet and as UCS-2 if even one does not,
and the two have different capacities -- one Amharic character, one curly
quote or one emoji turns a 3-segment message into an 8-segment one.

    GSM-7    160 septets alone, 153 per part when concatenated
    UCS-2     70 characters alone,  67 per part when concatenated

The concatenated figures are smaller because each part carries a 6-byte header
saying which part of which message it is.

Nine characters cost **two** septets in GSM-7 rather than one, because they
live in an extension table reached by an escape: ``^ { } \\ [ ] ~ |`` and the
euro sign. A link full of brackets is longer than it looks.

Used by the tests that hold the subscription messages inside their segment
budget. Nothing here changes what is sent.
"""

#: The GSM 03.38 basic alphabet: one septet each.
GSM_BASIC = (
    '@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?'
    '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà'
)

#: Reached by an escape, so two septets each.
GSM_EXTENDED = '^{}\\[~]|€'

GSM_SINGLE = 160
GSM_MULTIPART = 153
UCS2_SINGLE = 70
UCS2_MULTIPART = 67


def is_gsm7(text: str) -> bool:
    """Whether every character can be sent in the GSM-7 alphabet."""
    return all(ch in GSM_BASIC or ch in GSM_EXTENDED for ch in text or '')


def encoding_of(text: str) -> str:
    """``'GSM-7'`` or ``'UCS-2'`` -- what this text will be sent as."""
    return 'GSM-7' if is_gsm7(text) else 'UCS-2'


def septets(text: str) -> int:
    """The GSM-7 length: the unit a gateway counts, not len()."""
    return sum(2 if ch in GSM_EXTENDED else 1 for ch in text or '')


def units(text: str) -> int:
    """The length in whatever unit this message's encoding is billed in."""
    return septets(text) if is_gsm7(text) else len(text or '')


def segments(text: str) -> int:
    """How many SMS this message is sent as, and therefore billed as."""
    text = text or ''
    if not text:
        return 0

    if is_gsm7(text):
        single, multi = GSM_SINGLE, GSM_MULTIPART
    else:
        single, multi = UCS2_SINGLE, UCS2_MULTIPART

    total = units(text)
    if total <= single:
        return 1
    return -(-total // multi)


def describe(text: str) -> str:
    """One line for a test failure or a log: what it costs and why."""
    return f'{units(text)} {encoding_of(text)} units, {segments(text)} segment(s)'
