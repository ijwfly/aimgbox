import pytest

from aimg.services.billing import calculate_credit_split


def test_cost_less_than_free():
    free_d, paid_d = calculate_credit_split(free_credits=10, paid_credits=5, cost=3)
    assert free_d == 3
    assert paid_d == 0


def test_cost_equals_free():
    free_d, paid_d = calculate_credit_split(free_credits=5, paid_credits=10, cost=5)
    assert free_d == 5
    assert paid_d == 0


def test_cost_exceeds_free():
    free_d, paid_d = calculate_credit_split(free_credits=3, paid_credits=10, cost=7)
    assert free_d == 3
    assert paid_d == 4


def test_cost_uses_all_credits():
    free_d, paid_d = calculate_credit_split(free_credits=3, paid_credits=7, cost=10)
    assert free_d == 3
    assert paid_d == 7


def test_cost_exceeds_total():
    with pytest.raises(ValueError, match="Insufficient credits"):
        calculate_credit_split(free_credits=3, paid_credits=2, cost=10)


def test_zero_free_credits():
    free_d, paid_d = calculate_credit_split(free_credits=0, paid_credits=10, cost=5)
    assert free_d == 0
    assert paid_d == 5


def test_zero_cost():
    free_d, paid_d = calculate_credit_split(free_credits=10, paid_credits=5, cost=0)
    assert free_d == 0
    assert paid_d == 0
