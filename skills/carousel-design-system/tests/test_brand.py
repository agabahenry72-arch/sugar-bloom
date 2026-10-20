import pytest
from engine import brand, colors
from engine.paths import CarouselError


@pytest.mark.parametrize("brand_id", ["example-roastery", "example-kite"])
def test_example_tones_are_readable(brand_id):
    b = brand.load(brand_id)
    for tone, t in b.tones.items():
        assert colors.contrast(t["fg"], t["bg"]) >= 4.5, tone
        assert colors.contrast(t["muted"], t["bg"]) >= 4.5, tone
        assert colors.contrast(t["hl"], t["bg"]) >= 3.0, tone
        assert colors.contrast(t["hl_small"], t["bg"]) >= 4.5, tone
        assert colors.contrast(t["on_card"], t["card"]) >= 4.5, tone
    assert b.tones["dark"]["logo"] == "inverse"
    assert b.tones["light"]["logo"] == "default"
    css = b.css()
    assert "@font-face" in css and "--font-heading" in css and ".tone-brand{" in css


def test_bad_colour_and_missing_files(make_brand):
    make_brand("broken", **{"colors.primary": "orange", "fonts.body.files": ["fonts/Missing.ttf"], "logo.default": "nope.svg"})
    with pytest.raises(CarouselError) as err:
        brand.load("broken")
    message = str(err.value)
    assert "colors.primary" in message
    assert "font file not found: fonts/Missing.ttf" in message
    assert "logo.default: file not found" in message


def test_unknown_brand_lists_known():
    with pytest.raises(CarouselError, match="example-roastery"):
        brand.load("does-not-exist")


def test_low_contrast_brand_warns(make_brand):
    make_brand("pale", **{"colors.text": "#BBBBBB", "colors.background": "#FFFFFF"})
    b = brand.load("pale")
    assert any("text on background" in w for w in b.warnings)


def test_variable_font_detected(skill_root):
    b = brand.load("example-kite")
    face = b.faces_for("Manrope")[0]
    assert (face.weight_min, face.weight_max) == (100, 900)
    assert face.covers(800)
