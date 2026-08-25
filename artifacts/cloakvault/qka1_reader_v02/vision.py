"""Deterministic page detection, projective rectification, and profile inference."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from .constants import PROFILE_LAYOUTS, ProfileName
from .image import GrayImage, decode_png
from .interfaces import LocatedFooter, LocationFailure

_CONFIG_FIELDS = frozenset(
    {
        "format",
        "artifact_id",
        "page_aspect_ratio",
        "page_aspect_tolerance",
        "page_threshold",
        "page_fill_fraction",
        "min_page_fraction",
        "footer_left_fraction",
        "cell_pitch_fraction",
        "line_top_fractions",
        "line_height_fraction",
        "patch_width",
        "patch_height",
        "profile_ink_threshold",
        "profile_ink_margin",
    }
)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate geometry field: {key}")
        result[key] = value
    return result


def _fraction(value: Any, name: str, *, allow_one: bool = False) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    upper_ok = number <= 1.0 if allow_one else number < 1.0
    if number <= 0.0 or not upper_ok:
        raise ValueError(f"{name} must be in the required fractional range")
    return number


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


def _cross(
    first: tuple[float, float],
    second: tuple[float, float],
    third: tuple[float, float],
) -> float:
    return (second[0] - first[0]) * (third[1] - second[1]) - (
        second[1] - first[1]
    ) * (third[0] - second[0])


def _fit_line(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Return the least-squares line y = slope*x + intercept."""

    if len(points) < 2:
        raise ValueError("page edge has too few samples")
    count = len(points)
    mean_x = sum(point[0] for point in points) / count
    mean_y = sum(point[1] for point in points) / count
    denominator = sum((point[0] - mean_x) ** 2 for point in points)
    if denominator <= 0.0:
        raise ValueError("page edge samples have no span")
    slope = sum(
        (point[0] - mean_x) * (point[1] - mean_y) for point in points
    ) / denominator
    return slope, mean_y - slope * mean_x


def _edge_intersection(
    horizontal: tuple[float, float], vertical: tuple[float, float]
) -> tuple[float, float]:
    """Intersect y=mh*x+bh with x=mv*y+bv."""

    mh, bh = horizontal
    mv, bv = vertical
    denominator = 1.0 - mv * mh
    if abs(denominator) < 1e-12:
        raise ValueError("page edges do not have a finite intersection")
    x = (mv * bh + bv) / denominator
    return x, mh * x + bh


@dataclass(frozen=True)
class _ProjectiveMap:
    """Eight-coefficient map from the unit square into an image quadrilateral."""

    a: float
    b: float
    c: float
    d: float
    e: float
    f: float
    g: float
    h: float

    @classmethod
    def from_quad(
        cls,
        top_left: tuple[float, float],
        top_right: tuple[float, float],
        bottom_right: tuple[float, float],
        bottom_left: tuple[float, float],
    ) -> "_ProjectiveMap":
        x0, y0 = top_left
        x1, y1 = top_right
        x2, y2 = bottom_right
        x3, y3 = bottom_left
        dx1 = x1 - x2
        dx2 = x3 - x2
        dx3 = x0 - x1 + x2 - x3
        dy1 = y1 - y2
        dy2 = y3 - y2
        dy3 = y0 - y1 + y2 - y3
        if dx3 == 0 and dy3 == 0:
            g = h = 0.0
        else:
            denominator = dx1 * dy2 - dx2 * dy1
            if denominator == 0:
                raise ValueError("page quadrilateral has no projective solution")
            g = (dx3 * dy2 - dx2 * dy3) / denominator
            h = (dx1 * dy3 - dx3 * dy1) / denominator
        result = cls(
            a=x1 - x0 + g * x1,
            b=x3 - x0 + h * x3,
            c=float(x0),
            d=y1 - y0 + g * y1,
            e=y3 - y0 + h * y3,
            f=float(y0),
            g=g,
            h=h,
        )
        for u, v in ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)):
            result.point(u, v)
        return result

    def point(self, u: float, v: float) -> tuple[float, float]:
        denominator = self.g * u + self.h * v + 1.0
        if abs(denominator) < 1e-12:
            raise ValueError("page projective denominator is singular")
        return (
            (self.a * u + self.b * v + self.c) / denominator,
            (self.d * u + self.e * v + self.f) / denominator,
        )


