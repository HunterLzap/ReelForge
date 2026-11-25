import hashlib
import json


def content_hash(project, scene):
    parts = [project[k] for k in ("target_format", "theme", "voice")]
    parts.extend(scene[k] for k in ("template_type", "narration"))
    parts.append(
        json.dumps(
            scene["visual_payload"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return hashlib.sha256("".join(parts).encode()).hexdigest()
