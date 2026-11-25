from app.agents.base import BaseAgent
from app.schemas.research import FactCheckReport


class FactChecker(BaseAgent):
    async def process(self, pack):
        result = await self.llm.json(
            "逐条核验 key_facts 和 data_points 的数字、单位、结论。checks 逐条照录 claim 原文，source 为逗号分隔的真实来源编号，verdict 只能取 supported、unsupported、conflicting。缺乏证据打回，follow_up_queries 给具体搜索词。按此结构输出："
            + str(FactCheckReport.model_json_schema()),
            pack.model_dump(mode="json"),
            lambda: {
                "approved": True,
                "summary": "离线模拟核查通过，仅供演示。",
                "issues": [],
                "checks": [
                    {
                        "claim": x.claim,
                        "source": ",".join(x.source_ids),
                        "verdict": "supported",
                    }
                    for x in pack.key_facts + pack.data_points
                ],
            },
        )
        report = FactCheckReport.model_validate(result)
        if {x.claim for x in pack.key_facts + pack.data_points} - {
            x.get("claim") for x in report.checks
        }:
            report.approved = False
            report.issues.append("核查记录未覆盖全部关键事实")
        allowed = {s.id for s in pack.sources}
        for check in report.checks:
            cited = {v.strip() for v in check.get("source", "").split(",")}
            if check.get("verdict") != "supported" or not cited <= allowed:
                report.approved = False
                report.issues.append("需要查证：" + check.get("claim", "来源"))
        if not report.approved and not report.follow_up_queries:
            report.follow_up_queries = [
                f"{x.claim} 原始数据 来源" for x in pack.data_points + pack.key_facts
            ][:4] or [pack.outline[0] + " 原始出处"]
        return report
