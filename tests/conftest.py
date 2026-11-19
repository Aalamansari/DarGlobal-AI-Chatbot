import os

# keep tests offline: no Langfuse traces from test runs (set before the app reads .env)
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""

import pytest  # noqa: E402

from app.backend import data  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def load_data():
    data.load()
