import os
import tempfile

# Configure BEFORE the app is imported: offline providers, throwaway DB + media dir.
_tmp = tempfile.mkdtemp(prefix="studio-test-")
os.environ.update({
    "DATA_DIR": _tmp,
    "DATABASE_URL": f"sqlite+aiosqlite:///{_tmp}/test.db",
    "TEXT_PROVIDER": "heuristic",
    "IMAGE_PROVIDER": "mock",
    "VOICE_PROVIDER": "espeak",
    "GEMINI_API_KEY": "", "ELEVENLABS_API_KEY": "", "HF_API_KEY": "",
})

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from app.main import create_app
    with TestClient(create_app()) as c:   # context manager => lifespan runs and background tasks share one loop
        yield c


def wait_for(client, path, predicate, timeout=120, what="condition"):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = client.get(path).json()
        if predicate(last):
            return last
        time.sleep(0.4)
    raise AssertionError(f"timed out waiting for {what}; last={last}")
