

from crvusdsim.pool.crvusd.pool import LLAMMAPool
from crvusdsim.pool.crvusd.price_oracle.price_oracle import PriceOracle
from .conftest import approx


def test_p_oracle_updown():
    A = 100
    INIT_PRICE = 2000 * 10**18
    price_oracle = PriceOracle(INIT_PRICE)
    amm = LLAMMAPool(
        A=A,
        fee=6 * 10**15,
        BASE_PRICE=INIT_PRICE,
        admin_fee=0,
        price_oracle_contract=price_oracle,
    )
    p_base = amm.get_base_price()

    assert amm.p_oracle_up(0) == p_base
    assert approx(amm.p_oracle_down(0), p_base * (A - 1) // A, 1e-14)

    for i in range(-10, 10):
        mul = ((A - 1) / A) ** i
        p_up = p_base * mul
        p_down = p_up * (A - 1) / A
        assert approx(amm.p_oracle_up(i), p_up, 1e-14)
        assert approx(amm.p_oracle_down(i), p_down, 1e-14)