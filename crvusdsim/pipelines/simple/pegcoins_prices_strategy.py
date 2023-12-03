from typing import List
from crvusdsim.iterators import price_samplers
from crvusdsim.iterators.price_samplers.price_volume import PriceVolume
from crvusdsim.pool import SimMarketInstance
from crvusdsim.templates.PegcoinsPricesStrategy import PegcoinsPricesStrategy
from pandas import DataFrame
import numpy as np


class SimpleRisePegcoinsPricesStrategy(PegcoinsPricesStrategy):
    def __init__(
        self,
        sim_market: SimMarketInstance,
        price_sampler: PriceVolume,
        top_price=1.000,
        bottom_price=0.995,
    ):
        super().__init__(sim_market, price_sampler)
        self.top_price = top_price
        self.bottom_price = bottom_price

    def do_strategy(self):
        count = self.price_sampler.prices.shape[0]
        volatility = (self.top_price - self.bottom_price) / self.top_price / 100
        # generate random prices
        loop = 0
        prices = []
        while True:
            prices = random_prices(count, self.top_price, volatility)
            loop += 1
            if loop > 100:
                break
            if (
                abs(abs(max(prices) / self.top_price) - 1) < 1e-3
                and abs(abs(min(prices) / self.bottom_price) - 1) < 1e-3
            ):
                break
        prices = DataFrame(
            prices, index=self.price_sampler.prices.index, columns=["price"]
        )

        peg_prices = {}
        peg_volumes = {}
        for pegcoin_asset in self.pegcoins_assets:
            _symbols = (pegcoin_asset.symbols[0], "crvUSD")
            peg_prices[_symbols] = prices
            peg_volumes[_symbols] = None

        self.price_sampler.load_pegcoins_prices(prices=peg_prices)


def random_prices(steps, initial_price, volatility):
    prices = [initial_price]

    for _ in range(steps-1):
        # Generate a random number following a normal distribution
        # to represent price fluctuation
        price_change = np.random.normal(0, volatility)

        # Update the price
        new_price = prices[-1] * (1 + price_change)
        prices.append(new_price)

    return prices
