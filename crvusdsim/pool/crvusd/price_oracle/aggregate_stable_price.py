"""
AggregatorStablePrice - aggregator of stablecoin prices for crvUSD
"""

from collections import defaultdict
from typing import List

from crvusdsim.pool.crvusd.stableswap import CurveStableSwapPool

from ..utils import BlocktimestampMixins
from ..vyper_func import (
    shift,
    unsafe_add,
    unsafe_div,
    unsafe_mul,
    unsafe_sub,
)

MAX_PAIRS = 20
MIN_LIQUIDITY = 100_000 * 10**18  # Only take into account pools with enough liquidity
TVL_MA_TIME = 50000  # s


class PricePair:
    def __init__(self):
        self.pool = CurveStableSwapPool
        self.is_inverse = False


class AggregateStablePrice(BlocktimestampMixins):
    __all__ = [
        "STABLECOIN",
        "SIGMA",
        "price_pairs",
        "n_price_pairs",
        "last_timestamp",
        "last_tvl",
        "last_price",
        "admin",
    ]

    def __init__(self, stablecoin: any, sigma: int, admin: str = "aggregator_admin"):
        super().__init__()

        self.STABLECOIN = stablecoin
        # The change is so rare that we can change the whole thing altogether
        self.SIGMA = sigma
        self.admin = admin
        self.last_price = 10**18
        self.last_timestamp = self._block_timestamp

        self.price_pairs = defaultdict(PricePair)
        self.n_price_pairs = 0
        self.last_tvl = defaultdict(int)

    def set_admin(self, _admin: str):
        # We are not doing commit / apply because the owner will be a voting DAO anyway
        # which has vote delays
        # assert msg.sender == self.admin
        self.admin = _admin

    def sigma(self) -> int:
        return self.SIGMA

    def stablecoin(self) -> str:
        return self.STABLECOIN.address

    def add_price_pair(self, _pool: CurveStableSwapPool):
        # assert msg.sender == self.admin
        price_pair: PricePair = PricePair()
        price_pair.pool = _pool
        coins: List[str] = [_pool.coins[0], _pool.coins[1]]
        if coins[0] == self.STABLECOIN:
            price_pair.is_inverse = True
        else:
            assert coins[1] == self.STABLECOIN
        n: int = self.n_price_pairs
        self.price_pairs[n] = price_pair  # Should revert if too many pairs
        self.last_tvl[n] = _pool.totalSupply
        self.n_price_pairs = n + 1

    def remove_price_pair(self, n: int):
        # assert msg.sender == self.admin
        n_max: int = self.n_price_pairs - 1
        assert n <= n_max, "remove_price_pair error n %d n_max %d" % (n, n_max)

        if n < n_max:
            self.price_pairs[n] = self.price_pairs[n_max]

        self.price_pairs.pop(n_max)
        self.n_price_pairs = n_max

    def exp(self, power: int) -> int:
        if power <= -42139678854452767551:
            return 0

        if power >= 135305999368893231589:
            raise "exp overflow"

        x: int = unsafe_div(unsafe_mul(power, 2**96), 10**18)

        k: int = unsafe_div(
            unsafe_add(
                unsafe_div(unsafe_mul(x, 2**96), 54916777467707473351141471128),
                2**95,
            ),
            2**96,
        )
        x = unsafe_sub(x, unsafe_mul(k, 54916777467707473351141471128))

        y: int = unsafe_add(x, 1346386616545796478920950773328)
        y = unsafe_add(
            unsafe_div(unsafe_mul(y, x), 2**96), 57155421227552351082224309758442
        )
        p: int = unsafe_sub(unsafe_add(y, x), 94201549194550492254356042504812)
        p = unsafe_add(
            unsafe_div(unsafe_mul(p, y), 2**96), 28719021644029726153956944680412240
        )
        p = unsafe_add(unsafe_mul(p, x), (4385272521454847904659076985693276 * 2**96))

        q: int = x - 2855989394907223263936484059900
        q = unsafe_add(
            unsafe_div(unsafe_mul(q, x), 2**96), 50020603652535783019961831881945
        )
        q = unsafe_sub(
            unsafe_div(unsafe_mul(q, x), 2**96), 533845033583426703283633433725380
        )
        q = unsafe_add(
            unsafe_div(unsafe_mul(q, x), 2**96), 3604857256930695427073651918091429
        )
        q = unsafe_sub(
            unsafe_div(unsafe_mul(q, x), 2**96), 14423608567350463180887372962807573
        )
        q = unsafe_add(
            unsafe_div(unsafe_mul(q, x), 2**96), 26449188498355588339934803723976023
        )

        return shift(
            unsafe_mul(
                unsafe_div(p, q), 3822833074963236453042738258902158003155416615667
            ),
            unsafe_sub(k, 195),
        )

    def _ema_tvl(self) -> List[int]:
        tvls: List[int] = []
        last_timestamp: int = self.last_timestamp
        alpha: int = 10**18
        if last_timestamp < self._block_timestamp:
            alpha = self.exp(
                -1 * int(self._block_timestamp - last_timestamp) * 10**18 // TVL_MA_TIME
            )
        n_price_pairs: int = self.n_price_pairs

        for i in range(MAX_PAIRS):
            if i == n_price_pairs:
                break
            tvl: int = self.last_tvl[i]
            if alpha != 10**18:
                # alpha = 1.0 when dt = 0
                # alpha = 0.0 when dt = inf
                new_tvl: int = self.price_pairs[
                    i
                ].pool.totalSupply  # We don't do virtual price here to save on gas
                tvl = (new_tvl * (10**18 - alpha) + tvl * alpha) // 10**18
            tvls.append(tvl)

        return tvls

    def ema_tvl(self) -> List[int]:
        return self._ema_tvl()

    def _price(self, tvls: List[int]) -> int:
        n: int = self.n_price_pairs
        prices: List[int] = [0] * MAX_PAIRS
        D: List[int] = [0] * MAX_PAIRS
        Dsum: int = 0
        DPsum: int = 0
        for i in range(MAX_PAIRS):
            if i == n:
                break
            price_pair: PricePair = self.price_pairs[i]
            pool_supply: int = tvls[i]
            if pool_supply >= MIN_LIQUIDITY:
                p: int = price_pair.pool.price_oracle()
                if price_pair.is_inverse:
                    p = 10**36 // p
                prices[i] = p
                D[i] = pool_supply
                Dsum += pool_supply
                DPsum += pool_supply * p
        if Dsum == 0:
            return 10**18  # Placeholder for no active pools
        p_avg: int = DPsum // Dsum
        e: List[int] = [0] * MAX_PAIRS
        e_min: int = 2**256 - 1
        for i in range(MAX_PAIRS):
            if i == n:
                break
            p: int = prices[i]
            e[i] = int(max(p, p_avg) - min(p, p_avg)) ** 2 // (self.SIGMA**2 // 10**18)
            e_min = min(e[i], e_min)
        wp_sum: int = 0
        w_sum: int = 0
        for i in range(MAX_PAIRS):
            if i == n:
                break
            w: int = D[i] * self.exp(-(e[i] - e_min)) // 10**18
            w_sum += w
            wp_sum += w * prices[i]
        return wp_sum // w_sum

    def price(self) -> int:
        return self._price(self._ema_tvl())

    def price_w(self) -> int:
        if self.last_timestamp == self._block_timestamp:
            return self.last_price
        else:
            ema_tvl: List[int] = self._ema_tvl()
            self.last_timestamp = self._block_timestamp
            for i in range(MAX_PAIRS):
                if i == len(ema_tvl):
                    break
                self.last_tvl[i] = ema_tvl[i]
            p: int = self._price(ema_tvl)
            self.last_price = p
            return p
