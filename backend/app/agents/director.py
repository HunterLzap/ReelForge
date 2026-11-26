import itertools
import re

from pydantic import ValidationError

from app.agents.base import BaseAgent
from app.core.config import settings
from app.schemas.storyboard import StoryboardScript

RULES = {
    "video_16_9": (
        7,
        10,
        "60–120 秒。引入问题、拆解口径、呈现数据、比较取舍、交付行动清单，最后用一句话收束。",
    ),
    "video_9_16": (
        6,
        8,
        "35–60 秒。第一句话用痛点或反直觉结果抓人，口语短句，每句至多24字。",
    ),
    "cards_3_4": (
        6,
        8,
        "首图用有具体收益的标题、副标题、标签；内页完整可截图收藏，旁白为可单独阅读的笔记正文。",
    ),
}


def example(topic, fmt="video_16_9"):
    rental = "租" in topic

    def scene(kind, voice, **payload):
        return {
            "template_type": kind,
            "narration": voice,
            "visual_payload": payload,
            "source_ids": ["S1"],
        }

    subject = "租金" if rental else "报价"
    extra = "通勤" if rental else "配套"
    hook = "便宜两百，为什么反而多花一百？"
    scenes = [
        scene(
            "cover",
            hook + "别只盯着标价。我们把两种方案，放到同一张账单上。",
            title="便宜两百，却多花一百？",
            subtitle=topic[:52] + " · 一次同口径的算账练习",
            tag="看房手册" if rental else "决策手册",
        ),
        scene(
            "bullet_list",
            "先把账单分三栏。每月固定支出写在左边。可变开支列在中间。一次性费用单列出来。",
            heading="先统一账本的口径",
            items=[
                {"label": "固定项", "desc": subject + "与每月必付费用"},
                {"label": "浮动项", "desc": extra + "开支按同一月份计算"},
                {"label": "一次性", "desc": "押金、预付和不可退费用分开记"},
            ],
        ),
        scene(
            "hero_stat",
            "账面上，相差两百元。甲报四千二，乙报四千。省下的钱，真的进了口袋吗？",
            metric="200",
            unit="元 / 月",
            label="只看标价的差额",
            context="演算示例 · 甲 4,200 元，乙 4,000 元。",
            delta="下一步：加上两边各自的" + extra + "成本",
        ),
        scene(
            "stat_chart",
            "乙的标价是四千。每月再加三百元。合计四千三。甲的总额是四千二。便宜的一边反而贵了。",
            heading="同一个月，三笔账",
            unit="元",
            bars=[
                {"label": "乙 · 标价", "value": 4000, "accent": "#8d9fa5"},
                {"label": "甲 · 合计", "value": 4200, "accent": "#619394"},
                {"label": "乙 · 合计", "value": 4300, "accent": "#d3914c"},
            ],
            takeaway="假设甲无额外开支；乙每月多付 300 元，合计高出 100 元。",
        ),
        scene(
            "compare_split",
            "两份报价摆在一起。甲的价格直接写在首页。乙的小字藏着额外费用。把假设也一起写清楚。",
            heading="把两份报价摊开",
            left_title="甲方案",
            left_points=[subject + " 4,200 元", extra + "增量按 0 元计"],
            right_title="乙方案",
            right_points=[subject + " 4,000 元", extra + "增量按 300 元计"],
        ),
        scene(
            "timeline",
            "先拿到书面报价。再把数字放进同一列。最后试着改一个条件。差价会不会反过来？",
            heading="十分钟做完复核",
            steps=[
                {"step_label": "01", "title": "拿原件", "desc": "保存日期和报价版本"},
                {"step_label": "02", "title": "算总额", "desc": "标明单位和计费周期"},
                {
                    "step_label": "03",
                    "title": "换假设",
                    "desc": "调整浮动项，看结论是否改变",
                },
            ],
        ),
        scene(
            "checklist",
            "决定之前，问清三件事。费用能否写进附件？变动有没有上限？口头承诺，记得索要书面确认。",
            heading="决定前，逐项打勾",
            items=[
                {
                    "status": "do",
                    "title": "拿书面明细",
                    "detail": "把金额、周期和付款对象写在一起",
                },
                {
                    "status": "do",
                    "title": "核实浮动项",
                    "detail": extra + "按自己的真实情况替换",
                },
                {
                    "status": "dont",
                    "title": "跳过小字",
                    "detail": "额外收费没有列清，先别确认",
                },
            ],
        ),
        scene(
            "big_quote",
            "记住这条判断线。比总价之前，先比口径。把账算明白，才能知道自己买到了什么。",
            quote="比总价之前，先比口径。",
            highlight="先比口径",
            attribution="本期行动笔记",
        ),
    ]
    if not rental:
        hook = "十二条链接，真有十二份证据吗？"
        scenes = [
            scene(
                "cover",
                hook + "我们把一组模拟资料摊开。看看转载之后，还剩多少独立出处。",
                title=topic[:30] + "：先看出处",
                subtitle="用十二条模拟链接，拆开一次资料核查。",
                tag="资料观察",
            ),
            scene(
                "bullet_list",
                "先看谁发布。再看什么时候发布。最后看它引用了谁。三个问题，可以把转述和原始材料分开。",
                heading="读一条资料，先查三个位置",
                items=[
                    {"label": "作者", "desc": "找到最早署名或发布机构"},
                    {"label": "日期", "desc": "区分事件发生日与转载日"},
                    {"label": "引用", "desc": "回到原始报告或记录"},
                ],
            ),
            scene(
                "hero_stat",
                "表面上有十二条链接。追到源头，只剩四个出处。数量一下少了三分之二。",
                metric="4",
                unit="个出处",
                label="独立信源比链接少",
                context="模拟样本：12 条链接仅对应 4 个原始出处。",
                delta="去重后保留三分之一",
            ),
            scene(
                "stat_chart",
                "第一轮收录十二条。第二轮按标题合并，剩八条。沿引用回溯，只找到四个源头。",
                heading="同一批资料，三轮计数",
                unit="条",
                bars=[
                    {"label": k, "value": v, "accent": c}
                    for k, v, c in [
                        ("收录", 12, "#8d9fa5"),
                        ("标题去重", 8, "#619394"),
                        ("独立出处", 4, "#d3914c"),
                    ]
                ],
                takeaway="模拟计数：不同标题也可能指向同一份原文。",
            ),
            scene(
                "compare_split",
                "两篇文章说法一样。可能是独立观察，也可能是互相转载。先看引用链，再判断分量。",
                heading="一致说法，两种来源",
                left_title="独立记录",
                left_points=["不同作者直接观察", "各有可核对原件"],
                right_title="同源转述",
                right_points=["共引同一份材料", "改标题后再次发布"],
            ),
            scene(
                "timeline",
                "保存原文片段。沿脚注回到出处。把出处相同的记录放在一起。最后，再给结论打上置信标记。",
                heading="从链接到证据",
                steps=[
                    {"step_label": str(i), "title": a, "desc": b}
                    for i, (a, b) in enumerate(
                        [
                            ("摘录", "保留上下文"),
                            ("回溯", "找到原始出处"),
                            ("归并", "同一源头只计一次"),
                        ],
                        1,
                    )
                ],
            ),
            scene(
                "checklist",
                "动笔之前，核对三个细节。原文找到了吗？口径一致吗？别把重复转发当成多方证实。",
                heading="动笔前的证据清单",
                items=[
                    {
                        "status": "do",
                        "title": "保存原文",
                        "detail": "链接、日期和原句一起存档",
                    },
                    {
                        "status": "do",
                        "title": "标明范围",
                        "detail": "写清适用条件与时间",
                    },
                    {
                        "status": "dont",
                        "title": "重复计数",
                        "detail": "同源转载合并为一组",
                    },
                ],
            ),
            scene(
                "big_quote",
                "链接可以越转越多。证据的分量，来自独立出处。下次看到一致意见，先去看看它从哪里来。",
                quote="链接可以复制，出处才有分量。",
                highlight="出处",
                attribution="采编笔记",
            ),
        ]
    if fmt != "video_16_9":
        scenes = [
            s for s in scenes if s["template_type"] not in ("bullet_list", "timeline")
        ]
    if fmt == "video_9_16":
        scenes[0]["narration"] = hook + (
            "先看这两张账单。" if rental else "一起追到源头。"
        )
    if fmt == "cards_3_4":
        for s in scenes:
            p = s["visual_payload"]
            caption = (
                p.get("takeaway")
                or p.get("context")
                or p.get("subtitle")
                or p.get("quote")
                or p["heading"]
            )
            s["narration"] = caption + "\n" + s["narration"]
    return {"scenes": scenes}


