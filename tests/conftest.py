import os
import tempfile
from pathlib import Path

# Point the app at a throwaway database before anything imports the settings.
_tmp = Path(tempfile.mkdtemp(prefix="bankq-test-"))
os.environ["BANKQ_DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["BANKQ_LOG_JSON"] = "false"
os.environ["BANKQ_API_KEYS"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from bankq.config import get_settings  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from bankq.api.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def settings():
    s = get_settings()
    yield s
    s.api_keys = ""
    s.rate_limit_per_minute = 120
