from hypothesis import given, settings
from hypothesis import strategies as st
from test.utils import (approx)


def test_aggregator(factory, aggregator, stablecoin, other_coins, stableswaps):
    buy_amount = 10000 * 10**18
    time_delta = 1 * 60 # 10m

    before_agg_price = aggregator.price()
    aggregator._increment_timestamp(time_delta)

    for i in range(len(stableswaps)):
        pool = stableswaps[i]
        old_price = pool.get_p()
        pool._increment_timestamp(time_delta)
        pool.exchange(0, 1, buy_amount)
        assert pool.get_p() > old_price

    after_agg_price = aggregator.price()

    assert after_agg_price > before_agg_price