"""One-image overview of a carousel, optionally with QA issues marked on it."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .qa import Issue

THUMB_W = 324
THUMB_H = 405
GAP = 28
LABEL_H = 44
SHEET_BG = (236, 236, 238)
LABEL_FG = (60, 60, 67)
ERROR = (220, 38, 38)
WARNING = (217, 119, 6)


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build(slides: list[Image.Image], path: Path, issues: list[Issue] | None = None, columns: int | None = None) -> Path:
    count = len(slides)
    columns = columns or min(count, 5 if count > 8 else 4)
    rows = (count + columns - 1) // columns
    width = GAP + columns * (THUMB_W + GAP)
    height = GAP + rows * (THUMB_H + LABEL_H + GAP)
    sheet = Image.new("RGB", (width, height), SHEET_BG)
    draw = ImageDraw.Draw(sheet)
    label_font = _font(22)
    badge_font = _font(20)
    numbered = list(enumerate(issues or [], start=1))

    for i, slide in enumerate(slides):
        col, row = i % columns, i // columns
        x = GAP + col * (THUMB_W + GAP)
        y = GAP + row * (THUMB_H + LABEL_H + GAP)
        sheet.paste(slide.convert("RGB").resize((THUMB_W, THUMB_H), Image.LANCZOS), (x, y))
        scale = THUMB_W / 1080  # issue rects are in slide CSS pixels
        flagged = [(n, iss) for n, iss in numbered if iss.slide == i + 1]
        for n, issue in flagged:
            colour = ERROR if issue.severity == "error" else WARNING
            if issue.rect:
                r = issue.rect
                box = [x + r["x"] * scale, y + r["y"] * scale, x + (r["x"] + r["w"]) * scale, y + (r["y"] + r["h"]) * scale]
                draw.rectangle(box, outline=colour, width=3)
                _badge(draw, box[0], box[1], str(n), colour, badge_font)
        if any(iss.severity == "error" for _, iss in flagged):
            draw.rectangle([x - 4, y - 4, x + THUMB_W + 3, y + THUMB_H + 3], outline=ERROR, width=4)
        label = f"{i + 1:02d}"
        if flagged:
            shown = ", ".join(f"#{n}" for n, _ in flagged[:3])
            label += f"   issues: {shown}" + (f" +{len(flagged) - 3}" if len(flagged) > 3 else "")
        draw.text((x, y + THUMB_H + 10), label, fill=LABEL_FG, font=label_font)

    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, optimize=True)
    return path


def _badge(draw: ImageDraw.ImageDraw, x: float, y: float, text: str, colour, font) -> None:
    size = 28
    draw.ellipse([x - size / 2, y - size / 2, x + size / 2, y + size / 2], fill=colour)
    draw.text((x, y), text, fill=(255, 255, 255), font=font, anchor="mm")
