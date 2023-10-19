import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from crvusdsim.pool_data.metadata.bands_strategy import simple_bands_strategy
from test.sim_interface.conftest import create_sim_pool
from test.utils import approx, generate_prices


@given(
    init_y=st.integers(min_value=10**18, max_value=10**24),
    price_max=st.integers(min_value=2001, max_value=3000),
    dprice=st.integers(min_value=500, max_value=2000),
    trade_count=st.integers(min_value=10, max_value=200),
)
def test_simple_bands_strategy(assets, init_y, price_max, dprice, trade_count):
    pool = create_sim_pool()

    prices = generate_prices(
        price_max=price_max,
        price_min=price_max - dprice,
        trade_count=trade_count,
        columns=assets.symbol_pairs,
    )

    simple_bands_strategy(
        pool,
        prices,
        total_y=init_y,
    )

    pool.prepare_for_run(prices=prices)

    pool_max_price = pool.p_oracle_up(pool.min_band)
    pool_min_price = pool.p_oracle_down(pool.max_band)
    amm_p = pool.get_p()

    assert pool_max_price >= int(prices.iloc[:, 0].max() * 10**18)
    assert pool_min_price <= int(prices.iloc[:, 0].min() * 10**18)
    assert pool.active_band == pool.min_band
    assert amm_p <= pool.p_oracle_up(pool.active_band) and amm_p >= pool.p_oracle_down(
        pool.active_band
    )

    # assert approx(
    #     pool.get_total_xy_up(use_y=True), init_y, 1e-3
    # ), "init_y changed too much"


def test_simple_bands_strategy_1(assets, local_prices):
    pool = create_sim_pool()

    init_y = 10000 * 10**18
    prices, volumes = local_prices

    simple_bands_strategy(
        pool,
        prices,
        total_y=init_y,
    )

    pool.prepare_for_run(prices=prices)

    pool_max_price = pool.p_oracle_up(pool.min_band)
    pool_min_price = pool.p_oracle_down(pool.max_band)
    amm_p = pool.get_p()

    assert pool_max_price >= int(prices.iloc[:, 0].max() * 10**18)
    assert pool_min_price <= int(prices.iloc[:, 0].min() * 10**18)
    assert amm_p <= pool.p_oracle_up(pool.active_band) and amm_p >= pool.p_oracle_down(
        pool.active_band
    )

    if pool.active_band > pool.min_band:
        for i in range(pool.min_band, pool.active_band):
            assert pool.bands_x[i] > 0 and pool.bands_y[i] == 0

    # assert approx(
    #     pool.get_total_xy_up(use_y=True), init_y, 1e-3
    # ), "init_y changed too much"