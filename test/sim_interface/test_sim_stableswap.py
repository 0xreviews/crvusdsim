from hypothesis import given, settings
from hypothesis import strategies as st

from ..conftest import STABLE_A, STABLE_N, STABLE_FEE
from crvusdsim.pool.sim_interface.sim_stableswap import SimCurveStableSwapPool


@given(
    balance0=st.integers(
        min_value=10 * 10**4 * 10**18, max_value=5000 * 10**4 * 10**18
    ),
    balance1=st.integers(
        min_value=10 * 10**4 * 10**18, max_value=5000 * 10**4 * 10**18
    ),
)
def test_stableswap_get_p(stablecoin, other_coins, balance0, balance1):
    peg_coin = other_coins[0]
    pool = SimCurveStableSwapPool(
        name="crvUSD/%s" % (peg_coin.symbol),
        symbol="crvUSD-%s" % (peg_coin.symbol),
        A=STABLE_A,
        D=[balance0, balance1],
        n=STABLE_N,
        fee=STABLE_FEE,
        coins=[peg_coin, stablecoin],
    )

    amm_p = pool.get_p()

    amount_in, amount_out, fees = pool.trade(0, 1, 10**6)
    avg_p = (amount_in - fees) * 10**18 / amount_out

    assert abs(abs(amm_p / avg_p) - 1) < 5e-3


@given(
    target_price=st.integers(
        min_value=int(0.80 * 10**18), max_value=int(1.20 * 10**18)
    ),
    balance0=st.integers(
        min_value=1000 * 10**18, max_value=5000 * 10**4 * 10**18
    ),
    balance1=st.integers(
        min_value=1000 * 10**18, max_value=5000 * 10**4 * 10**18
    ),
)
def test_stableswap_get_amount_for_p(
    stablecoin, other_coins, target_price, balance0, balance1
):
    peg_coin = other_coins[0]
    pool = SimCurveStableSwapPool(
        name="crvUSD/%s" % (peg_coin.symbol),
        symbol="crvUSD-%s" % (peg_coin.symbol),
        A=STABLE_A,
        D=[balance0, balance1],
        n=STABLE_N,
        fee=STABLE_FEE,
        coins=[peg_coin, stablecoin],
    )

    amount, pump = pool.get_amount_for_price(target_price)

    if pump:
        i, j = 0, 1
    else:
        i, j = 1, 0

    pool.trade(i, j, amount)

    amm_p = pool.get_p()
    assert abs(abs(amm_p / target_price) - 1) < 1e-5