class DeterministicLocator:
    """Infer one page quadrilateral, rectify its footer, and infer its profile.

    Only frame pixels and this exact hashed configuration are consumed. Page
    corners come from the page itself; no body text, rig fiducial, scale-bar
    coordinate, manual crop, profile label, or candidate list is accepted.
    """

    def __init__(self, config_bytes: bytes) -> None:
        if type(config_bytes) is not bytes or not config_bytes:
            raise ValueError("geometry configuration must be immutable bytes")
        try:
            data = json.loads(
                config_bytes.decode("utf-8"), object_pairs_hook=_strict_object
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("geometry configuration must be UTF-8 JSON") from exc
        if not isinstance(data, dict) or frozenset(data) != _CONFIG_FIELDS:
            raise ValueError("geometry fields must match the frozen schema exactly")
        if data["format"] != "qka1-reader-geometry-v2":
            raise ValueError("unsupported geometry format")
        artifact_id = data["artifact_id"]
        if (
            not isinstance(artifact_id, str)
            or not artifact_id
            or artifact_id.strip() != artifact_id
        ):
            raise ValueError("geometry artifact_id must be non-empty")
        self.artifact_id = artifact_id
        self.artifact_sha256 = hashlib.sha256(config_bytes).hexdigest()
        self._aspect = _fraction(data["page_aspect_ratio"], "page_aspect_ratio")
        self._aspect_tolerance = _fraction(
            data["page_aspect_tolerance"], "page_aspect_tolerance"
        )
        threshold = data["page_threshold"]
        if type(threshold) is not int or not 1 <= threshold <= 255:
            raise ValueError("page_threshold must be an integer in [1,255]")
        self._page_threshold = threshold
        self._page_fill = _fraction(
            data["page_fill_fraction"], "page_fill_fraction", allow_one=True
        )
        self._min_page = _fraction(
            data["min_page_fraction"], "min_page_fraction", allow_one=True
        )
        self._footer_left = _fraction(
            data["footer_left_fraction"], "footer_left_fraction"
        )
        self._cell_pitch = _fraction(
            data["cell_pitch_fraction"], "cell_pitch_fraction"
        )
        line_tops = data["line_top_fractions"]
        if not isinstance(line_tops, list) or len(line_tops) != 2:
            raise ValueError("line_top_fractions must contain exactly two values")
        self._line_tops = tuple(
            _fraction(value, "line_top_fraction") for value in line_tops
        )
        if self._line_tops[0] >= self._line_tops[1]:
            raise ValueError("footer line order must be top-to-bottom")
        self._line_height = _fraction(
            data["line_height_fraction"], "line_height_fraction"
        )
        if self._line_tops[-1] + self._line_height > 1.0:
            raise ValueError("footer line box extends below the page")
        patch_width = data["patch_width"]
        patch_height = data["patch_height"]
        if type(patch_width) is not int or not 4 <= patch_width <= 64:
            raise ValueError("patch_width must be an integer in [4,64]")
        if type(patch_height) is not int or not 4 <= patch_height <= 64:
            raise ValueError("patch_height must be an integer in [4,64]")
        self._patch_width = patch_width
        self._patch_height = patch_height
        self._profile_ink = _fraction(
            data["profile_ink_threshold"], "profile_ink_threshold"
        )
        self._profile_margin = _fraction(
            data["profile_ink_margin"], "profile_ink_margin"
        )
        if self._profile_margin >= self._profile_ink:
            raise ValueError("profile ink margin must be below its threshold")
        if self._profile_ink + self._profile_margin >= 1.0:
            raise ValueError("profile ink threshold and margin exceed one")

    def locate(self, frame_bytes: bytes) -> LocatedFooter | LocationFailure:
        try:
            image = decode_png(frame_bytes)
        except ValueError:
            return LocationFailure("FOOTER_NOT_LOCATED")
        quad = self._page_quad(image)
        if quad is None:
            return LocationFailure("FOOTER_GEOMETRY_UNSUPPORTED")
        try:
            mapping = _ProjectiveMap.from_quad(*quad)
            cells = self._extract_max_grid(image, mapping)
        except ValueError:
            return LocationFailure("FOOTER_GEOMETRY_UNSUPPORTED")
        profile = self._infer_profile(cells)
        if profile is None:
            return LocationFailure("PROFILE_AMBIGUOUS")
        count = PROFILE_LAYOUTS[profile].symbol_count
        return LocatedFooter(
            profile=profile,
            cells=cells[:count],
            automatic=True,
            used_decoy_text=False,
            used_rig_marks=False,
            candidate_count=1,
        )

    def _page_quad(
        self, image: GrayImage
    ) -> tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ] | None:
        width = image.width
        height = image.height
        minimum_bright = int(width * height * self._page_fill)
        bright_count = 0
        min_y: list[int | None] = [None] * width
        max_y: list[int | None] = [None] * width
        min_x: list[int | None] = [None] * height
        max_x: list[int | None] = [None] * height
        for index, value in enumerate(image.pixels):
            if value < self._page_threshold:
                continue
            bright_count += 1
            y, x = divmod(index, width)
            if min_y[x] is None:
                min_y[x] = y
            max_y[x] = y
            if min_x[y] is None:
                min_x[y] = x
            max_x[y] = x
        if bright_count < minimum_bright:
            return None
        x_samples = [x for x, value in enumerate(min_y) if value is not None]
        y_samples = [y for y, value in enumerate(min_x) if value is not None]
        if len(x_samples) < 4 or len(y_samples) < 4:
            return None
        x_low, x_high = min(x_samples), max(x_samples)
        y_low, y_high = min(y_samples), max(y_samples)
        x_margin = (x_high - x_low) * 0.2
        y_margin = (y_high - y_low) * 0.2
        central_x = [
            x for x in x_samples if x_low + x_margin <= x <= x_high - x_margin
        ]
        central_y = [
            y for y in y_samples if y_low + y_margin <= y <= y_high - y_margin
        ]
        try:
            top = _fit_line([(x, float(min_y[x])) for x in central_x])
            bottom = _fit_line([(x, float(max_y[x])) for x in central_x])
            left = _fit_line([(y, float(min_x[y])) for y in central_y])
            right = _fit_line([(y, float(max_x[y])) for y in central_y])
            top = (top[0], top[1] - 0.5 * math.sqrt(1.0 + top[0] ** 2))
            bottom = (
                bottom[0],
                bottom[1] + 0.5 * math.sqrt(1.0 + bottom[0] ** 2),
            )
            left = (left[0], left[1] - 0.5 * math.sqrt(1.0 + left[0] ** 2))
            right = (
                right[0],
                right[1] + 0.5 * math.sqrt(1.0 + right[0] ** 2),
            )
            raw_quad = (
                _edge_intersection(top, left),
                _edge_intersection(top, right),
                _edge_intersection(bottom, right),
                _edge_intersection(bottom, left),
            )
        except ValueError:
            return None
        quad = tuple(
            (
                min(width - 1.0, max(0.0, point[0])),
                min(height - 1.0, max(0.0, point[1])),
            )
            for point in raw_quad
        )
        top_left, top_right, bottom_right, bottom_left = quad
        if any(
            _cross(quad[i], quad[(i + 1) % 4], quad[(i + 2) % 4]) <= 0
            for i in range(4)
        ):
            return None
        x_values = [point[0] for point in quad]
        y_values = [point[1] for point in quad]
        if max(x_values) - min(x_values) < width * self._min_page:
            return None
        if max(y_values) - min(y_values) < height * self._min_page:
            return None
        top_length = _distance(top_left, top_right)
        right_length = _distance(top_right, bottom_right)
        bottom_length = _distance(bottom_left, bottom_right)
        left_length = _distance(top_left, bottom_left)
        if min(top_length, right_length, bottom_length, left_length) <= 0.0:
            return None
        ratio = (top_length + bottom_length) / (left_length + right_length)
        if abs(ratio / self._aspect - 1.0) > self._aspect_tolerance:
            return None
        area_twice = sum(
            quad[i][0] * quad[(i + 1) % 4][1]
            - quad[(i + 1) % 4][0] * quad[i][1]
            for i in range(4)
        )
        if area_twice <= 0 or bright_count < (area_twice / 2.0) * self._page_fill:
            return None
        return quad

    def _extract_max_grid(
        self, image: GrayImage, mapping: _ProjectiveMap
    ) -> tuple[GrayImage, ...]:
        cells = []
        for row, count in enumerate((64, 64)):
            top = self._line_tops[row]
            bottom = top + self._line_height
            for column in range(count):
                left = self._footer_left + column * self._cell_pitch
                right = left + self._cell_pitch
                cells.append(
                    self._sample_patch(image, mapping, left, top, right, bottom)
                )
        return tuple(cells)

    def _sample_patch(
        self,
        image: GrayImage,
        mapping: _ProjectiveMap,
        u0: float,
        v0: float,
        u1: float,
        v1: float,
    ) -> GrayImage:
        out = bytearray(self._patch_width * self._patch_height)
        for oy in range(self._patch_height):
            v = v0 + (oy + 0.5) * (v1 - v0) / self._patch_height
            for ox in range(self._patch_width):
                u = u0 + (ox + 0.5) * (u1 - u0) / self._patch_width
                x, y = mapping.point(u, v)
                if not 0.0 <= x <= image.width - 1 or not 0.0 <= y <= image.height - 1:
                    raise ValueError("rectified footer sample leaves the frame")
                ix = min(image.width - 1, max(0, int(x + 0.5)))
                iy = min(image.height - 1, max(0, int(y + 0.5)))
                out[oy * self._patch_width + ox] = image.pixels[
                    iy * image.width + ix
                ]
        return GrayImage(self._patch_width, self._patch_height, bytes(out))

    def _ink_state(self, cells: tuple[GrayImage, ...]) -> bool | None:
        numerator = sum(255 - value for cell in cells for value in cell.pixels)
        denominator = len(cells) * self._patch_width * self._patch_height * 255
        fraction = numerator / denominator
        if fraction <= self._profile_ink - self._profile_margin:
            return False
        if fraction >= self._profile_ink + self._profile_margin:
            return True
        return None

    def _infer_profile(self, cells: tuple[GrayImage, ...]) -> ProfileName | None:
        if len(cells) != 128:
            return None
        second = cells[64:]
        common = self._ink_state(second[46:52])
        middle = self._ink_state(second[52:58])
        tail = self._ink_state(second[58:64])
        if common is not True:
            return None
        return {
            (False, False): ProfileName.RS72_60,
            (True, False): ProfileName.RS76_60,
            (True, True): ProfileName.RS80_60,
        }.get((middle, tail))
