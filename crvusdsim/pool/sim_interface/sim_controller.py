from collections import defaultdict
from math import isqrt
from typing import List
from curvesim.utils import override
from crvusdsim.pool.crvusd.LLAMMA import DEAD_SHARES, LLAMMAPool
from crvusdsim.pool.crvusd.clac import log2
from crvusdsim.pool.crvusd.controller import Controller, Position
from crvusdsim.pool.crvusd.vyper_func import unsafe_div, unsafe_sub


DEFAULT_LIQUIDATOR = "default_liquidator"


class LiquidatedPosition:
    def __init__(
        self,
        user: str,
        initial_debt: int,
        init_collateral: int,
        health: int,
        liquidate_profits_x: int,
        liquidate_profits_y: int,
        ts: int,
    ):
        self.user = user
        self.initial_debt = initial_debt
        self.init_collateral = init_collateral
        self.health = health
        self.liquidate_profits_x = liquidate_profits_x
        self.liquidate_profits_y = liquidate_profits_y
        self.timestamp = ts


class SimController(Controller):
    """
    Class to enable use of Controller in simulations by exposing
    a generic interface (`SimController`).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # log user has been liquidated
        self.users_liquidated = defaultdict(LiquidatedPosition)

    def _rebind_pool(self, new_pool: LLAMMAPool, update_A: bool = False):
        """
        Rebind the AMM and token in the controller
        so that they point to the new pool copy.
        """
        # set debt ceiling
        debt_ceiling = self.STABLECOIN.balanceOf[self.address]
        if debt_ceiling > 0:
            new_pool.BORROWED_TOKEN._mint(self.address, debt_ceiling)

        self.AMM = new_pool
        self.STABLECOIN = new_pool.BORROWED_TOKEN
        self.A = new_pool.A
        self.Aminus1 = new_pool.Aminus1

        if update_A:
            self.SQRT_BAND_RATIO = isqrt(
                unsafe_div(10**36 * self.A, unsafe_sub(self.A, 1))
            )
            self.LOG2_A_RATIO = log2(self.A * 10**18 // unsafe_sub(self.A, 1))

        self.COLLATERAL_TOKEN: str = new_pool.COLLATERAL_TOKEN
        self.COLLATERAL_PRECISION: int = new_pool.COLLATERAL_PRECISION

    @override
    def prepare_for_trades(self, timestamp):
        """
        Updates the controller's _block_timestamp attribute to current sim time.

        Parameters
        ----------
        timestamp : datetime.datetime
            The current timestamp in the simulation.
        """
        super().prepare_for_trades(timestamp)
        self._rate_mul_w()

    @override
    def prepare_for_run(self, prices):
        """
        Sets init _block_timestamp attribute to current sim time.

        Parameters
        ----------
        prices : pandas.DataFrame
            The price time_series, price_sampler.prices.
        """
        super().prepare_for_run(prices)

    def after_trades(self, do_liquidate=False):
        if do_liquidate:
            users_to_liquidate = self.users_to_liquidate()
            for i in range(len(users_to_liquidate)):
                position = users_to_liquidate[i]
                self.liquidate_sim(position)

    def _before_liquidate(self, position: Position):
        user = position.user
        debt = self.debt(user)
        initial_debt = self.loan[user].initial_debt
        initial_collateral = self.loan[user].initial_collateral
        health = self.health(user)
        to_repay = debt - position.x
        self.users_liquidated[user] = LiquidatedPosition(
            user=user,
            initial_debt=initial_debt,
            init_collateral=initial_collateral,
            health=health,
            liquidate_profits_x=to_repay,
            liquidate_profits_y=position.y,
            ts=self._block_timestamp,
        )

    def liquidate_sim(self, position, liquidator=DEFAULT_LIQUIDATOR, min_x=0):
        """
        Sim interface for liquidation that mints necessary
        stablecoin.
        """
        to_repay = position.debt - position.x
        if to_repay > 0:
            self.STABLECOIN._mint(liquidator, to_repay)
        self._before_liquidate(position)
        self.liquidate(liquidator, position.user, min_x)

    def calc_debt_by_health(
        self, collateral_amount: int, n1: int, n2: int, health: int
    ):
        N: int = n2 - n1 + 1

        max_debt = self.max_borrowable(collateral_amount, N, 0)
        debt = max_debt
        d_debt = int(debt / 100)

        pool_snapshot = self.AMM.get_snapshot()
        controller_snapshot = self.get_snapshot()

        user = "user0"
        self.COLLATERAL_TOKEN._mint(user, collateral_amount)
        self.create_loan(user, collateral_amount, debt, N)

        while self.health(user) < health:
            self.repay(d_debt, user)
            # self.borrow_more(user, 0, d_debt)
            debt -= d_debt

        self.AMM.revert_to_snapshot(pool_snapshot)
        self.revert_to_snapshot(controller_snapshot)

        return debt
