"""Automated QA: every carousel passes these checks before it is exported.

Errors block export (unless --force). Warnings are reported but don't block.
Each issue names the slide and brief field and says how to fix it, so a
revision is usually a one-line edit to the brief. See reference/qa-checks.md.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image

from . import colors as C
from . import markup
from .brand import Brand
from .brief import Brief
from .style import Style

CONTRAST_BODY = 4.5
CONTRAST_LARGE = 3.0
CONTRAST_TOLERANCE = 0.05
SHRINK_WARNING = 0.82
UPSCALE_WARNING = 1.15

_PLACEHOLDER = re.compile(
    r"lorem ipsum|\bTODO\b|\bTBD\b|\bTKTK\b|\bXXX+\b|\[[^\]]{0,40}\]|\{\{|\}\}|<[^>]{0,40}>",
    re.I,
)


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    check: str
    message: str
    hint: str = ""
    slide: int | None = None
    field: str | None = None
    rect: dict | None = None

    def label(self) -> str:
        where = f"slide {self.slide}" if self.slide else "carousel"
        if self.field:
            where += f" · {self.field}"
        return where


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)
    fits: list[dict] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def add(self, severity: str, check: str, message: str, hint: str = "", **where) -> None:
        self.issues.append(Issue(severity, check, message, hint, **where))

    def sort(self) -> None:
        self.issues.sort(key=lambda i: (i.severity != "error", i.slide or 0, i.check))

    def to_json(self) -> str:
        return json.dumps(
            {
                "passed": self.passed,
                "errors": len(self.errors),
                "warnings": len(self.warnings),
                "checks": self.checks_run,
                "issues": [asdict(i) for i in self.issues],
                "fit": self.fits,
            },
            indent=2,
        )

    def to_markdown(self, title: str) -> str:
        status = "PASSED" if self.passed else "FAILED"
        lines = [f"# QA report: {title}", "", f"**{status}**: {len(self.errors)} error(s), {len(self.warnings)} warning(s)", ""]
        for n, issue in enumerate(self.issues, start=1):
            icon = "ERROR" if issue.severity == "error" else "warning"
            lines.append(f"{n}. **{icon}** [{issue.label()}] {issue.message}")
            if issue.hint:
                lines.append(f"   - Fix: {issue.hint}")
        if not self.issues:
            lines.append("No issues found.")
        lines += ["", "Checks run: " + ", ".join(self.checks_run)]
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- copy checks (no browser needed)


def check_copy(brief: Brief, style: Style, report: Report) -> None:
    report.checks_run += ["placeholders", "copy-length", "slide-count"]
    total = len(brief.slides)
    if total == 1:
        report.add("warning", "slide-count", "Only one slide; this is a single post, not a carousel.",
                   "Add slides or confirm a single image is intended.")
    for index, slide in enumerate(brief.slides, start=1):
        for field_name, value in _copy_fields(slide):
            match = _PLACEHOLDER.search(value)
            if match:
                report.add("error", "placeholders", f"Placeholder text {match.group(0)!r} left in the copy.",
                           "Replace it with final copy.", slide=index, field=field_name)
        limits = style.limits.get(slide["layout"], {})
        for field_name, value in _copy_fields(slide):
            key = "item_title" if field_name.endswith(".title") else "item_body" if field_name.endswith(".body") else field_name
            limit = limits.get(key)
            length = len(markup.plain(value))
            if limit and length > limit:
                report.add("warning", "copy-length",
                           f"{field_name} is {length} characters; {style.name} is designed for {limit} or fewer.",
                           f"Trim about {length - limit} characters, or split it across two slides.",
                           slide=index, field=field_name)
        if slide["layout"] == "list" and limits.get("items") and len(slide["items"]) > limits["items"]:
            report.add("warning", "copy-length",
                       f"{len(slide['items'])} list items; {style.name} is designed for up to {limits['items']}.",
                       "Move the extra items onto a second list slide.", slide=index, field="items")


def _copy_fields(slide: dict):
    for key, value in slide.items():
        if key in ("layout", "tone", "notes", "image", "fit", "focus", "numbered"):
            continue
        if key == "items":
            for n, item in enumerate(value, start=1):
                for part in ("title", "body"):
                    if item.get(part):
                        yield f"items[{n}].{part}", item[part]
        elif isinstance(value, str):
            yield key, value


# ---------------------------------------------------------------- layout checks (from the rendered page)


def check_layout(page_data: dict, fits: list[dict], backgrounds: dict[int, Image.Image],
                 brand: Brand, style: Style, report: Report) -> None:
    report.checks_run += ["fonts", "overflow", "text-shrink", "safe-zone", "overlap", "contrast", "logo", "images", "orphans"]
    report.fits = fits
    _check_fonts(page_data, brand, report)
    for fit in fits:
        if fit["overflow"]:
            report.add("error", "overflow", "Copy doesn't fit even at the smallest allowed text size.",
                       "Shorten this copy or split it across two slides.",
                       slide=fit["slide"], field=fit["field"], rect=fit["rect"])
        elif fit["fit"] < SHRINK_WARNING:
            report.add("warning", "text-shrink",
                       f"Copy was shrunk to {round(fit['fit'] * 100)}% of the design size to fit.",
                       "Fine to ship; trim the copy if it should match the other slides' type size.",
                       slide=fit["slide"], field=fit["field"], rect=fit["rect"])

    for slide in page_data["slides"]:
        index = slide["index"]
        elements = slide["elements"]
        for el in elements:
            if el["kind"] == "text":
                _check_text(el, index, backgrounds.get(index), style, report)
            elif el["kind"] == "logo" and not el["loaded"]:
                report.add("error", "logo", "Logo failed to load.", "Check the logo file in the brand kit.",
                           slide=index, rect=el["rect"])
            elif el["kind"] == "image":
                _check_image(el, index, report)
            if el["kind"] in ("text", "logo"):
                _check_safe_zone(el, index, style, report)
        _check_overlaps(elements, index, report)


def _check_fonts(page_data: dict, brand: Brand, report: Report) -> None:
    for family, ok in page_data["fonts"].items():
        if not ok:
            report.add("error", "fonts", f"Brand font {family!r} isn't available, so a fallback font would be used.",
                       f"Add the font files to brands/{brand.id}/fonts and list them in brand.yaml.")
    for family in sorted(set(page_data["faceErrors"])):
        report.add("error", "fonts", f"A font file for {family!r} failed to load (corrupt or unsupported).",
                   "Replace the file with a .ttf, .otf, .woff or .woff2 version.")
    seen = set()
    for slide in page_data["slides"]:
        for el in slide["elements"]:
            if el["kind"] != "text":
                continue
            family = el["fontFamily"].split(",")[0].strip().strip('"\'')
            faces = brand.faces_for(family)
            key = (family, el["fontWeight"])
            if faces and key not in seen and not any(f.covers(el["fontWeight"]) for f in faces):
                seen.add(key)
                have = sorted({f"{f.weight_min}" if f.weight_min == f.weight_max else f"{f.weight_min}-{f.weight_max}" for f in faces})
                report.add("warning", "fonts",
                           f"{family} weight {el['fontWeight']} isn't in the brand kit (has {', '.join(have)}), so the browser fakes it.",
                           "Add that weight's font file, or set the weight in brand.yaml to one that exists.",
                           slide=slide["index"], field=el["field"])


def _check_text(el: dict, index: int, background: Image.Image | None, style: Style, report: Report) -> None:
    if el.get("overflowX"):
        report.add("error", "overflow", f"A word is too long for its line: {el['text'][:40]!r}.",
                   "Shorten or break the long word/URL.", slide=index, field=el["field"], rect=el["rect"])
    if el.get("role") == "headline" and el.get("lines"):
        rows = el["lines"]
        if len(rows) >= 2 and len(rows[-1]) == 1 and len(rows[-1][0]) <= 12:
            report.add("warning", "orphans", f"Headline ends with a single word on its own line ({rows[-1][0]!r}).",
                       "Reword slightly, or add a manual line break in the copy.", slide=index, field=el["field"], rect=el["rect"])
    if background is None:
        return
    for part in [el, *el.get("inline", [])]:
        ratio = _contrast_over(part, background)
        if ratio is None:
            continue
        large = part["fontSize"] >= 64 or (part["fontSize"] >= 48 and part["fontWeight"] >= 600)
        needed = CONTRAST_LARGE if large else CONTRAST_BODY
        if ratio + CONTRAST_TOLERANCE < needed:
            what = "Highlighted text" if part is not el else "Text"
            report.add("error", "contrast",
                       f"{what} {part['text'][:40]!r} has {ratio:.2f}:1 contrast; needs {needed}:1.",
                       "Change this slide's tone (e.g. tone: light or tone: dark), or adjust the brand colours.",
                       slide=index, field=el["field"], rect=part["rects"][0] if part.get("rects") else el["rect"])


def _contrast_over(part: dict, background: Image.Image) -> float | None:
    rgba = C.parse_css_color(part["color"])
    if rgba is None or not part.get("rects"):
        return None
    pixels = background.convert("RGB")
    width, height = pixels.size
    sx = width / 1080
    ratios = []
    for r in part["rects"]:
        cols = max(3, min(16, int(r["w"] / 24)))
        rows = max(2, min(8, int(r["h"] / 24)))
        for i in range(cols):
            for j in range(rows):
                x = int((r["x"] + 2 + (r["w"] - 4) * (i + 0.5) / cols) * sx)
                y = int((r["y"] + 2 + (r["h"] - 4) * (j + 0.5) / rows) * sx)
                if 0 <= x < width and 0 <= y < height:
                    bg = pixels.getpixel((x, y))[:3]
                    ratios.append(C.contrast(C.blend_over(rgba, bg), bg))
    if not ratios:
        return None
    ratios.sort()
    return ratios[len(ratios) // 10]


def _check_image(el: dict, index: int, report: Report) -> None:
    if not el["loaded"]:
        report.add("error", "images", "Image failed to load.", "Check the image file path in the brief.",
                   slide=index, field="image", rect=el["rect"])
        return
    shown_w, shown_h = el["rect"]["w"], el["rect"]["h"]
    nat_w, nat_h = el["naturalWidth"], el["naturalHeight"]
    if el["objectFit"] == "cover":
        scale = max(shown_w / nat_w, shown_h / nat_h)
    else:
        scale = min(shown_w / nat_w, shown_h / nat_h)
    if scale > UPSCALE_WARNING:
        report.add("warning", "images",
                   f"Image is {nat_w}x{nat_h}px but shown {scale:.1f}x larger, so it will look soft.",
                   f"Use a version at least {round(nat_w * scale)}px wide.", slide=index, field="image", rect=el["rect"])


def _check_safe_zone(el: dict, index: int, style: Style, report: Report) -> None:
    margin = style.meta_margin if el.get("role") == "meta" or el["kind"] == "logo" else style.safe_margin
    r = el["rect"]
    if r["w"] == 0 or r["h"] == 0:
        return
    inside = r["x"] >= margin - 1 and r["y"] >= margin - 1 and r["x"] + r["w"] <= 1080 - margin + 1 and r["y"] + r["h"] <= 1350 - margin + 1
    if not inside:
        what = "Logo" if el["kind"] == "logo" else f"Text {el['text'][:30]!r}"
        report.add("error", "safe-zone", f"{what} sits outside the {margin}px safe zone and may be cropped in feeds.",
                   "Shorten the copy so it stays inside the layout (or fix the style's layout).",
                   slide=index, field=el.get("field"), rect=r)


def _check_overlaps(elements: list[dict], index: int, report: Report) -> None:
    boxes = [e for e in elements if e["kind"] in ("text", "logo") and e["rect"]["w"] > 0]
    for a_i, a in enumerate(boxes):
        for b in boxes[a_i + 1:]:
            area = _intersection(a["rect"], b["rect"])
            if area > 16 and not _nested(a["rect"], b["rect"]):
                names = [e["field"] or e["kind"] for e in (a, b)]
                report.add("error", "overlap", f"{names[0]} overlaps {names[1]}.",
                           "Shorten one of them so they no longer collide.", slide=index, field=a.get("field"), rect=a["rect"])


def _intersection(a: dict, b: dict) -> float:
    w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return w * h if w > 0 and h > 0 else 0.0


def _nested(a: dict, b: dict) -> bool:
    def inside(x: dict, y: dict) -> bool:
        return x["x"] >= y["x"] - 1 and x["y"] >= y["y"] - 1 and x["x"] + x["w"] <= y["x"] + y["w"] + 1 and x["y"] + x["h"] <= y["y"] + y["h"] + 1
    return inside(a, b) or inside(b, a)


# ---------------------------------------------------------------- export checks


def check_exports(pngs: list[Path], pdf: Path | None, expected: tuple[int, int], report: Report) -> None:
    report.checks_run += ["export-png", "export-pdf"]
    for n, png in enumerate(pngs, start=1):
        with Image.open(png) as img:
            if img.size != expected:
                report.add("error", "export-png", f"{png.name} is {img.size[0]}x{img.size[1]}, expected {expected[0]}x{expected[1]}.",
                           "Re-render; this indicates a broken style layout.", slide=n)
        if png.stat().st_size > 8 * 1024 * 1024:
            report.add("warning", "export-png", f"{png.name} is over 8 MB; some platforms will recompress it.", slide=n)
    if pdf is None:
        return
    from pypdf import PdfReader

    reader = PdfReader(str(pdf))
    if len(reader.pages) != len(pngs):
        report.add("error", "export-pdf", f"PDF has {len(reader.pages)} pages for {len(pngs)} slides.",
                   "Re-render; a slide is spilling onto an extra page.")
    for n, page in enumerate(reader.pages, start=1):
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        if abs(w / h - 0.8) > 0.01:
            report.add("error", "export-pdf", f"PDF page {n} is {w:.0f}x{h:.0f}pt, not 4:5.", "Re-render.", slide=n)
