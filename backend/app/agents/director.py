from pydantic import ValidationError

from app.agents.base import BaseAgent
from app.core.config import settings
from app.schemas.storyboard import StoryboardScript


def example(topic):
    rental = "租" in topic
    labels = ["房源", "费用", "交接"] if rental else ["来源", "细节", "记录"]
    descriptions = (
        ["实地查看房屋现状", "列清每月固定开支", "拍照记录交接情况"]
        if rental
        else ["找到原始出处", "逐条核对信息", "保存核对结果"]
    )

    def scene(kind, narration, **payload):
        return {
            "template_type": kind,
            "narration": narration,
            "visual_payload": payload,
            "source_ids": ["S1"],
        }

    return {
        "scenes": [
            scene(
                "cover",
                topic + "。从三个问题开始。",
                title=topic,
                subtitle="行动前的核对指南",
                tag="实用手册",
            ),
            scene(
                "bullet_list",
                "。".join(descriptions) + "。",
                heading="先核对这三件事",
                items=[{"label": k, "desc": v} for k, v in zip(labels, descriptions)],
            ),
            scene(
                "big_quote",
                "把口头承诺变成书面记录。",
                quote="把口头承诺变成书面记录。",
                highlight="书面记录",
                attribution="行动提示",
            ),
        ]
    }


class Director(BaseAgent):
    async def process(self, topic, pack, report):
        evidence = {
            "topic": topic,
            "research": pack.model_dump(mode="json"),
            "fact_check": report.model_dump(),
        }
        allowed = {s.id for s in pack.sources}
        for attempt in range(settings().max_director_retries + 1):
            try:
                data = await self.llm.json(
                    "生成紧凑的中文分镜，封面在首幕，每幕引用材料编号。只采用核实内容。模板文字短小，符合 JSON Schema："
                    + str(StoryboardScript.model_json_schema()),
                    evidence,
                    lambda: example(topic),
                )
                script = StoryboardScript.model_validate(data)
                if any(
                    not s.source_ids or set(s.source_ids) - allowed
                    for s in script.scenes
                ):
                    raise ValueError("分镜缺少有效来源编号")
                return script
            except (ValidationError, ValueError) as exc:
                if attempt == settings().max_director_retries:
                    raise
                evidence["validation_error"] = str(exc)
