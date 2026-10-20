"""Brief + brand + style -> QA-checked, versioned PNG/PDF export."""

from __future__ import annotations

import io
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup
from PIL import Image

from . import brand as brand_mod
from . import brief as brief_mod
from . import browser, contact_sheet, qa
from . import style as style_mod
from .paths import TEMPLATES_DIR, CarouselError, default_output_root

SLIDE_W, SLIDE_H = 1080, 1350
_VERSION = re.compile(r"^v(\d+)$")


@dataclass
class Result:
    status: str  # "exported" | "qa_failed" | "checked"
    out_dir: Path
    report: qa.Report
    brief: brief_mod.Brief
    brand: brand_mod.Brand
    style: style_mod.Style
    pngs: list[Path] = field(default_factory=list)
    pdf: Path | None = None
    sheet: Path | None = None
    version: str | None = None
    changes: list[str] = field(default_factory=list)
    forced: bool = False


# ---------------------------------------------------------------- html


def build_document(brief: brief_mod.Brief, brand: brand_mod.Brand, style: style_mod.Style) -> str:
    macros = style.macros({})
    data = brief.data
    footer = data.get("footer") or data.get("handle") or brand.handle or brand.website
    total = len(brief.slides)
    slides = []
    for index, slide in enumerate(brief.slides, start=1):
        tone = style.tone_for(slide)
        ctx = {
            "index": index,
            "total": total,
            "is_first": index == 1,
            "is_last": index == total,
            "tone": tone,
            "logo_src": brand.logo_uri(tone) if data["logo"] else None,
            "brand_name": brand.name,
            "footer": footer,
            "slide_numbers": data["slide_numbers"] and total > 1,
            "swipe_hint": data["swipe_hint"] and total > 1,
        }
        values = dict.fromkeys(brief_mod.LAYOUTS[slide["layout"]]["optional"])
        values.update(slide)
        if slide["layout"] == "image":
            values["image_src"] = brand_mod.data_uri(Path(slide["image"]))
        html = getattr(macros, slide["layout"])(values, ctx)
        slides.append({**ctx, "layout": slide["layout"], "html": Markup(html)})

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    return env.get_template("document.html.j2").render(
        lang=data["lang"],
        title=data["title"],
        slides=slides,
        base_css=Markup((TEMPLATES_DIR / "base.css").read_text(encoding="utf-8")),
        brand_css=Markup(brand.css()),
        style_css=Markup(style.css),
        page_tools=Markup((TEMPLATES_DIR.parent / "page_tools.js").read_text(encoding="utf-8")),
    )


# ---------------------------------------------------------------- run


def load_inputs(brief_path: str | Path, style: str | None = None, brand: str | None = None):
    the_brief = brief_mod.load(brief_path)
    if style:
        the_brief.data["style"] = style
    if brand:
        the_brief.data["client"] = brand
    return the_brief, brand_mod.load(the_brief.data["client"]), style_mod.load(the_brief.data["style"])


def run(
    brief_path: str | Path,
    *,
    style: str | None = None,
    brand: str | None = None,
    out_root: str | Path | None = None,
    mode: str = "export",
    force: bool = False,
    scale: int = 1,
) -> Result:
    the_brief, the_brand, the_style = load_inputs(brief_path, style, brand)
    out_root = (Path(out_root).expanduser() if out_root else default_output_root()).resolve()
    project = out_root / the_brand.id / the_brief.slug
    return render(the_brief, the_brand, the_style, project, mode=mode, force=force, scale=scale)


