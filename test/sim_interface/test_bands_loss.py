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

    prices, volumes = local_prices
    prices = prices[:1000]
    time_duration = prices.index[-1] - prices.index[0]
    # prices_reverse = pd.DataFrame(prices.iloc[::-1].values.tolist(), index=prices.index + time_duration, columns=["price"])
    # prices = pd.concat([prices, prices_reverse], axis=0)
    print(prices)
    simple_bands_strategy(
        pool,
        init_price=prices.iloc[0, :].tolist()[0] * 10**18,
        max_price=int(prices.max() * 10**18),
        min_price=1500 * 10**18,
        total_y=10000 * 10**18,
    )

    pool.prepare_for_run(prices=prices)
    init_bands_x = pool.bands_x.copy()
    init_bands_y = pool.bands_y.copy()

    pool_max_price = pool.p_oracle_up(pool.min_band)
    pool_min_price = pool.p_oracle_down(pool.max_band)
    print("pool_max_price", pool_max_price / 1e18)
    print("pool_min_price", pool_min_price / 1e18)

    for ts, p_o in prices.iterrows():
        p_o = int(p_o["price"] * 10**18)
        pool.price_oracle_contract.set_price(p_o)
        pool.prepare_for_trades(ts)

        target_price = p_o
        target_price = min(pool_max_price, target_price)
        target_price = max(pool_min_price, target_price)

        amm_p = pool.get_p()
        amount_in, pump = pool.get_amount_for_price(int(target_price))

        if amount_in == 0:
            continue
        
        if pump:
            i, j = 0, 1
        else:
            i, j = 1, 0

        amount_in, amount_out = pool.get_dxdy(i, j, amount_in)
        price_avg = amount_in / amount_out if pump else amount_out / amount_in

        if pump:
            if amount_in < trade_threshold or price_avg * 1e18 > p_o:
                continue
        else:
            if amount_in < trade_threshold * 10**18 / p_o or price_avg * 1e18 < p_o:
                continue


        # exchange
        in_amount_done, out_amount_done = pool.trade(i, j, amount_in)
        # print("")
        # print(i, j)
        # print("fee", pool.dynamic_fee() / 1e18)
        # print(amount_in, amount_out)
        # print(in_amount_done, out_amount_done)
        # print("p_o", p_o / 1e18)
        # print("amm_p", amm_p / 1e18)
        # print("price_avg", price_avg)
        # print("amm_p after", pool.get_p() / 1e18)

    price = pool.price_oracle()
    init_pool_value = sum(init_bands_x.values()) + sum(init_bands_y.values()) * price / 1e18
    final_pool_value = sum(pool.bands_x.values()) + sum(pool.bands_y.values()) * price / 1e18
    
    assert final_pool_value < init_pool_value

    print("")
    print("init_pool_value", init_pool_value)
    print("final_pool_value", final_pool_value)
    print("loss {:.4f}%".format((final_pool_value / init_pool_value - 1) * 100) )

    # test bands_delta_snapshot
    total_value_loss = 0
    for ts in pool.bands_delta_snapshot:
        _snapshot = pool.bands_delta_snapshot[ts]
        for index in _snapshot:
            init_bands_x[index] += _snapshot[index]["x"]
            init_bands_y[index] += _snapshot[index]["y"]
            total_value_loss += _snapshot[index]["x0_loss"]
    
    for index in pool.bands_x:
        assert init_bands_x[index] == pool.bands_x[index]

    for index in pool.bands_y:
        assert init_bands_y[index] == pool.bands_y[index]
