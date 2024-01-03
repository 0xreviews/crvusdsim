"""Provides the TBTC price oracle."""
from typing import List
from curvesim.pool.sim_interface import SimCurveCryptoPool
from .base import Oracle
from ..aggregate_stable_price import AggregateStablePrice
from ... import ControllerFactory
from ...utils import BlocktimestampMixins
from ...stablecoin import StableCoin

PRECISION = 10**18


class OracleTBTC(Oracle):
    def __init__(
        self,
        tricrypto: List[SimCurveCryptoPool],
        ix: List[int],  # 0 = TBTC
        stable_aggregator: AggregateStablePrice,
        factory: ControllerFactory,
        # chainlink_aggregator_eth: ChainlinkAggregator,
        # bound_size: int,  # 1.5% sounds ok before we turn it off
        n_pools=1,
        **kwargs,
    ) -> None:
        BlocktimestampMixins.__init__(self)
        # Turn into list for compatibility with parent class
        self.tricrypto = tricrypto
        self.tricrypto_ix = ix
        self.stable_aggregator = stable_aggregator
        self.factory = factory
        self._stablecoin: StableCoin = stable_aggregator.STABLECOIN
        self.n_pools = n_pools
        assert (
            tricrypto[0].coin_addresses[0].lower() == self._stablecoin.address.lower()
        ), (
            tricrypto[0].coin_addresses[0].lower(),
            self._stablecoin.address.lower(),
        )  # TriCryptoLLAMMA has crvUSD as first coin

        # self.use_chainlink = True
        # CHAINLINK_AGGREGATOR_BTC = chainlink_aggregator_btc
        # CHAINLINK_PRICE_PRECISION_BTC = 10**convert(chainlink_aggregator_btc.decimals(), uint256)
        # BOUND_SIZE = bound_size

    def _raw_price(self, agg_price: int, **kwargs) -> int:
        p_crypto_stable = self.tricrypto[0].price_oracle()[
            self.tricrypto_ix[0]
        ]  # d_crvusd/d_tbtc
        p_stable_agg = agg_price  # d_usd/d_crvusd
        price = p_crypto_stable * p_stable_agg // 10**18  # d_usd/d_btc

        # Limit BTC price
        # if self.use_chainlink:
        #     chainlink_lrd: ChainlinkAnswer = CHAINLINK_AGGREGATOR_BTC.latestRoundData()
        #     if block.timestamp - min(chainlink_lrd.updated_at, block.timestamp) <= CHAINLINK_STALE_THRESHOLD:
        #         chainlink_p = convert(chainlink_lrd.answer) * 10**18 / CHAINLINK_PRICE_PRECISION_BTC
        #         lower = chainlink_p * (10**18 - BOUND_SIZE) / 10**18
        #         upper = chainlink_p * (10**18 + BOUND_SIZE) / 10**18
        #         price = min(max(price, lower), upper)

        return int(price)

    def raw_price(self, **kwargs) -> int:
        return self._raw_price(self.stable_aggregator.price(), **kwargs)

    def price_w(self, **kwargs) -> int:
        return self._raw_price(self.stable_aggregator.price(), **kwargs)
