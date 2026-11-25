import itertools

import pytest
from pydantic import ValidationError

from app.agents.director import example
from app.schemas.storyboard import StoryboardScript


def test_first_cover_and_payload():
    data = example("主题")
    script = StoryboardScript.model_validate(data)
    assert script.scenes[0].template_type == "cover"
    data["scenes"].reverse()
    with pytest.raises(ValidationError):
        StoryboardScript.model_validate(data)


def test_list_bounds_and_discriminator():
    data = example("主题")
    data["scenes"][1]["visual_payload"]["items"].pop()
    with pytest.raises(ValidationError):
        StoryboardScript.model_validate(data)
    data["scenes"][1]["template_type"] = "missing"
    with pytest.raises(ValidationError):
        StoryboardScript.model_validate(data)


def test_new_templates_and_platform_rules():
    for fmt, count in [("cards_3_4", 6), ("video_9_16", 6), ("video_16_9", 8)]:
        scenes = StoryboardScript.model_validate(example("租房", fmt)).scenes
        kinds = [s.template_type for s in scenes]
        assert len(scenes) == count and {"hero_stat", "checklist", "stat_chart"} <= set(
            kinds
        )
        assert all(a != b for a, b in itertools.pairwise(kinds))
    data = example("租房")
    next(s for s in data["scenes"] if s["template_type"] == "checklist")[
        "visual_payload"
    ]["items"][0]["status"] = "maybe"
    with pytest.raises(ValidationError):
        StoryboardScript.model_validate(data)


def test_compact_chart_and_tag_fields():
    data = example("租房")
    data["scenes"][0]["visual_payload"]["tag"] = "篇" * 17
    with pytest.raises(ValidationError):
        StoryboardScript.model_validate(data)
