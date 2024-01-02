"""
Provides a price oracle class that uses Tricrypto-ng
and StableSwap pools to calculate collateral prices.

TODO - add Chainlink price limits.
"""
from typing import List
from curvesim.pool.sim_interface import SimCurveCryptoPool
from . import AggregateStablePrice
from .. import ControllerFactory
from ..stablecoin import StableCoin
from ..clac import exp
from ..utils import BlocktimestampMixins, ERC20
from ...sim_interface import SimCurveStableSwapPool

PRECISION = 10**18


class CryptoWithStablePrice(BlocktimestampMixins):
    def __init__(
        self,
        tricrypto: List[SimCurveCryptoPool],
        ix: List[int],  # 1 = ETH
        stableswap: List[SimCurveStableSwapPool],
        stable_aggregator: AggregateStablePrice,
        factory: ControllerFactory,
        # chainlink_aggregator_eth: ChainlinkAggregator,
        # bound_size: int,  # 1.5% sounds ok before we turn it off
        n_pools=2,
        tvl_ma_time=50000,
    ) -> None:
        super().__init__()
        self.tricrypto = tricrypto
        self.tricrypto_ix = ix
        self.stableswap = stableswap
        self.stable_aggregator = stable_aggregator
        self.factory = factory
        self._stablecoin: StableCoin = stable_aggregator.STABLECOIN
        self.n_pools = n_pools
        self.tvl_ma_time = tvl_ma_time

        self._redeemable: List[ERC20] = []  # redeemable stablecoin addrs (e.g. USDC)
        self._is_inverse: List[bool] = []
        self.last_tvl: List[int] = []
        for i in range(n_pools):
            coins = stableswap[i].coins
            if coins[0] is self._stablecoin:
                self._redeemable.append(coins[1])
                self._is_inverse.append(True)
            else:
                self._redeemable.append(coins[0])
                self._is_inverse.append(False)
                assert coins[1] is self._stablecoin
            assert tricrypto[i].coin_addresses[0] == self._redeemable[i].address
            self.last_tvl[i] = (
                tricrypto[i].tokens * tricrypto[i].virtual_price // PRECISION
            )

        self.last_timestamp = self._block_timestamp
        # self.use_chainlink = False
        # CHAINLINK_AGGREGATOR_ETH = chainlink_aggregator_eth
        # CHAINLINK_PRICE_PRECISION_ETH = 10**convert(chainlink_aggregator_eth.decimals(), uint256)
        # BOUND_SIZE = bound_size

    def _ema_tvl(self) -> List[int]:
        last_timestamp = self.last_timestamp
        last_tvl = self.last_tvl

        if last_timestamp < self._block_timestamp:
            alpha = exp(
                -1
                * int(self._block_timestamp - last_timestamp)
                * PRECISION
                // self.tvl_ma_time
            )
            # alpha = 1.0 when dt = 0
            # alpha = 0.0 when dt = inf
            for i in range(self.n_pools):
                tricrypto = self.tricrypto[i]
                tvl = tricrypto.tokens * tricrypto.virtual_price() // PRECISION
                last_tvl[i] = (
                    tvl * (PRECISION - alpha) + last_tvl[i] * alpha
                ) // PRECISION

        return last_tvl

    def ema_tvl(self) -> List[int]:
        return self._ema_tvl()

    def _raw_price(self, tvls: List[int], agg_price: int) -> int:
        weighted_price = 0
        weights = 0
        for i in range(self.n_pools):
            p_crypto_r = self.tricrypto[i].price_oracle(
                self.tricrypto_ix[i]
            )  # d_usdt/d_eth
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

        # Limit BTC price
        # if self.use_chainlink:
        #     chainlink_lrd: ChainlinkAnswer = CHAINLINK_AGGREGATOR_ETH.latestRoundData()
        #     if block.timestamp - min(chainlink_lrd.updated_at, block.timestamp) <= CHAINLINK_STALE_THRESHOLD:
        #         chainlink_p = convert(chainlink_lrd.answer, uint256) * PRECISION / CHAINLINK_PRICE_PRECISION_ETH
        #         lower = chainlink_p * (PRECISION - BOUND_SIZE) / PRECISION
        #         upper = chainlink_p * (PRECISION + BOUND_SIZE) / PRECISION
        #         crv_p = min(max(crv_p, lower), upper)

        return crv_p

    def raw_price(self) -> int:
        return self._raw_price(self._ema_tvl(), self.stable_aggregator.price())

    def price(self) -> int:
        return self._raw_price(self._ema_tvl(), self.stable_aggregator.price())

    def price_w(self) -> int:
        tvls = self._ema_tvl()
        if self.last_timestamp < self._block_timestamp:
            self.last_timestamp = self._block_timestamp
            self.last_tvl = tvls
        return self._raw_price(tvls, self.stable_aggregator.price_w())

    def set_use_chainlink(self, do_it: bool) -> None:
        self.use_chainlink = do_it
