"""
Mainly a module to house the `LLAMMAPool`, a LLAMMA implementation in Python.
"""
import time
from math import isqrt, prod, log
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

        self.rate_mul = 10**18

        self.SQRT_BAND_RATIO = isqrt(int(A / (A - 1) * 10**18))
        self.LOG_A_RATIO = int(log(A / (A - 1)) * 10**18)
        # (A / (A - 1)) ** 50
        self.MAX_ORACLE_DN_POW = int(A**25 * 10**18 // (self.Aminus1 ** 25)) ** 2 // 10**18
        
    
    def _limit_p_o(self, p: int) -> List[int]:
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
        --------
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
                print(dt, old_p_o, ratio, 10**36 // MAX_P_O_CHG)
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
    

    def _increment_timestamp(self, blocks=1, timestamp=None):
        """Update the internal clock used to mimic the block timestamp."""
        if timestamp:
            self._block_timestamp = timestamp
            return

        self._block_timestamp += 12 * blocks


def _get_unix_timestamp():
    """Get the timestamp in Unix time."""
    return int(time.time())