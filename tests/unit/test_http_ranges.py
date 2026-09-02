"""
Range header parsing (RFC 7233).

Pinned closely because the failure modes are silent: a wrong bound serves the
wrong bytes and the video simply does not play, with a 200 in the log.
"""

import pytest

from common.http.ranges import (
    RangeNotSatisfiable,
    file_chunks,
    parse_range_header,
)

SIZE = 1000


# ─── whole-file cases ─────────────────────────────────────────────────────────

@pytest.mark.parametrize('header', [None, '', 'bytes=', 'items=0-10', 'garbage'])
def test_no_usable_range_means_send_everything(header):
    assert parse_range_header(header, SIZE) is None


def test_multi_range_falls_back_to_the_whole_file():
    """RFC 7233 permits ignoring Range; no media element sends multi-range."""
    assert parse_range_header('bytes=0-99,200-299', SIZE) is None


# ─── explicit ranges ──────────────────────────────────────────────────────────

def test_a_closed_range():
    spec = parse_range_header('bytes=0-499', SIZE)
    assert (spec.start, spec.end, spec.length) == (0, 499, 500)
    assert spec.content_range == 'bytes 0-499/1000'


def test_an_open_ended_range_runs_to_the_last_byte():
    spec = parse_range_header('bytes=500-', SIZE)
    assert (spec.start, spec.end, spec.length) == (500, 999, 500)


def test_a_single_byte():
    spec = parse_range_header('bytes=0-0', SIZE)
    assert (spec.start, spec.end, spec.length) == (0, 0, 1)


def test_the_whole_file_by_explicit_range():
    spec = parse_range_header('bytes=0-999', SIZE)
    assert spec.is_whole_file is True


# ─── suffix ranges ────────────────────────────────────────────────────────────

def test_a_suffix_range_returns_the_tail():
    """Players read the tail of an MP4 to find a moov atom stored at the end."""
    spec = parse_range_header('bytes=-500', SIZE)
    assert (spec.start, spec.end, spec.length) == (500, 999, 500)


def test_a_suffix_longer_than_the_file_clamps_to_the_whole_file():
    spec = parse_range_header('bytes=-5000', SIZE)
    assert (spec.start, spec.end) == (0, 999)


def test_a_zero_length_suffix_is_unsatisfiable():
    with pytest.raises(RangeNotSatisfiable):
        parse_range_header('bytes=-0', SIZE)


# ─── clamping vs refusing ─────────────────────────────────────────────────────

def test_an_end_past_the_file_is_clamped_not_refused():
    """Players routinely send an open upper bound; 416 here stalls playback."""
    spec = parse_range_header('bytes=0-99999999', SIZE)
    assert (spec.start, spec.end) == (0, 999)


def test_a_start_past_the_file_is_unsatisfiable():
    with pytest.raises(RangeNotSatisfiable):
        parse_range_header('bytes=1000-', SIZE)


def test_a_start_far_past_the_file_is_unsatisfiable():
    with pytest.raises(RangeNotSatisfiable):
        parse_range_header('bytes=5000-6000', SIZE)


def test_a_reversed_range_is_unsatisfiable():
    with pytest.raises(RangeNotSatisfiable):
        parse_range_header('bytes=500-100', SIZE)


def test_any_range_against_an_empty_file_is_unsatisfiable():
    with pytest.raises(RangeNotSatisfiable):
        parse_range_header('bytes=0-10', 0)


def test_the_last_byte_is_reachable():
    spec = parse_range_header('bytes=999-999', SIZE)
    assert (spec.start, spec.end, spec.length) == (999, 999, 1)


# ─── the streaming iterator ───────────────────────────────────────────────────

def test_chunks_yield_exactly_the_requested_span(tmp_path):
    f = tmp_path / 'clip.bin'
    f.write_bytes(bytes(range(256)) * 8)  # 2048 bytes

    out = b''.join(file_chunks(open(f, 'rb'), 100, 500, chunk_size=64))

    assert len(out) == 500
    assert out == f.read_bytes()[100:600]


def test_chunks_never_hold_the_whole_span(tmp_path):
    """The bug this replaces did f.read(length), pulling whole videos into RAM."""
    f = tmp_path / 'big.bin'
    f.write_bytes(b'x' * 100_000)

    sizes = [len(c) for c in file_chunks(open(f, 'rb'), 0, 100_000, chunk_size=8192)]

    assert max(sizes) <= 8192
    assert sum(sizes) == 100_000


def test_the_file_is_closed_when_the_client_stops_reading(tmp_path):
    """A viewer seeking away abandons the generator mid-stream."""
    f = tmp_path / 'clip.bin'
    f.write_bytes(b'y' * 10_000)
    handle = open(f, 'rb')

    gen = file_chunks(handle, 0, 10_000, chunk_size=100)
    next(gen)
    gen.close()

    assert handle.closed is True
