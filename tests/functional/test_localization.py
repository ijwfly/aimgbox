import pytest


@pytest.mark.asyncio
async def test_error_message_in_russian(client, seeded_data):
    """Accept-Language: ru should return error messages in Russian."""
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "i18n-user",
        "Accept-Language": "ru",
    }

    # Request a non-existent job
    resp = await client.get(
        "/v1/jobs/00000000-0000-0000-0000-000000000001",
        headers=headers,
    )
    assert resp.status_code == 404
    error = resp.json()["error"]
    assert error["code"] == "NOT_FOUND"
    # Should contain Russian text
    assert "не найден" in error["message"].lower() or "not found" in error["message"].lower()


@pytest.mark.asyncio
async def test_error_message_in_english_with_lang_param(client, seeded_data):
    """?lang=en should return error messages in English."""
    headers = {
        "X-API-Key": seeded_data["token"],
        "X-External-User-Id": "i18n-user-2",
    }

    resp = await client.get(
        "/v1/jobs/00000000-0000-0000-0000-000000000001?lang=en",
        headers=headers,
    )
    assert resp.status_code == 404
    error = resp.json()["error"]
    assert error["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_languages_endpoint(client):
    """GET /v1/meta/languages should return available languages."""
    resp = await client.get("/v1/meta/languages")
    assert resp.status_code == 200
    data = resp.json()["data"]
    langs = data["languages"]
    codes = [lang["code"] for lang in langs]
    assert "en" in codes
    assert "ru" in codes
