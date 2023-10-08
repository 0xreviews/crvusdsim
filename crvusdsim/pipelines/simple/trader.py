from curvesim.logging import get_logger
from crvusdsim.templates import Trade, Trader

from ..common import get_arb_trades

logger = get_logger(__name__)


class SimpleArbitrageur(Trader):
    """
    Computes, executes, and reports out arbitrage trades.
    """

    # pylint: disable-next=arguments-differ,too-many-locals
    def compute_trades(self, prices):
        """
        Compute trades to arbitrage the pool, as follows:
            1. For each coin pair i and j, calculate size of coin i
               needed to move price of coin i w.r.t. to j to the
               target price.
            2. Calculate the profit from each such swap.
            3. Take the swap that gives the largest profit.

        Parameters
        ----------
        prices : pandas.Series
            Current market prices from the price_sampler.

        Returns
        -------
        trades : list of :class:`Trade` objects
            List of trades to perform.

        additional_data: dict
            Dict of additional data to be passed to the state log as part of trade_data.
        """
        pool = self.pool
        trades = get_arb_trades(pool, prices)

        max_profit = 0
        best_trade = None
        price_error = None
        for t in trades:
            amount_in, amount_out, coins, price_target = t
            i, j = coins

            with pool.use_snapshot_context():
                # assume we transacted at "infinite" depth at target price
                # on the other exchange to obtain our in-token
                profit = amount_out - amount_in * price_target
                if profit > max_profit:
                    max_profit = profit
                    best_trade = Trade(i, j, amount_in)
                    price_error = pool.price(i, j) - price_target

        if not best_trade:
            return [], {"price_errors": []}

        return [best_trade], {"price_errors": [price_error]}
