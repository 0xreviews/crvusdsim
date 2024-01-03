"""
Provides the base implementation for the 
`crypto_with_stable_price` oracles.

Each child class must implement its own price methods.

TODO - add Chainlink price limits.
"""
from typing import List
from abc import ABC, abstractmethod
from curvesim.pool.sim_interface import SimCurveCryptoPool
from .. import AggregateStablePrice
from ... import ControllerFactory
from ...stablecoin import StableCoin
from ...clac import exp
from ...utils import BlocktimestampMixins, ERC20
from ....sim_interface import SimCurveStableSwapPool

PRECISION = 10**18


class Oracle(ABC, BlocktimestampMixins):
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

    @abstractmethod
    def _raw_price(self, *args, **kwargs) -> int:
        """
        Return the oracle price.
        Implemented by the child class.
        """

    @abstractmethod
    def raw_price(self, *args, **kwargs) -> int:
        """
        Public method for getting the oracle price.
        Implemented by the child class.
        """

    def price(self, *args, **kwargs) -> int:
        """
        Wrapper for compatibility with vyper implementation.
        """
        return self.raw_price(*args, **kwargs)

    @abstractmethod
    def price_w(self, *args, **kwargs) -> int:
        """
        Return the oracle price and modify state attributes
        (like internal timestamp) if appropriate for child class.
        """

    def set_use_chainlink(self, do_it: bool) -> None:
        """Whether to truncate using Chainlink prices."""
        self.use_chainlink = do_it
