import pytest
from hypothesis import given
from hypothesis import strategies as st

from test.conftest import INIT_PRICE_D1, create_controller_amm


@given(
    n=st.integers(min_value=5, max_value=50),
    debt=st.integers(min_value=10**10, max_value=2 * 10**6 * 10**18),
    collateral_amount=st.integers(min_value=10**10, max_value=10**9 * 10**18 // INIT_PRICE_D1),
)
def test_health_calculator_create(collateral_amount, debt, n, accounts):
    controller, market_amm = create_controller_amm()
    user = accounts[1]
    calculator_fail = False
    try:
        health = controller.health_calculator(user, collateral_amount, debt, False, n)
        health_full = controller.health_calculator(user, collateral_amount, debt, True, n)
    except Exception:
        calculator_fail = True


    try:
        controller.create_loan(user, collateral_amount, debt, n)
    except Exception:
        return
       
    assert not calculator_fail

    assert abs(controller.health(user) - health) / 1e18 < n * 2e-5
    assert abs(controller.health(user, True) - health_full) / 1e18 < n * 2e-5
