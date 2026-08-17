"""Adversarial tests for the v2 span-aware extractor's grouping rules.

Label integrity contract: mislabeling is strictly worse than dropping, so
any ambiguity (stray bands, wrong group size, wrong width pattern) must
reject the group — and a wrong group count must reject the whole capture.
"""
from dataclasses import dataclass

from reader.calibration.extract_v2 import (
    band_is_token_plausible, dedupe_same_line_bands, group_bands_by_spacing,
    is_footer_group)

WIDTHS = [87, 48, 50]


@dataclass
class Band:
    row_start: int
    row_end: int
    x0: int
    x1: int
    pitch: float


def _band(row: int, n_chars: int, pitch: float = 21.0, h: int = 28) -> Band:
    return Band(row, row + h, 100, 100 + int(round(n_chars * pitch)), pitch)


def _footer(row0: int, spacing: int = 40) -> list[Band]:
    return [_band(row0 + i * spacing, n) for i, n in enumerate(WIDTHS)]


def test_token_plausible_accepts_layout_consistent_and_harmonic():
    b = _band(0, 87, pitch=21.0)
    assert band_is_token_plausible(b, WIDTHS)
    # the known half-pitch harmonic must still be flagged plausible (it is
    # corrected downstream by the mandatory layout-consistent registration)
    b_h = _band(0, 87, pitch=21.0)
    b_h.pitch = 42.0
    assert band_is_token_plausible(b_h, WIDTHS)


def test_trailer_and_filler_are_not_token_plausible():
    # 32-char Printed trailer: ratio lands between the accepted windows
    trailer = _band(0, 32, pitch=21.0)
    assert not band_is_token_plausible(trailer, WIDTHS)
    filler = _band(0, 60, pitch=13.0)  # serif-ish geometry
    assert not band_is_token_plausible(filler, WIDTHS)


def test_exact_three_line_footer_is_accepted():
    assert is_footer_group(_footer(0), WIDTHS)


def test_stray_extra_band_rejects_whole_group():
    grp = _footer(0)
    grp.append(_band(120, 48))  # stray 4th token-plausible band
    assert not is_footer_group(grp, WIDTHS)


def test_partial_group_rejected():
    assert not is_footer_group(_footer(0)[:2], WIDTHS)


def test_wrong_width_order_rejected():
    grp = _footer(0)
    grp[0], grp[1] = grp[1], grp[0]  # URL line not first
    assert not is_footer_group(grp, WIDTHS)


def test_wrong_width_ratio_rejected():
    grp = [_band(0, 87), _band(40, 30), _band(80, 50)]
    assert not is_footer_group(grp, WIDTHS)


def test_grouping_splits_on_filler_gap():
    bands = _footer(0) + _footer(400)
    groups = group_bands_by_spacing(bands)
    assert [len(g) for g in groups] == [3, 3]


def test_harmonic_duplicate_of_same_line_is_deduped():
    # same physical line detected twice: a 2x-pitch harmonic band a few
    # rows above the true-pitch band, same horizontal span (observed on
    # real captures). Dedup keeps the layout-consistent one.
    harmonic = Band(3396, 3413, 588, 2027, 58.3)
    true_band = Band(3416, 3423, 591, 2002, 29.7)
    out = dedupe_same_line_bands([harmonic, true_band], WIDTHS)
    assert out == [true_band]


def test_distinct_lines_are_not_deduped():
    grp = _footer(0)
    assert dedupe_same_line_bands(grp, WIDTHS) == grp


def test_horizontally_disjoint_bands_are_not_deduped():
    a = _band(0, 48)
    b = Band(a.row_end + 2, a.row_end + 30, a.x1 + 500, a.x1 + 1500, 21.0)
    assert dedupe_same_line_bands([a, b], WIDTHS) == [a, b]


def test_interleaved_stray_band_cannot_silently_relabel():
    # a stray band inside a footer's vertical range joins that group and
    # (via is_footer_group) rejects it rather than shifting line roles
    bands = _footer(0)
    bands.insert(1, _band(20, 48))
    groups = group_bands_by_spacing(sorted(bands, key=lambda b: b.row_start))
    assert all(not is_footer_group(g, WIDTHS) for g in groups if len(g) != 3)
    assert not any(is_footer_group(g, WIDTHS) and len(g) == 4 for g in groups)
