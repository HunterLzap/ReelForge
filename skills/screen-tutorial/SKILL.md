---
name: screen-tutorial
description: 将已有录屏剪成可跟随操作的教程，用文稿校准节奏，以镜头标注指明操作位置。
version: 1.0.0
supported_aspects: ["16:9", "9:16", "1:1", "3:4"]
supported_formats: [video_16_9, video_9_16, video_1_1, cards_3_4]
---

先用一张开场卡交代要完成的操作，再将原始录屏放入 video 轨。使用 window_frame 的 screen_frame 参数设置窗口留白与圆角。以操作完成后的实际结果作结。

生成词级文稿，依次试听停顿、口癖和重说建议。保留较清楚的后一次表述，在两步操作之间留出阅读时间。校对界面名称、英文缩写与导出规格后再同步字幕。

在 annotation 轨添加 zoom_focus、spotlight 或 callout_box。start_ms 与 duration_ms 使用工程毫秒，target_bbox 为画布归一化坐标。将镜头中心放在即将点击的控件附近，放大倍率建议 1.4 到 2.2。聚光灯用于区分相邻按钮，气泡仅写当前操作，避开底部字幕。
