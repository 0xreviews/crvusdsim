from crvusdsim.iterators import price_samplers
from crvusdsim.iterators.price_samplers.price_volume import PriceVolume
from crvusdsim.pool import SimMarketInstance
from crvusdsim.templates.PegcoinsPricesStrategy import PegcoinsPricesStrategy
from pandas import DataFrame


class SimpleRisePegcoinsPricesStrategy(PegcoinsPricesStrategy):
    def __init__(
        self,
        sim_market: SimMarketInstance,
        price_sampler: PriceVolume,
        top_price=1.00,
        bottom_price=0.95,
    ):
        super().__init__(sim_market, price_sampler)
        self.top_price = top_price
        self.bottom_price = bottom_price

    def do_strategy(self):
        count = self.price_sampler.prices.shape[0]
        delta_p = (self.top_price - self.bottom_price) / (count // 2)

        _p = self.top_price
        _prices = []
        for i in range(count // 2):
            _prices.append(_p)
            _p -= delta_p
        for i in range(count // 2 + count % 2):
            _prices.append(_p)
            _p += delta_p

        _prices = DataFrame(_prices, index=self.price_sampler.prices.index, columns=["price"])

        peg_prices = {}
        peg_volumes = {}
        for pegcoin_asset in self.pegcoins_assets:
            _symbols = (pegcoin_asset.symbols[0], "crvUSD")
            peg_prices[_symbols] = _prices
            peg_volumes[_symbols] = None

        self.price_sampler.load_pegcoins_prices(prices=peg_prices)
