"""Plan cuts in timeline milliseconds, then publish one reversible edit."""

import itertools
import re
from difflib import SequenceMatcher

from fastapi import HTTPException
from pydantic import Field

from app.db import repository as repo
from app.schemas.timeline import TimelineOp, TimelinePatchRequest
from app.schemas.transcript import RoughCutIssue, RoughCutPreview
from app.services.timeline_engine import RevisionConflict, engine


class TranscriptPatch(TimelinePatchRequest):
    # A transcription without subtitle sync still writes a revision and undo pointer.
    ops: list[TimelineOp] = Field(default_factory=list)


async def context(pid, base=None, required=True):
    timeline = await engine.get(pid)
    if base is not None and base != timeline.revision:
        raise RevisionConflict(timeline.revision)
    transcript = await repo.get_latest_transcript(pid, timeline)
    if required and transcript is None:
        raise HTTPException(404, "尚未生成文稿")
    return timeline, transcript


async def publish(timeline, ops, summary, transcript=None):
    request = TranscriptPatch(base_revision=timeline.revision, ops=ops, summary=summary)
    return await engine.patch(timeline.project_id, request, transcript=transcript)


def active(segment):
    return [w for w in segment.words if not w.deleted and w.tag != "pause"]


def refresh(segment):
    live = active(segment)
    segment.text = "".join(w.text for w in live)
    times = live or segment.words
    segment.start_ms, segment.end_ms = times[0].start_ms, times[-1].end_ms


def union(ranges):
    result = []
    for a, b in sorted(ranges):
        if b <= a:
            continue
        if result and a <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], b))
        else:
            result.append((a, b))
    return result


def intersect(left, right):
    """Intersect two sorted, disjoint lists of half-open intervals in linear time."""
    i = j = 0
    while i < len(left) and j < len(right):
        a, b = left[i]
        x, y = right[j]
        if min(b, y) > max(a, x):
            yield max(a, x), min(b, y)
        if b <= y:
            i += 1
        if y <= b:
            j += 1


def media_ranges(timeline, transcript):
    return union(
        (c.start_ms, c.end_ms)
        for c in timeline.tracks.video
        if getattr(c, "asset_id", None) == transcript.asset_id
    )


def analyze(timeline, transcript):
    issues = []

    def add(kind, a, b, text, words=()):
        issues.append(
            RoughCutIssue(
                id=f"{kind}_{a}_{b}",
                kind=kind,
                start_ms=a,
                end_ms=b,
                text=text,
                word_ids=[w.id for w in words],
            )
        )

    words = sorted(
        (w for s in transcript.segments for w in active(s)), key=lambda w: w.start_ms
    )
    gaps = [
        (left.end_ms, right.start_ms)
        for left, right in itertools.pairwise(words)
        if right.start_ms - left.end_ms >= 600
    ]
    spans = media_ranges(timeline, transcript)
    pauses = union([*gaps, *transcript.silences])
    if transcript.engine == "mock" and words:
        # A silent demo track may have synthetic speech over its entire duration.
        # Protect those tokens; in real ASR the detector supplies independent evidence.
        spoken = union((w.start_ms, w.end_ms) for w in words)
        unspoken = [
            (0, spoken[0][0]),
            *((b, x) for (_, b), (x, _) in itertools.pairwise(spoken)),
            (spoken[-1][1], max((b for _, b in spans), default=0)),
        ]
        pauses = list(intersect(pauses, unspoken))
    for a, b in intersect(spans, pauses):
        if b - a >= 600:
            add("silence", a, b, f"停顿 {(b - a) / 1000:.1f}s")
    for w in words:
        if w.tag == "filler":
            add("filler", w.start_ms, w.end_ms, w.text, [w])
    segments = [s for s in transcript.segments if active(s)]

    def phrase(seg):
        text = "".join(w.text for w in active(seg) if w.tag != "filler")
        return re.sub(r"[\W_]+", "", text).removesuffix("不对").lower()

    for before, after in itertools.pairwise(segments):
        a, b = phrase(before), phrase(after)
        if (
            len(a) >= 4
            and after.start_ms - before.end_ms <= 2000
            and SequenceMatcher(None, a, b).ratio() >= 0.72
        ):
            add("retake", before.start_ms, before.end_ms, before.text, active(before))
    return sorted(issues, key=lambda issue: (issue.start_ms, issue.end_ms))


