"""QK-DEC-090/091 public print geometry constants."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

ALPHABET = "23456789abcdefghijkmnpqrstuvwxyz"
ERASURE = "?"
WRAP_WIDTH = 64


class ProfileName(str, Enum):
    RS72_60 = "Rs72_60"
    RS76_60 = "Rs76_60"
    RS80_60 = "Rs80_60"


@dataclass(frozen=True)
class GridLayout:
    profile: ProfileName
    symbol_count: int
    line_lengths: tuple[int, int]

    def __post_init__(self) -> None:
        if sum(self.line_lengths) != self.symbol_count:
            raise ValueError("line lengths must cover the exact transcript")
        if self.line_lengths[0] != WRAP_WIDTH:
            raise ValueError("the presentation break is fixed after symbol 64")


PROFILE_LAYOUTS = {
    ProfileName.RS72_60: GridLayout(ProfileName.RS72_60, 116, (64, 52)),
    ProfileName.RS76_60: GridLayout(ProfileName.RS76_60, 122, (64, 58)),
    ProfileName.RS80_60: GridLayout(ProfileName.RS80_60, 128, (64, 64)),
}


def layout_for(profile: ProfileName | str) -> GridLayout:
    try:
        name = profile if isinstance(profile, ProfileName) else ProfileName(profile)
    except ValueError as exc:
        raise ValueError("unknown QK-DEC-091 profile") from exc
    return PROFILE_LAYOUTS[name]
