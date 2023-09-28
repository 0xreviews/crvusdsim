from datetime import datetime
from random import randint
from crvusdsim.pool_data.metadata.bands_strategy import simple_bands_strategy
from test.sim_interface.conftest import create_sim_pool
from test.utils import approx
import time
import numpy as np
import pandas as pd

trade_threshold = 100 * 10**18


def test_bands_loss(local_prices):
    pool = create_sim_pool()

    def get_pool_value():
        p = pool.price_oracle()
        sum_x = sum(pool.bands_x.values())
        sum_y = sum(pool.bands_y.values())
        print("sum_x", sum_x, "sum_y", sum_y)
        return sum_x + sum_y * p // 10**18

    prices, volumes = local_prices
    prices = prices[:10]
    time_duration = prices.index[-1] - prices.index[0]
    prices_reverse = pd.DataFrame(prices.iloc[::-1].values.tolist(), index=prices.index + time_duration, columns=["price"])
    prices = pd.concat([prices, prices_reverse], axis=0)
    simple_bands_strategy(
        pool,
        init_price=prices.iloc[0, :].tolist()[0] * 10**18,
        total_y=10000 * 10**18,
    )
    print(prices)

    pool.prepare_for_run(prices=prices)
    init_pool_value = get_pool_value()
    init_bands_x = pool.bands_x.copy()
    init_bands_y = pool.bands_y.copy()
    print(init_pool_value)

    for ts, p_o in prices.iterrows():
        p_o = int(p_o["price"] * 10**18)
        pool.price_oracle_contract.set_price(p_o)
        pool.prepare_for_trades(ts)

        amm_p = pool.get_p()
        amount, pump = pool.get_amount_for_price(p_o)
        
        fee = pool.dynamic_fee() / 10**18

        if pump:
            if amount < trade_threshold or amm_p * (1 - fee) > p_o:
                continue
        else:
            if amount < trade_threshold * 10**18 / p_o or amm_p / (1 - fee) < p_o:
                continue

        if pump:
            i, j = 0, 1
        else:
            i, j = 1, 0

        # exchange
        in_amount_done, out_amount_done = pool.trade(i, j, amount)

    final_pool_value = get_pool_value()
    print(final_pool_value)

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
