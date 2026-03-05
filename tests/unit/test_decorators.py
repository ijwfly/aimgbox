import pytest
from unittest.mock import AsyncMock, MagicMock

from aimg.admin.decorators import require_auth, require_role


def _make_request(admin_user=None):
    request = MagicMock()
    request.state.admin_user = admin_user
    return request


@pytest.mark.asyncio
async def test_require_auth_allows_authenticated():
    handler = AsyncMock(return_value="ok")
    wrapped = require_auth(handler)
    request = _make_request(admin_user={"id": "123", "role": "admin"})
    result = await wrapped(request)
    assert result == "ok"
    handler.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_require_auth_redirects_unauthenticated():
    handler = AsyncMock(return_value="ok")
    wrapped = require_auth(handler)
    request = _make_request(admin_user=None)
    result = await wrapped(request)
    assert result.status_code == 302
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_require_role_allows_matching_role():
    handler = AsyncMock(return_value="ok")
    wrapped = require_role("admin", "super_admin")(handler)
    request = _make_request(admin_user={"id": "123", "role": "admin"})
    result = await wrapped(request)
    assert result == "ok"


@pytest.mark.asyncio
async def test_require_role_allows_super_admin():
    handler = AsyncMock(return_value="ok")
    wrapped = require_role("super_admin")(handler)
    request = _make_request(admin_user={"id": "123", "role": "super_admin"})
    result = await wrapped(request)
    assert result == "ok"


@pytest.mark.asyncio
async def test_require_role_denies_wrong_role():
    handler = AsyncMock(return_value="ok")
    wrapped = require_role("super_admin")(handler)
    request = _make_request(admin_user={"id": "123", "role": "viewer"})
    result = await wrapped(request)
    assert result.status_code == 403
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_require_role_redirects_unauthenticated():
    handler = AsyncMock(return_value="ok")
    wrapped = require_role("admin")(handler)
    request = _make_request(admin_user=None)
    result = await wrapped(request)
    assert result.status_code == 302
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_require_role_viewer_denied_for_admin_only():
    handler = AsyncMock(return_value="ok")
    wrapped = require_role("admin")(handler)
    request = _make_request(admin_user={"id": "123", "role": "viewer"})
    result = await wrapped(request)
    assert result.status_code == 403
