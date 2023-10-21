"""
Mainly a module to house the `Curve Stablecoin`, a Controller implementation in Python.
"""
from cmath import sqrt
from collections import defaultdict
from typing import Callable, List, Tuple
from math import floor, isqrt, log as math_log

from curvesim.pool.snapshot import SnapshotMixin

from crvusdsim.pool.crvusd.stablecoin import StableCoin

from .LLAMMA import LLAMMAPool
from .clac import ln_int, log2
from .vyper_func import (
    shift,
    unsafe_add,
    unsafe_div,
    unsafe_mul,
    unsafe_sub,
)

MAX_LOAN_DISCOUNT = 5 * 10**17
MIN_LIQUIDATION_DISCOUNT = 10**16  # Start liquidating when threshold reached
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
    def __init__(self, user: str, x: int, y: int, debt: int, health: int):
        self.user = user
        self.x = x
        self.y = y
        self.debt = debt
        self.health = health


class CallbackData:
    def __init__(self):
        self.active_band = 0
        self.stablecoins = 0
        self.collateral = 0


class Controller(SnapshotMixin):  # pylint: disable=too-many-instance-attributes
    """Controller implementation in Python."""

    snapshot_class = None

    __slots__ = (
        "address",
        "STABLECOIN",
        "FACTORY",
        "collateral_token",
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
        stablecoin: StableCoin,
        factory: any,
        collateral_token: any,
        loan_discount: int,
        liquidation_discount: int,
        amm: LLAMMAPool,
        monetary_policy: any = None,
        address: str = None,
        n_loans: int = 0,
        debt_ceiling: int = 5 * 10**24,
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

        self.address = (
            address if address is not None else "Controller_%s" % (collateral_token)
        )
        self.collateral_token = collateral_token
        self.STABLECOIN = stablecoin
        self.FACTORY = factory

        self.loan = defaultdict(Loan)
        self.liquidation_discounts = defaultdict(int)
        self._total_debt = Loan()

        self.loans = defaultdict(str)  # address[]
        self.loan_ix = defaultdict(int)  # HashMap[address, uint256]
        self.n_loans = n_loans

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

        self.SQRT_BAND_RATIO = isqrt(
            unsafe_div(10**36 * self.A, unsafe_sub(self.A, 1))
        )
        self.LOG2_A_RATIO = log2(self.A * 10**18 // unsafe_sub(self.A, 1))

        self.COLLATERAL_TOKEN: str = self.AMM.COLLATERAL_TOKEN
        self.COLLATERAL_PRECISION: int = self.AMM.COLLATERAL_PRECISION

        # @todo set debt ceiling
        # if debt_ceiling > 0:
        #     self.STABLECOIN._mint(self.address, debt_ceiling)

    def _rate_mul_w(self) -> int:
        """
        Getter for rate_mul (the one which is 1.0+) from the AMM

        """
        rate: int = min(self.monetary_policy.rate_write(self), MAX_RATE)
        return self.AMM.set_rate(rate)

    def _debt(self, user: str) -> Tuple[int, int]:
        """
        Get the value of debt and rate_mul and update the rate_mul counter

        Parameters
        ----------
        user : str
            Address of the user
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
        Get the value of debt without changing the state

        Parameters
        ----------
        user : str
            User address

        Returns
        -------
        int
            Value of debt
        """
        rate_mul: int = self.AMM.get_rate_mul()
        loan: Loan = self.loan[user]
        if loan.initial_debt == 0:
            return 0
        else:
            return loan.initial_debt * rate_mul // loan.rate_mul

    def debt(self, user: str) -> int:
        """
        Get the value of debt without changing the state

        Parameters
        ----------
        user : str
            User address

        Returns
        -------
        Value of debt
        """
        return self._debt_ro(user)

    def loan_exists(self, user: str) -> bool:
        """
        Check whether there is a loan of `user` in existence

        Parameters
        ----------
        user : str
            User address

        Returns
        -------
        bool
            whether there is a loan of `user` in existence
        """
        return self.loan[user].initial_debt > 0

    # No decorator because used in monetary policy
    def total_debt(self) -> int:
        """
        Total debt of this controller
        """
        rate_mul: int = self.AMM.get_rate_mul()
        loan: Loan = self._total_debt
        return loan.initial_debt * rate_mul // loan.rate_mul

    def get_y_effective(self, collateral: int, N: int, discount: int) -> int:
        """
        Intermediary method which calculates y_effective defined as x_effective / p_base,
        however discounted by loan_discount.
        x_effective is an amount which can be obtained from collateral when liquidating

        Parameters
        ----------
        collateral : int
            Amount of collateral to get the value for
        N : int
            Number of bands the deposit is made into
        discount : int
            Loan discount at 1e18 base (e.g. 1e18 == 100%)

        Returns
        -------
        int
            y_effective
        """
        # x_effective = sum_{i=0..N-1}(y / N * p(n_{n1+i})) =
        # = y / N * p_oracle_up(n1) * sqrt((A - 1) / A) * sum_{0..N-1}(((A-1) / A)**k)
        # === d_y_effective * p_oracle_up(n1) * sum(...) === y_effective * p_oracle_up(n1)
        # d_y_effective = y / N / sqrt(A / (A - 1))
        # d_y_effective: uint256 = collateral * unsafe_sub(10**18, discount) / (SQRT_BAND_RATIO * N)
        # Make some extra discount to always deposit lower when we have DEAD_SHARES rounding
        d_y_effective: int = (
            collateral
            * unsafe_sub(
                10**18,
                min(
                    discount
                    + (DEAD_SHARES * 10**18) // max(collateral // N, DEAD_SHARES),
                    10**18,
                ),
            )
            // (self.SQRT_BAND_RATIO * N)
        )
        print("\nd_y_effective01", d_y_effective)
        d_y_effective = int(collateral / N * ((10**18 - discount)) / isqrt(int(self.A * 10**18 / (self.A - 1))))
        print("\nd_y_effective02", d_y_effective)


        y_effective: int = d_y_effective
        for i in range(1, MAX_TICKS_UINT):
            if i == N:
                break
            d_y_effective = unsafe_div(d_y_effective * self.Aminus1, self.A)
            y_effective = unsafe_add(y_effective, d_y_effective)
        return y_effective

    def _calculate_debt_n1(self, collateral: int, debt: int, N: int) -> int:
        """
        Calculate the upper band number for the deposit to sit in to support
        the given debt. Reverts if requested debt is too high.

        Parameters
        ----------
        collateral : int
            Amount of collateral (at its native precision)
        debt : int
            Amount of requested debt
        N : int
            Number of bands to deposit into

        Returns
        -------
        int
            Upper band n1 (n1 <= n2) to deposit into. Signed integer
        """
        assert debt > 0, "No loan"
        n0: int = self.AMM.active_band
        p_base: int = self.AMM.p_oracle_up(n0)

        # x_effective = y / N * p_oracle_up(n1) * sqrt((A - 1) / A) * sum_{0..N-1}(((A-1) / A)**k)
        # === d_y_effective * p_oracle_up(n1) * sum(...) === y_effective * p_oracle_up(n1)
        # d_y_effective = y / N / sqrt(A / (A - 1))
        y_effective: int = self.get_y_effective(
            collateral * self.COLLATERAL_PRECISION, N, self.loan_discount
        )
        # p_oracle_up(n1) = base_price * ((A - 1) / A)**n1

        # We borrow up until min band touches p_oracle,
        # or it touches non-empty bands which cannot be skipped.
        # We calculate required n1 for given (collateral, debt),
        # and if n1 corresponds to price_oracle being too high, or unreachable band
        # - we revert.

        # n1 is band number based on adiabatic trading, e.g. when p_oracle ~ p
        y_effective = y_effective * p_base // (debt + 1)  # Now it's a ratio

        # n1 = floor(log2(y_effective) / self.logAratio)
        # EVM semantics is not doing floor unlike Python, so we do this
        assert y_effective > 0, "Amount too low"
        n1: int = log2(y_effective)  # <- switch to faster ln() XXX?
        if n1 < 0:
            n1 -= (
                self.LOG2_A_RATIO - 1
            )  # This is to deal with vyper's rounding of negative numbers
        n1 = n1 // self.LOG2_A_RATIO

        n1 = min(n1, 1024 - N) + n0
        if n1 <= n0:
            assert self.AMM.can_skip_bands(n1 - 1), "Debt too high"

        # Let's not rely on active_band corresponding to price_oracle:
        # this will be not correct if we are in the area of empty bands
        assert self.AMM.p_oracle_up(n1) < self.AMM.price_oracle(), "Debt too high"

        return n1

    def max_p_base(self) -> int:
        """
        Calculate max base price including skipping bands
        """
        p_oracle: int = self.AMM.price_oracle()
        # Should be correct unless price changes suddenly by MAX_P_BASE_BANDS+ bands
        n1: int = (
            unsafe_div(
                log2(self.AMM.get_base_price() * 10**18 // p_oracle),
                self.LOG2_A_RATIO,
            )
            + MAX_P_BASE_BANDS
        )
        p_base: int = self.AMM.p_oracle_up(n1)
        n_min: int = self.AMM.active_band_with_skip()

        for i in range(MAX_SKIP_TICKS + 1):
            n1 -= 1
            if n1 <= n_min:
                break
            p_base_prev: int = p_base
            p_base = unsafe_div(p_base * self.A, self.Aminus1)

            # @note A little price is subtracted here to offset the error caused by 
            # not using the same algorithm as the vyper code in _p_oracle_up
            if p_base > p_oracle - 10**6:
                return p_base_prev

        return p_base

    def max_borrowable(self, collateral: int, N: int, current_debt: int = 0) -> int:
        """
        Calculation of maximum which can be borrowed (details in comments)

        Parameters
        ----------
        collateral : int
            Collateral amount against which to borrow
        N : int
            number of bands to have the deposit into
        current_debt : int
            Current debt of the user (if any)

        Returns
        -------
        int
            Maximum amount of stablecoin to borrow
        """
        # Calculation of maximum which can be borrowed.
        # It corresponds to a minimum between the amount corresponding to price_oracle
        # and the one given by the min reachable band.
        #
        # Given by p_oracle (perhaps needs to be multiplied by (A - 1) / A to account for mid-band effects)
        # x_max ~= y_effective * p_oracle
        #
        # Given by band number:
        # if n1 is the lowest empty band in the AMM
        # xmax ~= y_effective * amm.p_oracle_up(n1)
        #
        # When n1 -= 1:
        # p_oracle_up *= A / (A - 1)

        y_effective: int = self.get_y_effective(
            collateral * self.COLLATERAL_PRECISION, N, self.loan_discount
        )

        x: int = unsafe_sub(
            max(unsafe_div(y_effective * self.max_p_base(), 10**18), 1), 1
        )
        x = unsafe_div(x * (10**18 - 10**14), 10**18)  # Make it a bit smaller

        return min(
            x, self.STABLECOIN.balanceOf[self.address] + current_debt
        )  # Cannot borrow beyond the amount of coins Controller has

    def min_collateral(self, debt: int, N: int) -> int:
        """
        Minimal amount of collateral required to support debt

        Parameters
        ----------
        debt : int
            The debt to support
        N : int
            Number of bands to deposit into

        Returns
        -------
        int
            Minimal collateral required
        """
        # Add N**2 to account for precision loss in multiple bands, e.g. N * 1 / (y/N) = N**2 / y
        return unsafe_div(
            unsafe_div(
                debt
                * 10**18
                / self.max_p_base()
                * 10**18
                / self.get_y_effective(10**18, N, self.loan_discount)
                + N * (N + 2 * DEAD_SHARES),
                self.COLLATERAL_PRECISION,
            )
            * 10**18,
            10**18 - 10**14,
        )

    def calculate_debt_n1(self, collateral: int, debt: int, N: int) -> int:
        """
        Calculate the upper band number for the deposit to sit in to support
        the given debt. Reverts if requested debt is too high.

        Parameters
        ----------
        collateral : int
            Amount of collateral (at its native precision)
        debt : int
            Amount of requested debt
        N : int
            Number of bands to deposit into

        Returns
        -------
        int
            Upper band n1 (n1 <= n2) to deposit into. Signed integer
        """
        return self._calculate_debt_n1(collateral, debt, N)

    def _deposit_collateral(self, amount: int, _receiver: str):
        """
        Deposits raw ETH, WETH or both at the same time
        """
        assert self.COLLATERAL_TOKEN.transferFrom(_receiver, self.AMM.address, amount)

    def _withdraw_collateral(self, amount: int, _receiver: str):
        assert self.COLLATERAL_TOKEN.transferFrom(self.AMM.address, _receiver, amount)
    
    def _transfer_stablecoin(self, _to: str, amount: int):
        if self.STABLECOIN.balanceOf[self.address] < amount:
            self.STABLECOIN._mint(self.address, amount)
        self.STABLECOIN.transfer(self.address, _to, amount)

    def execute_callback(
        self,
        callback: Callable,
        user: str,
        stablecoins: int,
        collateral: int,
        debt: int,
        **args
    ) -> CallbackData:
        data = CallbackData()
        data.active_band = self.AMM.active_band()
        band_x: int = self.AMM.bands_x(data.active_band)
        band_y: int = self.AMM.bands_y(data.active_band)

        # Callback
        (stablecoins, collateral) = callback(
            user, stablecoins, collateral, debt, **args
        )
        data.stablecoins = stablecoins
        data.collateral = collateral

        # Checks after callback
        assert data.active_band == self.AMM.active_band()
        assert band_x == self.AMM.bands_x(data.active_band)
        assert band_y == self.AMM.bands_y(data.active_band)

        return data

    def _create_loan(
        self,
        user: str,
        collateral: int,
        debt: int,
        N: int,
        transfer_coins: bool,
    ):
        assert self.loan[user].initial_debt == 0, "Loan already created"
        assert N > MIN_TICKS - 1, "Need more ticks"
        assert N < MAX_TICKS + 1, "Need less ticks"

        n1: int = self._calculate_debt_n1(collateral, debt, N)
        n2: int = n1 + N - 1

        rate_mul: int = self._rate_mul_w()
        self.loan[user].initial_debt = debt
        self.loan[user].rate_mul = rate_mul
        liquidation_discount: int = self.liquidation_discount
        self.liquidation_discounts[user] = liquidation_discount

        n_loans: int = self.n_loans
        self.loans[n_loans] = user
        self.loan_ix[user] = n_loans
        self.n_loans = unsafe_add(n_loans, 1)

        self._total_debt.initial_debt = (
            self._total_debt.initial_debt * rate_mul // self._total_debt.rate_mul + debt
        )
        self._total_debt.rate_mul = rate_mul

        self.AMM.deposit_range(user, collateral, n1, n2)
        self.minted += debt

        if transfer_coins:
            self._deposit_collateral(collateral, user)
            self._transfer_stablecoin(user, debt)

    def create_loan(self, user: str, collateral: int, debt: int, N: int):
        """
        Create loan

        Parameters
        ----------
        user: str
            user address
        collateral : int
            Amount of collateral to use
        debt : int
            Stablecoin debt to take
        N : int
            Number of bands to deposit into (to do autoliquidation-deliquidation),
            can be from MIN_TICKS to MAX_TICKS
        """
        self._create_loan(user, collateral, debt, N, True)

    def create_loan_extended(
        self,
        user: str,
        collateral: int,
        debt: int,
        N: int,
        callback: Callable,
        callback_args: List[int],
    ):
        """
        Create loan but pass stablecoin to a callback first so that it can build leverage

        Parameters
        ----------
        user: str
            user address
        collateral : int
            Amount of collateral to use
        debt : int
            Stablecoin debt to take
        N : int
            Number of bands to deposit into (to do autoliquidation-deliquidation),
            can be from MIN_TICKS to MAX_TICKS
        callback :
            callback function
        callback_args : List[int]
            Extra arguments for the callback (up to 5) such as min_amount etc
        """
        # Before callback
        self._transfer_stablecoin(user, debt)

        # Callback
        # If there is any unused debt, callbacker can send it to the user
        data: CallbackData = self.execute_callback(
            callback, user, 0, collateral, debt, callback_args
        )
        more_collateral: int = data.collateral

        # After callback
        self._create_loan(0, collateral + more_collateral, debt, N, False)
        self._deposit_collateral(collateral, user)

    def _add_collateral_borrow(
        self, d_collateral: int, d_debt: int, _for: str, remove_collateral: bool
    ):
        """
        Internal method to borrow and add or remove collateral

        Parameters
        ----------
        d_collateral : int
            Amount of collateral to add
        d_debt : int
            Amount of debt increase
        _for : str
            Address to transfer tokens to
        remove_collateral : bool
            Remove collateral instead of adding
        """
        debt: int = 0
        rate_mul: int = 0
        debt, rate_mul = self._debt(_for)
        assert debt > 0, "Loan doesn't exist"
        debt += d_debt
        ns: List[int] = self.AMM.read_user_tick_numbers(_for)
        size: int = unsafe_add(unsafe_sub(ns[1], ns[0]), 1)

        xy: List[int] = self.AMM.withdraw(_for, 10**18)
        assert xy[0] == 0, "Already in underwater mode"
        if remove_collateral:
            xy[1] -= d_collateral
        else:
            xy[1] += d_collateral
        n1: int = self._calculate_debt_n1(xy[1], debt, size)
        n2: int = n1 + unsafe_sub(ns[1], ns[0])

        self.AMM.deposit_range(_for, xy[1], n1, n2)
        self.loan[_for].initial_debt = debt
        self.loan[_for].rate_mul = rate_mul
        liquidation_discount: int = self.liquidation_discount
        self.liquidation_discounts[_for] = liquidation_discount

        if d_debt != 0:
            self._total_debt.initial_debt = (
                self._total_debt.initial_debt * rate_mul // self._total_debt.rate_mul
                + d_debt
            )
            self._total_debt.rate_mul = rate_mul

    def add_collateral(self, collateral: int, _for: str):
        """
        Add extra collateral to avoid bad liqidations

        Parameters
        ----------
        collateral : int
            Amount of collateral to add
        _for : str
            Address to add collateral for
        """
        if collateral == 0:
            return
        self._add_collateral_borrow(collateral, 0, _for, False)
        self._deposit_collateral(collateral, _for)

    def remove_collateral(self, user: str, collateral: int):
        """
        Remove some collateral without repaying the debt

        Parameters
        ----------
        user : str
            user address
        collateral : int
            Amount of collateral to remove
        use_eth : bool
            Use wrapping/unwrapping if collateral is ETH
        """
        if collateral == 0:
            return
        self._add_collateral_borrow(collateral, 0, user, True)
        self._withdraw_collateral(collateral, user)

    def borrow_more(self, user: str, collateral: int, debt: int):
        """
        Borrow more stablecoins while adding more collateral (not necessary)

        Parameters
        ----------
        user : str
            user address
        collateral : int
            Amount of collateral to add
        debt : int
            Amount of stablecoin debt to take
        """
        if debt == 0:
            return
        self._add_collateral_borrow(collateral, debt, user, False)
        self.minted += debt
        if collateral != 0:
            self._deposit_collateral(collateral, user)
        self._transfer_stablecoin(user, debt)

    def _remove_from_list(self, _for: str):
        last_loan_ix: int = self.n_loans - 1
        loan_ix: int = self.loan_ix[_for]
        assert self.loans[loan_ix] == _for  # dev: should never fail but safety first
        self.loan_ix[_for] = 0
        if loan_ix < last_loan_ix:  # Need to replace
            last_loan: str = self.loans[last_loan_ix]
            self.loans[loan_ix] = last_loan
            self.loan_ix[last_loan] = loan_ix
        self.n_loans = last_loan_ix

    def repay(
        self,
        _d_debt: int,
        _for: str,
        max_active_band: int = 2**255 - 1,
        use_eth: bool = True,
    ):
        """
        Repay debt (partially or fully)

        Parameters
        ----------
        _d_debt : int
            The amount of debt to repay. If higher than the current debt - will do full repayment
        _for : str
            The user to repay the debt for
        max_active_band : int
            Don't allow active band to be higher than this (to prevent front-running the repay)
        use_eth : bool
            Use wrapping/unwrapping if collateral is ETH
        """
        if _d_debt == 0:
            return
        # Or repay all for MAX_UINT256
        # Withdraw if debt become 0
        debt: int = 0
        rate_mul: int = 0
        debt, rate_mul = self._debt(_for)
        assert debt > 0, "Loan doesn't exist"
        d_debt: int = min(debt, _d_debt)
        debt = unsafe_sub(debt, d_debt)

        if debt == 0:
            # Allow to withdraw all assets even when underwater
            xy: int[2] = self.AMM.withdraw(_for, 10**18)

            if xy[0] > 0:
                self.STABLECOIN.transferFrom(self.AMM.address, _for, xy[0])

            if xy[1] > 0:
                self._withdraw_collateral(xy[1], _for)
            self._remove_from_list(_for)

        else:
            active_band: int = self.AMM.active_band_with_skip()
            assert active_band <= max_active_band

            ns: List[int] = self.AMM.read_user_tick_numbers(_for)
            size: int = unsafe_add(unsafe_sub(ns[1], ns[0]), 1)
            liquidation_discount: int = self.liquidation_discounts[_for]

            if ns[0] > active_band:
                # Not in liquidation - can move bands
                xy: int[2] = self.AMM.withdraw(_for, 10**18)
                n1: int = self._calculate_debt_n1(xy[1], debt, size)
                n2: int = n1 + unsafe_sub(ns[1], ns[0])
                self.AMM.deposit_range(_for, xy[1], n1, n2)
                # if _for == msg.sender:
                # Update liquidation discount only if we are that same user. No rugs
                liquidation_discount = self.liquidation_discount
                self.liquidation_discounts[_for] = liquidation_discount
            else:
                # Underwater - cannot move band but can avoid a bad liquidation
                # log UserState(_for, max_value(uint256), debt, ns[0], ns[1], liquidation_discount)
                # log Repay(_for, 0, d_debt)
                pass

            # if _for != msg.sender:
            # Doesn't allow non-sender to repay in a way which ends with unhealthy state
            # full = False to make this condition non-manipulatable (and also cheaper on gas)
            assert self._health(_for, debt, False, liquidation_discount) > 0

        # If we withdrew already - will burn less!
        assert self.STABLECOIN.transferFrom(
            _for, self.address, d_debt
        ), "fail: insufficient funds"
        self.redeemed += d_debt

        self.loan[_for].initial_debt = debt
        self.loan[_for].rate_mul = rate_mul
        total_debt: int = (
            self._total_debt.initial_debt * rate_mul // self._total_debt.rate_mul
        )
        self._total_debt.initial_debt = unsafe_sub(max(total_debt, d_debt), d_debt)
        self._total_debt.rate_mul = rate_mul

    def repay_extended(self, user: str, callback: Callable, callback_args: List[int]):
        """
        Repay loan but get a stablecoin for that from callback (to deleverage)

        Parameters
        ----------
        user : str
            user address
        callback : Callable
            Address of the callback contract
        callback_args : List[int]
            Extra arguments for the callback (up to 5) such as min_amount etc
        """
        # Before callback
        ns: List[int] = self.AMM.read_user_tick_numbers(user)
        xy: List[int] = self.AMM.withdraw(user, 10**18)
        debt: int = 0
        rate_mul: int = 0
        debt, rate_mul = self._debt(user)

        cb: CallbackData = self.execute_callback(
            callback, user, xy[0], xy[1], debt, callback_args
        )

        # After callback
        total_stablecoins: int = cb.stablecoins + xy[0]
        assert total_stablecoins > 0  # dev: no coins to repay

        # d_debt: uint256 = min(debt, total_stablecoins)

        d_debt: int = 0

        # If we have more stablecoins than the debt - full repayment and closing the position
        if total_stablecoins >= debt:
            d_debt = debt
            debt = 0
            self._remove_from_list(user)

            # Transfer debt to self, everything else to sender
            if cb.stablecoins > 0:
                self.STABLECOIN.transferFrom(user, self.address, cb.stablecoins)

            if xy[0] > 0:
                self.STABLECOIN.transferFrom(self.AMM.address, self.address, xy[0])
            if total_stablecoins > d_debt:
                self.STABLECOIN.transfer(
                    self.address, user, unsafe_sub(total_stablecoins, d_debt)
                )
            if cb.collateral > 0:
                # @todo assert self.COLLATERAL_TOKEN.transferFrom(callback, msg.sender, cb.collateral)
                pass

        # Else - partial repayment -> deleverage, but only if we are not underwater
        else:
            size: int = unsafe_add(unsafe_sub(ns[1], ns[0]), 1)
            assert ns[0] > cb.active_band
            d_debt = cb.stablecoins  # cb.stablecoins <= total_stablecoins < debt
            debt = unsafe_sub(debt, cb.stablecoins)

            # Not in liquidation - can move bands
            n1: int = self._calculate_debt_n1(cb.collateral, debt, size)
            n2: int = n1 + unsafe_sub(ns[1], ns[0])
            self.AMM.deposit_range(user, cb.collateral, n1, n2)
            liquidation_discount: int = self.liquidation_discount
            self.liquidation_discounts[user] = liquidation_discount

            assert self.COLLATERAL_TOKEN.transferFrom(
                user, self.AMM.address, cb.collateral
            )
            # Stablecoin is all spent to repay debt -> all goes to self
            self.STABLECOIN.transferFrom(user, self.address, cb.stablecoins)
            # We are above active band, so xy[0] is 0 anyway

            xy[1] -= cb.collateral

            # No need to check _health() because it's the sender

        # Common calls which we will do regardless of whether it's a full repay or not
        self.redeemed += d_debt
        self.loan[user].initial_debt = debt
        self.loan[user].rate_mul = rate_mul
        total_debt: int = (
            self._total_debt.initial_debt * rate_mul // self._total_debt.rate_mul
        )
        self._total_debt.initial_debt = unsafe_sub(max(total_debt, d_debt), d_debt)
        self._total_debt.rate_mul = rate_mul

    def _health(
        self, user: str, debt: int, full: bool, liquidation_discount: int
    ) -> int:
        """
        Returns position health normalized to 1e18 for the user.
        Liquidation starts when < 0, however devaluation of collateral doesn't cause liquidation

        Parameters
        ----------
        user : str
            User address to calculate health for
        debt : int
            The amount of debt to calculate health for
        full : bool
            Whether to take into account the price difference above the highest user's band
        liquidation_discount : str
            Liquidation discount to use (can be 0)

        Returns
        -------
        int
            Health: > 0 = good.
        """
        assert debt > 0, "Loan doesn't exist"
        health: int = 10**18 - liquidation_discount
        health = unsafe_div(self.AMM.get_x_down(user) * health, debt) - 10**18

        if full:
            ns0: int = self.AMM.read_user_tick_numbers(user)[0]  # ns[1] > ns[0]
            if ns0 > self.AMM.active_band:  # We are not in liquidation mode
                p: int = self.AMM.price_oracle()
                p_up: int = self.AMM.p_oracle_up(ns0)
                if p > p_up:
                    health += unsafe_div(
                        unsafe_sub(p, p_up)
                        * self.AMM.get_sum_xy(user)[1]
                        * self.COLLATERAL_PRECISION,
                        debt,
                    )

        return health

    def health_calculator(
        self, user: str, d_collateral: int, d_debt: int, full: bool, N: int = 0
    ) -> int:
        """
        Health predictor in case user changes the debt or collateral

        Parameters
        ----------
        user : str
            Address of the user
        d_collateral : int
            Change in collateral amount (signed)
        d_debt : int
            Change in debt amount (signed)
        full : bool
            Whether it's a 'full' health or not
        N : int
            Number of bands in case loan doesn't yet exist

        Returns
        -------
        int
            Signed health value
        """
        ns: List[int] = self.AMM.read_user_tick_numbers(user)
        debt: int = self._debt_ro(user)
        n: int = N
        ld: int = 0
        if debt != 0:
            ld = self.liquidation_discounts[user]
            n = unsafe_add(unsafe_sub(ns[1], ns[0]), 1)
        else:
            ld = self.liquidation_discount
            ns[0] = 2**256 - 1  # This will trigger a "re-deposit"

        n1: int = 0
        collateral: int = 0
        x_eff: int = 0
        debt += d_debt
        assert debt > 0, "Non-positive debt"

        active_band: int = self.AMM.active_band_with_skip()

        if ns[0] > active_band:  # re-deposit
            collateral = self.AMM.get_sum_xy(user)[1] + d_collateral
            n1 = self._calculate_debt_n1(collateral, debt, n)
            collateral *= self.COLLATERAL_PRECISION  # now has 18 decimals
        else:
            n1 = ns[0]
            x_eff = self.AMM.get_x_down(user) * 10**18

        p0: int = self.AMM.p_oracle_up(n1)
        if ns[0] > active_band:
            x_eff = self.get_y_effective(collateral, n, 0) * p0

        health: int = unsafe_div(x_eff, debt)
        health = health - unsafe_div(health * ld, 10**18) - 10**18

        if full:
            if n1 > active_band:  # We are not in liquidation mode
                p_diff: int = max(p0, self.AMM.price_oracle()) - p0
                if p_diff > 0:
                    health += unsafe_div(p_diff * collateral, debt)

        return health

    def _get_f_remove(self, frac: int, health_limit: int) -> int:
        # f_remove = ((1 + h / 2) / (1 + h) * (1 - frac) + frac) * frac
        f_remove: int = 10**18
        if frac < 10**18:
            f_remove = unsafe_div(
                unsafe_mul(
                    unsafe_add(10**18, unsafe_div(health_limit, 2)),
                    unsafe_sub(10**18, frac),
                ),
                unsafe_add(10**18, health_limit),
            )
            f_remove = unsafe_div(
                unsafe_mul(unsafe_add(f_remove, frac), frac), 10**18
            )

        return f_remove

    def _liquidate(
        self,
        liquidator: str,
        user: str,
        min_x: int,
        health_limit: int,
        frac: int,
        use_eth: bool,
        callback: Callable,
        callback_args: List[int],
    ):
        """
        Perform a bad liquidation of user if the health is too bad

        Parameters
        ----------
        liquidator : str
            Address of the liquidator (msg.sender)
        user : str
            Address of the user
        min_x : int
            Minimal amount of stablecoin withdrawn (to avoid liquidators being sandwiched)
        health_limit : int
            Minimal health to liquidate at
        frac : int
            Fraction to liquidate; 100% = 10**18
        use_eth : bool
            Use wrapping/unwrapping if collateral is ETH
        callback : Callable
            callback function
        callback_args : List[int]
            Extra arguments for the callback (up to 5) such as min_amount etc
        """
        debt: int = 0
        rate_mul: int = 0
        debt, rate_mul = self._debt(user)

        if health_limit != 0:
            assert self._health(user, debt, True, health_limit) < 0, "Not enough rekt"

        final_debt: int = debt
        debt = unsafe_div(debt * frac, 10**18)
        assert debt > 0
        final_debt = unsafe_sub(final_debt, debt)

        # Withdraw sender's stablecoin and collateral to our contract
        # When frac is set - we withdraw a bit less for the same debt fraction
        # f_remove = ((1 + h/2) / (1 + h) * (1 - frac) + frac) * frac
        # where h is health limit.
        # This is less than full h discount but more than no discount
        xy: List[int] = self.AMM.withdraw(
            user, self._get_f_remove(frac, health_limit)
        )  # [stable, collateral]

        # x increase in same block -> price up -> good
        # x decrease in same block -> price down -> bad
        assert xy[0] >= min_x, "Slippage"

        min_amm_burn: int = min(xy[0], debt)
        if min_amm_burn != 0:
            self.STABLECOIN.transferFrom(self.AMM.address, self.address, min_amm_burn)

        if debt > xy[0]:
            to_repay: int = unsafe_sub(debt, xy[0])

            if callback is None:
                # Withdraw collateral if no callback is present
                self._withdraw_collateral(xy[1], user)
                # Request what's left from user
                self.STABLECOIN.transferFrom(liquidator, self.AMM.address, to_repay)
            else:
                # @todo
                # # Move collateral to callbacker, call it and remove everything from it back in
                # if xy[1] > 0:
                #     assert self.COLLATERAL_TOKEN.transferFrom(self.AMM.address, liquidator, xy[1], default_return_value=True)
                # # Callback
                # cb: CallbackData = self.execute_callback(
                #     callback, user, xy[0], xy[1], debt, callback_args
                # )
                # assert cb.stablecoins >= to_repay, "not enough proceeds"
                # if cb.stablecoins > to_repay:
                #     self.STABLECOIN.transferFrom(callbacker, liquidator, unsafe_sub(cb.stablecoins, to_repay))
                # self.STABLECOIN.transferFrom(callbacker, self.address, to_repay)
                # if cb.collateral > 0:
                #     assert COLLATERAL_TOKEN.transferFrom(callbacker, msg.sender, cb.collateral)
                pass

        else:
            # Withdraw collateral
            self._withdraw_collateral(xy[1], user)
            # Return what's left to user
            if xy[0] > debt:
                self.STABLECOIN.transferFrom(
                    self.AMM.address, user, unsafe_sub(xy[0], debt)
                )

        self.redeemed += debt
        self.loan[user].initial_debt = final_debt
        self.loan[user].rate_mul = rate_mul
        if final_debt == 0:
            self._remove_from_list(user)

        d: int = self._total_debt.initial_debt * rate_mul // self._total_debt.rate_mul
        self._total_debt.initial_debt = unsafe_sub(max(d, debt), debt)
        self._total_debt.rate_mul = rate_mul

    def liquidate(self, liquidator: str, user: str, min_x: int, use_eth: bool = True):
        """
        Peform a bad liquidation (or self-liquidation) of user if health is not good

        Parameters
        ----------
        user : str
            Address of user
        min_x : int
            Minimal amount of stablecoin to receive (to avoid liquidators being sandwiched)
        use_eth : bool
            Use wrapping/unwrapping if collateral is ETH
        """
        discount: int = 0
        discount = self.liquidation_discounts[user]
        self._liquidate(liquidator, user, min_x, discount, 10**18, use_eth, None, [])

    def liquidate_extended(
        self,
        liquidator: str,
        user: str,
        min_x: int,
        frac: int,
        use_eth: bool,
        callback: Callable,
        callback_args: List[int],
    ):
        """
        Peform a bad liquidation (or self-liquidation) of user if health is not good

        Parameters
        ----------
        user : str
            Address of user
        min_x : int
            Minimal amount of stablecoin to receive (to avoid liquidators being sandwiched)
        frac : int
            Fraction to liquidate; 100% = 10**18
        use_eth : int
            Use wrapping/unwrapping if collateral is ETH
        callbacker : Callable
            Address of the callback contract
        callback_args : List[int]
            Extra arguments for the callback (up to 5) such as min_amount etc
        """
        discount: int = 0
        discount = self.liquidation_discounts[user]
        self._liquidate(
            liquidator,
            user,
            min_x,
            discount,
            min(frac, 10**18),
            use_eth,
            callback,
            callback_args,
        )

    def tokens_to_liquidate(self, user: str, frac: int = 10**18) -> int:
        """
        Calculate the amount of stablecoins to have in liquidator's wallet to liquidate a user

        Parameters
        ----------
        user : str
            Address of the user to liquidate
        frac : int
            Fraction to liquidate; 100% = 10**18

        Returns
        -------
        int
            The amount of stablecoins needed
        """
        health_limit: int = 0
        health_limit = self.liquidation_discounts[user]
        stablecoins: int = unsafe_div(
            self.AMM.get_sum_xy(user)[0] * self._get_f_remove(frac, health_limit),
            10**18,
        )
        debt: int = unsafe_div(self._debt_ro(user) * frac, 10**18)

        return unsafe_sub(max(debt, stablecoins), stablecoins)

    def health(self, user: str, full: bool = False) -> int:
        """
        Liquidation starts when < 0, however devaluation of collateral doesn't cause liquidation

        Parameters
        ----------
        user : str
            User address to calculate health for
        full : bool
            Whether to take into account the price difference above the highest user's band

        Returns
        -------
        int
            position health normalized to 1e18 for the user
        """
        return self._health(
            user, self._debt_ro(user), full, self.liquidation_discounts[user]
        )

    def users_to_liquidate(self, _from: int = 0, _limit: int = 0) -> List[Position]:
        """
        Returns a dynamic array of users who can be "hard-liquidated".
        This method is designed for convenience of liquidation bots.

        Parameters
        ----------
        _from : int
            Loan index to start iteration from
        _limit : int
            Number of loans to look over

        Returns
        -------
        List[Position]
            Dynamic array with detailed info about positions of users
        """
        n_loans: int = self.n_loans
        limit: int = _limit
        if _limit == 0:
            limit = n_loans
        ix: int = _from
        out: List[Position] = []
        for i in range(10**6):
            if ix >= n_loans or i == limit:
                break
            user: str = self.loans[ix]
            debt: int = self._debt_ro(user)
            health: int = self._health(
                user, debt, True, self.liquidation_discounts[user]
            )
            if health < 0:
                xy: int[2] = self.AMM.get_sum_xy(user)
                out.append(
                    Position(user=user, x=xy[0], y=xy[1], debt=debt, health=health)
                )
            ix += 1
        return out

    # AMM has a nonreentrant decorator
    def amm_price(self) -> int:
        """
        Current price from the AMM

        Returns
        -------
        int
        """
        return self.AMM.get_p()

    def user_prices(self, user: str) -> List[int]:  # Upper, lower
        """
        Lowest price of the lower band and highest price of the upper band the user has deposit in the AMM

        Parameters
        ----------
        user : str
            User address

        Returns
        -------
        List[int]
            (upper_price, lower_price)
        """
        assert self.AMM.has_liquidity(user)
        ns: List[int] = self.AMM.read_user_tick_numbers(user)  # ns[1] > ns[0]
        return [self.AMM.p_oracle_up(ns[0]), self.AMM.p_oracle_down(ns[1])]

    def user_state(self, user: str) -> List[int]:
        """
        Return the user state in one call

        Parameters
        ----------
        user : str
            User to return the state for

        Returns
        -------
        List[int]
            (collateral, stablecoin, debt, N)
        """
        xy: List[int] = self.AMM.get_sum_xy(user)
        ns: List[int] = self.AMM.read_user_tick_numbers(user)  # ns[1] > ns[0]
        return [
            xy[1],
            xy[0],
            self._debt_ro(user),
            unsafe_add(unsafe_sub(ns[1], ns[0]), 1),
        ]

    def set_amm_fee(self, fee: int):
        """
        Set the AMM fee (factory admin only)

        Parameters
        ----------
        fee : int
            The fee which should be no higher than MAX_FEE
        """
        # assert msg.sender == FACTORY.admin() @todo
        assert fee <= MAX_FEE and fee >= MIN_FEE, "Fee"
        self.AMM.set_fee(fee)

    # AMM has nonreentrant decorator
    def set_amm_admin_fee(self, fee: int):
        """
        Set AMM's admin fee

        Parameters
        ----------
        fee : int
            fee New admin fee (not higher than MAX_ADMIN_FEE)
        """
        # assert msg.sender == FACTORY.admin() @todo
        assert fee <= MAX_ADMIN_FEE, "High fee"
        self.AMM.set_admin_fee(fee)

    def set_monetary_policy(self, monetary_policy: any):
        """
        Set monetary policy contract

        Parameters
        ----------
        monetary_policy : MonetaryPolicy
            monetary policy contract
        """
        # assert msg.sender == FACTORY.admin()
        self.monetary_policy = monetary_policy
        monetary_policy.rate_write()

    def set_borrowing_discounts(self, loan_discount: int, liquidation_discount: int):
        """
        Set discounts at which we can borrow (defines max LTV) and where bad liquidation starts

        Parameters
        ----------
        loan_discount : int
            Discount which defines LTV
        liquidation_discount : int
            Discount where bad liquidation starts
        """
        # assert msg.sender == FACTORY.admin()
        assert loan_discount > liquidation_discount
        assert liquidation_discount >= MIN_LIQUIDATION_DISCOUNT
        assert loan_discount <= MAX_LOAN_DISCOUNT
        self.liquidation_discount = liquidation_discount
        self.loan_discount = loan_discount

    def set_callback(self, cb: str):
        """
        Set liquidity mining callback
        """
        # assert msg.sender == FACTORY.admin()
        self.AMM.set_callback(cb)

    def admin_fees(self) -> int:
        """
        Calculate the amount of fees obtained from the interest
        """
        rate_mul: int = self.AMM.get_rate_mul()
        loan: Loan = self._total_debt
        loan.initial_debt = (
            loan.initial_debt * rate_mul // loan.rate_mul + self.redeemed
        )
        minted: int = self.minted
        return unsafe_sub(max(loan.initial_debt, minted), minted)

    def collect_fees(self) -> int:
        """
        Collect the fees charged as interest
        """
        _to: str = self.FACTORY.fee_receiver
        # AMM-based fees
        borrowed_fees: int = self.AMM.admin_fees_x
        collateral_fees: int = self.AMM.admin_fees_y
        if borrowed_fees > 0:
            self.STABLECOIN.transferFrom(self.AMM.address, _to, borrowed_fees)
        if collateral_fees > 0:
            assert self.COLLATERAL_TOKEN.transferFrom(
                self.AMM.address, _to, collateral_fees, default_return_value=True
            )
        self.AMM.reset_admin_fees()

        # Borrowing-based fees
        rate_mul: int = self._rate_mul_w()
        loan: Loan = self._total_debt
        loan.initial_debt = loan.initial_debt * rate_mul / loan.rate_mul
        loan.rate_mul = rate_mul
        self._total_debt = loan

        # Amount which would have been redeemed if all the debt was repaid now
        to_be_redeemed: int = loan.initial_debt + self.redeemed
        # Amount which was minted when borrowing + all previously claimed admin fees
        minted: int = self.minted
        # Difference between to_be_redeemed and minted amount is exactly due to interest charged
        if to_be_redeemed > minted:
            self.minted = to_be_redeemed
            to_be_redeemed = unsafe_sub(
                to_be_redeemed, minted
            )  # Now this is the fees to charge
            self._transfer_stablecoin(_to, to_be_redeemed)
            return to_be_redeemed
        else:
            return 0
