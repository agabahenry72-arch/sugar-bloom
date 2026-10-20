"""Colour maths: hex parsing, WCAG contrast and token derivation helpers."""

from __future__ import annotations

import re

_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

RGB = tuple[int, int, int]

WHITE: RGB = (255, 255, 255)
NEAR_BLACK: RGB = (17, 17, 17)


def is_hex(value: object) -> bool:
    return isinstance(value, str) and bool(_HEX.match(value.strip()))


def parse_hex(value: str) -> RGB:
    match = _HEX.match(value.strip())
    if not match:
        raise ValueError(f"not a hex colour: {value!r}")
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))


def to_hex(rgb: RGB) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(c))) for c in rgb))


def _channel(c: float) -> float:
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: RGB) -> float:
    r, g, b = rgb
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: RGB, b: RGB) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a: RGB, b: RGB, t: float) -> RGB:
    """Blend a towards b by t (0 = a, 1 = b)."""
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


def blend_over(fg: tuple[int, int, int, float], bg: RGB) -> RGB:
    """Composite an RGBA colour (alpha 0..1) over an opaque background."""
    r, g, b, a = fg
    return (round(r * a + bg[0] * (1 - a)), round(g * a + bg[1] * (1 - a)), round(b * a + bg[2] * (1 - a)))


def best_on(bg: RGB, candidates: list[RGB]) -> RGB:
    """The candidate with the highest contrast against bg."""
    return max(candidates, key=lambda c: contrast(c, bg))


def first_readable(bg: RGB, candidates: list[RGB], minimum: float, fallback: RGB) -> RGB:
    """First candidate reaching `minimum` contrast against bg, else fallback."""
    for c in candidates:
        if contrast(c, bg) >= minimum:
            return c
    return fallback


def muted(fg: RGB, bg: RGB, minimum: float = 4.5) -> RGB:
    """A softer version of fg that still keeps `minimum` contrast on bg."""
    for t in (0.4, 0.33, 0.26, 0.2, 0.14, 0.08):
        candidate = mix(fg, bg, t)
        if contrast(candidate, bg) >= minimum:
            return candidate
    return fg


def is_dark(rgb: RGB) -> bool:
    return contrast(rgb, WHITE) > contrast(rgb, NEAR_BLACK)


_CSS_RGB = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)")


def parse_css_color(value: str) -> tuple[int, int, int, float] | None:
    """Parse a computed CSS colour (`rgb(...)` / `rgba(...)`) into RGBA."""
    match = _CSS_RGB.match(value.strip())
    if not match:
        if is_hex(value):
            return (*parse_hex(value), 1.0)
        return None
    r, g, b, a = match.groups()
    alpha = 1.0
    if a is not None:
        alpha = float(a[:-1]) / 100 if a.endswith("%") else float(a)
    return (round(float(r)), round(float(g)), round(float(b)), alpha)
