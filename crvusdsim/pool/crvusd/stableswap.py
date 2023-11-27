"""
StableSwap
@notice 2 coin pool implementation with no lending
@dev ERC20 support for return True/revert, return True/False, return None
"""

from collections import defaultdict
from typing import List, Tuple, Type

from curvesim.pool.base import Pool
from curvesim.pool.snapshot import Snapshot
from curvesim.pool.stableswap.pool import CurvePool
from crvusdsim.pool.crvusd.stablecoin import StableCoin
from crvusdsim.pool.crvusd.clac import exp, shift
from crvusdsim.pool.crvusd.utils import BlocktimestampMixins
from crvusdsim.pool.crvusd.conf import ARBITRAGUR_ADDRESS
from crvusdsim.pool.snapshot import CurveStableSwapPoolSnapshot
from curvesim.utils import override

PRECISION = 10**18
A_PRECISION = 100
FEE_DENOMINATOR = 10**10
ADMIN_FEE = 5000000000

LP_PROVIDER = "LP_PROVIDER"


class CurveStableSwapPool(Pool, BlocktimestampMixins):

    snapshot_class: Type[Snapshot] = CurveStableSwapPoolSnapshot

    __slots__ = (
        "address",
        "name",
        "symbol",
        "A",
        "D",
        "n",
        "rates",
        "fee",
        "fee_mul",
        "admin_fee",
        "coins",
        "balances",
        "balanceOf",
        "totalSupply",
        "decimals",
        "coins",
        "precisions",
        "last_price",
        "ma_price",
        "ma_last_time",
        "ma_exp_time",
        "_block_timestamp",
    )

    def __init__(
        self,
        A,
        D,
        n,
        rates=None,
        fee=4 * 10**6,
        admin_fee=0 * 10**9,
        address: str = None,
        decimals=18,
        name: str = "crvUSD/USDC",
        symbol: str = "crvUSD-USDC",
        coins: List[StableCoin] = None,
    ):
        """
        Parameters
        ----------
        A : int
            Amplification coefficient; this is :math:`A n^{n-1}` in the whitepaper.
        D : int or list of int
            virtual total balance or pool coin balances in native token units
        n: int
            number of coins
        rates: list of int
            precision and rate adjustments
        fee: int, optional
            fee with 10**10 precision (default = .004%)
        fee_mul: optional
            fee multiplier for dynamic fee pools
        admin_fee: int, optional
            percentage of `fee` with 10**10 precision (default = 50%)
        address : str
            Address of pool
        name : str
            Name of pool (eg. "crvUSD/USDC")
        symbol : str
            Symbol of pool (eg. "crvUSD-USDC")
        coins : List[Stablecoin]
            [Pegged coin, crvUSD]
        """

        BlocktimestampMixins.__init__(self)

        rates = rates or [10**18] * n

        if isinstance(D, list):
            balances = D
        else:
            balances = [D // n * 10**18 // _p for _p in rates]

        self.A = A * A_PRECISION
        self.n = n
        self.fee = fee
        self.rates = rates
        self.balances = balances
        self.admin_fee = admin_fee
        self.admin_balances = [0] * n

        self.address = address if address is not None else "%s_stableswap" % (name)
        self.name = name
        self.symbol = symbol + "-f"
        self.coins = (
            coins
            if coins is not None
            else [
                StableCoin(
                    address="%s_address" % name.split("/")[0],
                    name="%s" % name.split("/")[0],
                    symbol="%s_address" % name.split("/")[0],
                    decimals=18,
                ),
                StableCoin(), # crvUSD
            ]
        )
        self.precisions = [10 ** (18 - coin.decimals) for coin in self.coins]

        self.last_price = 10**18
        self.ma_price = 10**18
        self.ma_last_time = self._block_timestamp
        self.ma_exp_time = 866  # = 600 / ln(2)

        self.balanceOf = defaultdict(int)
        self.totalSupply = self.get_D_mem(rates, balances, self.A)
        self.decimals = decimals

        # mint token for init liquidity
        for i in range(len(self.balances)):
            if self.balances[i] > 0:
                self.coins[i]._mint(self.address, self.balances[i])

    @property
    @override
    def coin_names(self):
        return [c.name for c in self.coins]

    @property
    @override
    def coin_addresses(self):
        return [c.address for c in self.coins]

    @property
    @override
    def coin_decimals(self):
        return [c.decimals for c in self.coins]

    def _xp_mem(self, _rates: List[int], _balances: List[int]) -> List[int]:
        result: List[int] = [0] * self.n
        for i in range(self.n):
            result[i] = _rates[i] * _balances[i] // PRECISION
        return result

    def _xp(self) -> List[int]:
        rates = self.rates
        balances = self.balances
        return self._xp_mem(rates, balances)

    def get_D(self, _xp: List[int], _amp: int) -> int:
        """
        D invariant calculation in non-overflowing integer operations
        iteratively

        A * sum(x_i) * n**n + D = A * D * n**n + D**(n+1) / (n**n * prod(x_i))

        Converging solution:
        D[j+1] = (A * n**n * sum(x_i) - D[j]**(n+1) / (n**n prod(x_i))) / (A * n**n - 1)

        Parameters
        ----------
        _xp : list of ints
            Coin balances in units of D
        _amp : int
            Value of A

        Returns
        -------
        int
            The stableswap invariant, `D`.
        """
        S: int = 0
        for x in _xp:
            S += x
        if S == 0:
            return 0

        D: int = S
        Ann: int = _amp * self.n
        for i in range(255):
            D_P: int = D * D // _xp[0] * D // _xp[1] // (self.n**self.n)
            Dprev: int = D
            D = (
                (Ann * S // A_PRECISION + D_P * self.n)
                * D
                // ((Ann - A_PRECISION) * D // A_PRECISION + (self.n + 1) * D_P)
            )
            # Equality with the precision of 1
            if D > Dprev:
                if D - Dprev <= 1:
                    return D
            else:
                if Dprev - D <= 1:
                    return D
        # convergence typically occurs in 4 rounds or less, this should be unreachable!
        # if it does happen the pool is borked and LPs can withdraw via `remove_liquidity`
        raise

    def get_D_mem(self, _rates: List[int], _balances: List[int], _amp: int) -> int:
        xp: List[int] = self._xp_mem(_rates, _balances)
        return self.get_D(xp, _amp)

    def _get_p(self, xp: List[int], amp: int, D: int) -> int:
        # dx_0 / dx_1 only, however can have any number of coins in pool
        ANN: int = amp * self.n
        Dr: int = D // (self.n**self.n)
        for i in range(self.n):
            Dr = Dr * D // xp[i]
        return (
            10**18
            * (ANN * xp[0] // A_PRECISION + Dr * xp[0] // xp[1])
            // (ANN * xp[0] // A_PRECISION + Dr)
        )

    def get_p(self) -> int:
        amp: int = self.A
        xp: List[int] = self._xp_mem(self.rates, self.balances)
        D: int = self.get_D(xp, amp)
        return self._get_p(xp, amp, D)

    def add_liquidity(
        self,
        _amounts: List[int],
        _receiver: str = LP_PROVIDER,
        _min_mint_amount: int = 0,
    ) -> int:
        """
        Deposit coin amounts for LP token.

        Parameters
        ----------
        _amounts: list of int
            Coin amounts to deposit
        _receiver : str
            Address of user

        Returns
        -------
        int
            LP token amount received for the deposit amounts.
        """
        amp: int = self.A
        old_balances: List[int] = self.balances.copy()
        rates: List[int] = self.rates

        # Initial invariant
        D0: int = self.get_D_mem(rates, old_balances, amp)

        total_supply: int = self.totalSupply
        new_balances: List[int] = old_balances.copy()
        for i in range(self.n):
            amount: int = _amounts[i]
            if amount > 0:
                assert self.coins[i].transferFrom(
                    _receiver, self.address, amount
                ), "failed transfer"
                new_balances[i] += amount
            else:
                assert total_supply != 0, "initial deposit requires all coins"

        # Invariant after change
        D1: int = self.get_D_mem(rates, new_balances, amp)
        assert D1 > D0

        # We need to recalculate the invariant accounting for fees
        # to calculate fair user's share
        fees: List[int] = [0] * self.n
        mint_amount: int = 0

        if total_supply > 0:
            # Only account for fees if we are not the first to deposit
            base_fee: int = self.fee * self.n // (4 * (self.n - 1))
            for i in range(self.n):
                ideal_balance: int = D1 * old_balances[i] // D0
                difference: int = 0
                new_balance: int = new_balances[i]
                if ideal_balance > new_balance:
                    difference = ideal_balance - new_balance
                else:
                    difference = new_balance - ideal_balance
                fees[i] = base_fee * difference // FEE_DENOMINATOR
                self.balances[i] = new_balance - (
                    fees[i] * ADMIN_FEE // FEE_DENOMINATOR
                )
                new_balances[i] -= fees[i]
            xp: List[int] = self._xp_mem(rates, new_balances)
            D2: int = self.get_D(xp, amp)
            mint_amount = total_supply * (D2 - D0) // D0
            self.save_p(xp, amp, D2)

        else:
            self.balances = new_balances
            mint_amount = D1  # Take the dust if there was any

        assert mint_amount >= _min_mint_amount, "Slippage screwed you"

        # Mint pool tokens
        self._mint(_receiver, mint_amount)

        return mint_amount

    def get_y(self, i: int, j: int, x: int, xp: List[int], _amp: int, _D: int) -> int:
        """
        Calculate x[j] if one makes x[i] = x

        Done by solving quadratic equation iteratively.
        x_1**2 + x_1 * (sum' - (A*n**n - 1) * D / (A * n**n)) = D ** (n + 1) / (n ** (2 * n) * prod' * A)
        x_1**2 + b*x_1 = c

        x_1 = (x_1**2 + c) / (2*x_1 + b)

        Parameters
        ----------
        i: int
            index of coin; usually the "in"-token
        j: int
            index of coin; usually the "out"-token
        x: int
            balance of i-th coin in units of D
        xp: list of int
            coin balances in units of D


        Returns
        -------
        int
            The balance of the j-th coin, in units of D, for the other
            coin balances given.
        """
        # x in the input is converted to the same price/precision

        assert i != j, "same coin"
        assert j >= 0, "j below zero"
        assert j < self.n, "j above self.n"

        # should be unreachable, but good for safety
        assert i >= 0
        assert i < self.n

        amp: int = _amp
        D: int = _D
        if _D == 0:
            amp = self.A
            D = self.get_D(xp, amp)
        S_: int = 0
        _x: int = 0
        y_prev: int = 0
        c: int = D
        Ann: int = amp * self.n

        for _i in range(self.n):
            if _i == i:
                _x = x
            elif _i != j:
                _x = xp[_i]
            else:
                continue
            S_ += _x
            c = c * D // (_x * self.n)

        c = c * D * A_PRECISION // (Ann * self.n)
        b: int = S_ + D * A_PRECISION // Ann  # - D
        y: int = D

        for _i in range(255):
            y_prev = y
            y = (y * y + c) // (2 * y + b - D)
            # Equality with the precision of 1
            if y > y_prev:
                if y - y_prev <= 1:
                    return y
            else:
                if y_prev - y <= 1:
                    return y
        raise

    def get_dy(self, i: int, j: int, dx: int) -> int:
        """
        Calculate the current output dy given input dx
        @dev Index values can be found via the `coins` public getter method

        Parameters
        ----------
        i : int
            Index value for the coin to send
        j : int
            Index valie of the coin to recieve
        dx : int
            Amount of `i` being exchanged

        Returns
        -------
        int
            Amount of `j` predicted
        """
        rates: List[int] = self.rates
        xp: List[int] = self._xp_mem(rates, self.balances)

        x: int = xp[i] + (dx * rates[i] // PRECISION)
        y: int = self.get_y(i, j, x, xp, 0, 0)
        dy: int = xp[j] - y - 1
        fee: int = self.fee * dy // FEE_DENOMINATOR
        return (dy - fee) * PRECISION // rates[j]

    def get_dx(self, i: int, j: int, dy: int) -> int:
        """
        Calculate the current input dx given output dy
        @dev Index values can be found via the `coins` public getter method

        Parameters
        ----------
        i : int
            Index value for the coin to send
        j : int
            Index valie of the coin to recieve
        dy : int
            Amount of `j` being received after exchange

        Returns
        -------
        int
            Amount of `i` predicted
        """
        rates: List[int] = self.rates
        xp: List[int] = self._xp_mem(rates, self.balances)

        y: int = xp[j] - (dy * rates[j] // PRECISION + 1) * FEE_DENOMINATOR // (
            FEE_DENOMINATOR - self.fee
        )
        x: int = self.get_y(j, i, y, xp, 0, 0)
        return (x - xp[i]) * PRECISION // rates[i]

    def exchange(
        self, i: int, j: int, _dx: int, _receiver: str = ARBITRAGUR_ADDRESS, _min_dy: int = 0
    ):
        """
        Perform an exchange between two coins.
        Index values can be found via the `coins` public getter method.

        Parameters
        ----------
        i : int
            Index of "in" coin.
        j : int
            Index of "out" coin.
        _dx : int
            Amount of coin `i` being exchanged.
        _receiver : str
            Address of _receiver

        Returns
        -------
        (int, int)
            (amount of coin `j` received, trading fee)
        """
        rates: List[int] = self.rates
        old_balances: List[int] = self.balances.copy()
        xp: List[int] = self._xp_mem(rates, old_balances)

        x: int = xp[i] + _dx * rates[i] // PRECISION

        amp: int = self.A
        D: int = self.get_D(xp, amp)
        y: int = self.get_y(i, j, x, xp, amp, D)

        dy: int = xp[j] - y - 1  # -1 just in case there were some rounding errors
        dy_fee: int = dy * self.fee // FEE_DENOMINATOR

        # Convert all to real units
        dy = (dy - dy_fee) * PRECISION // rates[j]
        assert dy >= _min_dy, "Exchange resulted in fewer coins than expected"

        # xp is not used anymore, so we reuse it for price calc
        xp[i] = x
        xp[j] = y
        # D is not changed because we did not apply a fee
        self.save_p(xp, amp, D)

        dy_admin_fee: int = dy_fee * ADMIN_FEE // FEE_DENOMINATOR
        dy_admin_fee = dy_admin_fee * PRECISION // rates[j]

        # Change balances exactly in same way as we change actual ERC20 coin amounts
        self.balances[i] = old_balances[i] + _dx
        # When rounding errors happen, we undercharge admin fee in favor of LP
        self.balances[j] = old_balances[j] - dy - dy_admin_fee

        assert self.coins[i].transferFrom(
            _receiver, self.address, _dx
        ), "failed transfer"
        assert self.coins[j].transfer(self.address, _receiver, dy), "failed transfer"

        return dy

    def remove_liquidity(
        self, _burn_amount: int, _min_amounts: List[int], _receiver: str = LP_PROVIDER
    ) -> List[int]:
        """
        Withdraw coins from the pool
        @dev Withdrawal amounts are based on current deposit ratios

        Parameters
        ----------
        _burn_amount : int
            Quantity of LP tokens to burn in the withdrawal
        _min_amounts : List[int]
            Minimum amounts of underlying coins to receive
        _receiver : str
            Address that receives the withdrawn coins

        Returns
        -------
        List[int]
            List of amounts of coins that were withdrawn
        """
        total_supply: int = self.totalSupply
        amounts: List[int] = [0] * self.n

        for i in range(self.n):
            old_balance: int = self.balances[i]
            value: int = old_balance * _burn_amount // total_supply
            assert (
                value >= _min_amounts[i]
            ), "Withdrawal resulted in fewer coins than expected"
            self.balances[i] = old_balance - value
            amounts[i] = value
            # assert ERC20(self.coins[i]).transfer(_receiver, value, default_return_value=True)  # dev: failed transfer

        total_supply -= _burn_amount
        self.balanceOf[_receiver] -= _burn_amount
        self.totalSupply = total_supply

        for i in range(len(amounts)):
            assert self.coins[i].transfer(self.address, _receiver, amounts[i])

        return amounts

    def remove_liquidity_imbalance(
        self,
        _amounts: List[int],
        _max_burn_amount: int = 2**256 - 1,
        _receiver: str = LP_PROVIDER,
    ) -> int:
        """
        Withdraw coins from the pool in an imbalanced amount

        Parameters
        ----------
        _amounts : int
            List of amounts of underlying coins to withdraw
        _max_burn_amount : int
            Maximum amount of LP token to burn in the withdrawal
        _receiver : int
            Address that receives the withdrawn coins


        Returns
        -------
        int
            Actual amount of the LP token burned in the withdrawal
        """
        amp: int = self.A
        rates: List[int] = self.rates
        old_balances: List[int] = self.balances.copy()
        D0: int = self.get_D_mem(rates, old_balances, amp)

        new_balances: List[int] = old_balances
        for i in range(self.n):
            amount: int = _amounts[i]
            if amount != 0:
                new_balances[i] -= amount
                assert self.coins[i].transfer(self.address, _receiver, amount), "failed transfer"

        D1: int = self.get_D_mem(rates, new_balances, amp)

        fees: List[int] = [0] * self.n
        base_fee: int = self.fee * self.n // (4 * (self.n - 1))
        for i in range(self.n):
            ideal_balance: int = D1 * old_balances[i] // D0
            difference: int = 0
            new_balance: int = new_balances[i]
            if ideal_balance > new_balance:
                difference = ideal_balance - new_balance
            else:
                difference = new_balance - ideal_balance
            fees[i] = base_fee * difference // FEE_DENOMINATOR
            self.balances[i] = new_balance - (fees[i] * ADMIN_FEE // FEE_DENOMINATOR)
            new_balances[i] -= fees[i]
        new_balances = self._xp_mem(rates, new_balances)
        D2: int = self.get_D(new_balances, amp)

        self.save_p(new_balances, amp, D2)

        total_supply: int = self.totalSupply
        burn_amount: int = ((D0 - D2) * total_supply // D0) + 1
        assert burn_amount > 1, "zero tokens burned"
        assert burn_amount <= _max_burn_amount, "Slippage screwed you"

        self._burn(_receiver, burn_amount)

        return burn_amount

    def get_y_D(self, A: int, i: int, xp: List[int], D: int) -> int:
        """
        Calculate x[i] if one reduces D from being calculated for xp to D

        Done by solving quadratic equation iteratively.
        x_1**2 + x_1 * (sum' - (A*n**n - 1) * D / (A * n**n)) = D ** (n + 1) / (n ** (2 * n) * prod' * A)
        x_1**2 + b*x_1 = c

        x_1 = (x_1**2 + c) / (2*x_1 + b)

        Parameters
        ----------
        A : int
            Value of A
        i : int
            Index value for the coin to send
        xp : list of ints
            Coin balances in units of D
        D : int
            The stableswap invariant, `D`.

        Returns
        -------
        int
            calculated for xp to D
        """
        # x in the input is converted to the same price/precision

        assert i >= 0  # dev: i below zero
        assert i < self.n  # dev: i above N_COINS

        S_: int = 0
        _x: int = 0
        y_prev: int = 0
        c: int = D
        Ann: int = A * self.n

        for _i in range(self.n):
            if _i != i:
                _x = xp[_i]
            else:
                continue
            S_ += _x
            c = c * D // (_x * self.n)

        c = c * D * A_PRECISION // (Ann * self.n)
        b: int = S_ + D * A_PRECISION // Ann
        y: int = D

        for _i in range(255):
            y_prev = y
            y = (y * y + c) // (2 * y + b - D)
            # Equality with the precision of 1
            if y > y_prev:
                if y - y_prev <= 1:
                    return y
            else:
                if y_prev - y <= 1:
                    return y
        raise

    def _calc_withdraw_one_coin(self, _burn_amount: int, i: int) -> List[int]:
        # First, need to calculate
        # * Get current D
        # * Solve Eqn against y_i for D - _token_amount
        amp: int = self.A
        rates = self.rates
        xp = self._xp_mem(self.rates, self.balances)
        D0: int = self.get_D(xp, amp)

        total_supply: int = self.totalSupply
        D1: int = D0 - _burn_amount * D0 // total_supply
        new_y: int = self.get_y_D(amp, i, xp, D1)

        base_fee: int = self.fee * self.n // (4 * (self.n - 1))
        xp_reduced = [0] * self.n

        for j in range(self.n):
            dx_expected: int = 0
            xp_j: int = xp[j]
            if j == i:
                dx_expected = xp_j * D1 // D0 - new_y
            else:
                dx_expected = xp_j - xp_j * D1 // D0
            xp_reduced[j] = xp_j - base_fee * dx_expected // FEE_DENOMINATOR

        dy: int = xp_reduced[i] - self.get_y_D(amp, i, xp_reduced, D1)
        dy_0: int = (xp[i] - new_y) * PRECISION // rates[i]  # w/o fees
        dy = (
            (dy - 1) * PRECISION // rates[i]
        )  # Withdraw less to account for rounding errors

        xp[i] = new_y
        last_p: int = 0
        if new_y > 0:
            last_p = self.get_p()

        return [dy, dy_0 - dy, last_p]

    def calc_withdraw_one_coin(self, _burn_amount: int, i: int) -> int:
        """
        Calculate the amount received when withdrawing a single coin

        Parameters
        ----------
        _burn_amount : int
            Amount of LP tokens to burn in the withdrawal
        i : int
            Index value of the coin to withdraw

        Returns
        -------
        int
            Amount of coin received
        """
        return self._calc_withdraw_one_coin(_burn_amount, i)[0]

    def remove_liquidity_one_coin(
        self, _burn_amount, i, _receiver: str = LP_PROVIDER, _min_received: int = 0
    ) -> int:
        """
        Redeem given LP token amount for the i-th coin.

        Parameters
        ----------
        _burn_amount : int
            Amount of LP tokens to redeem
        i : int
            Index of coin to withdraw in
        _receiver : str
            Address of receiver

        Returns
        -------
        dy : int
            Amount of coin received
        """
        dy: List[int] = self._calc_withdraw_one_coin(_burn_amount, i)
        assert dy[0] >= _min_received, "Not enough coins removed"

        self.balances[i] -= dy[0] + dy[1] * ADMIN_FEE // FEE_DENOMINATOR
        total_supply: int = self.totalSupply - _burn_amount
        self.totalSupply = total_supply
        self.balanceOf[_receiver] -= _burn_amount

        assert self.coins[i].transfer(self.address, _receiver, dy[0]), "failed transfer"

        self.save_p_from_price(dy[2])

        return dy[0]

    def _get_p(self, xp: List[int], amp: int, D: int) -> int:
        # dx_0 / dx_1 only, however can have any number of coins in pool
        ANN: int = amp * self.n
        Dr: int = D // (self.n**self.n)
        for i in range(self.n):
            Dr = Dr * D // xp[i]
        return (
            10**18
            * (ANN * xp[0] // A_PRECISION + Dr * xp[0] // xp[1])
            // (ANN * xp[0] // A_PRECISION + Dr)
        )

    def get_p(self) -> int:
        amp: int = self.A
        xp = self._xp_mem(self.rates, self.balances)
        D: int = self.get_D(xp, amp)
        return self._get_p(xp, amp, D)

    def _ma_price(self) -> int:
        ma_last_time: int = self.ma_last_time

        last_price: int = min(self.last_price, 2 * 10**18)
        last_ema_price: int = self.ma_price

        if ma_last_time < self._block_timestamp:
            alpha: int = exp(
                -1
                * (self._block_timestamp - ma_last_time)
                * 10**18
                // self.ma_exp_time
            )
            return (
                last_price * (10**18 - alpha) + last_ema_price * alpha
            ) // 10**18

        else:
            return last_ema_price

    def price_oracle(self) -> int:
        return self._ma_price()

    def save_p_from_price(self, last_price: int):
        """
        Saves current price and its EMA
        """
        if last_price != 0:
            self.last_price = last_price
            self.ma_price = self._ma_price()
            if self.ma_last_time < self._block_timestamp:
                self.ma_last_time = self._block_timestamp

    def save_p(self, xp: List[int], amp: int, D: int):
        """
        Saves current price and its EMA
        """
        self.save_p_from_price(self._get_p(xp, amp, D))

    def get_virtual_price(self) -> int:
        """
        The current virtual price of the pool LP token
        @dev Useful for calculating profits

        Returns
        -------
        int
            LP token virtual price normalized to 1e18
        """
        amp: int = self.A
        xp: List[int] = self._xp_mem(self.rates, self.balances)
        D: int = self.get_D(xp, amp)
        # D is in the units similar to DAI (e.g. converted to precision 1e18)
        # When balanced, D = n * x_u - total virtual value of the portfolio
        return D * PRECISION // self.totalSupply

    def calc_token_amount(self, _amounts: List[int], _is_deposit: bool) -> int:
        """
        Calculate addition or reduction in token supply from a deposit or withdrawal

        Parameters
        ----------
        _amounts : int
            Amount of each coin being deposited
        _is_deposit : int
            set True for deposits, False for withdrawals

        Returns
        -------
        int
            Expected amount of LP tokens received
        """
        amp: int = self.A
        old_balances: List[int] = self.balances.copy()
        rates: List[int] = self.rates

        # Initial invariant
        D0: int = self.get_D_mem(rates, old_balances, amp)

        total_supply: int = self.totalSupply
        new_balances: List[int] = old_balances
        for i in range(self.n):
            amount: int = _amounts[i]
            if _is_deposit:
                new_balances[i] += amount
            else:
                new_balances[i] -= amount

        # Invariant after change
        D1: int = self.get_D_mem(rates, new_balances, amp)

        # We need to recalculate the invariant accounting for fees
        # to calculate fair user's share
        D2: int = D1
        if total_supply > 0:
            # Only account for fees if we are not the first to deposit
            base_fee: int = self.fee * self.n // (4 * (self.n - 1))
            for i in range(self.n):
                ideal_balance: int = D1 * old_balances[i] // D0
                difference: int = 0
                new_balance: int = new_balances[i]
                if ideal_balance > new_balance:
                    difference = ideal_balance - new_balance
                else:
                    difference = new_balance - ideal_balance
                new_balances[i] -= base_fee * difference // FEE_DENOMINATOR
            xp: List[int] = self._xp_mem(rates, new_balances)
            D2 = self.get_D(xp, amp)
        else:
            return D1  # Take the dust if there was any

        diff: int = 0
        if _is_deposit:
            diff = D2 - D0
        else:
            diff = D0 - D2
        return diff * total_supply // D0

    def transfer(self, _from: str, _to: str, _value: int) -> bool:
        """
        ERC20 transfer

        Parameters
        ----------
        _from : str
            Address of from user
        _to : str
            Address of to user
        _value : int
            transfer amount

        Returns
        -------
        bool
            wether transfering is success or not
        """
        assert self.balanceOf[_from] >= _value, "insufficient balance"
        self.balanceOf[_from] -= _value
        self.balanceOf[_to] += _value
        return True

    def transferFrom(self, _from: str, _to: str, _value: int) -> bool:
        """
        ERC20 transferFrom

        Parameters
        ----------
        _from : str
            Address of from user
        _to : str
            Address of to user
        _value : int
            transfer amount

        Returns
        -------
        bool
            wether transfering is success or not
        """
        assert self.balanceOf[_from] - _value >= 0, "insufficient balance"
        self.balanceOf[_from] -= _value
        self.balanceOf[_to] += _value
        # self.allowances[_from][msg.sender] -= _value
        return True

    def _mint(self, _to: str, _value: int):
        """
        ERC20 _mint

        Parameters
        ----------
        _to : str
            Address of to user
        _value : int
            mint amount
        """
        self.balanceOf[_to] += _value
        self.totalSupply += _value

    def _burn(self, _to: str, _value: int):
        """
        ERC20 _burn

        Parameters
        ----------
        _to : str
            Address of to user
        _value : int
            burn amount
        """
        assert self.balanceOf[_to] - _value >= 0, "insufficient balance"
        self.balanceOf[_to] -= _value
        self.totalSupply -= _value

    def get_A(self):
        return self.A // A_PRECISION
