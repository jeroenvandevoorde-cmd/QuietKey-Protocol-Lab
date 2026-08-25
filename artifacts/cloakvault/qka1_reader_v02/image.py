"""Bounded standard-library image primitives for Reader v0.2.

Only non-interlaced 8-bit PNG is accepted.  The decoder validates chunk CRCs,
rejects unknown critical chunks, bounds dimensions, and returns immutable
grayscale pixels.  It is an image transport decoder, not a QuietKey codec.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_PIXELS = 20_000_000
_MAX_PNG_BYTES = 64_000_000


@dataclass(frozen=True)
class GrayImage:
    width: int
    height: int
    pixels: bytes

    def __post_init__(self) -> None:
        if type(self.width) is not int or type(self.height) is not int:
            raise ValueError("image dimensions must be integers")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("image dimensions must be positive")
        if self.width * self.height > _MAX_PIXELS:
            raise ValueError("image exceeds the bounded pixel count")
        if type(self.pixels) is not bytes or len(self.pixels) != self.width * self.height:
            raise ValueError("grayscale image byte count mismatch")

    def pixel(self, x: int, y: int) -> int:
        if not 0 <= x < self.width or not 0 <= y < self.height:
            raise ValueError("pixel coordinate lies outside the image")
        return self.pixels[y * self.width + x]

    def resample_box(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        out_width: int,
        out_height: int,
    ) -> "GrayImage":
        """Rectify an axis-aligned page box into one fixed-size patch."""

        if not 0.0 <= x0 < x1 <= self.width or not 0.0 <= y0 < y1 <= self.height:
            raise ValueError("sample box lies outside the image")
        if out_width <= 0 or out_height <= 0:
            raise ValueError("output dimensions must be positive")
        out = bytearray(out_width * out_height)
        for oy in range(out_height):
            sy = y0 + (oy + 0.5) * (y1 - y0) / out_height
            iy = min(self.height - 1, max(0, int(sy)))
            row = iy * self.width
            for ox in range(out_width):
                sx = x0 + (ox + 0.5) * (x1 - x0) / out_width
                ix = min(self.width - 1, max(0, int(sx)))
                out[oy * out_width + ox] = self.pixels[row + ix]
        return GrayImage(out_width, out_height, bytes(out))


def _paeth(a: int, b: int, c: int) -> int:
    estimate = a + b - c
    da = abs(estimate - a)
    db = abs(estimate - b)
    dc = abs(estimate - c)
    if da <= db and da <= dc:
        return a
    return b if db <= dc else c


def _unfilter(scan: bytes, prior: bytes, filter_type: int, bpp: int) -> bytes:
    row = bytearray(scan)
    if filter_type == 0:
        return bytes(row)
    if filter_type == 2:
        return bytes((value + prior[i]) & 0xFF for i, value in enumerate(row))
    for i, value in enumerate(row):
        left = row[i - bpp] if i >= bpp else 0
        above = prior[i]
        upper_left = prior[i - bpp] if i >= bpp else 0
        if filter_type == 1:
            predictor = left
        elif filter_type == 3:
            predictor = (left + above) // 2
        elif filter_type == 4:
            predictor = _paeth(left, above, upper_left)
        else:
            raise ValueError("unsupported PNG row filter")
        row[i] = (value + predictor) & 0xFF
    return bytes(row)


def decode_png(raw: bytes) -> GrayImage:
    if type(raw) is not bytes or not raw.startswith(_PNG_SIGNATURE):
        raise ValueError("frame is not a PNG byte string")
    if len(raw) > _MAX_PNG_BYTES:
        raise ValueError("PNG exceeds the bounded transport size")
    offset = len(_PNG_SIGNATURE)
    width = height = bit_depth = color_type = interlace = None
    compressed: list[bytes] = []
    saw_iend = False
    while offset < len(raw):
        if offset + 12 > len(raw):
            raise ValueError("truncated PNG chunk")
        length = struct.unpack(">I", raw[offset : offset + 4])[0]
        kind = raw[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(raw):
            raise ValueError("truncated PNG chunk data")
        data = raw[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", raw[offset + 8 + length : end])[0]
        if zlib.crc32(data, zlib.crc32(kind)) & 0xFFFFFFFF != expected_crc:
            raise ValueError("PNG chunk CRC mismatch")
        offset = end
        if kind == b"IHDR":
            if width is not None or length != 13:
                raise ValueError("invalid PNG header")
            width, height, bit_depth, color_type, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", data)
            )
            if compression != 0 or filtering != 0:
                raise ValueError("unsupported PNG compression or filter method")
        elif kind == b"IDAT":
            compressed.append(data)
        elif kind == b"IEND":
            if length != 0:
                raise ValueError("invalid PNG terminator")
            saw_iend = True
            break
        elif kind[:1].isupper() and kind not in {b"PLTE"}:
            raise ValueError("unsupported critical PNG chunk")
    if not saw_iend or offset != len(raw):
        raise ValueError("PNG must end exactly at IEND")
    if width is None or height is None or not compressed:
        raise ValueError("PNG is missing required chunks")
    if width <= 0 or height <= 0 or width * height > _MAX_PIXELS:
        raise ValueError("PNG dimensions exceed the bounded pixel count")
    if bit_depth != 8 or interlace != 0 or color_type not in {0, 2, 4, 6}:
        raise ValueError("only non-interlaced 8-bit gray/RGB PNG is supported")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    stride = width * channels
    expected_length = height * (stride + 1)
    try:
        decompressor = zlib.decompressobj()
        filtered = decompressor.decompress(
            b"".join(compressed), expected_length + 1
        )
    except zlib.error as exc:
        raise ValueError("invalid PNG compressed data") from exc
    if (
        len(filtered) != expected_length
        or not decompressor.eof
        or decompressor.unconsumed_tail
        or decompressor.unused_data
    ):
        raise ValueError("PNG decompressed byte count mismatch")

    rows: list[bytes] = []
    prior = bytes(stride)
    cursor = 0
    for _ in range(height):
        filter_type = filtered[cursor]
        scan = filtered[cursor + 1 : cursor + 1 + stride]
        cursor += stride + 1
        prior = _unfilter(scan, prior, filter_type, channels)
        rows.append(prior)

    gray = bytearray(width * height)
    at = 0
    for row in rows:
        for x in range(width):
            start = x * channels
            if color_type in {0, 4}:
                value = row[start]
            else:
                red, green, blue = row[start : start + 3]
                value = (299 * red + 587 * green + 114 * blue + 500) // 1000
            if color_type in {4, 6}:
                alpha = row[start + channels - 1]
                value = (value * alpha + 255 * (255 - alpha) + 127) // 255
            gray[at] = value
            at += 1
    return GrayImage(width, height, bytes(gray))
