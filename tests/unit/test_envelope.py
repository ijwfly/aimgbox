from aimg.api.envelope import ApiResponse, ErrorDetail


def test_success_response():
    resp = ApiResponse(
        request_id="test-123",
        success=True,
        data={"key": "value"},
    )
    d = resp.model_dump(mode="json")
    assert d["request_id"] == "test-123"
    assert d["success"] is True
    assert d["data"] == {"key": "value"}
    assert d["error"] is None


def test_error_response():
    resp = ApiResponse(
        request_id="test-456",
        success=False,
        error=ErrorDetail(
            code="INSUFFICIENT_CREDITS",
            message="Not enough credits",
            details={"required": 5, "available": 2},
        ),
    )
    d = resp.model_dump(mode="json")
    assert d["success"] is False
    assert d["data"] is None
    assert d["error"]["code"] == "INSUFFICIENT_CREDITS"
    assert d["error"]["details"]["required"] == 5


def test_error_detail_without_details():
    ed = ErrorDetail(code="NOT_FOUND", message="Not found")
    d = ed.model_dump(mode="json")
    assert d["code"] == "NOT_FOUND"
    assert d["details"] is None
