from aimg.admin.pagination import get_page_info


def test_basic():
    info = get_page_info(1, 100, per_page=50)
    assert info["page"] == 1
    assert info["total"] == 100
    assert info["total_pages"] == 2
    assert info["has_prev"] is False
    assert info["has_next"] is True
    assert info["offset"] == 0


def test_page_two():
    info = get_page_info(2, 100, per_page=50)
    assert info["page"] == 2
    assert info["has_prev"] is True
    assert info["has_next"] is False
    assert info["offset"] == 50


def test_page_zero_clamped():
    info = get_page_info(0, 100, per_page=50)
    assert info["page"] == 1


def test_page_beyond_total_clamped():
    info = get_page_info(999, 100, per_page=50)
    assert info["page"] == 2


def test_zero_total():
    info = get_page_info(1, 0, per_page=50)
    assert info["total_pages"] == 1
    assert info["page"] == 1
    assert info["has_prev"] is False
    assert info["has_next"] is False


def test_single_page():
    info = get_page_info(1, 10, per_page=50)
    assert info["total_pages"] == 1
    assert info["has_next"] is False


def test_exact_boundary():
    info = get_page_info(1, 50, per_page=50)
    assert info["total_pages"] == 1
    assert info["has_next"] is False


def test_one_over_boundary():
    info = get_page_info(1, 51, per_page=50)
    assert info["total_pages"] == 2
    assert info["has_next"] is True
