"""Provides the WETH price oracle."""
from typing import List
from .base import Oracle

PRECISION = 10**18


class OracleWETH(Oracle):
    def _raw_price(self, tvls: List[int], agg_price: int, **kwargs) -> int:
        weighted_price = 0
        weights = 0
        for i in range(self.n_pools):
            p_crypto_r = self.tricrypto[i].price_oracle()[
                self.tricrypto_ix[i]
            ]  # d_usdt/d_eth
            p_stable_r = self.stableswap[i].price_oracle()  # d_usdt/d_st
            p_stable_agg = agg_price  # d_usd/d_st
            if self._is_inverse[i]:
                p_stable_r = 10**36 // p_stable_r
            weight = tvls[i]
            # Prices are already EMA but weights - not so much
            weights += weight
            weighted_price += (
                p_crypto_r * p_stable_agg // p_stable_r * weight
            )  # d_usd/d_eth
        crv_p = weighted_price // weights

        # Limit WETH price
        # if self.use_chainlink:
        #     chainlink_lrd: ChainlinkAnswer = CHAINLINK_AGGREGATOR_ETH.latestRoundData()
        #     if block.timestamp - min(chainlink_lrd.updated_at, block.timestamp) <= CHAINLINK_STALE_THRESHOLD:
        #         chainlink_p = convert(chainlink_lrd.answer, uint256) * PRECISION / CHAINLINK_PRICE_PRECISION_ETH
        #         lower = chainlink_p * (PRECISION - BOUND_SIZE) / PRECISION
        #         upper = chainlink_p * (PRECISION + BOUND_SIZE) / PRECISION
        #         crv_p = min(max(crv_p, lower), upper)

        return int(crv_p)

    def raw_price(self, **kwargs) -> int:
        return self._raw_price(
            self._ema_tvl(), self.stable_aggregator.price(), **kwargs
        )

    def price_w(self, **kwargs) -> int:
        tvls = self._ema_tvl()
        if self.last_timestamp < self._block_timestamp:
            self.last_timestamp = self._block_timestamp
            self.last_tvl = tvls
        return self._raw_price(tvls, self.stable_aggregator.price_w(), **kwargs)
