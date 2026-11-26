import hashlib
import json


def content_hash(project, scene, count=1):
    values = [
        6,
        project.get("subtitle_style","pill_dark"),
        project.get("speech_rate","+0%"),
        project["target_format"],
        project["theme"],
        project["voice"],
        project.get("brand_label", ""),
        project.get("transition", "fade"),
        project.get("topic", ""),
        scene.get("order_index", 1),
        count,
        scene["template_type"],
        scene["narration"],
        scene["visual_payload"],
    ]
    return hashlib.sha256(
        json.dumps(
            values, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
