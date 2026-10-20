"""Client brand kits: colours, fonts and logos turned into design tokens.

A brand kit is a folder (brands/<client-id>/) holding brand.yaml plus its
logo and font files. Styles never hard-code colours or fonts; they read the
CSS custom properties generated here. See reference/brand-kits.md.
"""

from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import colors as C
from .brief import TONES
from .paths import CarouselError, brand_dirs

COLOR_REQUIRED = ["primary", "background", "text"]
COLOR_OPTIONAL = ["secondary", "accent", "surface", "dark", "on_primary", "on_accent", "on_dark"]
FONT_ROLES = ["heading", "body"]
FONT_KEYS = ["family", "files", "weight", "bold_weight", "fallback", "letter_spacing", "uppercase", "line_height", "variable"]
TOP_KEYS = ["name", "handle", "website", "colors", "fonts", "logo", "notes"]
LOGO_KEYS = ["default", "inverse", "height"]
FONT_EXTS = {".ttf": "truetype", ".otf": "opentype", ".woff": "woff", ".woff2": "woff2"}
LOGO_EXTS = {".svg", ".png", ".webp", ".jpg", ".jpeg"}
DEFAULT_FALLBACK = {"heading": "sans-serif", "body": "sans-serif"}
DEFAULT_WEIGHT = {"heading": 700, "body": 400}


@dataclass
class FontFace:
    family: str
    path: Path
    weight_min: int
    weight_max: int
    style: str

    def covers(self, weight: int) -> bool:
        return self.weight_min - 50 <= weight <= self.weight_max + 50


