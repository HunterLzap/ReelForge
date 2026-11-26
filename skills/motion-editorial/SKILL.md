---
name: motion-editorial
description: 以数字、引语、图像和步骤卡片编排可溯源的动态科普短片。
version: 1.0.0
supported_aspects: ["16:9", "9:16", "1:1", "3:4"]
supported_formats: [video_16_9, video_9_16, video_1_1, cards_3_4]
---

用 cover 提出一个具体问题，每张内页只回答一个问题。数字写明单位，引用保留署名，对照组使用相同口径。每段视频使用毫秒标注入点与出点，让字幕与旁白对齐。

在 video 轨新增 motion_card，设置 skill_id 为 motion-editorial，component_id 选自 manifest.json，并将文案和已登记图片写入 props。可用 stat 解释数字，用 compare 比较选项，用 steps 或 timeline_card 交代顺序。warning 用于限制条件，code_card 展示短代码，image_card 配合原始资料说明。竖屏减少每行字数，保留字幕安全区。
