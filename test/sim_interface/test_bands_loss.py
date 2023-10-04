import pytest
from datetime import datetime
from random import randint
from crvusdsim.pool.crvusd.conf import ARBITRAGUR_ADDRESS
from crvusdsim.pool_data.metadata.bands_strategy import simple_bands_strategy
from test.sim_interface.conftest import create_sim_pool
from test.utils import approx
import time
import numpy as np
import pandas as pd

trade_threshold = 10**2 * 10**18
profit_threshold = 50 * 10**18


def test_bands_snapshot():
    pool = create_sim_pool()
    ts_begin = int(time.time())
    ts = ts_begin
    pool._increment_timestamp(ts)
    p_up = pool.p_oracle_up(0)
    p_down = pool.p_oracle_down(9)
    total_y = 10000 * 10**18
    simple_bands_strategy(
        pool,
        init_price=p_up,
        max_price=p_up,
        min_price=p_down,
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


def test_bands_loss(local_prices):
    pool = create_sim_pool()

    prices, volumes = local_prices
    prices = prices[3000:8000]
    # time_duration = prices.index[-1] - prices.index[0]
    # prices_reverse = pd.DataFrame(prices.iloc[::-1].values.tolist(), index=prices.index + time_duration, columns=["price"])
    # prices = pd.concat([prices, prices_reverse], axis=0)
    simple_bands_strategy(
        pool,
        init_price=prices.iloc[0, :].tolist()[0] * 10**18,
        max_price=int(prices.iloc[0, :].max() * 10**18),
        min_price=1500 * 10**18,
        total_y=10000 * 10**18,
    )

    pool.prepare_for_run(prices=prices)
    init_bands_x = pool.bands_x.copy()
    init_bands_y = pool.bands_y.copy()
    
    arbitragur_collateral_balance_before = pool.COLLATERAL_TOKEN.balanceOf[ARBITRAGUR_ADDRESS]
    arbitragur_stablecoin_balance_before = pool.BORROWED_TOKEN.balanceOf[ARBITRAGUR_ADDRESS]

    pool_max_price = pool.p_oracle_up(pool.min_band)
    pool_min_price = pool.p_oracle_down(pool.max_band)
    print("pool_max_price", pool_max_price / 1e18)
    print("pool_min_price", pool_min_price / 1e18)

    total_profit = 0
    total_fee_collateral = 0
    total_fee_borrowed = 0
    for ts, p_o in prices.iloc[:].iterrows():
        p_o = int(p_o.iloc[0] * 10**18)
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

        if pump:
            if amount_in < trade_threshold:
                continue
        else:
            if amount_out < trade_threshold:
                continue

        # price_avg = amount_in / amount_out if pump else amount_out / amount_in

        if pump:
            profit = amount_out * p_o / 10**18 - amount_in
        else:
            profit = amount_out - amount_in * p_o / 10**18

        if profit < profit_threshold:
            continue

        # exchange
        in_amount_done, out_amount_done = pool.trade(i, j, amount_in)

        total_profit += profit

        fee_rate = pool.dynamic_fee()
        if pump:
            total_fee_borrowed += in_amount_done * fee_rate / 1e18
        else:
            total_fee_collateral += in_amount_done * fee_rate / 1e18

        if fee_rate > pool.fee:
            print("")
            print(i, j)
            print("fee_rate", fee_rate / 1e18)
            # print(amount_in, amount_out)
            print(in_amount_done / 1e18, out_amount_done / 1e18)
            print("p_o", p_o / 1e18)
            print("amm_p", amm_p / 1e18)
            # print("price_avg", price_avg)
            print("amm_p after", pool.get_p() / 1e18)
            print("profit", profit / 1e18)

    price = prices.iloc[-1, 0]
    init_pool_value = sum(init_bands_x.values()) + sum(init_bands_y.values()) * price
    final_pool_value = sum(pool.bands_x.values()) + sum(pool.bands_y.values()) * price
    
    arbitragur_collateral_profit = pool.COLLATERAL_TOKEN.balanceOf[ARBITRAGUR_ADDRESS]  - arbitragur_collateral_balance_before
    arbitragur_stablecoin_profit = pool.BORROWED_TOKEN.balanceOf[ARBITRAGUR_ADDRESS] - arbitragur_stablecoin_balance_before


    print("")
    print("init_pool_value", init_pool_value)
    print("final_pool_value", final_pool_value)
    print("loss {:.4f}%".format((final_pool_value / init_pool_value - 1) * 100))
    print("total_fee_borrowed", total_fee_borrowed / 1e18)
    print("total_fee_collateral", total_fee_collateral / 1e18)
    print("arbitragur_collateral_balance delta", arbitragur_collateral_profit / 1e18)
    print("arbitragur_stablecoin_balance delta", arbitragur_stablecoin_profit / 1e18)

    assert final_pool_value < init_pool_value

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
