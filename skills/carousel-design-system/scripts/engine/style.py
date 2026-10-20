"""Carousel styles: reusable layouts that take their look from brand tokens.

A style is a folder (styles/<style-id>/) holding:
  style.yaml        name, description, default tones, copy limits, safe margins
  slides.html.j2    one Jinja macro per layout (cover, text, list, quote, stat, image, cta)
  style.css         layout CSS that only uses brand/tone custom properties
See reference/style-authoring.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError

from . import markup
from .brief import LAYOUTS, TONES
from .paths import TEMPLATES_DIR, CarouselError, style_dirs

STYLE_KEYS = ["name", "description", "best_for", "safe_margin", "meta_margin", "tones", "limits", "version"]


@dataclass
class Style:
    id: str
    dir: Path
    name: str
    description: str
    best_for: list[str]
    safe_margin: int
    meta_margin: int
    tones: dict[str, str]
    limits: dict[str, dict[str, int]]
    css: str
    env: Environment = field(repr=False)

    def tone_for(self, slide: dict) -> str:
        return slide.get("tone") or self.tones.get(slide["layout"]) or self.tones.get("default", "light")

    def macros(self, globals_: dict):
        return self.env.get_template("slides.html.j2").make_module(globals_)


def find(ref: str) -> Path:
    candidate = Path(ref).expanduser()
    if candidate.is_dir() and (candidate / "style.yaml").exists():
        return candidate.resolve()
    for root in style_dirs():
        folder = root / ref
        if (folder / "style.yaml").exists():
            return folder.resolve()
    known = ", ".join(s for s, _ in list_all()) or "none"
    raise CarouselError(f"No style called {ref!r}. Available styles: {known}")


def list_all() -> list[tuple[str, Path]]:
    seen: dict[str, Path] = {}
    for root in style_dirs():
        if not root.is_dir():
            continue
        for folder in sorted(root.iterdir()):
            if (folder / "style.yaml").exists() and folder.name not in seen and not folder.name.startswith("_"):
                seen[folder.name] = folder
    return sorted(seen.items())


def load(ref: str) -> Style:
    folder = find(ref)
    try:
        raw = yaml.safe_load((folder / "style.yaml").read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CarouselError(f"{folder.name}/style.yaml is not valid YAML:\n{exc}") from None
    errors = []
    for key in raw:
        if key not in STYLE_KEYS:
            errors.append(f"style.yaml: unknown field '{key}'")
    tones = dict(raw.get("tones") or {})
    for layout, tone in tones.items():
        if layout != "default" and layout not in LAYOUTS:
            errors.append(f"style.yaml tones: unknown layout '{layout}'")
        if tone not in TONES:
            errors.append(f"style.yaml tones.{layout}: '{tone}' is not one of {', '.join(TONES)}")
    for name in ("slides.html.j2", "style.css"):
        if not (folder / name).exists():
            errors.append(f"missing {name}")
    if errors:
        raise CarouselError(f"Style '{folder.name}' is broken:\n  - " + "\n  - ".join(errors))

    env = Environment(
        loader=FileSystemLoader([str(folder), str(TEMPLATES_DIR)]),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["md"] = markup.render
    style = Style(
        id=folder.name,
        dir=folder,
        name=str(raw.get("name", folder.name)),
        description=str(raw.get("description", "")).strip(),
        best_for=list(raw.get("best_for") or []),
        safe_margin=int(raw.get("safe_margin", 80)),
        meta_margin=int(raw.get("meta_margin", 40)),
        tones=tones,
        limits={k: dict(v) for k, v in (raw.get("limits") or {}).items()},
        css=(folder / "style.css").read_text(encoding="utf-8"),
        env=env,
    )
    try:
        module = style.macros({})
    except TemplateError as exc:
        raise CarouselError(f"Style '{folder.name}': slides.html.j2 failed to load: {exc}") from None
    missing = [layout for layout in LAYOUTS if not hasattr(module, layout)]
    if missing:
        raise CarouselError(f"Style '{folder.name}' has no macro for layout(s): {', '.join(missing)}")
    return style


_HEX_IN_CSS = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_FONT_FAMILY = re.compile(r"font-family\s*:\s*([^;}]+)")


def lint(style: Style) -> list[str]:
    """Catch styles that would ignore client branding."""
    problems = []
    css = re.sub(r"/\*.*?\*/", "", style.css, flags=re.S)
    for match in _HEX_IN_CSS.finditer(css):
        line = css[: match.start()].count("\n") + 1
        problems.append(f"style.css line {line}: hard-coded colour {match.group(0)}; use a token such as var(--hl)")
    for match in _FONT_FAMILY.finditer(css):
        value = match.group(1).strip()
        if "var(--font-" not in value and value not in ("inherit", "unset"):
            line = css[: match.start()].count("\n") + 1
            problems.append(f"style.css line {line}: font-family '{value}'; use var(--font-heading) or var(--font-body)")
    template = (style.dir / "slides.html.j2").read_text(encoding="utf-8")
    for match in _HEX_IN_CSS.finditer(re.sub(r"\{#.*?#\}", "", template, flags=re.S)):
        problems.append(f"slides.html.j2: hard-coded colour {match.group(0)}")
    if "data-qa" not in template:
        problems.append("slides.html.j2: no data-qa attributes; QA cannot check text (see style-authoring.md)")
    return problems
