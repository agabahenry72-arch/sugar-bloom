"""Where the skill looks for styles, brands and where it writes output.

Environment overrides (all optional):
  CAROUSEL_BRANDS_DIR   extra brand-kit folder(s), os.pathsep separated, searched first
  CAROUSEL_STYLES_DIR   extra style folder(s), os.pathsep separated, searched first
  CAROUSEL_OUTPUT_DIR   default output root (otherwise ./carousel-output)
  CAROUSEL_CHROMIUM     path to a Chromium/Chrome binary to render with
"""

from __future__ import annotations

import os
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
ENGINE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = ENGINE_DIR / "templates"


def _env_dirs(name: str) -> list[Path]:
    raw = os.environ.get(name, "")
    return [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()]


def brand_dirs() -> list[Path]:
    return _env_dirs("CAROUSEL_BRANDS_DIR") + [SKILL_ROOT / "brands"]


def style_dirs() -> list[Path]:
    return _env_dirs("CAROUSEL_STYLES_DIR") + [SKILL_ROOT / "styles"]


def default_output_root() -> Path:
    raw = os.environ.get("CAROUSEL_OUTPUT_DIR")
    return Path(raw).expanduser() if raw else Path.cwd() / "carousel-output"


class CarouselError(Exception):
    """A user-facing problem (bad brief, missing brand, ...). Message is shown as-is."""
