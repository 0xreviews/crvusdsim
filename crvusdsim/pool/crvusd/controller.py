"""
Mainly a module to house the `Curve Stablecoin`, a Controller implementation in Python.
"""
from collections import defaultdict
from typing import List, Tuple
from math import isqrt

from curvesim.pool.snapshot import SnapshotMixin

from crvusdsim.pool.crvusd.pool import LLAMMAPool
from crvusdsim.pool.crvusd.clac import ln_int

MAX_LOAN_DISCOUNT = 5 * 10**17
MIN_LIQUIDATION_DISCOUNT = 10**16 # Start liquidating when threshold reached
MAX_TICKS = 50
MAX_TICKS_UINT = 50
MIN_TICKS = 4
MAX_SKIP_TICKS = 1024
MAX_P_BASE_BANDS = 5
MAX_RATE = 43959106799  # 400% APY
MAX_ADMIN_FEE = 10**18  # 100%
MIN_FEE = 10**6  # 1e-12, still needs to be above 0
MAX_FEE = 10**17  # 10%
DEAD_SHARES = 1000
MAX_ETH_GAS = 10000  # Forward this much gas to ETH transfers (2300 is what send() does)

class Loan:
    def __init__(self):
        self.initial_debt = 0
        self.rate_mul = 0

class Position:
    def __init__(self):
        self.user = ""
        self.x = 0
        self.y = 0
        self.debt = 0
        self.health = 0


class Controller(SnapshotMixin):  # pylint: disable=too-many-instance-attributes
    """Controller implementation in Python."""

    snapshot_class = None

    __slots__ = (
        "loan",
        "liquidation_discounts",
        "_total_debt",
        "loans",
        "loan_ix",
        "n_loans",
        "minted",
        "redeemed",
        "monetary_policy",
        "liquidation_discount",
        "loan_discount",
        "COLLATERAL_TOKEN",
        "COLLATERAL_PRECISION",
        "AMM",
        "A",
        "Aminus1",
        "LOG2_A_RATIO",
        "SQRT_BAND_RATIO",
    )

    def __init__(
        self,
        collateral_token: str,
        loan_discount: int,
        liquidation_discount: int,
        amm: LLAMMAPool,
        monetary_policy: str = None,
    ):
        """
        Controller constructor deployed by the factory from blueprint

        Parameters
        ----------
        collateral_token : str
            Token to use for collateral (address)
        monetary_policy : RatePolicy
            AggMonetaryPolicy - monetary policy based on aggregated
            prices for crvUSD
        loan_discount : int
            Discount of the maximum loan size compare to get_x_down() value
        liquidation_discount : int
            Discount of the maximum loan size compare to
            get_x_down() for "bad liquidation" purposes
        amm : LLAMMAPool
            LLAMMA - crvUSD AMM

        """

        self.loan = defaultdict(Loan)
        self.liquidation_discounts = defaultdict(int)
        self._total_debt = Loan()

        self.loans: List[str] = [] # address[]
        self.loan_ix = defaultdict(int) # HashMap[address, uint256]
        self.n_loans = 0

        self.minted = 0
        self.redeemed = 0
        
        if monetary_policy is not None:
            self.monetary_policy = monetary_policy

        self.liquidation_discount = liquidation_discount
        self.loan_discount = loan_discount
        self._total_debt.rate_mul = 10**18

        if amm is not None:
            self.AMM = amm
        
        self.A = self.AMM.A
        self.Aminus1 = self.AMM.Aminus1

        A_ratio = 10**18 * self.A // (self.A - 1)
        self.LOG_A_RATIO = ln_int(A_ratio)
        self.SQRT_BAND_RATIO = isqrt(A_ratio * 10**18)

        self.COLLATERAL_TOKEN: str = self.AMM.COLLATERAL_TOKEN
        self.COLLATERAL_PRECISION: int = self.AMM.COLLATERAL_PRECISION

    
    def _rate_mul_w(self) -> int:
        """
        @notice Getter for rate_mul (the one which is 1.0+) from the AMM
        """
        rate: int = min(self.monetary_policy.rate_write(), MAX_RATE)
        return self.AMM.set_rate(rate)


    def _debt(self, user: str) -> Tuple[int, int]:
        """
        @notice Get the value of debt and rate_mul and update the rate_mul counter
        @param user User address
        @return (debt, rate_mul)
        """
        rate_mul: int = self._rate_mul_w()
        loan: Loan = self.loan[user]
        if loan.initial_debt == 0:
            return (0, rate_mul)
        else:
            return (loan.initial_debt * rate_mul // loan.rate_mul, rate_mul)


    def _debt_ro(self, user: str) -> int:
        """
        @notice Get the value of debt without changing the state
        @param user User address
        @return Value of debt
        """
        rate_mul: int = self.AMM.get_rate_mul()
        loan: Loan = self.loan[user]
        if loan.initial_debt == 0:
            return 0
        else:
            return loan.initial_debt * rate_mul // loan.rate_mul