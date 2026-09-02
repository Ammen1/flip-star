"""
HTTP range parsing for byte-serving media (RFC 7233).

Django 4.2's ``FileResponse`` does not implement ``Range`` -- that arrived in
Django 5.0 -- so anything this project serves from local storage answers 200
with the whole file and no ``Accept-Ranges``. A browser cannot seek into that,
and on a phone it means paying for the entire clip to watch three seconds of
it. This module supplies the parsing half; ``api/views/media.py`` supplies the
responses.

Deliberately narrow: single ranges only. A multi-range request is answered with
the full representation, which RFC 7233 §3.1 explicitly permits ("A server MAY
ignore the Range header field"), and which no video element ever sends.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: `bytes=0-1023`, `bytes=1024-` or `bytes=-1024` (a suffix length).
_RANGE_RE = re.compile(r'^bytes=(?P<start>\d*)-(?P<end>\d*)$')

#: Read size for the streaming iterator. Large enough not to syscall per
#: kilobyte, small enough that a worker never holds a meaningful slice of a
#: video in memory.
DEFAULT_CHUNK_SIZE = 64 * 1024


class RangeNotSatisfiable(Exception):
    """The range cannot be met, and the caller must answer 416."""


@dataclass(frozen=True)
class RangeSpec:
    """A resolved, inclusive byte range within a file of ``size`` bytes."""

    start: int
    end: int
    size: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1

    @property
    def content_range(self) -> str:
        return f'bytes {self.start}-{self.end}/{self.size}'

    @property
    def is_whole_file(self) -> bool:
        return self.start == 0 and self.end == self.size - 1


def parse_range_header(header: str | None, size: int) -> RangeSpec | None:
    """Resolve a ``Range`` header against a file of ``size`` bytes.

    Returns ``None`` when there is no usable range and the whole file should be
    sent (absent header, a unit this server does not speak, or a multi-range
    request). Raises ``RangeNotSatisfiable`` when the client asked for bytes
    that cannot exist.
    """
    if not header:
        return None

    header = header.strip()

    # Multi-range: answer with the full representation rather than building a
    # multipart/byteranges body no media element asks for.
    if ',' in header:
        return None

    match = _RANGE_RE.match(header)
    if not match:
        return None

    raw_start, raw_end = match.group('start'), match.group('end')

    # A zero-length file can satisfy no range at all.
    if size <= 0:
        raise RangeNotSatisfiable

    if not raw_start:
        # `bytes=-N` -- the final N bytes. Players use this to read the moov
        # atom of an MP4 whose metadata sits at the end.
        if not raw_end:
            return None
        suffix = int(raw_end)
        if suffix == 0:
            raise RangeNotSatisfiable
        start = max(size - suffix, 0)
        end = size - 1
    else:
        start = int(raw_start)
        if start >= size:
            raise RangeNotSatisfiable
        # An end past the last byte is clamped, not rejected: players routinely
        # send an open-ended upper bound like `bytes=0-99999999`, and answering
        # 416 to that stalls playback.
        end = min(int(raw_end), size - 1) if raw_end else size - 1

    if end < start:
        raise RangeNotSatisfiable

    return RangeSpec(start=start, end=end, size=size)


def file_chunks(file_obj, start: int, length: int, chunk_size: int = DEFAULT_CHUNK_SIZE):
    """Yield ``length`` bytes from ``start``, ``chunk_size`` at a time.

    The point of the generator is that the worker never holds more than one
    chunk: the previous implementation did ``f.read(length)``, so a request for
    ``bytes=0-`` pulled an entire video into memory before sending a byte of it.

    Closes ``file_obj`` when finished or abandoned, which matters because a
    client seeking away mid-response leaves the generator un-exhausted.
    """
    try:
        file_obj.seek(start)
        remaining = length
        while remaining > 0:
            data = file_obj.read(min(chunk_size, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data
    finally:
        try:
            file_obj.close()
        except Exception:
            pass
