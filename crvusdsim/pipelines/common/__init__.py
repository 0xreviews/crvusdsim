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

        pool.price_oracle_contract.set_price(p_o)
        amount, pump = pool.get_amount_for_price(p_o)

        if pump and amount < trade_threshold:
            continue
        if not pump and amount < trade_threshold * 10**18 / p_o:
            continue

        if pump:
            price = prices[pair]
            coin_in, coin_out = i, j
        else:
            price = 1 / prices[pair]
            coin_in, coin_out = j, i
        
        # exchange
        in_amount_done, out_amount_done = pool.trade(i, j, amount)

        # simply calc profit
        amm_p = pool.price(i, j)
        profit = amount * (amm_p - p_o) / 10**18
        if abs(profit) < profit_threshold:
            trades.append((0, pair, prices[pair]))
            continue

        trades.append((in_amount_done, out_amount_done, (coin_in, coin_out), price))

    return trades