class Director(BaseAgent):
    async def process(self, topic, pack, report, target_format="video_16_9"):
        minimum, maximum, style = RULES[target_format]
        evidence = {
            "topic": topic,
            "platform": target_format,
            "research": pack.model_dump(mode="json"),
            "fact_check": report.model_dump(),
        }
        for attempt in range(settings().max_director_retries + 1):
            try:
                data = await self.llm.json(
                    f"为此选题编写{minimum}至{maximum}幕中文分镜。{style}每幕引用真实材料编号；相邻模板不同，数值比较必须画图。"
                    + str(StoryboardScript.model_json_schema()),
                    evidence,
                    lambda: example(topic, target_format),
                )
                script = StoryboardScript.model_validate(data)
                kinds = [s.template_type for s in script.scenes]
                if not minimum <= len(kinds) <= maximum or any(
                    a == b for a, b in itertools.pairwise(kinds)
                ):
                    raise ValueError("幕数或相邻模板不符合平台规则")
                if pack.data_points and not set(kinds) & {"hero_stat", "stat_chart"}:
                    raise ValueError("数据需要数字卡或图表")
                if any(
                    not s.source_ids or set(s.source_ids) - {i.id for i in pack.sources}
                    for s in script.scenes
                ):
                    raise ValueError("来源编号无效")
                if target_format == "video_9_16" and any(
                    len(line.strip()) > 24
                    for s in script.scenes
                    for line in re.split(r"[。！？；，、：.!?;,:]", s.narration)
                ):
                    raise ValueError("竖屏旁白每句至多24字")
                return script
            except (ValidationError, ValueError) as exc:
                if attempt == settings().max_director_retries:
                    raise
                evidence["validation_error"] = str(exc)
