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

    pool_max_price = pool.p_oracle_up(pool.min_band)
    pool_min_price = pool.p_oracle_down(pool.max_band)

    for pair in prices:
        i, j = pair
        p_o = int(prices[pair] * 10**18)

        target_price = p_o
        target_price = min(pool_max_price, target_price)
        target_price = max(pool_min_price, target_price)
        
        pool.price_oracle_contract.set_price(p_o)
        amount, pump = pool.get_amount_for_price(p_o)

        amount_in, amount_out = pool.get_dxdy(i, j, amount)

        if pump:
            if amount_in < trade_threshold:
                continue
        else:
            if amount_out < trade_threshold:
                continue

        price_avg = amount_in / amount_out if pump else amount_out / amount_in

        if pump:
            if price_avg * 1e18 > p_o:
                continue
        else:
            if price_avg * 1e18 < p_o:
                continue

        if pump:
            price = prices[pair]
            coin_in, coin_out = i, j
        else:
            price = 1 / prices[pair]
            coin_in, coin_out = j, i
        
        # exchange
        in_amount_done, out_amount_done = pool.trade(i, j, amount_in)

        # simply calc profit
        amm_p = pool.price(i, j)
        profit = amount_in * (amm_p - p_o) / 10**18
        if abs(profit) < profit_threshold:
            trades.append((0, pair, prices[pair]))
            continue

        trades.append((in_amount_done, out_amount_done, (coin_in, coin_out), price))

    return trades
