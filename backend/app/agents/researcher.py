import asyncio

from app.agents.base import BaseAgent
from app.core.config import settings
from app.schemas.research import ResearchPack, SourceItem


class Researcher(BaseAgent):
    async def process(self, topic, issues):
        questions = await self.llm.json(
            '拆成最多三个检索关键词，格式 {"queries":["..."]}',
            [topic, issues],
            lambda: {"queries": [topic]},
        )
        if settings().mock_llm:
            hits = [
                {
                    "title": "离线演示素材",
                    "url": "https://example.org/",
                    "snippet": "模拟采编材料，仅用于工作流演示。",
                }
            ]
        else:
            from app.tools.web_search import search

            batches = await asyncio.gather(
                *(search(q) for q in questions["queries"][:3]), return_exceptions=True
            )
            hits = [
                hit for batch in batches if isinstance(batch, list) for hit in batch
            ]
            if not hits:
                raise RuntimeError("未检索到可用来源，请检查网络后重试")
        unique = {h["url"]: h for h in hits}
        sources = [
            SourceItem(
                id=f"S{i}",
                credibility_note="模拟来源"
                if settings().mock_llm
                else "检索原文或搜索摘要",
                **h,
            )
            for i, h in enumerate(unique.values(), 1)
        ]
        result = await self.llm.json(
            '根据材料提炼中文大纲，每条标明来源编号。格式 {"outline":["..."]}',
            [topic, [s.model_dump(mode="json") for s in sources], issues],
            lambda: {"outline": [topic, "行动前确认关键信息", "逐项核对并留存记录"]},
        )
        return ResearchPack(outline=result["outline"], sources=sources)
