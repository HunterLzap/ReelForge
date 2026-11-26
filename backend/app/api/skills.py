from fastapi import APIRouter, HTTPException

from app.schemas.skill import SkillDetail
from app.services import skill_registry

router = APIRouter(prefix="/api/skills")
router.get("")(skill_registry.list_skills)


@router.get("/{skill_id}")
def detail(skill_id: str) -> SkillDetail:
    try:
        return skill_registry.get_skill(skill_id)
    except KeyError:
        raise HTTPException(404, "编导技能不存在") from None
