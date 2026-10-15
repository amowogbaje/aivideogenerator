"""Where generated files live. DB rows store paths RELATIVE to media_path, so moving DATA_DIR never breaks them."""
import re
import uuid
from pathlib import Path

from app.config import settings


def media_root() -> Path:
    settings.media_path.mkdir(parents=True, exist_ok=True)
    return settings.media_path


def new_path(*parts: str, ext: str) -> tuple[str, Path]:
    """Returns (relative path for the DB, absolute path to write). A random suffix means a regenerated file never
    collides with — or gets served stale from the browser cache as — the one it replaces."""
    rel = Path(*parts) / f"{uuid.uuid4().hex[:10]}.{ext.lstrip('.')}"
    abs_path = media_root() / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return rel.as_posix(), abs_path


def abs_path(rel: str) -> Path:
    return media_root() / rel


def url(rel: str | None) -> str | None:
    return f"/media/{rel}" if rel else None


def delete(rel: str | None) -> None:
    if not rel:
        return
    try:
        abs_path(rel).unlink(missing_ok=True)
    except OSError:
        pass


def slugify(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())
