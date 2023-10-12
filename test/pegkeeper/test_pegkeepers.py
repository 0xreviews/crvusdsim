from hypothesis import given, settings
from hypothesis import strategies as st
from crvusdsim.pool.crvusd.conf import ARBITRAGUR_ADDRESS
from test.utils import approx


def test_pegkeepers_params(
    factory, aggregator, stablecoin, other_coins, stableswaps, pegkeepers
):
    for i in range(len(pegkeepers)):
        pool = stableswaps[i]
        pk = pegkeepers[i]

        assert pk.factory() == factory
        assert pk.pool() == pool
        assert pk.pegged() == stablecoin
        assert pk.aggregator() == aggregator


def test_pegkeepers_update(
    factory, aggregator, stablecoin, other_coins, stableswaps, pegkeepers
):
    beneficiary_addr = "_beneficiary_address"
    buy_amount = 1 * 10**5 * 10**18
    time_delta = 2 * 60  # 10m

    def increase_timestamp(td):
        for i in range(len(stableswaps)):
            stableswaps[i]._increment_timestamp(timedelta=td)
            pegkeepers[i]._increment_timestamp(timedelta=td)

    increase_timestamp(time_delta)
    # make crvUSD price above water
    for i in range(len(stableswaps)):
        pool = stableswaps[i]
        pk = pegkeepers[i]
        pool.exchange(0, 1, buy_amount, _receiver=ARBITRAGUR_ADDRESS)

    aggregator._increment_timestamp(timedelta=time_delta)

    old_agg_p = aggregator.price()
    assert old_agg_p > 10**18, "aggregator.price() must be greater"

    increase_timestamp(time_delta)
    for i in range(len(pegkeepers)):
        pool = stableswaps[i]
        pk = pegkeepers[i]
        old_pool_p = pool.get_p()
        assert pool.get_p() > 10**18, "crvUSD price must above water"
        caller_profit = pk.update(beneficiary_addr)
        assert pool.balanceOf[pk.address] > 0
        assert old_pool_p > pool.get_p(), "price must go down after provide"

    # make crvUSD price under water
    aggregator._increment_timestamp(timedelta=time_delta)
    assert old_agg_p > aggregator.price(), "price must go down after provide"
    old_agg_p = aggregator.price()

    increase_timestamp(time_delta)
    for i in range(len(stableswaps)):
        pool = stableswaps[i]
        pk = pegkeepers[i]
        old_pool_p = pool.get_p()
        dx, dy, fees = pool.exchange(1, 0, int(buy_amount * 1.1), _receiver=ARBITRAGUR_ADDRESS)
        assert old_pool_p > pool.get_p(), "price must go down after exchange"

    aggregator._increment_timestamp(timedelta=time_delta)
    assert old_agg_p > aggregator.price(), "price must go down after exchange"

    increase_timestamp(time_delta)
    for i in range(len(pegkeepers)):
        pool = stableswaps[i]
        pk = pegkeepers[i]
        caller_profit = pk.update(beneficiary_addr)
        assert caller_profit > 0, "must have profit"

    aggregator._increment_timestamp(timedelta=time_delta)


# def test_pegkeepers_calcp_rofit(factory, aggregator, stablecoin, pegged_coins, stableswaps, pegkeepers):
#     for i in range(len(pegkeepers)):
#         pool = stableswaps[i]
#         pk = pegkeepers[i]

#         assert pk.calc_profit() == 0, "profit must be zero at begining"
