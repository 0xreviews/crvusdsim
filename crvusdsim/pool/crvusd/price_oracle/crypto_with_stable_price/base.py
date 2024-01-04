"""
Provides the base implementation for the 
`crypto_with_stable_price` oracles.

Each child class must implement its own price methods.

TODO - add Chainlink price limits.
"""
from typing import List
from abc import ABC
from dataclasses import dataclass
from curvesim.pool.sim_interface import SimCurveCryptoPool
from .. import AggregateStablePrice
from ... import ControllerFactory
from ...stablecoin import StableCoin
from ...clac import exp
from ...utils import BlocktimestampMixins, ERC20
from ....sim_interface import SimCurveStableSwapPool

PRECISION = 10**18


@dataclass
class StakedOracle:
    """
    Simple interface for tracking conversions
    for staked derivatives.
    """

    price: int = 10**18

    def update(self, new: int) -> None:
        """Update the price."""
        self.price = new


class Oracle(ABC, BlocktimestampMixins):
    """
    Base Oracle implementation is equivalent
    to WBTC and WETH oracles. The sfrxETH and
    wstETH oracle add a staked oracle conversion.
    The TBTC oracle is a special case and overrides
    many methods.
    """

    def __init__(
        self,
        tricrypto: List[SimCurveCryptoPool],
        ix: List[int],  # 0 = WBTC, 1 = ETH
        stableswap: List[SimCurveStableSwapPool],
        stable_aggregator: AggregateStablePrice,
        factory: ControllerFactory,
        # chainlink_aggregator_eth: ChainlinkAggregator,
        # bound_size: int,  # 1.5% sounds ok before we turn it off
        n_pools=2,
        tvl_ma_time=50000,
        **kwargs,
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
            assert len(tricrypto[i].coin_addresses) == 3, tricrypto[i].coin_addresses
            assert (
                tricrypto[i].coin_addresses[0].lower()
                == self._redeemable[i].address.lower()
            )
            self.last_tvl.append(
                tricrypto[i].tokens * tricrypto[i].virtual_price // PRECISION
            )

        self.last_timestamp = self._block_timestamp

        # self.use_chainlink = False
        # CHAINLINK_AGGREGATOR_ETH = chainlink_aggregator_eth
        # CHAINLINK_PRICE_PRECISION_ETH = 10**convert(chainlink_aggregator_eth.decimals(), uint256)
        # BOUND_SIZE = bound_size

    def _ema_tvl(self) -> List[int]:
        """
        Get the EMA for the TVL of each TriCrypto pool.
        """
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
                tvl = tricrypto.tokens * tricrypto.virtual_price // PRECISION
                last_tvl[i] = (
                    tvl * (PRECISION - alpha) + last_tvl[i] * alpha
                ) // PRECISION

        return last_tvl

    def ema_tvl(self) -> List[int]:
        """Public wrapper for EMA TVL."""
        return self._ema_tvl()

    def _raw_price(self, *args, **kwargs) -> int:
        """
        Base raw price implementation. Child classes may override
        (tBTC) or extend (sfrxETH, wstETH) this method.
        """
        tvls = args[0]
        agg_price = args[1]

        weighted_price = 0
        weights = 0
        for i in range(self.n_pools):
            p_crypto_r = self.tricrypto[i].price_oracle()[
                self.tricrypto_ix[i]
            ]  # d_usdt/d_collat
            p_stable_r = self.stableswap[i].price_oracle()  # d_usdt/d_crvusd
            p_stable_agg = agg_price  # d_usd/d_crvusd
            if self._is_inverse[i]:
                p_stable_r = 10**36 // p_stable_r
            weight = tvls[i]
            weights += weight
            weighted_price += (
                p_crypto_r * p_stable_agg // p_stable_r * weight
            )  # d_usd/d_collat
        crv_p = weighted_price // weights

        return crv_p

    def raw_price(self) -> int:
        """
        Public method for getting the oracle price.
        Implemented by the child class.
        """
        return self._raw_price(self._ema_tvl(), self.stable_aggregator.price())

    def price(self) -> int:
        """
        Wrapper for compatibility with vyper implementation.
        """
        return self.raw_price()

    def price_w(self) -> int:
        """
        Return the oracle price and modify state attributes
        (like internal timestamp) if appropriate for child class.
        """
        tvls = self._ema_tvl()
        if self.last_timestamp < self._block_timestamp:
            self.last_timestamp = self._block_timestamp
            self.last_tvl = tvls
        return self._raw_price(tvls, self.stable_aggregator.price_w())

    def set_use_chainlink(self, do_it: bool) -> None:
        """Whether to truncate using Chainlink prices."""
        self.use_chainlink = do_it
