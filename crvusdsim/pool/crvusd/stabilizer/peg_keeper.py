"""
Peg Keeper for pool with equal decimals of coins
"""

from collections import defaultdict
from typing import List

from ..stableswap import CurveStableSwapPool
from ..utils import BlocktimestampMixins
from ..controller_factory import ControllerFactory
from ..price_oracle.aggregate_stable_price import (
    AggregateStablePrice,
)

# Time between providing/withdrawing coins
ACTION_DELAY = 15 * 60
ADMIN_ACTIONS_DELAY = 3 * 86400

PRECISION = 10**18
# Calculation error for profit
PROFIT_THRESHOLD = 10**18
SHARE_PRECISION = 10**5


class PegKeeper(BlocktimestampMixins):
    __all__ = [
        "address",
        "POOL",
        "I",
        "PEGGED",
        "IS_INVERSE",
        "PEG_MUL",
        "AGGREGATOR",
        "last_change",
        "debt",
        "caller_share",
        "admin",
        "future_admin",
        "receiver",
        "future_receiver",
        "new_admin_deadline",
        "new_receiver_deadline",
        "FACTORY",
    ]

    def __init__(
        self,
        _pool: CurveStableSwapPool,
        _index: int,
        _caller_share: int,
        _factory: ControllerFactory,
        _aggregator: AggregateStablePrice,
        _address: str = None,
        _receiver: str = "",
        _admin: str = "",
        debt : int = 0,
    ):
        """
        Contract constructor

        Parameters
        ----------
        _pool : CurveStableSwapPool
            Contract pool address
        _index : int
            Index of the pegged
        _receiver : str
            Receiver of the profit
        _caller_share : int
            Caller's share of profit
        _factory : ControllerFactory
            Factory which should be able to take coins away
        _aggregator : AggregateStablePrice
            Price aggregator which shows the price of pegged in real "dollars"
        _admin : str
            Admin account
        """
        super().__init__()

        self.address = (
            _address if _address is not None else "%s_peg_keeper" % (_pool.name)
        )

        self.last_change = 0
        self.debt = 0
        self.caller_share = 0

        assert _index < 2
        self.POOL = _pool
        self.I = _index
        pegged: str = _pool.coins[_index]
        self.PEGGED = pegged

        self.PEG_MUL = _pool.precisions[1 - _index]

        self.admin = _admin
        # assert _receiver != empty(address)
        self.receiver = _receiver
        self.debt = debt

        assert _caller_share <= SHARE_PRECISION, "bad part value"
        self.caller_share = _caller_share

        self.new_admin_deadline = 0
        self.new_receiver_deadline = 0

        self.FACTORY = _factory
        self.AGGREGATOR = _aggregator
        self.IS_INVERSE = _index == 0

    def factory(self) -> str:
        return self.FACTORY

    def pegged(self) -> str:
        return self.PEGGED

    def pool(self) -> CurveStableSwapPool:
        return self.POOL

    def aggregator(self) -> AggregateStablePrice:
        return self.AGGREGATOR

    def _provide(self, _amount: int):
        # We already have all reserves here
        # ERC20(PEGGED).mint(self, _amount)
        if _amount == 0:
            return

        amounts: List[int] = [0, 0]
        amounts[self.I] = _amount
        self.POOL.add_liquidity(amounts, _receiver=self.address)

        self.last_change = self._block_timestamp

        self.debt += _amount

    def _withdraw(self, _amount: int):
        if _amount == 0:
            return

        debt: int = self.debt
        amount: int = min(_amount, debt)

        amounts: List[int] = [0, 0]
        amounts[self.I] = amount
        self.POOL.remove_liquidity_imbalance(amounts, _receiver=self.address)

        self.last_change = self._block_timestamp
        self.debt -= amount

    def _calc_profit(self) -> int:
        lp_balance: int = self.POOL.balanceOf[self.address]

        virtual_price: int = self.POOL.get_virtual_price()
        lp_debt: int = self.debt * PRECISION // virtual_price + PROFIT_THRESHOLD

        if lp_balance <= lp_debt:
            return 0
        else:
            return lp_balance - lp_debt

    def _calc_future_profit(self, _amount: int, _is_deposit: bool) -> int:
        lp_balance: int = self.POOL.balanceOf[self.address]
        debt: int = self.debt
        amount: int = _amount
        if not _is_deposit:
            amount = min(_amount, debt)

        amounts: List[int] = [0, 0]
        amounts[self.I] = amount
        lp_balance_diff: int = self.POOL.calc_token_amount(amounts, _is_deposit)

        if _is_deposit:
            lp_balance += lp_balance_diff
            debt += amount
        else:
            lp_balance -= lp_balance_diff
            debt -= amount

        virtual_price: int = self.POOL.get_virtual_price()
        lp_debt: int = debt * PRECISION // virtual_price + PROFIT_THRESHOLD

        if lp_balance <= lp_debt:
            return 0
        else:
            return lp_balance - lp_debt

    def calc_profit(self) -> int:
        """
        Calculate generated profit in LP tokens

        Returns
        -------
        int
            Amount of generated profit
        """
        return self._calc_profit()

    def estimate_caller_profit(self) -> int:
        """
        Estimate profit from calling update()
        @dev This method is not precise, real profit is always more because of increasing virtual price

        Returns
        -------
        int
            Expected amount of profit going to beneficiary
        """
        if self.last_change + ACTION_DELAY > self._block_timestamp:
            return 0

        balance_pegged: int = self.POOL.balances[self.I]
        balance_peg: int = self.POOL.balances[1 - self.I] * self.PEG_MUL

        initial_profit: int = self._calc_profit()

        p_agg: int = self.AGGREGATOR.price()  # Current USD per stablecoin

        # Checking the balance will ensure no-loss of the stabilizer, but to ensure stabilization
        # we need to exclude "bad" p_agg, so we add an extra check for it

        new_profit: int = 0
        if balance_peg > balance_pegged:
            if p_agg < 10**18:
                return 0
            new_profit = self._calc_future_profit(
                (balance_peg - balance_pegged) // 5, True
            )  # this dumps stablecoin

        else:
            if p_agg > 10**18:
                return 0
            new_profit = self._calc_future_profit(
                (balance_pegged - balance_peg) // 5, False
            )  # this pumps stablecoin

        if new_profit < initial_profit:
            return 0
        lp_amount: int = new_profit - initial_profit

        return lp_amount * self.caller_share // SHARE_PRECISION

    def update(self, _beneficiary: str) -> int:
        """
        Provide or withdraw coins from the pool to stabilize it

        Parameters
        ----------
        _beneficiary : str
            Beneficiary address

        Returns
        -------
        int
            Amount of profit received by beneficiary
        """
        if self.last_change + ACTION_DELAY > self._block_timestamp:
            return 0

        balance_pegged: int = self.POOL.balances[self.I]
        balance_peg: int = self.POOL.balances[1 - self.I] * self.PEG_MUL

        initial_profit: int = self._calc_profit()

        p_agg: int = self.AGGREGATOR.price()  # Current USD per stablecoin

        # Checking the balance will ensure no-loss of the stabilizer, but to ensure stabilization
        # we need to exclude "bad" p_agg, so we add an extra check for it

        if balance_peg > balance_pegged:
            assert p_agg >= 10**18
            self._provide((balance_peg - balance_pegged) // 5)  # this dumps stablecoin
        else:
            assert p_agg <= 10**18
            self._withdraw((balance_pegged - balance_peg) // 5)  # this pumps stablecoin

        # Send generated profit
        new_profit: int = self._calc_profit()
        assert new_profit >= initial_profit, "peg unprofitable"
        lp_amount: int = new_profit - initial_profit
        caller_profit: int = lp_amount * self.caller_share // SHARE_PRECISION
        if caller_profit > 0:
            self.POOL.transfer(self.address, _beneficiary, caller_profit)

        return caller_profit

    def set_new_caller_share(self, _new_caller_share: int):
        """
        Set new update caller's part

        Parameters
        ----------
        _new_caller_share : int
            Part with SHARE_PRECISION
        """
        # assert msg.sender == self.admin, "only admin"
        assert _new_caller_share <= SHARE_PRECISION, "bad part value"

        self.caller_share = _new_caller_share

    def withdraw_profit(self) -> int:
        """
        Withdraw profit generated by Peg Keeper

        Returns
        -------
        int
            Amount of LP Token received
        """
        lp_amount: int = self._calc_profit()
        self.POOL.transfer(self.receiver, lp_amount)

        return lp_amount

    def commit_new_admin(self, _new_admin: str):
        """
        Commit new admin of the Peg Keeper

        Parameters
        ----------
        _new_admin : str
            Address of the new admin
        """
        # assert msg.sender == self.admin, "only admin"
        assert self.new_admin_deadline == 0, "active action"

        deadline: int = self._block_timestamp + ADMIN_ACTIONS_DELAY
        self.new_admin_deadline = deadline
        self.future_admin = _new_admin

    def apply_new_admin(self):
        """
        Apply new admin of the Peg Keeper
        @dev Should be executed from new admin
        """
        new_admin: str = self.future_admin
        # assert msg.sender == new_admin, "only new admin"
        assert self._block_timestamp >= self.new_admin_deadline, "insufficient time"
        assert self.new_admin_deadline != 0, "no active action"

        self.admin = new_admin
        self.new_admin_deadline = 0

    def commit_new_receiver(self, _new_receiver: str):
        """
        Commit new receiver of profit

        Parameters
        ----------
        _new_receiver : str
            Address of the new receiver
        """
        # assert msg.sender == self.admin, "only admin"
        assert self.new_receiver_deadline == 0  # dev: active action

        deadline: int = self._block_timestamp + ADMIN_ACTIONS_DELAY
        self.new_receiver_deadline = deadline
        self.future_receiver = _new_receiver

    def apply_new_receiver(self):
        """
        @notice Apply new receiver of profit
        """
        assert self._block_timestamp >= self.new_receiver_deadline, "insufficient time"
        assert self.new_receiver_deadline != 0, "no active action"

        new_receiver: str = self.future_receiver
        self.receiver = new_receiver
        self.new_receiver_deadline = 0

    def revert_new_options(self):
        """
        Revert new admin of the Peg Keeper or new receiver
        @dev Should be executed from admin
        """
        # assert msg.sender == self.admin, "only admin"

        self.new_admin_deadline = 0
        self.new_receiver_deadline = 0
