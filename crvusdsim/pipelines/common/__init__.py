from datetime import datetime
from scipy.optimize import root_scalar

from curvesim.logging import get_logger
from crvusdsim.metrics import metrics_pool as PoolMetrics
from crvusdsim.metrics import metrics_N as RangeNMetrics
from crvusdsim.metrics import metrics_controller as ControllerMetric
from crvusdsim.metrics import metrics_rate as RateMetric
from curvesim.templates.trader import Trade, Trader


logger = get_logger(__name__)

DEFAULT_POOL_METRICS = [
    PoolMetrics.Timestamp,
    PoolMetrics.PoolValue,
    PoolMetrics.PoolVolume,
    PoolMetrics.ArbMetrics,
]
DEFAULT_CONTROLLER_METRICS = [
    PoolMetrics.Timestamp,
    ControllerMetric.UsersHealth,
    ControllerMetric.LiquidationVolume,
]
DEFAULT_N_METRICS = [PoolMetrics.Timestamp, RangeNMetrics.RangeNReturns]
DEFAULT_RATE_METRICS = [PoolMetrics.Timestamp, RateMetric.RatePegKeeper]

DEFAULT_POOL_PARAMS = {
    "A": [50, 100, 150, 200],
    "fee": [
        6 * 10**15,
        10 * 10**15,
    ],
}
DEFAULT_CONTROLLER_PARAMS = {
    "loan_discount": [int(0.09 * 10**18), int(0.05 * 10**18)]
}
DEFAULT_N_PARAMS = {"N": [n for n in range(4, 51)]}
DEFAULT_RATE_PARAMS = {"rate0": [0.05, 0.10, 0.15]}
TEST_PARAMS = {
    "A": [50, 100, 150, 200],
    "fee": [
        6 * 10**15,
        10 * 10**15,
    ],
}


def get_arb_trades(
    pool, prices, trade_threshold=1 * 10**18, profit_threshold=50 * 10**18
):
    """
    Parameters
    ----------
    pool: SimPool
        Pool to arbitrage on

    prices : iterable
        External market prices for LLAMMA's collateral


    Returns
    -------
    trades: List[Tuple]
        List of triples (in_amount_done, out_amount_done, coins, price_target)
        "in_amount_done": trade in_amount_done
        "out_amount_done": trade out_amount_done
        "coins": in token, out token
        "price_target": price target for arbing the token pair
    """

    trades = []

    for pair in prices:
        p_o = int(prices[pair] * 10**18)
        target_price = p_o

        amount, pump = pool.get_amount_for_price(target_price)

        if amount < 10**6:
            # trades.append((0, 0, 0, 0, pair, prices[pair]))
            continue

        if pump:
            price = prices[pair]
            coin_in, coin_out = pool.asset_names
            amount_in, amount_out, fees = pool.get_dxdy(0, 1, amount)
        else:
            price = 1 / prices[pair]
            coin_out, coin_in = pool.asset_names
            amount_in, amount_out, fees = pool.get_dxdy(1, 0, amount)

        # FIXME: trade_threshold should consider rate_multiplier and usdvalue(price)
        # if pump:
        #     if amount_in < trade_threshold * pool.rates[0] / 10**18:
        #         continue
        # else:
        #     if amount_out < trade_threshold * pool.rates[0] / 10**18:
        #         continue

        if pump:
            profit = (
                amount_out * pool.rates[1] / 10**18 * p_o / 10**18
                - amount_in * pool.rates[0] / 10**18
            )
        else:
            profit = (
                amount_out * pool.rates[0] / 10**18
                - amount_in * pool.rates[1] / 10**18 * p_o / 10**18
            )

        # do exchange if profit enough, except for last round
        # (we need amm p to approximate p_out in order to calculate loss)
        if profit < profit_threshold:
            # trades.append((0, 0, 0, 0, pair, prices[pair]))
            continue

        trades.append((amount_in, amount_out, fees, profit, (coin_in, coin_out), price))

    

    return trades
