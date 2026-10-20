import pytest
from conftest import minimal_brief
from engine import brief, markup
from engine.paths import CarouselError


def test_yaml_example_loads(skill_root):
    b = brief.load(skill_root / "briefs" / "example-roastery.yaml")
    assert b.data["client"] == "example-roastery"
    assert [s["layout"] for s in b.slides] == ["cover", "list", "stat", "image", "quote", "text", "cta"]
    assert b.slug == "5-ways-to-brew-better-coffee-at-home"
    assert b.slides[1]["items"][0] == {"title": "Buy whole beans", "body": "Ground coffee goes stale in minutes, beans last weeks."}


def test_copy_brief_parses(skill_root):
    b = brief.load(skill_root / "briefs" / "example-kite.brief.md")
    assert b.data["title"] == "The 50/30/20 budget, explained"
    assert len(b.slides) == 6
    items = b.slides[1]["items"]
    assert items[0] == {"title": "50% Needs", "body": "Rent, groceries, bills, minimum debt payments"}
    assert len(items) == 3
    assert b.slides[1]["headline"] == "Split every paycheck three ways"
    assert b.slides[3]["tone"] == "brand"
    assert b.slides[3]["body"] == "That's normal. Don't cut everything at once.\n\nPick one category this month and trim it by 10%."


def test_copy_brief_and_yaml_roundtrip(skill_root, tmp_path):
    b = brief.load(skill_root / "briefs" / "example-kite.brief.md")
    target = tmp_path / "kite.yaml"
    target.write_text(b.to_yaml(base_dir=tmp_path))
    again = brief.load(target)
    assert again.data == b.data


def test_typos_are_reported_with_suggestions(write_brief):
    data = minimal_brief()
    data["slides"][1] = {"layout": "text", "headine": "Oops", "body": "x"}
    data["slides"].append({"layout": "listt", "items": ["a"]})
    with pytest.raises(CarouselError) as err:
        brief.load(write_brief(data))
    message = str(err.value)
    assert "unknown field 'headine' (did you mean 'headline'?)" in message
    assert "layout 'listt'" in message and "did you mean 'list'" in message


def test_missing_required_and_bad_tone(write_brief):
    data = minimal_brief()
    data["slides"][0] = {"layout": "cover", "tone": "neon"}
    with pytest.raises(CarouselError) as err:
        brief.load(write_brief(data))
    assert "missing required field 'headline'" in str(err.value)
    assert "tone 'neon'" in str(err.value)


def test_unbalanced_markup_is_rejected(write_brief):
    data = minimal_brief()
    data["slides"][0]["headline"] = "A **broken highlight"
    with pytest.raises(CarouselError, match="unmatched"):
        brief.load(write_brief(data))


def test_too_many_slides(write_brief):
    data = minimal_brief(slides=[{"layout": "text", "body": f"Slide {i}"} for i in range(21)])
    with pytest.raises(CarouselError, match="at most 20"):
        brief.load(write_brief(data))


def test_missing_image(write_brief):
    data = minimal_brief()
    data["slides"].insert(1, {"layout": "image", "image": "nope.jpg"})
    with pytest.raises(CarouselError, match="image file not found"):
        brief.load(write_brief(data))


def test_markup_rendering_escapes_html():
    html = str(markup.render('Use **fresh** beans <script>alert(1)</script> & *enjoy*\nNew line'))
    assert '<strong class="hl">fresh</strong>' in html
    assert "<em>enjoy</em>" in html
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<br>" in html
    assert markup.plain("Use **fresh** beans") == "Use fresh beans"
