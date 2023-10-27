from math import isqrt
from typing import List
from curvesim.pool.snapshot import SnapshotMixin
from crvusdsim.pool.crvusd.LLAMMA import DEAD_SHARES, LLAMMAPool
from crvusdsim.pool.crvusd.clac import log2
from crvusdsim.pool.crvusd.controller import Controller
from crvusdsim.pool.crvusd.vyper_func import unsafe_div, unsafe_sub


class SimController(Controller):
    """
    Class to enable use of Controller in simulations by exposing
    a generic interface (`SimController`).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
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

    def prepare_for_trades(self, timestamp):
        """
        Updates the controller's _block_timestamp attribute to current sim time.

        Parameters
        ----------
        timestamp : datetime.datetime
            The current timestamp in the simulation.
        """

        if isinstance(timestamp, float):
            timestamp = int(timestamp)
        if not isinstance(timestamp, int):
            timestamp = int(timestamp.timestamp())  # unix timestamp in seconds
        self._increment_timestamp(timestamp=timestamp)

    def prepare_for_run(self, prices):
        """
        Sets init _block_timestamp attribute to current sim time.

        Parameters
        ----------
        prices : pandas.DataFrame
            The price time_series, price_sampler.prices.
        """
        # Get/set initial prices
        init_ts = int(prices.index[0].timestamp())
        self._increment_timestamp(timestamp=init_ts)

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
