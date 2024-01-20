"""
Provides the base implementation for the 
`crypto_with_stable_price` oracles.

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
    Simple object for tracking simulated prices.

    Serves as the Staking/Chainlink Oracle.
    """

    def __init__(self, price: int = 1e18, decimals: int = 18) -> None:
        self.price = price
        self.decimals = decimals

    def update(self, new: int) -> None:
        """Update the price."""
        self.price = int(new)


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
        chainlink_aggregator: StakedOracle | None = None,
        bound_size: int | None = None,
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
        self.frozen = False  # SIM INTERFACE

        self.use_chainlink = True if chainlink_aggregator else False
        self.chainlink_aggregator = chainlink_aggregator
        self.chainlink_price_precision = (
            int(10**chainlink_aggregator.decimals) if chainlink_aggregator else None
        )
        self.bound_size = bound_size

    @property
    def _price_last(self):
        """
        For compatibility.
        """
        return self.price()

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

        if self.use_chainlink:
            chainlink_lrd = self.chainlink_aggregator.price
            chainlink_p = chainlink_lrd * 10**18 // self.chainlink_price_precision
            lower = chainlink_p * (10**18 - self.bound_size) // 10**18
            upper = chainlink_p * (10**18 + self.bound_size) // 10**18
            crv_p = int(min(max(crv_p, lower), upper))

        self.last_price = crv_p

        return crv_p

    def raw_price(self) -> int:
        """
        Public method for getting the oracle price.
        Implemented by the child class.
        """
        if self.frozen:
            return self.last_price
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
        if self.frozen:
            return self.last_price
        tvls = self._ema_tvl()
        if self.last_timestamp < self._block_timestamp:
            self.last_timestamp = self._block_timestamp
            self.last_tvl = tvls
        return self._raw_price(
            tvls, self.stable_aggregator.price()
        )  # NOTE the Vyper implementation uses `price_w`

    def set_use_chainlink(self, do_it: bool) -> None:
        """Whether to truncate using Chainlink prices."""
        self.use_chainlink = do_it

    # SIM INTERFACE

    def freeze(self):
        """
        Freeze the oracle price.

        A user may `freeze()` or `unfreeze()` the oracle to prevent
        price changes. This is useful if the user wants to keep the oracle
        price constant through a series of trades. It is also useful as
        a form of caching.

        If `frozen` is false, the
        oracle will behave exaclty like the Vyper implementation.
        """
        self.frozen = True

    def unfreeze(self):
        """Unfreeze the oracle price."""
        self.frozen = False

    def set_chainlink_price(self, price: int) -> None:
        """Update the Chainlink price."""
        self.chainlink_aggregator.update(price)

    def set_chainlink(self, price: int, decimals: int, bound_size: int) -> None:
        """Configure a chainlink aggregator."""
        self.chainlink_aggregator = StakedOracle(price, decimals)
        self.chainlink_price_precision = int(10**decimals)
        self.bound_size = bound_size
        self.use_chainlink = True
