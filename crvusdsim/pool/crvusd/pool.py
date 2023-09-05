"""
Mainly a module to house the `LLAMMAPool`, a LLAMMA implementation in Python.
"""
import time
from math import isqrt, prod
from typing import List

from curvesim.exceptions import CalculationError, CryptoPoolError
from curvesim.logging import get_logger
from curvesim.pool.base import Pool
from crvusdsim.pool.snapshot import LLAMMABandsSnapshot

logger = get_logger(__name__)

MAX_TICKS = 50
MAX_TICKS_UINT = 50
MAX_SKIP_TICKS = 1024
PREV_P_O_DELAY = 2 * 60  # s = 2 min
MAX_P_O_CHG = 12500 * 10**14  # <= 2**(1/3) - max relative change to have fee < 50%
BORROWED_TOKEN = "0xf939e0a03fb07f59a73314e73794be0e57ac1b4e"
BORROWED_PRECISION = 18


class LLAMMAPool(Pool):  # pylint: disable=too-many-instance-attributes
    """LLAMMA implementation in Python."""

    snapshot_class = LLAMMABandsSnapshot

    __slots__ = (
        "A",
        "Aminus1",
        "A2",                   # A^2
        "Aminus12",             # (A-1)^2
        "SQRT_BAND_RATIO",      # sqrt(A / (A - 1))
        "LOG_A_RATIO",          # ln(A / (A - 1))
        "MAX_ORACLE_DN_POW",    # (A / (A - 1)) ** 50

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
        "PREV_P_O_DELAY",
        "MAX_P_O_CHG",

        "bands_x",
        "bands_y",

        "total_shares",
        "user_shares",
        "DEAD_SHARES",

        "liquidity_mining_callback", # LMGauge

        "collateral",
        "BASE_PRICE",
        "admin",                # admin address
    )

    def __init__(  # pylint: disable=too-many-locals,too-many-arguments
        self,
        A: int,
        fee: int,
        admin_fee: int,
        BASE_PRICE: int,
        collateral=None,
        price_oracle_contract=None,
        admin=None,
    ):
        """
        Parameters
        ----------
        A : int
        @todo
        """
        self.collateral = collateral

        self.A = A
        self.Aminus1 = A - 1
        self.A2 = A**2
        self.Aminus12 = (A-1)**2

        self.fee = fee
        self.admin_fee = admin_fee
        self.BASE_PRICE = BASE_PRICE

        self._block_timestamp = _get_unix_timestamp()
        self.price_oracle_contract = price_oracle_contract
        self.old_p_o = price_oracle_contract.price()
        self.prev_p_o_time = self._block_timestamp

        self.old_dfee = 0

        self.rate = 0
        self.rate_time = self._block_timestamp
        self.rate_mul = 10**18
        
        A_ratio = 10**18 * A // (A - 1)
        self.SQRT_BAND_RATIO = isqrt(A_ratio * 10**18)
        self.LOG_A_RATIO = ln_int(A_ratio)
        # (A / (A - 1)) ** 50
        self.MAX_ORACLE_DN_POW = int(A**25 * 10**18 // (self.Aminus1 ** 25)) ** 2 // 10**18
    

    def _increment_timestamp(self, blocks=1, timestamp=None):
        """Update the internal clock used to mimic the block timestamp."""
        if timestamp:
            self._block_timestamp = timestamp
            return

        self._block_timestamp += 12 * blocks
        
    
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
        p_new = p
        dt = PREV_P_O_DELAY - min(PREV_P_O_DELAY, self._block_timestamp - self.prev_p_o_time)
        ratio = 0

        # ratio = 1 - (p_o_min / p_o_max)**3

        if dt > 0:
            old_p_o = self.old_p_o
            old_ratio = self.old_dfee
            # ratio = p_o_min / p_o_max
            if p > old_p_o:
                ratio = old_p_o * 10**18 // p
                if ratio < 10**36 // MAX_P_O_CHG:
                    p_new = old_p_o * MAX_P_O_CHG // 10**18
                    ratio = 10**36 // MAX_P_O_CHG
            else:
                ratio = p * 10**18 // old_p_o
                if ratio < 10**36 // MAX_P_O_CHG:
                    p_new = old_p_o * 10**18 // MAX_P_O_CHG
                    ratio = 10**36 // MAX_P_O_CHG

            # ratio is guaranteed to be less than 1e18
            # Also guaranteed to be limited, therefore can have all ops unsafe
            ratio = ((10**18 + old_ratio) - (ratio**3 // 10**36)) * dt  //  PREV_P_O_DELAY

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
        return self.rate_mul * (10**18 + self.rate * (self._block_timestamp - self.rate_time)) // 10**18


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
        # return unsafe_div(self._base_price() * self.exp_int(-n * LOG_A_RATIO), 10**18)

        power: int = -n * self.LOG_A_RATIO

        # ((A - 1) / A) ** n = exp(-n * A / (A - 1)) = exp(-n * LOG_A_RATIO)
        ## Exp implementation based on solmate's
        assert power > -42139678854452767551
        assert power < 135305999368893231589

        x: int = (power * 2**96) // 10**18

        k: int = ((x * 2**96) // 54916777467707473351141471128 + 2**95) // 2**96
        x = x - k * 54916777467707473351141471128

        y: int = x + 1346386616545796478920950773328
        y = y * x // 2**96 + 57155421227552351082224309758442
        p: int = y + x - 94201549194550492254356042504812
        p = p * y // 2**96 + 28719021644029726153956944680412240
        p = p * x + (4385272521454847904659076985693276 * 2**96)

        q: int = x - 2855989394907223263936484059900
        q = ((q * x) // 2**96) + 50020603652535783019961831881945
        q = ((q * x) // 2**96) - 533845033583426703283633433725380
        q = ((q * x) // 2**96) + 3604857256930695427073651918091429
        q = ((q * x) // 2**96) - 14423608567350463180887372962807573
        q = ((q * x) // 2**96) + 26449188498355588339934803723976023


        exp_result: int = shift(
            (p // q) * 3822833074963236453042738258902158003155416615667,
            (k - 195))
        ## End exp
        assert exp_result > 1000  # dev: limit precision of the multiplier
        return self._base_price() * exp_result // 10**18


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
        Price at 1e18 base
        """
        return self._p_oracle_up(n)



def shift(n: int, s: int) -> int:
    if s >= 0:
        return n << abs(s)
    else:
        return n >> abs(s)


def _get_unix_timestamp():
    """Get the timestamp in Unix time."""
    return int(time.time())

def ln_int(_x: int) -> int:
    """
    @notice Logarithm ln() function based on log2. Not very gas-efficient but brief
    """
    # adapted from: https://medium.com/coinmonks/9aef8515136e
    # and vyper log implementation
    # This can be much more optimal but that's not important here
    x: int = _x
    res: int = 0
    for i in range(8):
        t: int = 2**(7 - i)
        p: int = 2**t
        if x >= p * 10**18:
            x //= p
            res += t * 10**18
    d: int = 10**18
    for i in range(59):  # 18 decimals: math.log2(10**10) == 59.7
        if (x >= 2 * 10**18):
            res += d
            x //= 2
        x = x * x // 10**18
        d //= 2
    # Now res = log2(x)
    # ln(x) = log2(x) / log2(e)
    return res * 10**18 // 1442695040888963328
## End of low-level math