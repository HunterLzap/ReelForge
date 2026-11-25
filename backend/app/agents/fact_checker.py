from app.agents.base import BaseAgent
from app.schemas.research import FactCheckReport


class FactChecker(BaseAgent):
    async def process(self, pack):
        result = await self.llm.json(
            "对照各来源正文交叉核查大纲，指出无依据或矛盾之处。关键事实无出处须退回。按此结构输出："
            + str(FactCheckReport.model_json_schema()),
            pack.model_dump(mode="json"),
            lambda: {
                "approved": True,
                "summary": "离线模拟核查通过，仅供演示。",
                "issues": [],
            },
        )
        return FactCheckReport.model_validate(result)
