"""Provides the wstETH price oracle."""
from typing import List
from .base import Oracle

PRECISION = 10**18


class OracleWSTETH(Oracle):
    def _raw_price(
        self, tvls: List[int], agg_price: int, p_staked: int = 10**18, **kwargs
    ) -> int:
        """
        Get the price of the underlying asset from TriCrypto and StableSwap
        pools (e.g. ETH price).

        Convert this price to the staked asset price using the given p_staked
        (e.g. ETH -> wstETH).
        """
        weighted_price = 0
        weights = 0
        for i in range(self.n_pools):
            p_crypto_r = self.tricrypto[i].price_oracle()[
                self.tricrypto_ix[i]
            ]  # d_usdt/d_eth
            p_stable_r = self.stableswap[i].price_oracle()  # d_usdt/d_crvusd
            p_stable_agg = agg_price  # d_usd/d_crvusd
            if self._is_inverse[i]:
                p_stable_r = 10**36 // p_stable_r
            weight = tvls[i]
            weights += weight
            weighted_price += (
                p_crypto_r * p_stable_agg // p_stable_r * weight
            )  # d_usd/d_eth
        crv_p = weighted_price // weights

        # use_chainlink: bool = self.use_chainlink

        # # Limit ETH price
        # if use_chainlink:
        #     chainlink_lrd: ChainlinkAnswer = CHAINLINK_AGGREGATOR_ETH.latestRoundData()
        #     if block.timestamp - min(chainlink_lrd.updated_at, block.timestamp) <= CHAINLINK_STALE_THRESHOLD:
        #         chainlink_p = convert(chainlink_lrd.answer) * 10**18 / CHAINLINK_PRICE_PRECISION_ETH
        #         lower = chainlink_p * (10**18 - BOUND_SIZE) / 10**18
        #         upper = chainlink_p * (10**18 + BOUND_SIZE) / 10**18
        #         crv_p = min(max(crv_p, lower), upper)

        return int(p_staked * crv_p // 10**18)

    def raw_price(self, p_staked: int = 10**18, **kwargs) -> int:
        return self._raw_price(
            self._ema_tvl(), self.stable_aggregator.price(), p_staked, **kwargs
        )

    def price_w(self, p_staked: int = 10**18, **kwargs) -> int:
        tvls = self._ema_tvl()
        if self.last_timestamp < self._block_timestamp:
            self.last_timestamp = self._block_timestamp
            self.last_tvl = tvls
        return self._raw_price(
            tvls, self.stable_aggregator.price_w(), p_staked, **kwargs
        )
