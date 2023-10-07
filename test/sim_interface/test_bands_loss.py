import pytest
from datetime import datetime, timedelta
from random import randint
from crvusdsim.pool.crvusd.conf import ARBITRAGUR_ADDRESS
from crvusdsim.pool_data.metadata.bands_strategy import simple_bands_strategy
from test.sim_interface.conftest import create_sim_pool
from test.utils import approx, generate_prices
import time
import numpy as np
import pandas as pd

trade_threshold = 10**2 * 10**18
profit_threshold = 50 * 10**18


def test_bands_snapshot(assets):
    pool = create_sim_pool()
    ts_begin = int(time.time())
    ts = ts_begin
    pool._increment_timestamp(ts)
    p_up = pool.p_oracle_up(0)
    p_down = pool.p_oracle_down(9)

    prices = generate_prices(
        price_max=p_up / 1e18,
        price_min=p_down / 1e18,
        trade_count=100,
        columns=assets.symbol_pairs,
    )

    total_y = 10000 * 10**18
    simple_bands_strategy(
        pool,
        prices,
        total_y=total_y,
    )

    for i in range(pool.min_band, pool.max_band + 1):
        p_o = pool.p_oracle_down(i)
        ts += 30 * 60
        pool.price_oracle_contract.set_price(p_o)
        pool._increment_timestamp(ts)
        pool.price_oracle_contract._increment_timestamp(ts)
        amount_out = pool.bands_y[i]
        amount_in = pool.get_dx(0, 1, amount_out)
        amount_in_done, amount_out_done = pool.trade(0, 1, amount_in)

    for i in range(pool.min_band, pool.max_band + 1):
        assert pool.get_band_snapshot(i, ts_begin)["y"] == total_y // (
            pool.max_band + 1 - pool.min_band
        )


def test_bands_loss(assets, local_prices):
    pool = create_sim_pool()

    prices, volumes = local_prices
    prices = prices[:]

    # Populate inverse price data, bringing it back to the initial price
    # time_duration = prices.index[-1] - prices.index[0]
    # prices_reverse = pd.DataFrame(
    #     prices.iloc[::-1].values.tolist(),
    #     index=prices.index + time_duration,
    #     columns=assets.symbol_pairs,
    # )
    # prices = pd.concat([prices.iloc[:, 0], prices_reverse.iloc[:, 0]])
    # prices = pd.DataFrame(prices, columns=assets.symbol_pairs)

    simple_bands_strategy(pool, prices, total_y=10000 * 10**18, unuse_bands=20)

    pool.prepare_for_run(prices=prices)
    init_bands_x = pool.bands_x.copy()
    init_bands_y = pool.bands_y.copy()

    init_pool_value = pool.get_total_xy_up(use_y=False)

    total_profit = 0
    total_fee_collateral = 0
    total_fee_borrowed = 0
    for ts, p_o in prices.iloc[:].iterrows():
        p_o = int(p_o.iloc[0] * 10**18)
        pool.price_oracle_contract.set_price(p_o)
        pool.prepare_for_trades(ts)

        target_price = pool.price_oracle()

        amount_in, pump = pool.get_amount_for_price(int(target_price))

        if amount_in == 0:
            continue

        if pump:
            i, j = 0, 1
        else:
            i, j = 1, 0

        amount_in, amount_out = pool.get_dxdy(i, j, amount_in)

        if pump:
            if amount_in < trade_threshold:
                continue
        else:
            if amount_out < trade_threshold:
                continue

        if pump:
            profit = amount_out * p_o / 10**18 - amount_in
        else:
            profit = amount_out - amount_in * p_o / 10**18

        # do exchange if profit enough, except for last round
        # (we need amm p to approximate p_out in order to calculate loss)
        if profit < profit_threshold and ts != prices.index[-1]:
            continue

        # exchange
        in_amount_done, out_amount_done = pool.trade(i, j, amount_in)

        total_profit += profit

        fee_rate = pool.dynamic_fee()
        if pump:
            total_fee_borrowed += in_amount_done * fee_rate / 1e18
        else:
            total_fee_collateral += in_amount_done * fee_rate / 1e18

    assert approx(pool.get_p(), pool.price_oracle(), 1e-3), "should no price diff at last"

    final_pool_value = pool.get_total_xy_up(use_y=False)

    price = pool.price_oracle() / 1e18
    bench_pool_value = pool.bench_x + pool.bench_y * price
    pool_value = sum(pool.bands_x.values()) + sum(pool.bands_y.values()) * price

    print("")
    print("init_pool_value", init_pool_value / 1e18)
    print("final_pool_value", final_pool_value / 1e18)
    print("total_profit", total_profit / 1e18)
    print((init_pool_value - final_pool_value) / 1e18)
    print("loss {:.4f}%".format((final_pool_value / init_pool_value - 1) * 100))
    print("profit {:.4f}%".format((total_profit / init_pool_value)  * 100))
    print(bench_pool_value / 1e18)
    print(pool_value / 1e18)
    print("bech loss {:.4f}%".format((pool_value / bench_pool_value - 1)  * 100), (bench_pool_value - pool_value) / 1e18)
    print("total_fee_borrowed", total_fee_borrowed / 1e18)
    print("total_fee_collateral", total_fee_collateral / 1e18)

    # assert final_pool_value < init_pool_value
    assert pool_value < bench_pool_value

    # test bands_delta_snapshot
    for ts in pool.bands_delta_snapshot:
        _snapshot = pool.bands_delta_snapshot[ts]
        for index in _snapshot:
            init_bands_x[index] += _snapshot[index]["x"]
            init_bands_y[index] += _snapshot[index]["y"]

    for index in pool.bands_x:
        assert init_bands_x[index] == pool.bands_x[index]

    for index in pool.bands_y:
        assert init_bands_y[index] == pool.bands_y[index]
