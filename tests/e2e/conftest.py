import os

import httpx
import pytest


@pytest.fixture
def client():
    base_url = os.environ.get("AIMG_API_URL", "http://localhost:8010")
    with httpx.Client(base_url=base_url) as client:
        yield client
