from math import log2
from hypothesis import given, settings
from hypothesis import strategies as st
from crvusdsim.pool.crvusd.LLAMMA import LLAMMAPool
from crvusdsim.pool.crvusd.price_oracle.price_oracle import PriceOracle
from ..conftest import INIT_PRICE


@given(
    n=st.integers(min_value=5, max_value=50),
    debt=st.integers(min_value=10**6, max_value=2 * 10**6 * 10**18),
    collateral_amount=st.integers(min_value=10**6, max_value=10**9 * 10**36 // INIT_PRICE),
)
@settings(max_examples=100)
def test_calculate_n1(collateral_amount, debt, n, controller_and_amm):
    controller, pool = controller_and_amm
    n0 = pool.active_band
    A = pool.A
    p0 = pool.p_oracle_down(n0) / 1e18
    discounted_collateral = collateral_amount * (10**18 - controller.loan_discount) // 10**18

    too_high = False
    too_deep = False
    try:
        n1 = controller.calculate_debt_n1(collateral_amount, debt, n)
    except Exception as e:
        too_high = 'Debt too high' in str(e)
        too_deep = 'Too deep' in str(e)
        if not too_high and not too_deep:
            raise
    if too_high:
        assert discounted_collateral * p0 * ((A - 1) / A)**n <= debt
        return
    if too_deep:
        assert abs(log2(debt / discounted_collateral * p0)) > log2(500)
        return

    assert discounted_collateral * p0 >= debt

    n2 = n1 + n - 1

    assert discounted_collateral * pool.p_oracle_up(n1) / 1e18 >= debt
    if n2 < 1023:
        assert discounted_collateral * pool.p_oracle_down(n2) / 1e18 <= debt

