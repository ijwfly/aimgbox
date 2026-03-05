from aimg.api.middleware import _resolve_language


class FakeRequest:
    def __init__(self, query_params=None, headers=None):
        self.query_params = query_params or {}
        self.headers = headers or {}


def test_lang_from_query_param():
    req = FakeRequest(query_params={"lang": "ru"})
    assert _resolve_language(req) == "ru"


def test_lang_from_accept_language_header():
    req = FakeRequest(headers={"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"})
    assert _resolve_language(req) == "ru"


def test_lang_query_param_overrides_header():
    req = FakeRequest(
        query_params={"lang": "en"},
        headers={"Accept-Language": "ru"},
    )
    assert _resolve_language(req) == "en"


def test_lang_defaults_to_en():
    req = FakeRequest()
    assert _resolve_language(req) == "en"


def test_lang_simple_accept_language():
    req = FakeRequest(headers={"Accept-Language": "de"})
    assert _resolve_language(req) == "de"


def test_lang_accept_language_with_region():
    req = FakeRequest(headers={"Accept-Language": "en-US"})
    assert _resolve_language(req) == "en"
