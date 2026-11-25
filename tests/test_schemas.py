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
