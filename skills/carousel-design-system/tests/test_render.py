"""End-to-end: these launch Chromium, so they take a few seconds each."""

import json

import pytest
import yaml
from conftest import minimal_brief
from engine import brand as brand_mod
from engine import render, style
from PIL import Image
from pypdf import PdfReader


def checks(result, severity="error"):
    return {i.check for i in result.report.issues if i.severity == severity}


def test_export_writes_pngs_pdf_and_reports(skill_root, out):
    result = render.run(skill_root / "briefs" / "example-roastery.yaml")
    assert result.status == "exported", result.report.to_markdown("x")
    assert result.version == "v01"
    assert len(result.pngs) == 7
    for png in result.pngs:
        with Image.open(png) as img:
            assert img.size == (1080, 1350)
            assert img.mode == "RGB"
    reader = PdfReader(str(result.pdf))
    assert len(reader.pages) == 7
    page = reader.pages[0]
    assert abs(float(page.mediabox.width) / float(page.mediabox.height) - 0.8) < 0.01
    assert "brew" in page.extract_text().lower()  # vector text, not a flat image
    manifest = json.loads((result.out_dir / "manifest.json").read_text())
    assert manifest["qa"]["passed"] is True
    assert (result.out_dir / "brief.yaml").exists()


def test_revision_creates_new_version_with_diff(write_brief, out):
    path = write_brief(minimal_brief())
    first = render.run(path)
    assert first.version == "v01" and first.changes == ["first version"]

    data = yaml.safe_load(path.read_text())
    data["slides"][1]["body"] = "Revised body copy."
    path.write_text(yaml.safe_dump(data))
    second = render.run(path)
    assert second.version == "v02"
    assert second.changes == ["since v01: slide 2: body changed"]
    assert first.out_dir.exists()  # old version kept


def test_overflow_blocks_export(write_brief, out):
    data = minimal_brief()
    data["slides"][1]["body"] = " ".join(["This copy is far too long for one slide."] * 40)
    result = render.run(write_brief(data))
    assert result.status == "qa_failed"
    assert "overflow" in checks(result)
    assert result.pdf is None
    assert result.out_dir.name == "_qa-failed"
    assert (result.out_dir / "qa-sheet.png").exists()
    assert not any(p.name.startswith("v") for p in result.out_dir.parent.iterdir() if p.is_dir())


def test_force_exports_despite_errors(write_brief, out):
    data = minimal_brief()
    data["slides"][1]["body"] = " ".join(["This copy is far too long for one slide."] * 40)
    result = render.run(write_brief(data), force=True)
    assert result.status == "exported" and result.forced
    assert result.pdf.exists()


def test_long_word_overflow(write_brief, out):
    data = minimal_brief()
    # URLs wrap at / and -, so use a word with no break opportunities at all.
    data["slides"][1]["body"] = "Use code " + "WELCOMEBACKSPECIALOFFER" * 4
    result = render.run(write_brief(data), mode="check")
    assert "overflow" in checks(result)


def test_low_contrast_is_caught(make_brand, write_brief, out):
    # Pale yellow primary with forced white text: unreadable cover.
    make_brand("pale-brand", **{"colors.primary": "#F7E27A", "colors.on_primary": "#FFFFFF"})
    result = render.run(write_brief(minimal_brief(client="pale-brand")), mode="check")
    contrast = [i for i in result.report.errors if i.check == "contrast"]
    assert contrast and all(i.slide in (1, 3) for i in contrast)


def test_missing_font_is_caught(make_brand, write_brief, out):
    make_brand("no-font", **{"fonts.heading": {"family": "Totally Not Installed Sans"}})
    result = render.run(write_brief(minimal_brief(client="no-font")), mode="check")
    assert any(i.check == "fonts" and "Totally Not Installed Sans" in i.message for i in result.report.errors)


def test_placeholders_and_length_warnings(write_brief, out):
    data = minimal_brief()
    data["slides"][0]["headline"] = "Big news from [CLIENT NAME] TODO"
    data["slides"][1]["body"] = "Word " * 70
    result = render.run(write_brief(data), mode="check")
    assert "placeholders" in checks(result)
    assert "copy-length" in checks(result, "warning")


def test_check_mode_exports_nothing(write_brief, out):
    result = render.run(write_brief(minimal_brief()), mode="check")
    assert result.status == "checked" and result.report.passed
    assert result.pdf is None and result.version is None
    assert result.out_dir.name == "_check"


def test_style_and_brand_override(skill_root, out):
    result = render.run(skill_root / "briefs" / "example-roastery.yaml", style="editorial", brand="example-kite", mode="check")
    assert result.style.id == "editorial" and result.brand.id == "example-kite"
    assert result.report.passed, result.report.to_markdown("x")


@pytest.mark.parametrize("style_id", ["bold-minimal", "editorial", "card-stack"])
@pytest.mark.parametrize("brief_name", ["showcase.yaml", "stress.yaml"])
@pytest.mark.parametrize("brand_id", ["example-roastery", "example-kite"])
def test_every_style_passes_qa(skill_root, out, style_id, brief_name, brand_id):
    the_style = style.load(style_id)
    assert style.lint(the_style) == []
    the_brief, _, _ = render.load_inputs(skill_root / "briefs" / brief_name, style=style_id, brand=brand_id)
    result = render.render(the_brief, brand_mod.load(brand_id), the_style, out / "t", mode="check")
    assert result.report.passed, result.report.to_markdown(f"{style_id}/{brand_id}/{brief_name}")