def subtitle_ops(timeline, transcript, *, clear_all=False):
    segments = {s.id for s in transcript.segments}
    spans = media_ranges(timeline, transcript)
    ops = []
    for c in timeline.tracks.subtitle:
        owned = getattr(c, "transcript_segment_id", None) in segments
        if owned or (
            clear_all and any(a <= c.start_ms and c.end_ms <= b for a, b in spans)
        ):
            ops.append({"op": "delete_clip", "track": "subtitle", "clip_id": c.id})
    for s in transcript.segments:
        if s.text and s.end_ms > s.start_ms:
            ops.append(
                {
                    "op": "add_clip",
                    "track": "subtitle",
                    "clip": {
                        "kind": "subtitle",
                        "start_ms": s.start_ms,
                        "end_ms": s.end_ms,
                        "text": s.text,
                        "transcript_segment_id": s.id,
                    },
                }
            )
    return ops


def move_time(t, cuts):
    return t - sum(max(0, min(t, b) - a) for a, b in cuts)


async def rough_cut(pid, body):
    timeline, doc = await context(pid, body.base_revision)
    issues = analyze(timeline, doc)
    words = {w.id: w for s in doc.segments for w in active(s)}
    deleted = set()
    if body.cut_ranges_ms is not None:
        ranges = body.cut_ranges_ms
    elif body.delete_word_ids is not None:
        deleted.update(body.delete_word_ids)
        if deleted - words.keys():
            raise HTTPException(422, "选中的词已变化")
        ranges = [(words[i].start_ms, words[i].end_ms) for i in deleted]
    else:
        if body.issue_ids is not None:
            ids = set(body.issue_ids)
            issues = [i for i in issues if i.id in ids]
            if len(issues) != len(ids):
                raise HTTPException(422, "粗剪建议已变化，请重新预览")
        ranges = []
        for issue in issues:
            pad = body.buffer_ms if issue.kind == "silence" else 0
            ranges.append((issue.start_ms + pad, issue.end_ms - pad))
            deleted.update(issue.word_ids)
    cuts = union(ranges)
    spans = media_ranges(timeline, doc)
    if any(not any(a <= x and y <= b for a, b in spans) for x, y in cuts):
        raise HTTPException(422, "剪辑范围必须位于转写素材内")
    preview = RoughCutPreview(
        issues=issues,
        cut_ranges_ms=cuts,
        saved_ms=sum(b - a for a, b in cuts),
        base_revision=timeline.revision,
    )
    if not body.apply or not cuts:
        return preview
    # Captions carry editor-authored text. Preserve split, merged and manually
    # corrected captions while ripple-trimming their screen time as one unit.
    segments = {s.id: s for s in doc.segments}
    linked = {}
    for clip in timeline.tracks.subtitle:
        segment = segments.get(getattr(clip, "transcript_segment_id", None))
        if segment and (clip.start_ms, clip.end_ms, clip.text) == (
            segment.start_ms,
            segment.end_ms,
            segment.text,
        ):
            linked[clip.id] = segment
    ops = [
        {
            "op": "ripple_delete",
            "tracks": ["video", "annotation", "overlay", "audio"],
            "start_ms": a,
            "end_ms": b,
        }
        for a, b in reversed(cuts)
    ]
    for s in doc.segments:
        for w in s.words:
            w.start_ms, w.end_ms = (
                move_time(w.start_ms, cuts),
                move_time(w.end_ms, cuts),
            )
            w.deleted |= w.id in deleted or w.end_ms <= w.start_ms
        refresh(s)
    doc.silences = union(
        (move_time(a, cuts), move_time(b, cuts)) for a, b in doc.silences
    )
    for clip in timeline.tracks.subtitle:
        segment = linked.get(clip.id)
        a, b = move_time(clip.start_ms, cuts), move_time(clip.end_ms, cuts)
        fields = {"start_ms": a, "end_ms": b}
        if segment:
            fields.update(
                start_ms=segment.start_ms, end_ms=segment.end_ms, text=segment.text
            )
        if b <= a or (segment and not segment.text):
            ops.append({"op": "delete_clip", "track": "subtitle", "clip_id": clip.id})
        else:
            ops.append(
                {
                    "op": "update_clip",
                    "track": "subtitle",
                    "clip_id": clip.id,
                    "patch": fields,
                }
            )
    preview.timeline = await publish(timeline, ops, "文稿波纹剪辑", doc)
    return preview


