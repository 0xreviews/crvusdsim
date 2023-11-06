from crvusdsim.pool.crvusd.clac import exp
from crvusdsim.pool.crvusd.vyper_func import unsafe_div
from ..utils import BlocktimestampMixins

MA_TIME = 866  # 600 seconds / ln(2)


class PriceOracle(BlocktimestampMixins):
    def __init__(self, p: int):
        super().__init__()
        self._price_last = p
        self._price_oracle = p
        self.last_prices_timestamp = self._block_timestamp

    def set_price(self, p: int):
        self._price_last = p

    def price_w(self):
        _price_oracle = self._price()
        self._price_oracle = _price_oracle
        self.last_prices_timestamp = self._block_timestamp
        return _price_oracle

    def price(self):
        return self._price()

    def _price(self):
        _price_oracle = self._price_oracle
        if self._block_timestamp > self.last_prices_timestamp:
            alpha = exp(
                -1
                * unsafe_div(
                    (self._block_timestamp - self.last_prices_timestamp) * 10**18,
                    MA_TIME,
                )
            )
            _price_oracle = unsafe_div(
                self._price_last * (10**18 - alpha) + alpha * self._price_oracle,
                10**18,
            )
        return _price_oracle
