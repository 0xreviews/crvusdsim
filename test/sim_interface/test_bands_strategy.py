import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
import numpy as np

from crvusdsim.pipelines.simple.bands_strategy import (
    IinitYBandsStrategy,
    UserLoansBandsStrategy,
)
from test.sim_interface.conftest import create_sim_pool
from test.utils import approx, generate_prices

from crvusdsim.pipelines.simple import CRVUSD_POOL_MAP, ParameterizedLLAMMAPoolIterator


@given(
    init_y=st.integers(min_value=10**18, max_value=10**24),
    price_max=st.integers(min_value=2001, max_value=3000),
    dprice=st.integers(min_value=500, max_value=2000),
    trade_count=st.integers(min_value=10, max_value=200),
)
def test_init_y_bands_strategy(assets, init_y, price_max, dprice, trade_count):
    (pool, controller, *rest) = create_sim_pool()

    prices = generate_prices(
        price_max=price_max,
        price_min=price_max - dprice,
        trade_count=trade_count,
        columns=assets.symbol_pairs,
    )

    bands_strategy = IinitYBandsStrategy(pool, prices, controller)
    bands_strategy.do_strategy()

    pool.prepare_for_run(prices=prices)

    pool_max_price = pool.p_oracle_up(pool.min_band)
    pool_min_price = pool.p_oracle_down(pool.max_band)
    amm_p = pool.get_p()

    assert pool_max_price >= int(prices.iloc[:, 0].max() * 10**18)
    assert pool_min_price <= int(prices.iloc[:, 0].min() * 10**18)
    assert amm_p <= pool.p_oracle_up(pool.active_band) and amm_p >= pool.p_oracle_down(
        pool.active_band
    )

    # assert approx(
    #     pool.get_total_xy_up(use_y=True), init_y, 1e-3
    # ), "init_y changed too much"


def test_init_y_bands_strategy_1(assets, local_prices):
    (pool, controller, *rest) = create_sim_pool()

    init_y = 10000 * 10**18
    prices, volumes = local_prices

    bands_strategy = IinitYBandsStrategy(pool, prices, controller, init_y=init_y)
    bands_strategy.do_strategy()

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


variable_params = {
    "A": [50 + i * 10 for i in range(16)],
    "fee": [
        6 * 10**15,
    ],
}


def test_pool_value(assets, local_prices):
    sim_market = create_sim_pool()
    (pool, controller, *rest) = sim_market
    prices, volumes = local_prices

    init_y = int(sum(pool.bands_x.values()) / prices.iloc[0, 0]) + sum(
        pool.bands_y.values()
    )

    param_sampler = ParameterizedLLAMMAPoolIterator(
        sim_market,
        sim_mode="pool",
        variable_params=variable_params,
        fixed_params={},
    )

    pool_values = {}

    for sim_market, params in param_sampler:
        (pool, controller, *rest) = sim_market
        bands_strategy = IinitYBandsStrategy(pool, prices, controller, init_y=init_y)
        bands_strategy.do_strategy()
        pool.prepare_for_run(prices)

        last_out_price = pool.price_oracle_contract._price_last / 1e18
        # base_price = pool.get_base_price() / 1e18
        (
            bands_x_sum,
            bands_y_sum,
            bands_x_benchmark,
            bands_y_benchmark,
        ) = pool.get_sum_within_fluctuation_range()
        pool_value = bands_x_sum + bands_y_sum * last_out_price

        pool_values[pool.A] = pool_value / 1e18

    mean_value = np.mean(list(pool_values.values()))

    for A, v in pool_values.items():
        diff = mean_value - v
        assert approx(v, mean_value, 8e-3)

        # print("")
        # print("A", A)
        # print("diff", round(diff / v * 100, 4), diff)
        # print("pool_value", v)


def test_user_loan_strategy(assets, local_prices):
    (
        pool,
        controller,
        collateral_token,
        stablecoin,
        aggregator,
        price_oracle,
        stableswap_pools,
        peg_keepers,
        policy,
        factory,
    ) = create_sim_pool()
    prices, volumes = local_prices

    init_y = 10000 * 10**18

    bands_strategy = UserLoansBandsStrategy(pool, prices, controller, total_y=init_y)
    bands_strategy.do_strategy()
