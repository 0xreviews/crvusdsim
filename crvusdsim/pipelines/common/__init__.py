from scipy.optimize import root_scalar

from curvesim.logging import get_logger
from crvusdsim.metrics import metrics as Metrics
from curvesim.templates.trader import Trade, Trader

logger = get_logger(__name__)
DEFAULT_METRICS = [
    Metrics.Timestamp,
    Metrics.PoolValue,
    Metrics.PoolVolume,
    Metrics.ArbMetrics,
]

DEFAULT_PARAMS = {"A": [100], "fee": [6 * 10**15], "admin_fee": [0]}
TEST_PARAMS = {"A": [100], "fee": [6 * 10**15], "admin_fee": [0]}


def get_arb_trades(pool, prices, trade_threshold=100 * 10**18, profit_threshold=50 * 10**18):
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
        i, j = pair
        p_o = int(prices[pair] * 10**18)

        target_price = pool.price_oracle()
        
        amount, pump = pool.get_amount_for_price(target_price)

        if pump:
            price = prices[pair]
            coin_in, coin_out = i, j
            amount_in, amount_out, fees = pool.get_dxdy(0, 1, amount)
        else:
            price = 1 / prices[pair]
            coin_in, coin_out = j, i
            amount_in, amount_out, fees = pool.get_dxdy(1, 0, amount)
        
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
        if profit < profit_threshold:
            continue

        # simply calc profit
        amm_p = pool.price(i, j)
        profit = amount_in * (amm_p - p_o) / 10**18
        if abs(profit) < profit_threshold:
            trades.append((0, pair, prices[pair]))
            continue

        trades.append((amount_in, amount_out, (coin_in, coin_out), price))

    return trades
