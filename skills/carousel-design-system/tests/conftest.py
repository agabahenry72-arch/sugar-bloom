import shutil
import sys
from pathlib import Path

import pytest
import yaml

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))


@pytest.fixture
def skill_root() -> Path:
    return SKILL


@pytest.fixture
def out(tmp_path, monkeypatch) -> Path:
    target = tmp_path / "out"
    monkeypatch.setenv("CAROUSEL_OUTPUT_DIR", str(target))
    return target


@pytest.fixture
def brands_dir(tmp_path, monkeypatch) -> Path:
    """An extra brands folder searched before the skill's own."""
    folder = tmp_path / "brands"
    folder.mkdir()
    monkeypatch.setenv("CAROUSEL_BRANDS_DIR", str(folder))
    return folder


@pytest.fixture
def make_brand(brands_dir):
    """Copy example-roastery under a new id, applying changes to brand.yaml."""

    def factory(brand_id: str, **changes) -> Path:
        target = brands_dir / brand_id
        shutil.copytree(SKILL / "brands" / "example-roastery", target)
        data = yaml.safe_load((target / "brand.yaml").read_text())
        for key, value in changes.items():
            node = data
            parts = key.split(".")
            for part in parts[:-1]:
                node = node[part]
            if value is None:
                node.pop(parts[-1], None)
            else:
                node[parts[-1]] = value
        (target / "brand.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
        return target

    return factory


@pytest.fixture
def write_brief(tmp_path):
    def factory(data: dict, name: str = "brief.yaml") -> Path:
        path = tmp_path / name
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        return path

    return factory


def minimal_brief(**overrides) -> dict:
    data = {
        "client": "example-roastery",
        "style": "bold-minimal",
        "title": "Test carousel",
        "slides": [
            {"layout": "cover", "headline": "A short headline"},
            {"layout": "text", "headline": "Second slide", "body": "Some body copy."},
            {"layout": "cta", "headline": "Follow for more"},
        ],
    }
    data.update(overrides)
    return data
