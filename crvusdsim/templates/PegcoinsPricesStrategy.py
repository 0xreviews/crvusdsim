from abc import ABC, abstractmethod
from crvusdsim.iterators.price_samplers.price_volume import PriceVolume
from crvusdsim.pool import SimMarketInstance


class PegcoinsPricesStrategy(ABC):
    def __init__(self, sim_market: SimMarketInstance, price_sampler: PriceVolume):
        self.sim_market = sim_market
        self.pegcoins_assets = [
            stable_pool.assets for stable_pool in sim_market.stableswap_pools
        ]
        self.price_sampler = price_sampler

    @abstractmethod
    def do_strategy(self):
        """
        Process the bands strategy to get liquidity.
        """
        raise NotImplementedError
