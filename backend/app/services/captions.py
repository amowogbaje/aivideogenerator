"""Burned-in captions: an ASS subtitle file per scene, phrase-timed across that scene's actual audio length."""
import re


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def phrases(text: str, max_words: int = 4, max_chars: int = 26) -> list[str]:
    """Short on-screen chunks (like a Reel/TikTok caption) that break at punctuation where possible."""
    words = re.sub(r"\s+", " ", text).strip().split(" ")
    out: list[str] = []
    cur: list[str] = []
    for w in words:
        cur.append(w)
        joined = " ".join(cur)
        if len(cur) >= max_words or len(joined) >= max_chars or re.search(r"[.!?,;:]$", w):
            out.append(joined)
            cur = []
    if cur:
        out.append(" ".join(cur))
    return [p for p in out if p]


def build_ass(text: str, duration: float, width: int, height: int, lead_in: float = 0.1, tail: float = 0.3) -> str:
    chunks = phrases(text)
    weights = [max(1, len(c)) for c in chunks]
    span = max(0.5, duration - lead_in - tail)
    total = sum(weights)

    font_size = round(height * 0.036)
    margin_v = round(height * 0.14)
    margin_h = round(width * 0.08)

    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,"
        "StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Cap,DejaVu Sans,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,"
        f"{max(3, round(font_size / 12))},1,2,{margin_h},{margin_h},{margin_v},1",
        "", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    t = lead_in
    for chunk, w in zip(chunks, weights):
        d = span * w / total
        safe = chunk.replace("\\", "").replace("{", "(").replace("}", ")")
        lines.append(f"Dialogue: 0,{_ts(t)},{_ts(t + d)},Cap,,0,0,0,,{safe}")
        t += d
    return "\n".join(lines) + "\n"
