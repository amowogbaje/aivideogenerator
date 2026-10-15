import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger("app.ffmpeg")


class FFmpegError(RuntimeError):
    pass


async def run(cmd: list[str], *, timeout: float = 600) -> str:
    """Runs a subprocess without blocking the event loop. Raises FFmpegError carrying the tail of stderr."""
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise FFmpegError(f"{cmd[0]} timed out after {timeout}s")
    if proc.returncode != 0:
        tail = err.decode(errors="replace")[-1500:]
        logger.error("%s failed (%s):\n%s", cmd[0], proc.returncode, tail)
        raise FFmpegError(f"{cmd[0]} exited {proc.returncode}: {tail[-400:]}")
    return out.decode(errors="replace")


async def probe_duration(path: str | Path) -> float:
    out = await run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(path)], timeout=60)
    return float(json.loads(out)["format"]["duration"])


async def to_mp3(src: str | Path, dst: str | Path) -> None:
    """Normalises any provider's audio (wav/mp3/webm) to mono 44.1kHz mp3 so every scene's audio is uniform."""
    await run(["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", "44100", "-b:a", "128k", str(dst)], timeout=120)
