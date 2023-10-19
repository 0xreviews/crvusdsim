"""
Mainly a module to house the `Curve Stablecoin`, a LLAMMA implementation in Python.
"""
from collections import defaultdict
import time
from math import isqrt, prod
from typing import List, Tuple

from curvesim.exceptions import CalculationError, CryptoPoolError
from curvesim.logging import get_logger
from curvesim.pool.base import Pool
from crvusdsim.pool.crvusd.conf import ARBITRAGUR_ADDRESS
from crvusdsim.pool.crvusd.utils.ERC20 import ERC20

from crvusdsim.pool.crvusd.stablecoin import StableCoin

from .clac import exp, ln_int
from .vyper_func import (
    pow_mod256,
    shift,
    unsafe_add,
    unsafe_div,
    unsafe_mul,
    unsafe_sub,
)
from .utils import BlocktimestampMixins, _get_unix_timestamp
from ..snapshot import LLAMMASnapshot


logger = get_logger(__name__)

MAX_TICKS = 50
MAX_TICKS_UINT = 50
MAX_SKIP_TICKS = 1024
PREV_P_O_DELAY = 2 * 60  # s = 2 min
MAX_P_O_CHG = 12500 * 10**14  # <= 2**(1/3) - max relative change to have fee < 50%
BORROWED_PRECISION = 1
DEAD_SHARES = 1000


class DetailedTrade:
    def __init__(self):
        self.in_amount: int = 0
        self.out_amount: int = 0
        self.n1: int = 0
        self.n2: int = 0
        self.ticks_in: List[int] = []
        self.last_tick_j: int = 0
        self.admin_fee: int = 0
        # SIM_INTERFACE: fees
        self.fees: List[int] = []