def rewrite_words(segment, new_text):
    """Map character edits back to the original timed tokens, including cross-token matches."""
    words = active(segment)
    original = "".join(w.text for w in words)
    owners = [i for i, w in enumerate(words) for _ in w.text]
    if not owners:
        return
    parts = [""] * len(words)
    for kind, a, b, x, y in SequenceMatcher(
        None, original, new_text, autojunk=False
    ).get_opcodes():
        if kind == "equal":
            for offset in range(b - a):
                parts[owners[a + offset]] += new_text[x + offset]
        elif kind in {"insert", "replace"}:
            for k, ch in enumerate(new_text[x:y]):
                index = a + k * (b - a) // max(1, y - x)
                parts[owners[min(index, len(owners) - 1)]] += ch
    from app.services.asr_service import FILLERS

    for w, text in zip(words, parts):
        w.text = text
        w.deleted = not text
        w.tag = "filler" if text.strip(" ，。,.") in FILLERS else "normal"
    refresh(segment)


async def replace(pid, body):
    timeline, doc = await context(pid, body.base_revision, required=False)
    ops = []
    count = 0
    linked = set()
    for clip in timeline.tracks.subtitle:
        text = getattr(clip, "text", "")
        if n := text.count(body.find):
            count += n
            ops.append(
                {
                    "op": "update_clip",
                    "track": "subtitle",
                    "clip_id": clip.id,
                    "patch": {"text": text.replace(body.find, body.replace)},
                }
            )
            linked.add(getattr(clip, "transcript_segment_id", None))
    if doc:
        for s in doc.segments:
            if n := s.text.count(body.find):
                if s.id not in linked:
                    count += n
                rewrite_words(s, s.text.replace(body.find, body.replace))
        if count and body.replace and body.replace not in doc.hotwords:
            doc.hotwords.append(body.replace)
    if count:
        timeline = await publish(timeline, ops, "字幕批量替换", doc)
    return {"timeline": timeline, "replaced_count": count}


def export_subtitles(timeline, fmt):
    def stamp(ms):
        unit = 100 if fmt == "ass" else 1000
        t = ms // (1000 // unit)
        seconds, fraction = divmod(t, unit)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return (
            f"{hours}:{minutes:02}:{seconds:02}.{fraction:02}"
            if fmt == "ass"
            else f"{hours:02}:{minutes:02}:{seconds:02},{fraction:03}"
        )

    lines = []
    if fmt == "ass":
        lines.extend(
            [
                "[Script Info]",
                "ScriptType: v4.00+",
                f"PlayResX: {timeline.resolution.width}",
                f"PlayResY: {timeline.resolution.height}",
                "",
                "[V4+ Styles]",
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
                "Style: Default,Arial,44,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,20,20,50,1",
                "",
                "[Events]",
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            ]
        )
    for i, c in enumerate(
        sorted(timeline.tracks.subtitle, key=lambda c: c.start_ms), 1
    ):
        text = getattr(c, "text", "").replace("\r", "")
        a, b = stamp(c.start_ms), stamp(c.end_ms)
        if fmt == "srt":
            lines.extend([str(i), f"{a} --> {b}", text, ""])
        else:
            text = (
                text.replace("\\", "＼")
                .replace("{", "｛")
                .replace("}", "｝")
                .replace("\n", r"\N")
            )
            lines.append(f"Dialogue: 0,{a},{b},Default,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"