@dataclass
class Brand:
    id: str
    dir: Path
    name: str
    handle: str | None
    website: str | None
    colors: dict[str, C.RGB]
    fonts: dict[str, dict]
    faces: list[FontFace]
    logos: dict[str, Path]
    logo_height: int
    notes: str | None
    tones: dict[str, dict[str, C.RGB | str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    # ------------------------------------------------------------ css

    def css(self) -> str:
        parts = [self._font_face_css(), self._root_css()]
        for tone, values in self.tones.items():
            props = "".join(
                f"--{k.replace('_', '-')}:{C.to_hex(v) if isinstance(v, tuple) else v};"
                for k, v in values.items()
                if k != "logo"
            )
            parts.append(f".tone-{tone}{{{props}}}")
        return "\n".join(parts)

    def _font_face_css(self) -> str:
        rules = []
        for face in self.faces:
            fmt = FONT_EXTS[face.path.suffix.lower()]
            data = base64.b64encode(face.path.read_bytes()).decode("ascii")
            weight = f"{face.weight_min} {face.weight_max}" if face.weight_min != face.weight_max else str(face.weight_min)
            rules.append(
                "@font-face{"
                f"font-family:{_css_string(face.family)};"
                f"src:url(data:font/{face.path.suffix[1:].lower()};base64,{data}) format('{fmt}');"
                f"font-weight:{weight};font-style:{face.style};font-display:block;}}"
            )
        return "\n".join(rules)

    def _root_css(self) -> str:
        props = {f"--brand-{k.replace('_', '-')}": C.to_hex(v) for k, v in self.colors.items()}
        for role, spec in self.fonts.items():
            props[f"--font-{role}"] = f"{_css_string(spec['family'])}, {spec['fallback']}"
            props[f"--{role}-weight"] = str(spec["weight"])
            props[f"--{role}-tracking"] = str(spec.get("letter_spacing") or "normal")
            props[f"--{role}-transform"] = "uppercase" if spec.get("uppercase") else "none"
            if spec.get("line_height") is not None:
                props[f"--{role}-leading"] = str(spec["line_height"])
        props["--body-bold-weight"] = str(self.fonts["body"]["bold_weight"])
        props["--logo-height"] = f"{self.logo_height}px"
        return ":root{" + "".join(f"{k}:{v};" for k, v in props.items()) + "}"

    # ------------------------------------------------------------ assets

    def logo_uri(self, tone: str) -> str | None:
        variant = self.tones[tone]["logo"]
        path = self.logos.get(str(variant)) or self.logos.get("default")
        return data_uri(path) if path else None

    def families(self) -> list[str]:
        return list(dict.fromkeys(spec["family"] for spec in self.fonts.values()))

    def faces_for(self, family: str) -> list[FontFace]:
        return [f for f in self.faces if f.family.lower() == family.lower()]


def _css_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if path.suffix.lower() == ".svg":
        mime = "image/svg+xml"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


# ---------------------------------------------------------------- discovery


def find(ref: str) -> Path:
    """Resolve a brand reference (client id, folder, or brand.yaml path) to its folder."""
    candidate = Path(ref).expanduser()
    if candidate.is_file() and candidate.name in ("brand.yaml", "brand.yml"):
        return candidate.parent.resolve()
    if candidate.is_dir() and (candidate / "brand.yaml").exists():
        return candidate.resolve()
    for root in brand_dirs():
        folder = root / ref
        if (folder / "brand.yaml").exists():
            return folder.resolve()
    known = ", ".join(b for b, _ in list_all()) or "none"
    raise CarouselError(
        f"No brand kit called {ref!r}. Known brands: {known}.\n"
        "Create one with: carousel.py new-brand <client-id> --name \"Client Name\""
    )


def list_all() -> list[tuple[str, Path]]:
    seen: dict[str, Path] = {}
    for root in brand_dirs():
        if not root.is_dir():
            continue
        for folder in sorted(root.iterdir()):
            if (folder / "brand.yaml").exists() and folder.name not in seen and not folder.name.startswith("_"):
                seen[folder.name] = folder
    return sorted(seen.items())


# ---------------------------------------------------------------- loading


def load(ref: str) -> Brand:
    folder = find(ref)
    try:
        raw = yaml.safe_load((folder / "brand.yaml").read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CarouselError(f"{folder.name}/brand.yaml is not valid YAML:\n{exc}") from None
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(raw, dict):
        raise CarouselError(f"{folder.name}/brand.yaml must be a mapping")

    for key in raw:
        if key not in TOP_KEYS:
            errors.append(f"unknown field '{key}' (allowed: {', '.join(TOP_KEYS)})")
    if not raw.get("name"):
        errors.append("missing 'name'")

    palette = _load_colors(raw.get("colors"), errors)
    fonts, faces = _load_fonts(raw.get("fonts"), folder, errors, warnings)
    logos, logo_height = _load_logos(raw.get("logo"), folder, errors, warnings)

    if errors:
        raise CarouselError(f"Brand kit '{folder.name}' has {len(errors)} problem(s):\n  - " + "\n  - ".join(errors))

    handle = raw.get("handle")
    if handle and not str(handle).startswith("@"):
        handle = "@" + str(handle)
    brand = Brand(
        id=folder.name,
        dir=folder,
        name=str(raw["name"]),
        handle=str(handle) if handle else None,
        website=str(raw["website"]) if raw.get("website") else None,
        colors=palette,
        fonts=fonts,
        faces=faces,
        logos=logos,
        logo_height=logo_height,
        notes=str(raw["notes"]).strip() if raw.get("notes") else None,
        warnings=warnings,
    )
    brand.tones = derive_tones(brand)
    _check_contrast(brand)
    return brand


def _load_colors(raw: object, errors: list[str]) -> dict[str, C.RGB]:
    if not isinstance(raw, dict):
        errors.append("missing 'colors' (needs at least primary, background, text)")
        return {}
    palette: dict[str, C.RGB] = {}
    for key, value in raw.items():
        if key not in COLOR_REQUIRED + COLOR_OPTIONAL:
            errors.append(f"colors: unknown role '{key}' (allowed: {', '.join(COLOR_REQUIRED + COLOR_OPTIONAL)})")
        elif not C.is_hex(value):
            errors.append(f"colors.{key}: {value!r} is not a hex colour like \"#1A2B3C\" (quote it in YAML)")
        else:
            palette[key] = C.parse_hex(value)
    for key in COLOR_REQUIRED:
        if key not in raw:
            errors.append(f"colors: missing required role '{key}'")
    if errors:
        return palette

    palette.setdefault("secondary", palette["primary"])
    palette.setdefault("accent", palette["secondary"])
    palette.setdefault("surface", C.WHITE if not C.is_dark(palette["background"]) else C.mix(palette["background"], C.WHITE, 0.08))
    if "dark" not in palette:
        palette["dark"] = next(
            (palette[k] for k in ("secondary", "text", "primary") if C.luminance(palette[k]) < 0.06),
            C.NEAR_BLACK,
        )
    for role in ("primary", "accent", "dark", "secondary"):
        key = f"on_{role}"
        if key not in palette:
            palette[key] = _on(palette[role], palette)
    return palette


def _on(bg: C.RGB, palette: dict[str, C.RGB]) -> C.RGB:
    preferred = [palette["background"], palette["text"], C.WHITE, C.NEAR_BLACK]
    return C.first_readable(bg, preferred, 4.5, C.best_on(bg, preferred))


def _load_fonts(raw: object, folder: Path, errors: list[str], warnings: list[str]) -> tuple[dict, list[FontFace]]:
    fonts: dict[str, dict] = {}
    faces: list[FontFace] = []
    if not isinstance(raw, dict):
        errors.append("missing 'fonts' (needs heading and body)")
        return fonts, faces
    for role in raw:
        if role not in FONT_ROLES:
            errors.append(f"fonts: unknown role '{role}' (allowed: heading, body)")
    for role in FONT_ROLES:
        spec = raw.get(role)
        if isinstance(spec, str):
            spec = {"family": spec}
        if not isinstance(spec, dict) or not spec.get("family"):
            errors.append(f"fonts.{role}: needs at least a family name")
            continue
        for key in spec:
            if key not in FONT_KEYS:
                errors.append(f"fonts.{role}: unknown field '{key}' (allowed: {', '.join(FONT_KEYS)})")
        clean = {
            "family": str(spec["family"]).strip(),
            "weight": int(spec.get("weight", DEFAULT_WEIGHT[role])),
            "bold_weight": int(spec.get("bold_weight", 700)),
            "fallback": str(spec.get("fallback", DEFAULT_FALLBACK[role])),
            "letter_spacing": spec.get("letter_spacing"),
            "uppercase": bool(spec.get("uppercase", False)),
            "line_height": spec.get("line_height"),
        }
        fonts[role] = clean
        files = spec.get("files") or []
        if not files:
            warnings.append(
                f"fonts.{role}: no font files for {clean['family']!r}; it must be installed on the machine "
                "that renders (QA fails if it is missing)"
            )
        already = {(f.family, f.path) for f in faces}
        for entry in files if isinstance(files, list) else [files]:
            face = _load_face(entry, clean["family"], bool(spec.get("variable")), folder, role, errors)
            if face and (face.family, face.path) not in already:
                faces.append(face)
    return fonts, faces


def _load_face(entry: object, family: str, variable: bool, folder: Path, role: str, errors: list[str]) -> FontFace | None:
    if isinstance(entry, str):
        entry = {"path": entry}
    if not isinstance(entry, dict) or "path" not in entry:
        errors.append(f"fonts.{role}.files: each entry needs a path")
        return None
    path = (folder / str(entry["path"])).resolve()
    if path.suffix.lower() not in FONT_EXTS:
        errors.append(f"fonts.{role}: {path.name} must be one of {', '.join(FONT_EXTS)}")
        return None
    if not path.exists():
        errors.append(f"fonts.{role}: font file not found: {entry['path']}")
        return None
    is_variable = variable or "[" in path.name or "variable" in path.stem.lower()
    if "weight" in entry:
        weight = str(entry["weight"]).split()
        low, high = int(weight[0]), int(weight[-1])
    elif is_variable:
        low, high = 100, 900
    else:
        low = high = _weight_from_name(path.stem)
    style = str(entry.get("style") or ("italic" if "italic" in path.stem.lower() else "normal"))
    return FontFace(family, path, low, high, style)


_WEIGHT_NAMES = [
    ("extralight", 200), ("ultralight", 200), ("semibold", 600), ("demibold", 600), ("extrabold", 800),
    ("ultrabold", 800), ("thin", 100), ("light", 300), ("medium", 500), ("bold", 700), ("black", 900),
    ("heavy", 900),
]


def _weight_from_name(stem: str) -> int:
    lowered = re.sub(r"[^a-z]", "", stem.lower())
    for name, weight in _WEIGHT_NAMES:
        if name in lowered:
            return weight
    return 400


def _load_logos(raw: object, folder: Path, errors: list[str], warnings: list[str]) -> tuple[dict[str, Path], int]:
    if raw is None:
        warnings.append("no logo set; slides will render without one")
        return {}, 56
    if isinstance(raw, str):
        raw = {"default": raw}
    if not isinstance(raw, dict):
        errors.append("logo: must be a file name or a mapping with default/inverse")
        return {}, 56
    logos: dict[str, Path] = {}
    for key, value in raw.items():
        if key not in LOGO_KEYS:
            errors.append(f"logo: unknown field '{key}' (allowed: {', '.join(LOGO_KEYS)})")
        elif key != "height":
            path = (folder / str(value)).resolve()
            if path.suffix.lower() not in LOGO_EXTS:
                errors.append(f"logo.{key}: {path.name} must be one of {', '.join(sorted(LOGO_EXTS))}")
            elif not path.exists():
                errors.append(f"logo.{key}: file not found: {value}")
            else:
                logos[key] = path
    if "default" not in raw:
        errors.append("logo: missing 'default' (logo for light backgrounds)")
    elif "inverse" not in raw:
        warnings.append("logo: no 'inverse' version for dark backgrounds; the default logo is used everywhere")
    return logos, int(raw.get("height", 56))


# ---------------------------------------------------------------- tones


def derive_tones(brand: Brand) -> dict[str, dict]:
    """Resolve each slide tone into the semantic colours templates use.

    Templates only reference these semantic tokens, so one style works for every client:
      --bg --fg --muted --line            slide background, text, secondary text, hairlines
      --hl                                highlight for large text and graphics (>= 3:1)
      --hl-small                          highlight for small text (>= 4.5:1)
      --on-hl                             text on a --hl fill (buttons)
      --card --on-card --card-muted       panels on top of the slide
      --card-hl --card-hl-small           highlights inside panels
    """
    p = brand.colors
    backgrounds = {
        "light": (p["background"], p["text"]),
        "brand": (p["primary"], p["on_primary"]),
        "dark": (p["dark"], p["on_dark"]),
        "accent": (p["accent"], p["on_accent"]),
    }
    highlight_order = {
        "light": [p["primary"], p["accent"], p["secondary"]],
        "brand": [p["accent"], p["secondary"], p["background"]],
        "dark": [p["accent"], p["primary"], p["background"]],
        "accent": [p["primary"], p["dark"], p["secondary"]],
    }
    tones = {}
    for tone in TONES:
        bg, fg = backgrounds[tone]
        options = [c for c in highlight_order[tone] if c != bg]
        hl = C.first_readable(bg, options, 3.0, fg)
        card = p["surface"] if C.contrast(p["surface"], bg) >= 1.15 else (C.WHITE if C.is_dark(bg) else p["background"])
        if card == bg:
            card = C.mix(bg, C.WHITE if C.is_dark(bg) else C.NEAR_BLACK, 0.08)
        on_card = C.first_readable(card, [p["text"], p["dark"], C.NEAR_BLACK, C.WHITE], 4.5, C.best_on(card, [C.NEAR_BLACK, C.WHITE]))
        card_options = [p["primary"], p["accent"], p["secondary"]]
        tones[tone] = {
            "bg": bg,
            "fg": fg,
            "muted": C.muted(fg, bg),
            "hl": hl,
            "hl_small": C.first_readable(bg, options, 4.5, fg),
            "on_hl": C.best_on(hl, [bg, fg, C.WHITE, C.NEAR_BLACK]),
            "line": C.mix(fg, bg, 0.78),
            "card": card,
            "on_card": on_card,
            "card_muted": C.muted(on_card, card),
            "card_hl": C.first_readable(card, card_options, 3.0, on_card),
            "card_hl_small": C.first_readable(card, card_options, 4.5, on_card),
            "logo": "inverse" if C.is_dark(bg) and "inverse" in brand.logos else "default",
        }
    return tones


def _check_contrast(brand: Brand) -> None:
    p = brand.colors
    pairs = [("text", "background")] + [(f"on_{r}", r) for r in ("primary", "accent", "dark")]
    for fg, bg in pairs:
        ratio = C.contrast(p[fg], p[bg])
        if ratio < 4.5:
            brand.warnings.append(
                f"colors: {fg} on {bg} is only {ratio:.2f}:1 (needs 4.5:1 for body text); "
                f"avoid the '{_tone_for(bg)}' tone for small copy or adjust the colour"
            )


def _tone_for(role: str) -> str:
    return {"background": "light", "primary": "brand", "accent": "accent", "dark": "dark"}[role]