class LLAMMAPool(
    Pool, BlocktimestampMixins
):  # pylint: disable=too-many-instance-attributes
    """LLAMMA implementation in Python."""

    snapshot_class = LLAMMASnapshot

    __slots__ = (
        "address",
        "A",
        "Aminus1",
        "A2",  # A^2
        "Aminus12",  # (A-1)^2
        "SQRT_BAND_RATIO",  # sqrt(A / (A - 1))
        "LOG_A_RATIO",  # ln(A / (A - 1))
        "MAX_ORACLE_DN_POW",  # (A / (A - 1)) ** 50
        "fee",
        "admin_fee",
        "rate",
        "rate_time",
        "rate_mul",
        "active_band",
        "min_band",
        "max_band",
        "admin_fees_x",
        "admin_fees_y",
        "price_oracle_contract",
        "old_p_o",
        "old_dfee",
        "prev_p_o_time",
        "bands_x",
        "bands_y",
        "total_shares",
        "user_shares",
        "liquidity_mining_callback",  # LMGauge
        "BORROWED_TOKEN",
        "COLLATERAL_TOKEN",
        "COLLATERAL_PRECISION",
        "BASE_PRICE",
        "admin",  # admin address
        # SIM_INTERFACE
        "bands_fees_x",
        "bands_fees_y",
        "benchmark_slippage_rate",
        "bands_x_benchmark",  # bands x benchmark to calc loss
        "bands_y_benchmark",  # bands y benchmark to calc loss
        "bands_delta_snapshot",
    )

    def __init__(  # pylint: disable=too-many-locals,too-many-arguments
        self,
        A: int,
        fee: int,
        admin_fee: int,
        BASE_PRICE: int,
        active_band: int = None,
        min_band: int = None,
        max_band: int = None,
        rate: int = None,
        rate_mul: int = None,
        collateral=None,
        price_oracle_contract=None,
        liquidity_mining_callback=None,
        bands_x=None,
        bands_y=None,
        admin=None,
        address: str = None,
        borrowed_token: StableCoin = None,
        benchmark_slippage_rate: int = 0,
    ):
        """
        Parameters
        ----------
        A : int
        @todo
        """
        super().__init__()

        self.address = (
            address if address is not None else "LLAMMA_%s" % (collateral.symbol)
        )
        self.BORROWED_TOKEN = (
            borrowed_token if borrowed_token is not None else StableCoin()
        )

        self.COLLATERAL_TOKEN: ERC20 = collateral
        self.COLLATERAL_PRECISION: int = 10 ** (18 - collateral.decimals)

        self.A = A
        self.Aminus1 = A - 1
        self.A2 = A**2
        self.Aminus12 = (A - 1) ** 2

        A_ratio = 10**18 * A // (A - 1)
        self.SQRT_BAND_RATIO = isqrt(A_ratio * 10**18)
        self.LOG_A_RATIO = ln_int(A_ratio)
        # (A / (A - 1)) ** 50
        self.MAX_ORACLE_DN_POW = (
            int(A**25 * 10**18 // (self.Aminus1**25)) ** 2 // 10**18
        )

        self.fee = fee
        self.admin_fee = admin_fee
        self.BASE_PRICE = BASE_PRICE

        self.price_oracle_contract = price_oracle_contract
        self.old_p_o = price_oracle_contract.price()
        self.prev_p_o_time = self._block_timestamp

        self.old_dfee = 0
        self.admin_fees_x = 0
        self.admin_fees_y = 0

        self.rate = 0 if rate is None else rate
        self.rate_time = self._block_timestamp
        self.rate_mul = 10**18 if rate_mul is None else rate_mul

        self.active_band = 0 if active_band is None else active_band
        self.min_band = 0 if min_band is None else min_band
        self.max_band = 0 if max_band is None else max_band
        self.admin_fees_x = 0
        self.admin_fees_y = 0

        if bands_x is None:
            self.bands_x = defaultdict(int)
        else:
            self.bands_x = bands_x
        if bands_y is None:
            self.bands_y = defaultdict(int)
        else:
            self.bands_y = bands_y

        self.total_shares = defaultdict(int)
        self.user_shares = defaultdict(_default_user_shares)

        self.liquidity_mining_callback = liquidity_mining_callback

        # _mint for amm pool
        if sum(self.bands_x.values()) > 0:
            self.BORROWED_TOKEN._mint(self.address, sum(self.bands_x.values()))
        if sum(self.bands_y.values()) > 0:
            self.COLLATERAL_TOKEN._mint(self.address, sum(self.bands_y.values()))

        # SIM_INTERFACE: fees
        self.bands_fees_x = defaultdict(int)
        self.bands_fees_y = defaultdict(int)

        # SIM_INTERFACE: loss
        self.benchmark_slippage_rate = benchmark_slippage_rate
        self.bands_x_benchmark = defaultdict(int)
        self.bands_y_benchmark = defaultdict(int)

        self.bands_delta_snapshot = {}

    def limit_p_o(self, p: int) -> List[int]:
        """
        Limits oracle price to avoid losses at abrupt changes, as well as calculates a dynamic fee.
        If we consider oracle_change such as:
            ratio = p_new / p_old
        (let's take for simplicity p_new < p_old, otherwise we compute p_old / p_new)
        Then if the minimal AMM fee will be:
            fee = (1 - ratio**3),
        AMM will not have a loss associated with the price change.
        However, over time fee should still go down (over PREV_P_O_DELAY), and also ratio should be limited
        because we don't want the fee to become too large (say, 50%) which is achieved by limiting the instantaneous
        change in oracle price.

        Parameters
        ----------
        p : int
            price of price_oracle_contract

        Returns
        -------
        List[int]
            [limited_price_oracle, dynamic_fee]
        """
        p_new: int = p
        dt: int = unsafe_sub(
            PREV_P_O_DELAY,
            min(PREV_P_O_DELAY, self._block_timestamp - self.prev_p_o_time),
        )
        ratio: int = 0

        # ratio = 1 - (p_o_min / p_o_max)**3

        if dt > 0:
            old_p_o: int = self.old_p_o
            old_ratio: int = self.old_dfee
            # ratio = p_o_min / p_o_max
            if p > old_p_o:
                ratio = unsafe_div(old_p_o * 10**18, p)
                if ratio < 10**36 // MAX_P_O_CHG:
                    p_new = unsafe_div(old_p_o * MAX_P_O_CHG, 10**18)
                    ratio = 10**36 // MAX_P_O_CHG
            else:
                ratio = unsafe_div(p * 10**18, old_p_o)
                if ratio < 10**36 // MAX_P_O_CHG:
                    p_new = unsafe_div(old_p_o * 10**18, MAX_P_O_CHG)
                    ratio = 10**36 // MAX_P_O_CHG

            # ratio is guaranteed to be less than 1e18
            # Also guaranteed to be limited, therefore can have all ops unsafe
            ratio = unsafe_div(
                unsafe_mul(
                    unsafe_sub(
                        unsafe_add(10**18, old_ratio),
                        unsafe_div(pow_mod256(ratio, 3), 10**36),
                    ),  # (f' + (1 - r**3))
                    dt,
                ),  # * dt / T
                PREV_P_O_DELAY,
            )

        return [p_new, ratio]

    def _price_oracle_ro(self) -> List[int]:
        return self.limit_p_o(self.price_oracle_contract.price())

    def _price_oracle_w(self) -> List[int]:
        p = self.limit_p_o(self.price_oracle_contract.price_w())
        self.prev_p_o_time = self._block_timestamp
        self.old_p_o = p[0]
        self.old_dfee = p[1]
        return p

    def price_oracle(self) -> int:
        """
        @notice Value returned by the external price oracle contract
        """
        return self._price_oracle_ro()[0]

    def dynamic_fee(self) -> int:
        """
        @notice Dynamic fee which accounts for price_oracle shifts
        """
        return max(self.fee, self._price_oracle_ro()[1])

    def _rate_mul(self) -> int:
        """
        @notice Rate multiplier which is 1.0 + integral(rate, dt)
        @return Rate multiplier in units where 1.0 == 1e18
        """
        return unsafe_div(
            self.rate_mul
            * (10**18 + self.rate * (self._block_timestamp - self.rate_time)),
            10**18,
        )

    def get_rate_mul(self) -> int:
        """
        Rate multiplier which is 1.0 + integral(rate, dt)

        Returns
        -------
        int
            Rate multiplier in units where 1.0 == 1e18
        """
        return self._rate_mul()

    def _base_price(self) -> int:
        """
        Price which corresponds to band 0.
        Base price grows with time to account for interest rate (which is 0 by default)
        """
        return self.BASE_PRICE * self._rate_mul() // 10**18

    def get_base_price(self) -> int:
        """
        Price which corresponds to band 0.
        Base price grows with time to account for interest rate (which is 0 by default)

        Returns
        -------
        int
            Base price (Adjusted by rate_mul)
        """
        return self._base_price()

    def _p_oracle_up(self, n: int) -> int:
        """
        Upper oracle price for the band to have liquidity when p = p_oracle

        Parameters
        ----------
        n : int
            Band number (can be negative)

        Returns
        -------
        int
            Price at 1e18 base
        """
        # p_oracle_up(n) = p_base * ((A - 1) / A) ** n
        # p_oracle_down(n) = p_base * ((A - 1) / A) ** (n + 1) = p_oracle_up(n+1)

        # Because the A is a variable, so we don't use vyper optimization algorithm.
        return int(self._base_price() * (self.Aminus1 / self.A) ** n)


    def _p_current_band(self, n: int) -> int:
        """
        Lowest possible price of the band at current oracle price

        Parameters
        ----------
        n : int
            Band number (can be negative)

        Returns
        -------
        Price at 1e18 base
        """
        # k = (self.A - 1) / self.A  # equal to (p_down / p_up)
        # p_base = self.p_base * k ** n = p_oracle_up(n)
        p_base: int = self._p_oracle_up(n)

        # return self.p_oracle**3 / p_base**2
        p_oracle: int = self._price_oracle_ro()[0]
        return p_oracle**2 // p_base * p_oracle // p_base

    def p_current_up(self, n: int) -> int:
        """
        Highest possible price of the band at current oracle price

        Parameters
        ----------
        n : int
            Band number (can be negative)

        Returns
        -------
        int
            Price at 1e18 base
        """
        return self._p_current_band(n + 1)

    def p_current_down(self, n: int) -> int:
        """
        Lowest possible price of the band at current oracle price

        Parameters
        ----------
        n : int
            Band number (can be negative)

        Returns
        -------
        int
            Price at 1e18 base
        """
        return self._p_current_band(n)

    def p_oracle_up(self, n: int) -> int:
        """
        Highest oracle price for the band to have liquidity when p = p_oracle

        Parameters
        ----------
        n : int
            Band number (can be negative)

        Returns
        -------
        Price at 1e18 base
        """
        return self._p_oracle_up(n)

    def p_oracle_down(self, n: int) -> int:
        """
        Lowest oracle price for the band to have liquidity when p = p_oracle

        Parameters
        ----------
        n : int
            Band number (can be negative)

        Returns
        -------
        int
            Price at 1e18 base
        """
        return self._p_oracle_up(n + 1)

    def _get_y0(self, x: int, y: int, p_o: int, p_o_up: int) -> int:
        """
        Calculate y0 for the invariant based on current liquidity in band.
        The value of y0 has a meaning of amount of collateral when band has no stablecoin
        but current price is equal to both oracle price and upper band price.

        Parameters
        ----------
        x : int
            Amount of stablecoin in band
        y : int
            Amount of collateral in band
        p_o : int
            External oracle price
        p_o_up : int
            Upper boundary of the band

        Returns
        -------
        y0 : int
        """
        assert p_o != 0
        # solve:
        # p_o * A * y0**2 - y0 * (p_oracle_up/p_o * (A-1) * x + p_o**2/p_oracle_up * A * y) - xy = 0
        b: int = 0
        # p_o_up * unsafe_sub(A, 1) * x / p_o + A * p_o**2 / p_o_up * y / 10**18
        if x != 0:
            b = unsafe_div(p_o_up * self.Aminus1 * x, p_o)
        if y != 0:
            b += unsafe_div(self.A * p_o**2 // p_o_up * y, 10**18)
        if x > 0 and y > 0:
            D: int = b**2 + unsafe_div(((4 * self.A) * p_o) * y, 10**18) * x
            return unsafe_div(int((b + isqrt(D)) * 10**18), unsafe_mul(2 * self.A, p_o))
        else:
            return unsafe_div(b * 10**18, unsafe_mul(self.A, p_o))

    def _get_p(self, n: int, x: int, y: int) -> int:
        """
        Get current AMM price in band

        Parameters
        ----------
        n : int
            Band number
        x : int
            Amount of stablecoin in band
        y : int
            Amount of collateral in band

        Returns
        -------
        int
            Current price at 1e18 base
        """
        p_o_up: int = self._p_oracle_up(n)
        p_o: int = self._price_oracle_ro()[0]
        assert p_o_up != 0

        # Special cases
        if x == 0:
            if y == 0:  # x and y are 0
                # Return mid-band
                return unsafe_div(
                    (unsafe_div(unsafe_div(p_o**2, p_o_up) * p_o, p_o_up) * self.A),
                    self.Aminus1,
                )
            # if x == 0: # Lowest point of this band -> p_current_down
            return unsafe_div(unsafe_div(p_o**2, p_o_up) * p_o, p_o_up)
        if y == 0:  # Highest point of this band -> p_current_up
            p_o_up = unsafe_div(
                p_o_up * self.Aminus1, self.A
            )  # now this is _actually_ p_o_down
            return unsafe_div(p_o**2 // p_o_up * p_o, p_o_up)

        y0: int = self._get_y0(x, y, p_o, p_o_up)
        # ^ that call also checks that p_o != 0

        # (f(y0) + x) / (g(y0) + y)
        f: int = unsafe_div(self.A * y0 * p_o, p_o_up) * p_o
        g: int = unsafe_div(self.Aminus1 * y0 * p_o_up, p_o)
        return (f + x * 10**18) // (g + y)

    def get_p(self) -> int:
        """
        Get current AMM price in active_band

        Returns
        -------
        int
            Current price at 1e18 base
        """
        n: int = self.active_band
        return self._get_p(n, self.bands_x[n], self.bands_y[n])

    def _read_user_tick_numbers(self, user: str) -> List[int]:
        n1: int = self.user_shares[user].n1
        n2: int = self.user_shares[user].n2
        return [n1, n2]

    def read_user_tick_numbers(self, user: str) -> List[int]:
        """
        Unpacks and reads user tick numbers
        @param user User address

        Returns
        -------
        [n1, n2] : List[int]
            Lowest and highest band the user deposited into
        """
        return self._read_user_tick_numbers(user)

    def _read_user_ticks(self, user: str, ns: List[int]) -> List[int]:
        """
        Unpacks and reads user ticks (shares) for all the ticks user deposited into

        Parameters
        ----------
        user : str
            User address
        ns : [int, int]
            [n1, n2] Number of ticks the user deposited into

        Returns
        -------
        List[int]
            Array of shares the user has
        """
        ticks: List[int] = []
        size: int = ns[1] - ns[0] + 1
        for i in range(MAX_TICKS):
            if len(ticks) == size:
                break
            ticks.append(self.user_shares[user].ticks[i])
        return ticks

    def can_skip_bands(self, n_end: int) -> bool:
        """
        Check that we have no liquidity between active_band and `n_end`
        """
        n: int = self.active_band
        for i in range(MAX_SKIP_TICKS):
            if n_end > n:
                if self.bands_y[n] != 0:
                    return False
                n += 1
            else:
                if self.bands_x[n] != 0:
                    return False
                n -= 1
            if n == n_end:  # not including n_end
                break
        return True
        # Actually skipping bands:
        # * change self.active_band to the new n
        # * change self.p_base_mul
        # to do n2-n1 times (if n2 > n1):
        # out.base_mul = unsafe_div(out.base_mul * Aminus1, A)

    def active_band_with_skip(self) -> int:
        n0: int = self.active_band
        n: int = n0
        min_band: int = self.min_band
        for i in range(MAX_SKIP_TICKS):
            if n < min_band:
                n = n0 - MAX_SKIP_TICKS
                break
            if self.bands_x[n] != 0:
                break
            n -= 1
        return n

    def has_liquidity(self, user: str) -> bool:
        """
        Check if `user` has any liquidity in the AMM
        """
        return self.user_shares[user].ticks[0] != 0

    def save_user_shares(self, user: str, user_shares: List[int]):
        ptr: int = 0
        for j in range(MAX_TICKS_UINT):
            if ptr >= len(user_shares):
                break
            tick: int = user_shares[ptr]
            ptr += 1
            self.user_shares[user].ticks[j] = tick

    def deposit_range(self, user: str, amount: int, n1: int, n2: int):
        """
        Deposit for a user in a range of bands. Only admin contract (Controller) can do it

        Parameters
        ----------
        user : str
            User address
        amount : int
            Amount of collateral to deposit
        n1 : int
            Lower band in the deposit range
        n2 : int
            Upper band in the deposit range
        """
        # assert msg.sender == self.admin @todo

        user_shares: List[int] = []
        collateral_shares: List[int] = []

        n0: int = self.active_band

        # We assume that n1,n2 area already sorted (and they are in Controller)
        assert n2 < 2**127
        assert n1 > -(2**127)

        lm = self.liquidity_mining_callback

        # Autoskip bands if we can
        for i in range(MAX_SKIP_TICKS + 1):
            if n1 > n0:
                if i != 0:
                    self.active_band = n0
                break
            assert (
                self.bands_x[n0] == 0 and i < MAX_SKIP_TICKS
            ), "Deposit below current band"
            n0 -= 1

        n_bands: int = unsafe_add(unsafe_sub(n2, n1), 1)
        assert n_bands <= MAX_TICKS_UINT

        y_per_band: int = unsafe_div(amount * self.COLLATERAL_PRECISION, n_bands)
        assert y_per_band > 100, "Amount too low"

        assert self.user_shares[user].ticks[0] == 0, "User must have no liquidity"
        self.user_shares[user].n1 = n1
        self.user_shares[user].n2 = n2

        for i in range(MAX_TICKS):
            band: int = unsafe_add(n1, i)
            if band > n2:
                break

            assert self.bands_x[band] == 0, "Band not empty"
            y: int = y_per_band
            if i == 0:
                y = amount * self.COLLATERAL_PRECISION - y * unsafe_sub(n_bands, 1)

            total_y: int = self.bands_y[band]

            # Total / user share
            s: int = self.total_shares[band]
            ds: int = unsafe_div((s + DEAD_SHARES) * y, total_y + 1)
            assert ds > 0, "Amount too low"
            user_shares.append(ds)
            s += ds
            assert s <= 2**128 - 1
            self.total_shares[band] = s

            total_y += y
            self.bands_y[band] = total_y

            if lm is not None and lm.address is not None:
                # If initial s == 0 - s becomes equal to y which is > 100 => nonzero
                collateral_shares.append(unsafe_div(total_y * 10**18, s))

        self.min_band = min(self.min_band, n1)
        self.max_band = max(self.max_band, n2)

        self.save_user_shares(user, user_shares)

        self.rate_mul = self._rate_mul()
        self.rate_time = self._block_timestamp

        if lm is not None and lm.address is not None:
            lm.callback_collateral_shares(n1, collateral_shares)
            lm.callback_user_shares(user, n1, user_shares)

    def withdraw(self, user: str, frac: int) -> List[int]:
        """
        Withdraw liquidity for the user. Only admin contract can do it

        Parameters
        ----------
        user : str
            User who owns liquidity
        frac : int
            Fraction to withdraw (1e18 being 100%)

        Returns
        -------
        List[int]
            Amount of [stablecoins, collateral] withdrawn
        """
        # assert msg.sender == self.admin @todo
        assert frac <= 10**18

        lm = self.liquidity_mining_callback

        ns: List[int] = self._read_user_tick_numbers(user)
        n: int = ns[0]
        user_shares: List[int] = self._read_user_ticks(user, ns)
        assert user_shares[0] > 0, "No deposits"

        total_x: int = 0
        total_y: int = 0
        min_band: int = self.min_band
        old_min_band: int = min_band
        old_max_band: int = self.max_band
        max_band: int = n - 1

        for i in range(MAX_TICKS):
            x: int = self.bands_x[n]
            y: int = self.bands_y[n]
            ds: int = unsafe_div(
                frac * user_shares[i], 10**18
            )  # Can ONLY zero out when frac == 10**18
            user_shares[i] = unsafe_sub(user_shares[i], ds)
            s: int = self.total_shares[n]
            new_shares: int = s - ds
            self.total_shares[n] = new_shares
            s += DEAD_SHARES
            dx: int = (x + 1) * ds // s
            dy: int = unsafe_div((y + 1) * ds, s)

            x -= dx
            y -= dy

            # If withdrawal is the last one - tranfer dust to admin fees
            if new_shares == 0:
                if x > 0:
                    self.admin_fees_x += x
                if y > 0:
                    self.admin_fees_y += y // self.COLLATERAL_PRECISION
                x = 0
                y = 0

            if n == min_band:
                if x == 0:
                    if y == 0:
                        min_band += 1
            if x > 0 or y > 0:
                max_band = n
            self.bands_x[n] = x
            self.bands_y[n] = y
            total_x += dx
            total_y += dy

            if n == ns[1]:
                break
            else:
                n += 1

        self.save_user_shares(user, user_shares)

        if old_min_band != min_band:
            self.min_band = min_band
        if old_max_band <= ns[1]:
            self.max_band = max_band

        total_x = unsafe_div(total_x, BORROWED_PRECISION)
        total_y = unsafe_div(total_y, self.COLLATERAL_PRECISION)

        self.rate_mul = self._rate_mul()
        self.rate_time = self._block_timestamp

        if lm is not None and lm.address is not None:
            lm.callback_collateral_shares(0, [])  # collateral/shares ratio is unchanged
            lm.callback_user_shares(user, ns[0], user_shares)

        return [total_x, total_y]

    def get_xy_up(self, user: str, use_y: bool) -> int:
        """
        Measure the amount of y (collateral) in the band n if we adiabatically trade near p_oracle on the way up,
        or the amount of x (stablecoin) if we trade adiabatically down

        Parameters
        ----------
        user : str
            User the amount is calculated for
        use_y : bool
            Calculate amount of collateral if True and of stablecoin if False

        Returns
        -------
        int
            Amount of coins
        """
        ns: List[int] = self._read_user_tick_numbers(user)
        ticks: List[int] = self._read_user_ticks(user, ns)
        if ticks[0] == 0:  # Even dynamic array will have 0th element set here
            return 0
        p_o: int = self._price_oracle_ro()[0]
        assert p_o != 0

        n: int = ns[0] - 1
        n_active: int = self.active_band
        p_o_down: int = self._p_oracle_up(ns[0])
        XY: int = 0

        for i in range(MAX_TICKS):
            n += 1
            if n > ns[1]:
                break
            x: int = 0
            y: int = 0
            if n >= n_active:
                y = self.bands_y[n]
            if n <= n_active:
                x = self.bands_x[n]
            # p_o_up: int = self._p_oracle_up(n)
            p_o_up: int = p_o_down
            # p_o_down = self._p_oracle_up(n + 1)
            p_o_down = unsafe_div(p_o_down * self.Aminus1, self.A)
            if x == 0:
                if y == 0:
                    continue

            total_share: int = self.total_shares[n]
            user_share: int = ticks[i]
            if total_share == 0:
                continue
            if user_share == 0:
                continue
            total_share += DEAD_SHARES
            # Also ideally we'd want to add +1 to all quantities when calculating with shares
            # but we choose to save bytespace and slightly under-estimate the result of this call
            # which is also more conservative

            # Also this will revert if p_o_down is 0, and p_o_down is 0 if p_o_up is 0
            p_current_mid: int = unsafe_div(p_o**2 // p_o_down * p_o, p_o_up)

            # if p_o > p_o_up - we "trade" everything to y and then convert to the result
            # if p_o < p_o_down - "trade" to x, then convert to result
            # otherwise we are in-band, so we do the more complex logic to trade
            # to p_o rather than to the edge of the band
            # trade to the edge of the band == getting to the band edge while p_o=const

            # Cases when special conversion is not needed (to save on computations)
            if x == 0 or y == 0:
                if p_o > p_o_up:  # p_o < p_current_down
                    # all to y at constant p_o, then to target currency adiabatically
                    y_equiv: int = y
                    if y == 0:
                        y_equiv = x * 10**18 // p_current_mid
                    if use_y:
                        XY += unsafe_div(y_equiv * user_share, total_share)
                    else:
                        XY += unsafe_div(
                            unsafe_div(y_equiv * p_o_up, self.SQRT_BAND_RATIO)
                            * user_share,
                            total_share,
                        )
                    continue

                elif p_o < p_o_down:  # p_o > p_current_up
                    # all to x at constant p_o, then to target currency adiabatically
                    x_equiv: int = x
                    if x == 0:
                        x_equiv = unsafe_div(y * p_current_mid, 10**18)
                    if use_y:
                        XY += unsafe_div(
                            unsafe_div(x_equiv * self.SQRT_BAND_RATIO, p_o_up)
                            * user_share,
                            total_share,
                        )
                    else:
                        XY += unsafe_div(x_equiv * user_share, total_share)
                    continue

            # If we are here - we need to "trade" to somewhere mid-band
            # So we need more heavy math

            y0: int = self._get_y0(x, y, p_o, p_o_up)
            f: int = unsafe_div(unsafe_div(self.A * y0 * p_o, p_o_up) * p_o, 10**18)
            g: int = unsafe_div(self.Aminus1 * y0 * p_o_up, p_o)
            # (f + x)(g + y) = const = p_top * A**2 * y0**2 = I
            Inv: int = (f + x) * (g + y)
            # p = (f + x) / (g + y) => p * (g + y)**2 = I or (f + x)**2 / p = I

            # First, "trade" in this band to p_oracle
            x_o: int = 0
            y_o: int = 0

            if p_o > p_o_up:  # p_o < p_current_down, all to y
                # x_o = 0
                y_o = unsafe_sub(max(Inv // f, g), g)
                if use_y:
                    XY += unsafe_div(y_o * user_share, total_share)
                else:
                    XY += unsafe_div(
                        unsafe_div(y_o * p_o_up, self.SQRT_BAND_RATIO) * user_share,
                        total_share,
                    )

            elif p_o < p_o_down:  # p_o > p_current_up, all to x
                # y_o = 0
                x_o = unsafe_sub(max(Inv // g, f), f)
                if use_y:
                    XY += unsafe_div(
                        unsafe_div(x_o * self.SQRT_BAND_RATIO, p_o_up) * user_share,
                        total_share,
                    )
                else:
                    XY += unsafe_div(x_o * user_share, total_share)

            else:
                # Equivalent from Chainsecurity (which also has less numerical errors):
                y_o = unsafe_div(self.A * y0 * unsafe_sub(p_o, p_o_down), p_o)
                # x_o = unsafe_div(A * y0 * p_o, p_o_up) * unsafe_sub(p_o_up, p_o)
                # Old math
                # y_o = unsafe_sub(max(isqrt(unsafe_div(Inv * 10**18, p_o)), g), g)
                x_o = unsafe_sub(max(Inv // (g + y_o), f), f)

                # Now adiabatic conversion from definitely in-band
                if use_y:
                    XY += unsafe_div(
                        (y_o + x_o * 10**18 // isqrt(p_o_up * p_o)) * user_share,
                        total_share,
                    )

                else:
                    XY += unsafe_div(
                        (x_o + unsafe_div(y_o * isqrt(p_o_down * p_o), 10**18))
                        * user_share,
                        total_share,
                    )

        if use_y:
            return unsafe_div(XY, self.COLLATERAL_PRECISION)
        else:
            return unsafe_div(XY, BORROWED_PRECISION)

    def get_y_up(self, user: str) -> int:
        """
        Measure the amount of y (collateral) in the band n if we adiabatically trade near p_oracle on the way up

        Parameters
        ----------
        user : str
            User the amount is calculated for

        Returns
        -------
        int
            Amount of coins
        """
        return self.get_xy_up(user, True)

    def get_x_down(self, user: str) -> int:
        """
        Measure the amount of x (stablecoin) if we trade adiabatically down

        Parameters
        ----------
        user : int
            User the amount is calculated for

        Returns
        -------
        int
            Amount of coins
        """
        return self.get_xy_up(user, False)

    def _get_xy(self, user: str, is_sum: bool) -> List[int]:
        """
        A low-gas function to measure amounts of stablecoins and collateral which user currently owns

        Parameters
        ----------
        user :
            User address
        is_sum :
            Return sum or amounts by bands

        Returns
        -------
        List[int]
            Amounts of [stablecoin, collateral] in a List
        """
        xs: List[int] = []
        ys: List[int] = []
        if is_sum:
            xs.append(0)
            ys.append(0)
        ns: List[int] = self._read_user_tick_numbers(user)
        ticks: List[int] = self._read_user_ticks(user, ns)
        if ticks[0] != 0:
            for i in range(MAX_TICKS):
                total_shares: int = self.total_shares[ns[0]] + DEAD_SHARES
                ds: int = ticks[i]
                dx: int = unsafe_div((self.bands_x[ns[0]] + 1) * ds, total_shares)
                dy: int = unsafe_div((self.bands_y[ns[0]] + 1) * ds, total_shares)
                if is_sum:
                    xs[0] += dx
                    ys[0] += dy
                else:
                    xs.append(unsafe_div(dx, BORROWED_PRECISION))
                    ys.append(unsafe_div(dy, self.COLLATERAL_PRECISION))
                if ns[0] == ns[1]:
                    break
                ns[0] = unsafe_add(ns[0], 1)

        if is_sum:
            xs[0] = unsafe_div(xs[0], BORROWED_PRECISION)
            ys[0] = unsafe_div(ys[0], self.COLLATERAL_PRECISION)

        return [xs, ys]

    def get_sum_xy(self, user: str) -> List[int]:
        """
        A low-gas function to measure amounts of stablecoins and collateral which user currently owns

        Parameters
        ----------
        user : str
            User address

        Returns
        -------
        List[int]
            Amounts of (stablecoin, collateral) in a tuple
        """
        xy: List[int] = self._get_xy(user, True)
        return [xy[0][0], xy[1][0]]

    def get_xy(self, user: str) -> List[int]:
        """
        A low-gas function to measure amounts of stablecoins and collateral by bands which user currently owns

        Parameters
        ----------
        user : str
            User address

        Returns
        -------
        List[int]
            Amounts of (stablecoin, collateral) by bands in a tuple
        """
        return self._get_xy(user, False)

    def calc_swap_out(
        self,
        pump: bool,
        in_amount: int,
        p_o: List[int],
        in_precision: int,
        out_precision: int,
    ) -> DetailedTrade:
        """
        Calculate the amount which can be obtained as a result of exchange.
        If couldn't exchange all - will also update the amount which was actually used.
        Also returns other parameters related to state after swap.
        This function is core to the AMM functionality.

        Parameters
        ----------
        pump : bool
            Indicates whether the trade buys or sells collateral
        in_amount : int
            Amount of token going in
        p_o : List[int]
            Current oracle price and ratio (p_o, dynamic_fee)

        Returns
        -------
        DetailedTrade
            Amounts spent and given out, initial and final bands of the AMM, new
            amounts of coins in bands in the AMM, as well as admin fee charged,
            all in one data structure
        """
        # pump = True: borrowable (USD) in, collateral (ETH) out; going up
        # pump = False: collateral (ETH) in, borrowable (USD) out; going down
        min_band: int = self.min_band
        max_band: int = self.max_band
        out: DetailedTrade = DetailedTrade()
        out.n2 = self.active_band
        p_o_up: int = self._p_oracle_up(out.n2)
        x: int = self.bands_x[out.n2]
        y: int = self.bands_y[out.n2]

        in_amount_left: int = in_amount
        antifee: int = unsafe_div(
            (10**18) ** 2, unsafe_sub(10**18, max(self.fee, p_o[1]))
        )
        admin_fee: int = self.admin_fee
        j: int = MAX_TICKS_UINT

        for i in range(MAX_TICKS + MAX_SKIP_TICKS):
            y0: int = 0
            f: int = 0
            g: int = 0
            Inv: int = 0

            if x > 0 or y > 0:
                if j == MAX_TICKS_UINT:
                    out.n1 = out.n2
                    j = 0
                y0 = self._get_y0(x, y, p_o[0], p_o_up)  # <- also checks p_o
                f = unsafe_div(self.A * y0 * p_o[0] // p_o_up * p_o[0], 10**18)
                g = unsafe_div(self.Aminus1 * y0 * p_o_up, p_o[0])
                Inv = (f + x) * (g + y)

            if j != MAX_TICKS_UINT:
                # Initialize
                _tick: int = y
                if pump:
                    _tick = x
                out.ticks_in.append(_tick)

                # SIM_INTERFACE: fees
                out.fees.append(0)

            # Need this to break if price is too far
            p_ratio: int = unsafe_div(p_o_up * 10**18, p_o[0])

            if pump:
                if y != 0:
                    if g != 0:
                        x_dest: int = (unsafe_div(Inv, g) - f) - x
                        dx: int = unsafe_div(x_dest * antifee, 10**18)
                        if dx >= in_amount_left:
                            # This is the last band
                            x_dest = unsafe_div(
                                in_amount_left * 10**18, antifee
                            )  # LESS than in_amount_left
                            out.last_tick_j = min(
                                Inv // (f + (x + x_dest)) - g + 1, y
                            )  # Should be always >= 0

                            # SIM_INTERFACE: fees
                            fees = unsafe_sub(in_amount_left, x_dest)
                            out.fees[j] = fees

                            x_dest = unsafe_div(
                                fees * admin_fee, 10**18
                            )  # abs admin fee now
                            x += in_amount_left  # x is precise after this
                            # Round down the output
                            out.out_amount += y - out.last_tick_j
                            out.ticks_in[j] = x - x_dest
                            out.in_amount = in_amount
                            out.admin_fee = unsafe_add(out.admin_fee, x_dest)
                            break

                        else:
                            # We go into the next band
                            dx = max(dx, 1)  # Prevents from leaving dust in the band

                            # SIM_INTERFACE: fees
                            fees = unsafe_sub(dx, x_dest)
                            out.fees[j] = fees

                            x_dest = unsafe_div(
                                fees * admin_fee, 10**18
                            )  # abs admin fee now
                            in_amount_left -= dx
                            out.ticks_in[j] = x + dx - x_dest
                            out.in_amount += dx
                            out.out_amount += y
                            out.admin_fee = unsafe_add(out.admin_fee, x_dest)

                if i != MAX_TICKS + MAX_SKIP_TICKS - 1:
                    if out.n2 == max_band:
                        break
                    if j == MAX_TICKS_UINT - 1:
                        break
                    if p_ratio < 10**36 // self.MAX_ORACLE_DN_POW:
                        # Don't allow to be away by more than ~50 ticks
                        break
                    out.n2 += 1
                    p_o_up = unsafe_div(p_o_up * self.Aminus1, self.A)
                    x = 0
                    y = self.bands_y[out.n2]

            else:  # dump
                if x != 0:
                    if f != 0:
                        y_dest: int = (unsafe_div(Inv, f) - g) - y
                        dy: int = unsafe_div(y_dest * antifee, 10**18)
                        if dy >= in_amount_left:
                            # This is the last band
                            y_dest = unsafe_div(in_amount_left * 10**18, antifee)
                            out.last_tick_j = min(Inv // (g + (y + y_dest)) - f + 1, x)

                            # SIM_INTERFACE: fees
                            fees = unsafe_sub(in_amount_left, y_dest)
                            out.fees[j] = fees

                            y_dest = unsafe_div(
                                fees * admin_fee, 10**18
                            )  # abs admin fee now
                            y += in_amount_left
                            out.out_amount += x - out.last_tick_j
                            out.ticks_in[j] = y - y_dest
                            out.in_amount = in_amount
                            out.admin_fee = unsafe_add(out.admin_fee, y_dest)
                            break

                        else:
                            # We go into the next band
                            dy = max(dy, 1)  # Prevents from leaving dust in the band

                            # SIM_INTERFACE: fees
                            fees = unsafe_sub(dy, y_dest)
                            out.fees[j] = fees

                            y_dest = unsafe_div(
                                fees * admin_fee, 10**18
                            )  # abs admin fee now
                            in_amount_left -= dy
                            out.ticks_in[j] = y + dy - y_dest
                            out.in_amount += dy
                            out.out_amount += x
                            out.admin_fee = unsafe_add(out.admin_fee, y_dest)

                if i != MAX_TICKS + MAX_SKIP_TICKS - 1:
                    if out.n2 == min_band:
                        break
                    if j == MAX_TICKS_UINT - 1:
                        break
                    if p_ratio > self.MAX_ORACLE_DN_POW:
                        # Don't allow to be away by more than ~50 ticks
                        break
                    out.n2 -= 1
                    p_o_up = unsafe_div(p_o_up * self.A, self.Aminus1)
                    x = self.bands_x[out.n2]
                    y = 0

            if j != MAX_TICKS_UINT:
                j = unsafe_add(j, 1)

        # Round up what goes in and down what goes out
        # ceil(in_amount_used/BORROWED_PRECISION) * BORROWED_PRECISION
        out.in_amount = unsafe_mul(
            unsafe_div(
                unsafe_add(out.in_amount, unsafe_sub(in_precision, 1)), in_precision
            ),
            in_precision,
        )
        out.out_amount = unsafe_mul(
            unsafe_div(out.out_amount, out_precision), out_precision
        )

        return out

    def _get_dxdy(self, i: int, j: int, amount: int, is_in: bool) -> DetailedTrade:
        """
        Method to use to calculate out amount and spent in amount

        Parameters
        ----------
        i : int
            Input coin index
        j : int
            Output coin index
        amount : int
            Amount of input or output coin to swap
        is_in : bool
            Whether IN our OUT amount is known

        Returns
        -------
        DetailedTrade with all swap results
        """
        # i = 0: borrowable (USD) in, collateral (ETH) out; going up
        # i = 1: collateral (ETH) in, borrowable (USD) out; going down
        assert (i == 0 and j == 1) or (i == 1 and j == 0), "Wrong index"
        out: DetailedTrade = DetailedTrade()
        if amount == 0:
            return out
        in_precision: int = self.COLLATERAL_PRECISION
        out_precision: int = BORROWED_PRECISION
        if i == 0:
            in_precision = BORROWED_PRECISION
            out_precision = self.COLLATERAL_PRECISION
        p_o: List[int] = self._price_oracle_ro()
        if is_in:
            out = self.calc_swap_out(
                i == 0, amount * in_precision, p_o, in_precision, out_precision
            )
        else:
            out = self.calc_swap_in(
                i == 0, amount * out_precision, p_o, in_precision, out_precision
            )
        out.in_amount = unsafe_div(out.in_amount, in_precision)
        out.out_amount = unsafe_div(out.out_amount, out_precision)
        return out

    def get_dy(self, i: int, j: int, in_amount: int) -> int:
        """
        Method to use to calculate out amount

        Parameters
        ----------
        i : int
            Input coin index
        j : int
            Output coin index
        in_amount : int
            Amount of input coin to swap

        Returns
        -------
        int
            Amount of coin j to give out
        """
        return self._get_dxdy(i, j, in_amount, True).out_amount

    def get_dxdy(self, i: int, j: int, in_amount: int) -> Tuple[int, int]:
        """
        Method to use to calculate out amount and spent in amount

        Parameters
        ----------
        i : int
            Input coin index
        j : int
            Output coin index
        in_amount : int
            Amount of input coin to swap

        Returns
        -------
        Tuple[int, int]
            A tuple with in_amount used and out_amount returned
        """
        out: DetailedTrade = self._get_dxdy(i, j, in_amount, True)
        return (out.in_amount, out.out_amount, sum(out.fees))

    def _exchange(
        self,
        i: int,
        j: int,
        amount: int,
        minmax_amount: int,
        use_in_amount: bool,
        _receiver: str = ARBITRAGUR_ADDRESS,
    ) -> List[int]:
        """
        Exchanges two coins, callable by anyone

        Parameters
        ----------
        i : int
            Input coin index
        j : int
            Output coin index
        amount : int
            Amount of input/output coin to swap
        minmax_amount : int
            Minimal/maximum amount to get as output/input
        _for : str
            Address to send coins to
        use_in_amount : bool
            Whether input or output amount is specified

        Returns
        -------
        [in_amount_done, out_amount_done, fees] : [int, int, int]
            Amount of coins given in and out, fees (coin_in)
        """
        assert (i == 0 and j == 1) or (i == 1 and j == 0), "Wrong index"
        p_o: List[
            int
        ] = self._price_oracle_w()  # Let's update the oracle even if we exchange 0
        if amount == 0:
            return [0, 0]

        lm = self.liquidity_mining_callback
        collateral_shares: List[int] = []

        in_coin = self.BORROWED_TOKEN
        out_coin = self.COLLATERAL_TOKEN
        in_precision: int = BORROWED_PRECISION
        out_precision: int = self.COLLATERAL_PRECISION
        if i == 1:
            in_precision = out_precision
            in_coin = out_coin
            out_precision = BORROWED_PRECISION
            out_coin = self.BORROWED_TOKEN

        out: DetailedTrade = DetailedTrade()
        if use_in_amount:
            out = self.calc_swap_out(
                i == 0, amount * in_precision, p_o, in_precision, out_precision
            )
        else:
            out = self.calc_swap_in(
                i == 0, amount * out_precision, p_o, in_precision, out_precision
            )
        in_amount_done: int = unsafe_div(out.in_amount, in_precision)
        out_amount_done: int = unsafe_div(out.out_amount, out_precision)
        if use_in_amount:
            assert out_amount_done >= minmax_amount, "Slippage"
        else:
            assert in_amount_done <= minmax_amount, "Slippage"
        if out_amount_done == 0 or in_amount_done == 0:
            return [0, 0]

        out.admin_fee = unsafe_div(out.admin_fee, in_precision)
        if i == 0:
            self.admin_fees_x += out.admin_fee
        else:
            self.admin_fees_y += out.admin_fee

        n: int = min(out.n1, out.n2)
        n_start: int = n
        n_diff: int = abs(unsafe_sub(out.n2, out.n1))

        for k in range(MAX_TICKS):
            x: int = 0
            y: int = 0
            if i == 0:
                x = out.ticks_in[k]
                if n == out.n2:
                    y = out.last_tick_j
            else:
                y = out.ticks_in[unsafe_sub(n_diff, k)]
                if n == out.n2:
                    x = out.last_tick_j

            # SIM_INTERFACE: fees
            if i == 0:
                self.bands_fees_x[n] += out.fees[k]
            else:
                self.bands_fees_y[n] += out.fees[unsafe_sub(n_diff, k)]

            # SIM_INTERFACE: loss
            _price_last = self.price_oracle_contract._price_last
            _benchmark_slippage_mul = unsafe_sub(10**18, self.benchmark_slippage_rate)
            if i == 0:
                band_in_amount = (
                    (x - self.bands_x[n]) * _benchmark_slippage_mul // 10**18
                )
                self.bands_x_benchmark[n] += band_in_amount
                self.bands_y_benchmark[n] -= band_in_amount * 10**18 // _price_last
            else:
                band_in_amount = (
                    (y - self.bands_y[n]) * _benchmark_slippage_mul // 10**18
                )
                self.bands_x_benchmark[n] -= band_in_amount * _price_last // 10**18
                self.bands_y_benchmark[n] += band_in_amount

            self.bands_x[n] = x
            self.bands_y[n] = y

            if lm is not None and lm.address is not None:
                s: int = 0
                if y > 0:
                    s = unsafe_div(y * 10**18, self.total_shares[n])
                collateral_shares.append(s)

            if k == n_diff:
                break
            n = unsafe_add(n, 1)

        self.active_band = out.n2

        if lm is not None and lm.address is not None:
            lm.callback_collateral_shares(n_start, collateral_shares)

        assert in_coin.transferFrom(_receiver, self.address, in_amount_done)
        assert out_coin.transfer(self.address, _receiver, out_amount_done)

        return [in_amount_done, out_amount_done, sum(out.fees)]

    def calc_swap_in(
        self,
        pump: bool,
        out_amount: int,
        p_o: List[int],
        in_precision: int,
        out_precision: int,
    ) -> DetailedTrade:
        """
        Calculate the input amount required to receive the desired output amount.
        If couldn't exchange all - will also update the amount which was actually received.
        Also returns other parameters related to state after swap.

        Parameters
        ----------
        pump : bool
            Indicates whether the trade buys or sells collateral
        out_amount : int
            Desired amount of token going out
        p_o : List[int]
            Current oracle price and antisandwich fee (p_o, dynamic_fee)

        Returns
        -------
        DetailedTrade
            Amounts required and given out, initial and final bands of the AMM, new
            amounts of coins in bands in the AMM, as well as admin fee charged,
            all in one data structure
        """
        # pump = True: borrowable (USD) in, collateral (ETH) out; going up
        # pump = False: collateral (ETH) in, borrowable (USD) out; going down
        min_band: int = self.min_band
        max_band: int = self.max_band
        out: DetailedTrade = DetailedTrade()
        out.n2 = self.active_band
        p_o_up: int = self._p_oracle_up(out.n2)
        x: int = self.bands_x[out.n2]
        y: int = self.bands_y[out.n2]

        out_amount_left: int = out_amount
        antifee: int = unsafe_div(
            (10**18) ** 2, unsafe_sub(10**18, max(self.fee, p_o[1]))
        )
        admin_fee: int = self.admin_fee
        j: int = MAX_TICKS_UINT

        for i in range(MAX_TICKS + MAX_SKIP_TICKS):
            y0: int = 0
            f: int = 0
            g: int = 0
            Inv: int = 0

            if x > 0 or y > 0:
                if j == MAX_TICKS_UINT:
                    out.n1 = out.n2
                    j = 0
                y0 = self._get_y0(x, y, p_o[0], p_o_up)  # <- also checks p_o
                f = unsafe_div(self.A * y0 * p_o[0] // p_o_up * p_o[0], 10**18)
                g = unsafe_div(self.Aminus1 * y0 * p_o_up, p_o[0])
                Inv = (f + x) * (g + y)

            if j != MAX_TICKS_UINT:
                # Initialize
                _tick: int = y
                if pump:
                    _tick = x
                out.ticks_in.append(_tick)

                # DEV_SIM: fees
                out.fees.append(0)

            # Need this to break if price is too far
            p_ratio: int = unsafe_div(p_o_up * 10**18, p_o[0])

            if pump:
                if y != 0:
                    if g != 0:
                        if y >= out_amount_left:
                            # This is the last band
                            out.last_tick_j = unsafe_sub(y, out_amount_left)
                            x_dest: int = Inv // (g + out.last_tick_j) - f - x
                            dx: int = unsafe_div(
                                x_dest * antifee, 10**18
                            )  # MORE than x_dest
                            out.out_amount = out_amount  # We successfully found liquidity for all the out_amount
                            out.in_amount += dx

                            # SIM_INTERFACE: fees
                            fees = unsafe_sub(dx, x_dest)
                            out.fees[j] = fees

                            x_dest = unsafe_div(
                                fees * admin_fee, 10**18
                            )  # abs admin fee now
                            out.ticks_in[j] = x + dx - x_dest
                            out.admin_fee = unsafe_add(out.admin_fee, x_dest)
                            break

                        else:
                            # We go into the next band
                            x_dest: int = (unsafe_div(Inv, g) - f) - x
                            dx: int = max(unsafe_div(x_dest * antifee, 10**18), 1)
                            out_amount_left -= y
                            out.in_amount += dx
                            out.out_amount += y

                            # SIM_INTERFACE: fees
                            fees = unsafe_sub(dx, x_dest)
                            out.fees[j] = fees

                            x_dest = unsafe_div(
                                fees * admin_fee, 10**18
                            )  # abs admin fee now
                            out.ticks_in[j] = x + dx - x_dest
                            out.admin_fee = unsafe_add(out.admin_fee, x_dest)

                if i != MAX_TICKS + MAX_SKIP_TICKS - 1:
                    if out.n2 == max_band:
                        break
                    if j == MAX_TICKS_UINT - 1:
                        break
                    if p_ratio < 10**36 // self.MAX_ORACLE_DN_POW:
                        # Don't allow to be away by more than ~50 ticks
                        break
                    out.n2 += 1
                    p_o_up = unsafe_div(p_o_up * self.Aminus1, self.A)
                    x = 0
                    y = self.bands_y[out.n2]

            else:  # dump
                if x != 0:
                    if f != 0:
                        if x >= out_amount_left:
                            # This is the last band
                            out.last_tick_j = unsafe_sub(x, out_amount_left)
                            y_dest: int = Inv // (f + out.last_tick_j) - g - y
                            dy: int = unsafe_div(
                                y_dest * antifee, 10**18
                            )  # MORE than y_dest
                            out.out_amount = out_amount
                            out.in_amount += dy

                            # SIM_INTERFACE: fees
                            fees = unsafe_sub(dy, y_dest)
                            out.fees[j] = fees

                            y_dest = unsafe_div(
                                fees * admin_fee, 10**18
                            )  # abs admin fee now
                            out.ticks_in[j] = y + dy - y_dest
                            out.admin_fee = unsafe_add(out.admin_fee, y_dest)
                            break

                        else:
                            # We go into the next band
                            y_dest: int = (unsafe_div(Inv, f) - g) - y
                            dy: int = max(unsafe_div(y_dest * antifee, 10**18), 1)
                            out_amount_left -= x
                            out.in_amount += dy
                            out.out_amount += x

                            # SIM_INTERFACE: fees
                            fees = unsafe_sub(dy, y_dest)
                            out.fees[j] = fees

                            y_dest = unsafe_div(
                                fees * admin_fee, 10**18
                            )  # abs admin fee now
                            out.ticks_in[j] = y + dy - y_dest
                            out.admin_fee = unsafe_add(out.admin_fee, y_dest)

                if i != MAX_TICKS + MAX_SKIP_TICKS - 1:
                    if out.n2 == min_band:
                        break
                    if j == MAX_TICKS_UINT - 1:
                        break
                    if p_ratio > self.MAX_ORACLE_DN_POW:
                        # Don't allow to be away by more than ~50 ticks
                        break
                    out.n2 -= 1
                    p_o_up = unsafe_div(p_o_up * self.A, self.Aminus1)
                    x = self.bands_x[out.n2]
                    y = 0

            if j != MAX_TICKS_UINT:
                j = unsafe_add(j, 1)

        # Round up what goes in and down what goes out
        # ceil(in_amount_used/BORROWED_PRECISION) * BORROWED_PRECISION
        out.in_amount = unsafe_mul(
            unsafe_div(
                unsafe_add(out.in_amount, unsafe_sub(in_precision, 1)), in_precision
            ),
            in_precision,
        )
        out.out_amount = unsafe_mul(
            unsafe_div(out.out_amount, out_precision), out_precision
        )

        return out

    def get_dx(self, i: int, j: int, out_amount: int) -> int:
        """
        Method to use to calculate in amount required to receive the desired out_amount

        Parameters
        ----------
        i : int
            Input coin index
        j : int
            Output coin index
        out_amount : int
            Desired amount of output coin to receive

        Returns
        -------
        int
            Amount of coin i to spend
        """
        # i = 0: borrowable (USD) in, collateral (ETH) out; going up
        # i = 1: collateral (ETH) in, borrowable (USD) out; going down
        return self._get_dxdy(i, j, out_amount, False).in_amount

    def get_dydx(self, i: int, j: int, out_amount: int) -> Tuple[int, int]:
        """
        Method to use to calculate in amount required and out amount received

        Parameters
        ----------
        i : int
            Input coin index
        j : int
            Output coin index
        out_amount : int
            Desired amount of output coin to receive


        Returns
        -------
        (out_amount, in_amount) : Tuple[int, int]
            A tuple with out_amount received and in_amount returned
        """
        # i = 0: borrowable (USD) in, collateral (ETH) out; going up
        # i = 1: collateral (ETH) in, borrowable (USD) out; going down
        out: DetailedTrade = self._get_dxdy(i, j, out_amount, False)
        return (out.out_amount, out.in_amount, sum(out.fees))

    def exchange(
        self,
        i: int,
        j: int,
        in_amount: int,
        min_amount: int = 0,
        _receiver: str = ARBITRAGUR_ADDRESS,
    ) -> List[int]:
        """
        Exchanges two coins, callable by anyone

        Parameters
        ----------
        i : int
            Input coin index
        j : int
            Output coin index
        in_amount : int
            Amount of input coin to swap
        min_amount : int
            Minimal amount to get as output
        _for : int
            Address to send coins to

        Returns
        -------
        [in_amount_done, out_amount_done] : [int, int]
            Amount of coins given in/out
        """
        return self._exchange(i, j, in_amount, min_amount, True, _receiver)

    def exchange_dy(
        self,
        i: int,
        j: int,
        out_amount: int,
        max_amount: int,
        _receiver: str = ARBITRAGUR_ADDRESS,
    ) -> List[int]:
        """
        Exchanges two coins, callable by anyone

        Parameters
        ----------
        i : int
            Input coin index
        j : int
            Output coin index
        out_amount : int
            Desired amount of output coin to receive
        max_amount : int
            Maximum amount to spend (revert if more)

        Returns
        -------
        [in_amount_done, out_amount_done] : [int, int]
            Amount of coins given in/out
        """
        return self._exchange(i, j, out_amount, max_amount, False, _receiver)

    def get_amount_for_price(self, p: int) -> Tuple[int, bool]:
        """
        Amount necessary to be exchanged to have the AMM at the final price `p`

        Returns
        -------
        amount, pump: Tuple[int, bool]
        """
        min_band: int = self.min_band
        max_band: int = self.max_band
        n: int = self.active_band
        p_o: List[int] = self._price_oracle_ro()
        p_o_up: int = self._p_oracle_up(n)
        p_down: int = unsafe_div(
            unsafe_div(p_o[0] ** 2, p_o_up) * p_o[0], p_o_up
        )  # p_current_down
        p_up: int = unsafe_div(p_down * self.A2, self.Aminus12)  # p_crurrent_up
        amount: int = 0
        y0: int = 0
        f: int = 0
        g: int = 0
        Inv: int = 0
        j: int = MAX_TICKS_UINT
        pump: bool = True

        for i in range(MAX_TICKS + MAX_SKIP_TICKS):
            assert p_o_up > 0
            x: int = self.bands_x[n]
            y: int = self.bands_y[n]
            if i == 0:
                if p < self._get_p(n, x, y):
                    pump = False
            not_empty: bool = x > 0 or y > 0
            if not_empty:
                y0 = self._get_y0(x, y, p_o[0], p_o_up)
                f = unsafe_div(
                    unsafe_div(self.A * y0 * p_o[0], p_o_up) * p_o[0], 10**18
                )
                g = unsafe_div(self.Aminus1 * y0 * p_o_up, p_o[0])
                Inv = (f + x) * (g + y)
                if j == MAX_TICKS_UINT:
                    j = 0

            if p <= p_up:
                if p >= p_down:
                    if not_empty:
                        ynew: int = unsafe_sub(
                            max(isqrt(int(Inv * 10**18 // p)), g), g
                        )
                        xnew: int = unsafe_sub(max(Inv // (g + ynew), f), f)
                        if pump:
                            amount += unsafe_sub(max(xnew, x), x)
                        else:
                            amount += unsafe_sub(max(ynew, y), y)
                    break

            # Need this to break if price is too far
            p_ratio: int = unsafe_div(p_o_up * 10**18, p_o[0])

            if pump:
                if not_empty:
                    amount += (Inv // g - f) - x
                if n == max_band:
                    break
                if j == MAX_TICKS_UINT - 1:
                    break
                if p_ratio < 10**36 // self.MAX_ORACLE_DN_POW:
                    # Don't allow to be away by more than ~50 ticks
                    break
                n += 1
                p_down = p_up
                p_up = unsafe_div(p_up * self.A2, self.Aminus12)
                p_o_up = unsafe_div(p_o_up * self.Aminus1, self.A)

            else:
                if not_empty:
                    amount += (Inv // f - g) - y
                if n == min_band:
                    break
                if j == MAX_TICKS_UINT - 1:
                    break
                if p_ratio > self.MAX_ORACLE_DN_POW:
                    # Don't allow to be away by more than ~50 ticks
                    break
                n -= 1
                p_up = p_down
                p_down = unsafe_div(p_down * self.Aminus12, self.A2)
                p_o_up = unsafe_div(p_o_up * self.A, self.Aminus1)

            if j != MAX_TICKS_UINT:
                j = unsafe_add(j, 1)

        amount = amount * 10**18 // unsafe_sub(10**18, max(self.fee, p_o[1]))
        if amount == 0:
            return 0, pump

        # Precision and round up
        if pump:
            amount = unsafe_add(
                unsafe_div(unsafe_sub(amount, 1), BORROWED_PRECISION), 1
            )
        else:
            amount = unsafe_add(
                unsafe_div(unsafe_sub(amount, 1), self.COLLATERAL_PRECISION), 1
            )

        return amount, pump

    def set_rate(self, rate: int) -> int:
        """
        Set interest rate. That affects the dependence of AMM base price over time

        Parameters
        ----------
        rate :
            New rate in units of int(fraction * 1e18) per second

        Returns
        -------
        rate_mul : int
            rate_mul multiplier (e.g. 1.0 + integral(rate, dt))
        """
        # assert msg.sender == self.admin @todo
        rate_mul: int = self._rate_mul()
        self.rate_mul = rate_mul
        self.rate_time = self._block_timestamp
        self.rate = rate
        return rate_mul

    def set_fee(self, fee: int):
        """
        Set AMM fee

        Parameters
        ----------
        fee :
            Fee where 1e18 == 100%
        """
        # assert msg.sender == self.admin
        self.fee = fee

    def set_admin(self, admin: any):
        """
        Set admin of the factory (should end up with DAO)

        Parameters
        ----------
        admin Address of the admin
        """
        # assert msg.sender == self.admin
        self.admin = admin  # Controller

    def set_admin_fee(self, fee: int):
        """
        Set admin fee - fraction of the AMM fee to go to admin

        Parameters
        ----------
        fee : int
            Admin fee where 1e18 == 100%
        """
        # assert msg.sender == self.admin
        self.admin_fee = fee

    def reset_admin_fees(self):
        """
        Zero out AMM fees collected
        """
        # assert msg.sender == self.admin
        self.admin_fees_x = 0
        self.admin_fees_y = 0


class UserShares:
    """n1, n2 and fraction of n'th band owned by a user"""

    def __init__(self):
        self.n1 = 0
        self.n2 = 0
        self.ticks = [0] * MAX_TICKS


def _default_user_shares():
    return UserShares()
