import os

import httpx
import pytest


@pytest.fixture
def base_url():
    return os.environ.get("AIMG_API_URL", "http://localhost:8010")


@pytest.fixture
def api_key():
    """Must be set via env var after running `aimg seed`."""
    key = os.environ.get("AIMG_API_KEY")
    if not key:
        pytest.skip("AIMG_API_KEY not set; run `aimg seed` first")
    return key


@pytest.fixture
def client(base_url):
    with httpx.Client(base_url=base_url) as client:
        yield client
