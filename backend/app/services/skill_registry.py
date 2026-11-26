from app.core.config import ROOT
from app.schemas.skill import SkillDetail, SkillManifest


def list_skills() -> list[SkillManifest]:
    manifests = []
    for file in sorted((ROOT / "skills").glob("*/manifest.json")):
        manifest = SkillManifest.model_validate_json(file.read_text("utf-8"))
        if manifest.id == file.parent.name and (file.parent / "SKILL.md").is_file():
            manifests.append(manifest)
    return manifests


def get_skill(skill_id):
    for skill in list_skills():
        if skill.id == skill_id:
            guide = (ROOT / "skills" / skill.id / "SKILL.md").read_text("utf-8")
            return SkillDetail(**skill.model_dump(), guide=guide)
    raise KeyError(skill_id)
