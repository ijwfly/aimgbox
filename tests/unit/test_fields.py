from aimg.jobs.fields import FileConstraints


def test_valid_file():
    fc = FileConstraints(max_size_mb=10, formats=["png", "jpg"])
    errors = fc.validate("image/png", 1024)
    assert errors == []


def test_size_exceeded():
    fc = FileConstraints(max_size_mb=1, formats=["png"])
    errors = fc.validate("image/png", 2 * 1024 * 1024)
    assert len(errors) == 1
    assert "exceeds limit" in errors[0]


def test_invalid_format():
    fc = FileConstraints(max_size_mb=10, formats=["png", "jpg"])
    errors = fc.validate("image/gif", 1024)
    assert len(errors) == 1
    assert "not allowed" in errors[0]


def test_jpeg_normalized_to_jpg():
    fc = FileConstraints(max_size_mb=10, formats=["jpg"])
    errors = fc.validate("image/jpeg", 1024)
    assert errors == []


def test_multiple_errors():
    fc = FileConstraints(max_size_mb=0.001, formats=["png"])
    errors = fc.validate("image/gif", 2 * 1024 * 1024)
    assert len(errors) == 2
