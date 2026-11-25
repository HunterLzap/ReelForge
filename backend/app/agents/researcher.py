import asyncio

from app.agents.base import BaseAgent
from app.core.config import settings
from app.schemas.research import ResearchPack, SourceItem


class Researcher(BaseAgent):
    async def process(self, topic, issues):
        questions = await self.llm.json(
            '围绕核心事实、最新数据、争议误区、实操建议给出三至四个不同检索词，格式 {"queries":["..."]}',
            [topic, issues],
            lambda: {
                "queries": [
                    topic + " " + x
                    for x in ("核心事实", "最新数据", "常见争议", "实操案例")
                ]
            },
        )
        if settings().mock_llm:
            hits = [
                {
                    "title": "离线演示素材",
                    "url": "https://example.org/",
                    "snippet": "演算示例：甲每月4200元，无额外开支；乙每月4000元，另加300元，合计4300元。乙的标价低200元，总额反而高100元。仅用于演示，非市场统计。",
                }
            ]
        else:
            from app.tools.web_search import search

            batches = await asyncio.gather(
                *(
                    search(q)
                    for q in list(
                        dict.fromkeys(
                            [
                                *issues,
                                *questions["queries"],
                                *(
                                    topic + " " + axis
                                    for axis in ("数据口径", "争议出处", "实践案例")
                                ),
                            ]
                        )
                    )[:4]
                ),
                return_exceptions=True,
            )
            hits = [
                hit for batch in batches if isinstance(batch, list) for hit in batch
            ]
            if not hits:
                raise RuntimeError("未检索到可用来源，请检查网络后重试")
        if settings().mock_llm and "租" not in topic:
            hits[0]["snippet"] = (
                "采编教学模拟样本：收录12条链接，标题去重后8条，独立出处4个。多个转载标题可指向同一份材料。"
            )
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
            '根据材料提炼中文大纲，每条标明来源编号。格式 {"outline":["..."],"key_facts":[{"claim":"可复核事实","source_ids":["S1"]}],"data_points":[{"claim":"数值、日期、单位、口径","source_ids":["S1"]}]}',
            [topic, [s.model_dump(mode="json") for s in sources], issues],
            lambda: {
                "outline": [topic, "行动前确认关键信息", "逐项核对并留存记录"],
                "key_facts": [
                    {"claim": "比较前要统一计费周期和费用范围", "source_ids": ["S1"]}
                ],
                "data_points": [
                    {
                        "claim": "演算示例：4200 对 4000+300=4300，总额差100元",
                        "source_ids": ["S1"],
                    }
                ],
            },
        )
        if settings().mock_llm and "租" not in topic:
            result["key_facts"] = [
                {"claim": "同源转载不能视为独立证据", "source_ids": ["S1"]}
            ]
            result["data_points"] = [
                {"claim": hits[0]["snippet"], "source_ids": ["S1"]}
            ]
        pack = ResearchPack(**result, sources=sources)
        if not pack.key_facts:
            raise ValueError("采编材料缺少可复核的核心事实")
        if any(
            set(item.source_ids) - {s.id for s in sources}
            for item in pack.key_facts + pack.data_points
        ):
            raise ValueError("采编事实引用了未知来源")
        return pack
