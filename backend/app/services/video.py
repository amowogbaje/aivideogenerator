"""Scene clip = still image (slow Ken Burns move) + that scene's voice + burned-in captions. Episode = clips joined."""
import logging
import tempfile
from pathlib import Path

from app.services import captions
from app.services.ffmpeg_util import run

logger = logging.getLogger("app.video")

FPS = 25
SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
PAD = 0.5  # silence after each line so scenes don't feel clipped


def _esc(path: str) -> str:
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


async def build_scene_clip(*, image: Path, audio: Path, audio_duration: float, text: str, aspect: str,
                           index: int, out: Path) -> float:
    """Returns the clip duration in seconds."""
    w, h = SIZES[aspect]
    duration = audio_duration + PAD
    frames = max(1, round(duration * FPS))

    # Alternate zoom-in / zoom-out per scene so consecutive shots don't feel identical.
    if index % 2 == 0:
        zoom = f"1.0+0.12*on/{frames}"
    else:
        zoom = f"1.12-0.12*on/{frames}"
    # Work on a 1.5x frame: enough headroom for a smooth zoom without the render cost of a huge canvas.
    big_w, big_h = round(w * 1.5), round(h * 1.5)
    vf = (f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,crop={big_w}:{big_h},"
          f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={FPS},"
          f"format=yuv420p")

    with tempfile.TemporaryDirectory() as tmp:
        ass = Path(tmp) / "cap.ass"
        ass.write_text(captions.build_ass(text, duration, w, h), encoding="utf-8")
        vf += f",subtitles='{_esc(str(ass))}'"
        await run([
            "ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(image), "-i", str(audio),
            "-vf", vf, "-af", "apad,aresample=44100", "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-ar", "44100",
            "-movflags", "+faststart", str(out),
        ], timeout=900)
    return duration


async def concat_clips(clips: list[Path], out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lst = Path(tmp) / "list.txt"
        lst.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in clips))
        await run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                   "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)], timeout=900)
