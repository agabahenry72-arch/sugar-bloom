"""Load, parse and validate carousel briefs.

Two interchangeable formats are accepted:
  *.yaml / *.yml   structured brief (canonical)
  *.md / *.txt     copywriter brief (KEY: value lines, one `## n. layout` heading per slide)

Both normalise to the same dictionary; see reference/brief-format.md.
"""

from __future__ import annotations

import copy
import difflib
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import markup
from .paths import CarouselError

TONES = ("light", "brand", "dark", "accent")

LAYOUTS: dict[str, dict[str, list[str]]] = {
    "cover": {"required": ["headline"], "optional": ["eyebrow", "subhead"]},
    "text": {"required": ["body"], "optional": ["eyebrow", "headline"]},
    "list": {"required": ["items"], "optional": ["eyebrow", "headline", "numbered"]},
    "quote": {"required": ["quote"], "optional": ["author", "role"]},
    "stat": {"required": ["stat", "label"], "optional": ["eyebrow", "body", "source"]},
    "image": {"required": ["image"], "optional": ["headline", "caption", "fit", "focus"]},
    "cta": {"required": ["headline"], "optional": ["eyebrow", "body", "button"]},
}
SLIDE_COMMON = ["layout", "tone", "notes"]
TOP_REQUIRED = ["client", "style", "title", "slides"]
TOP_OPTIONAL = ["lang", "handle", "footer", "slide_numbers", "swipe_hint", "logo", "notes"]
BOOL_FIELDS = {"slide_numbers", "swipe_hint", "logo", "numbered"}
NON_COPY_FIELDS = {"layout", "tone", "notes", "image", "fit", "focus", "numbered"}

MAX_SLIDES = 20
MAX_LIST_ITEMS = 10
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
FIT_VALUES = ("cover", "contain")
FOCUS_VALUES = ("center", "top", "bottom", "left", "right")


@dataclass
class Brief:
    data: dict
    path: Path | None = None

    @property
    def slides(self) -> list[dict]:
        return self.data["slides"]

    @property
    def slug(self) -> str:
        return slugify(self.data["title"])

    def to_yaml(self, base_dir: Path | None = None) -> str:
        """Serialise as a YAML brief. Image paths are made relative to base_dir if given."""
        out = copy.deepcopy(self.data)
        for slide in out["slides"]:
            if slide.get("layout") == "list":
                slide["items"] = [_item_to_yaml(i) for i in slide["items"]]
            if "image" in slide and base_dir is not None:
                slide["image"] = os.path.relpath(slide["image"], base_dir)
        return yaml.safe_dump(out, sort_keys=False, allow_unicode=True, width=100)


def _item_to_yaml(item: dict) -> str | dict:
    if item.get("body") is None:
        return item["title"]
    return {k: v for k, v in item.items() if v is not None}


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", markup.plain(text).lower()).strip("-")
    return slug[:60].rstrip("-") or "carousel"


# ---------------------------------------------------------------- loading


