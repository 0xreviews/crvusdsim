from curvesim.metrics.base import Metric, PricingMixin
from crvusdsim.pool import SimMarketInstance


class MarketMetric(Metric):
    __slots__ = [
        "_pool",
        "_controller",
        "_collateral_token",
        "_stablecoin",
        "_aggregator",
        "_price_oracle",
        "_stableswap_pools",
        "_peg_keepers",
        "_policy",
        "_factory",
    ]

    def __init__(self, sim_market: SimMarketInstance, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pool = sim_market.pool
        self._controller = sim_market.controller
        self._collateral_token = sim_market.collateral_token
        self._stablecoin = sim_market.stablecoin
        self._aggregator = sim_market.aggregator
        self._price_oracle = sim_market.price_oracle
        self._stableswap_pools = sim_market.stableswap_pools
        self._peg_keepers = sim_market.peg_keepers
        self._policy = sim_market.policy
        self._factory = sim_market.factory


class PricingMarketMetric(PricingMixin, MarketMetric):
    """
    :class:`Metric` with :class:`PricingMixin` functionality.
    """

    def __init__(self, sim_market: SimMarketInstance, *args, **kwargs):
        """
        Parameters
        ----------
        coin_names : iterable of str
            Symbols for the coins used in a simulation. A numeraire is selected from
            the specified coins.

        """
        super().__init__(
            sim_market.pool.assets.symbols, sim_market=sim_market, *args, **kwargs
        )
