from typing import List, Any
from datetime import datetime, timedelta
from math import log
import pandas as pd

def approx(x1: int, x2: int, precision: int, abs_precision=None):
    if precision >= 1:
        return True
    result = False
    if abs_precision is not None:
        result = abs(x2 - x1) <= abs_precision
    else:
        abs_precision = 0
    if x2 == 0:
        return abs(x1) <= abs_precision
    elif x1 == 0:
        return abs(x2) <= abs_precision
    return result or (abs(log(x1 / x2)) <= precision)

def generate_prices(price_max, price_min, trade_count, columns):
    # trade_count = 10 * (24 * 60 // 10)
    ts_list = []
    prices = []
    _ts = datetime.strptime("2023-08-01 00:00:00", "%Y-%m-%d %H:%M:%S")
    _price = price_max
    _price_delta = (price_min - price_max) / trade_count
    _ts_delta = timedelta(minutes=5)
    while _price > price_min:
        ts_list.append(_ts)
        prices.append(_price)
        _price += _price_delta
        _ts += _ts_delta

    prices = pd.DataFrame(prices, columns=columns, index=ts_list)
    return prices

def increment_timestamps(objects: List[Any], ts: int) -> None:
    for obj in objects:
        obj._increment_timestamp(ts)

def trade(oracle, pool, i, j, frac):
    amount = pool.get_max_trade_size(i, j, frac)
    pool.exchange(i, j, amount)  # sell crvUSD for stablecoin

    objects = oracle.stableswap + oracle.tricrypto + [oracle.stable_aggregator]
    ts = oracle.last_timestamp + 60 * 60
    increment_timestamps(objects, ts)

    return oracle.price_w()
