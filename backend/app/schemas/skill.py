from pydantic import BaseModel

from app.schemas.timeline import Aspect


class SkillTemplate(BaseModel):
    id: str
    name: str
    props_schema: dict


class SkillManifest(BaseModel):
    id: str
    name: str
    version: str
    description: str
    supported_aspects: list[Aspect]
    inputs: dict
    templates: list[SkillTemplate]


class SkillDetail(SkillManifest):
    guide: str