def load(path: str | Path) -> Brief:
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise CarouselError(f"Brief not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise CarouselError(f"{path.name} is not valid YAML:\n{exc}") from None
    else:
        raw = parse_copy_brief(text)
    return validate(raw, base_dir=path.parent, path=path)


# ---------------------------------------------------------------- copy (markdown) brief

_SLIDE_HEADING = re.compile(r"^#{2,3}\s*(?:slide\s*)?(\d+)?\s*[.):\-–—]?\s*([A-Za-z]+)?\s*$", re.I)
_KEY_LINE = re.compile(r"^([A-Za-z][A-Za-z _-]{0,24}):\s?(.*)$")
_BULLET = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+(.*)$")


def parse_copy_brief(text: str) -> dict:
    """Parse the copywriter brief format into a raw brief dict.

    Values may span several lines: every line after `KEY:` belongs to that key
    until the next known `KEY:` or slide heading. On list slides, bullet lines
    become items (`- Title | optional body`).
    """
    top: dict = {}
    slides: list[dict] = []
    current: dict = top
    lines: dict[int, dict[str, list[str]]] = {id(top): {}}
    current_key: str | None = None
    errors: list[str] = []

    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("<!--"):
            continue
        if stripped.startswith("#") and not stripped.startswith("##"):
            continue  # a title line like "# Carousel brief" is decoration

        heading = _SLIDE_HEADING.match(stripped)
        if heading and stripped.startswith("##"):
            layout = (heading.group(2) or "").lower()
            current = {"layout": layout} if layout else {}
            slides.append(current)
            lines[id(current)] = {}
            current_key = None
            continue

        bullet = _BULLET.match(line)
        if bullet and current is not top and current.get("layout") == "list" and current_key != "notes":
            current.setdefault("items", []).append(_parse_item(bullet.group(1).strip()))
            current_key = "items"
            continue

        key_match = _KEY_LINE.match(stripped)
        if key_match and _norm_key(key_match.group(1)) in _known_keys(current is top):
            key = _norm_key(key_match.group(1))
            value = key_match.group(2).strip()
            if key == "items":
                current.setdefault("items", [])
                if value:
                    current["items"].append(_parse_item(value))
            else:
                lines[id(current)][key] = [value] if value else []
                current[key] = ""
            current_key = key
            continue

        buffer = lines[id(current)].get(current_key) if current_key else None
        if buffer is not None:
            buffer.append(stripped)
            continue
        if not stripped:
            continue
        where = f"slide {len(slides)}" if current is not top else "header"
        errors.append(f"line {lineno} ({where}): can't tell which field this belongs to: {stripped[:60]!r}")

    if errors:
        raise CarouselError("Couldn't read the copy brief:\n  - " + "\n  - ".join(errors))

    for block in [top, *slides]:
        for key, buffer in lines[id(block)].items():
            value = re.sub(r"\n{3,}", "\n\n", "\n".join(buffer)).strip()
            block[key] = _parse_bool(value) if key in BOOL_FIELDS else value
    top["slides"] = slides
    return top


def _parse_item(text: str) -> dict | str:
    if "|" in text:
        title, body = text.split("|", 1)
        return {"title": title.strip(), "body": body.strip()}
    return text


def _parse_bool(value: str) -> bool | str:
    lowered = value.strip().lower()
    if lowered in ("yes", "true", "on", "1"):
        return True
    if lowered in ("no", "false", "off", "0"):
        return False
    return value


def _norm_key(key: str) -> str:
    return re.sub(r"[\s-]+", "_", key.strip().lower())


def _known_keys(is_top: bool) -> set[str]:
    if is_top:
        return set(TOP_REQUIRED + TOP_OPTIONAL) - {"slides"}
    keys = set(SLIDE_COMMON)
    for spec in LAYOUTS.values():
        keys.update(spec["required"] + spec["optional"])
    return keys


# ---------------------------------------------------------------- validation


def validate(raw: object, base_dir: Path | None = None, path: Path | None = None) -> Brief:
    errors: list[str] = []
    if not isinstance(raw, dict):
        raise CarouselError("A brief must be a mapping with client, style, title and slides.")
    data = dict(raw)

    _check_fields(data, TOP_REQUIRED, TOP_OPTIONAL, "brief", errors)
    for key in ("client", "style", "title", "lang", "handle", "footer"):
        if key in data and data[key] is not None and not isinstance(data[key], str):
            data[key] = str(data[key])
    for key in BOOL_FIELDS & set(data):
        if not isinstance(data[key], bool):
            errors.append(f"brief: {key} must be yes/no (true/false), got {data[key]!r}")
    data.setdefault("lang", "en")
    data.setdefault("slide_numbers", True)
    data.setdefault("swipe_hint", True)
    data.setdefault("logo", True)

    slides = data.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("brief: slides must be a non-empty list")
        slides = []
    elif len(slides) > MAX_SLIDES:
        errors.append(f"brief: {len(slides)} slides; Instagram and LinkedIn allow at most {MAX_SLIDES}")

    clean_slides = []
    for index, slide in enumerate(slides, start=1):
        clean_slides.append(_validate_slide(slide, index, base_dir, errors))
    data["slides"] = clean_slides

    if errors:
        name = path.name if path else "brief"
        raise CarouselError(f"{name} has {len(errors)} problem(s):\n  - " + "\n  - ".join(errors))
    return Brief(data=data, path=path)


def _validate_slide(slide: object, index: int, base_dir: Path | None, errors: list[str]) -> dict:
    where = f"slide {index}"
    if not isinstance(slide, dict):
        errors.append(f"{where}: must be a mapping of fields, got {type(slide).__name__}")
        return {"layout": "text", "body": ""}
    slide = dict(slide)
    layout = str(slide.get("layout") or "").strip().lower()
    if layout not in LAYOUTS:
        hint = _suggest(layout, LAYOUTS)
        errors.append(f"{where}: layout {layout or '(missing)'!r} is not one of {', '.join(LAYOUTS)}{hint}")
        return slide
    slide["layout"] = layout
    where = f"slide {index} ({layout})"
    spec = LAYOUTS[layout]
    _check_fields(slide, ["layout", *spec["required"]], SLIDE_COMMON + spec["optional"], where, errors)

    tone = slide.get("tone")
    if tone is not None:
        tone = str(tone).strip().lower()
        if tone not in TONES:
            errors.append(f"{where}: tone {tone!r} must be one of {', '.join(TONES)}")
        slide["tone"] = tone

    for key, value in list(slide.items()):
        if key in ("items",) or key in BOOL_FIELDS:
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            slide[key] = value = str(value)
        if key not in NON_COPY_FIELDS and isinstance(value, str):
            if not value.strip():
                if key in spec["required"]:
                    errors.append(f"{where}: {key} is empty")
                else:
                    del slide[key]
                continue
            for problem in markup.problems(value):
                errors.append(f"{where}: {key} has {problem}")

    for key in BOOL_FIELDS & set(slide):
        if not isinstance(slide[key], bool):
            errors.append(f"{where}: {key} must be yes/no (true/false), got {slide[key]!r}")

    if layout == "list" and "items" in slide:
        slide["items"] = _validate_items(slide["items"], where, errors)
        slide.setdefault("numbered", True)

    if layout == "image" and "image" in slide:
        slide["image"] = _resolve_image(slide["image"], base_dir, where, errors)
        fit = str(slide.get("fit", "cover")).lower()
        if fit not in FIT_VALUES:
            errors.append(f"{where}: fit must be one of {', '.join(FIT_VALUES)}")
        slide["fit"] = fit
        focus = str(slide.get("focus", "center")).lower()
        if focus not in FOCUS_VALUES:
            errors.append(f"{where}: focus must be one of {', '.join(FOCUS_VALUES)}")
        slide["focus"] = focus
    return slide


def _validate_items(items: object, where: str, errors: list[str]) -> list[dict]:
    if not isinstance(items, list) or not items:
        errors.append(f"{where}: items must be a non-empty list")
        return []
    if len(items) > MAX_LIST_ITEMS:
        errors.append(f"{where}: {len(items)} items; split across slides (max {MAX_LIST_ITEMS})")
    clean = []
    for n, item in enumerate(items, start=1):
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            item = str(item)
        if isinstance(item, str):
            item = _parse_item(item) if "|" in item else {"title": item, "body": None}
        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
            errors.append(f"{where}: item {n} needs text (or a title)")
            continue
        unknown = set(item) - {"title", "body"}
        if unknown:
            errors.append(f"{where}: item {n} has unknown field(s) {', '.join(sorted(unknown))}; use title and body")
        entry = {"title": str(item["title"]).strip(), "body": (str(item["body"]).strip() or None) if item.get("body") else None}
        for key, value in entry.items():
            if value:
                for problem in markup.problems(value):
                    errors.append(f"{where}: item {n} {key} has {problem}")
        clean.append(entry)
    return clean


def _resolve_image(value: object, base_dir: Path | None, where: str, errors: list[str]) -> str:
    candidate = Path(str(value)).expanduser()
    if not candidate.is_absolute() and base_dir is not None:
        candidate = base_dir / candidate
    if candidate.suffix.lower() not in IMAGE_EXTS:
        errors.append(f"{where}: image must be one of {', '.join(sorted(IMAGE_EXTS))}: {value}")
    elif not candidate.exists():
        errors.append(f"{where}: image file not found: {candidate}")
    return str(candidate.resolve()) if candidate.exists() else str(candidate)


def _check_fields(block: dict, required: list[str], optional: list[str], where: str, errors: list[str]) -> None:
    allowed = set(required) | set(optional)
    for key in required:
        if key not in block or block[key] in (None, "", []):
            errors.append(f"{where}: missing required field '{key}'")
    for key in block:
        if key not in allowed:
            errors.append(f"{where}: unknown field '{key}'{_suggest(key, allowed)}")


def _suggest(word: str, options) -> str:
    match = difflib.get_close_matches(word, list(options), n=1, cutoff=0.6)
    return f" (did you mean '{match[0]}'?)" if match else ""