def render(
    the_brief: brief_mod.Brief,
    the_brand: brand_mod.Brand,
    the_style: style_mod.Style,
    project: Path,
    *,
    mode: str = "export",
    force: bool = False,
    scale: int = 1,
) -> Result:
    if mode not in ("export", "check"):
        raise CarouselError(f"unknown mode {mode!r}")
    if scale not in (1, 2):
        raise CarouselError("scale must be 1 (1080x1350) or 2 (2160x2700)")
    html = build_document(the_brief, the_brand, the_style)
    report = qa.Report()
    qa.check_copy(the_brief, the_style, report)
    total = len(the_brief.slides)

    with browser.chromium() as chrome:
        page = chrome.new_page(viewport={"width": SLIDE_W, "height": SLIDE_H}, device_scale_factor=scale)
        page.set_content(html, wait_until="load")
        fits = page.evaluate("() => window.__carousel.fit()")
        page_data = page.evaluate("families => window.__carousel.collect(families)", the_brand.families())
        page.evaluate("() => window.__carousel.hideText(true)")
        backgrounds = {i: _shot(page, i) for i in range(1, total + 1)}
        page.evaluate("() => window.__carousel.hideText(false)")
        slides = [_shot(page, i) for i in range(1, total + 1)]
        qa.check_layout(page_data, fits, backgrounds, the_brand, the_style, report)

        exporting = mode == "export" and (report.passed or force)
        if exporting:
            out_dir, version = _next_version(project)
            out_dir.mkdir(parents=True)
            pdf = out_dir / f"{the_brief.slug}.pdf"
            page.pdf(path=str(pdf), width=f"{SLIDE_W}px", height=f"{SLIDE_H}px", print_background=True,
                     prefer_css_page_size=True)
        else:
            out_dir = project / ("_check" if mode == "check" else "_qa-failed")
            if out_dir.exists():
                shutil.rmtree(out_dir)
            out_dir.mkdir(parents=True)
            version, pdf = None, None
        page.close()

    result = Result(
        status="exported" if exporting else ("checked" if mode == "check" else "qa_failed"),
        out_dir=out_dir, report=report, brief=the_brief, brand=the_brand, style=the_style,
        version=version, pdf=pdf, forced=exporting and not report.passed,
    )
    prefix = the_brief.slug if exporting else "preview"
    for i, image in enumerate(slides, start=1):
        path = out_dir / f"{prefix}-{i:02d}.png"
        image.convert("RGB").save(path, optimize=True)
        result.pngs.append(path)

    if exporting:
        qa.check_exports(result.pngs, pdf, (SLIDE_W * scale, SLIDE_H * scale), report)
        result.changes = _changes(project, out_dir, the_brief)
        (out_dir / "brief.yaml").write_text(the_brief.to_yaml(), encoding="utf-8")

    report.sort()
    sheet_name = "contact-sheet.png" if exporting else "qa-sheet.png"
    result.sheet = contact_sheet.build(slides, out_dir / sheet_name, issues=report.issues)
    title = f"{the_brief.data['title']} ({the_brand.name} · {the_style.name})"
    (out_dir / "qa-report.md").write_text(report.to_markdown(title), encoding="utf-8")
    (out_dir / "qa-report.json").write_text(report.to_json(), encoding="utf-8")
    _write_manifest(result)
    return result


def _shot(page, index: int) -> Image.Image:
    data = page.locator(f"#slide-{index}").screenshot(type="png", animations="disabled")
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


# ---------------------------------------------------------------- versions


def _versions(project: Path) -> list[tuple[int, Path]]:
    if not project.is_dir():
        return []
    found = []
    for child in project.iterdir():
        match = _VERSION.match(child.name)
        if match and child.is_dir():
            found.append((int(match.group(1)), child))
    return sorted(found)


def _next_version(project: Path) -> tuple[Path, str]:
    versions = _versions(project)
    number = versions[-1][0] + 1 if versions else 1
    name = f"v{number:02d}"
    return project / name, name


def _changes(project: Path, current_dir: Path, the_brief: brief_mod.Brief) -> list[str]:
    previous = [v for v in _versions(project) if v[1] != current_dir]
    if not previous:
        return ["first version"]
    snapshot = previous[-1][1] / "brief.yaml"
    if not snapshot.exists():
        return []
    old = yaml.safe_load(snapshot.read_text(encoding="utf-8")) or {}
    new = yaml.safe_load(the_brief.to_yaml()) or {}
    return diff_briefs(old, new, previous[-1][1].name)


def diff_briefs(old: dict, new: dict, old_label: str) -> list[str]:
    changes = []
    for key in sorted((set(old) | set(new)) - {"slides"}):
        if old.get(key) != new.get(key):
            changes.append(f"{key}: {old.get(key)!r} -> {new.get(key)!r}")
    old_slides, new_slides = old.get("slides", []), new.get("slides", [])
    for i in range(max(len(old_slides), len(new_slides))):
        a = old_slides[i] if i < len(old_slides) else None
        b = new_slides[i] if i < len(new_slides) else None
        if a == b:
            continue
        if a is None:
            changes.append(f"slide {i + 1}: added ({b.get('layout')})")
        elif b is None:
            changes.append(f"slide {i + 1}: removed")
        else:
            fields = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
            changes.append(f"slide {i + 1}: {', '.join(fields)} changed")
    return [f"since {old_label}: {c}" for c in changes] or [f"no changes since {old_label}"]


def _write_manifest(result: Result) -> None:
    manifest = {
        "status": result.status,
        "forced": result.forced,
        "version": result.version,
        "title": result.brief.data["title"],
        "client": result.brand.id,
        "style": result.style.id,
        "slides": len(result.pngs),
        "rendered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": {
            "png": [p.name for p in result.pngs],
            "pdf": result.pdf.name if result.pdf else None,
            "contact_sheet": result.sheet.name if result.sheet else None,
        },
        "qa": {"passed": result.report.passed, "errors": len(result.report.errors), "warnings": len(result.report.warnings)},
        "changes": result.changes,
    }
    (result.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
