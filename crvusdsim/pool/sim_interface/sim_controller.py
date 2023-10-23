from typing import List
from curvesim.pool.snapshot import SnapshotMixin
from crvusdsim.pool.crvusd.LLAMMA import DEAD_SHARES
from crvusdsim.pool.crvusd.controller import Controller
from crvusdsim.pool.crvusd.vyper_func import unsafe_div


class SimController(Controller):
    """
    Class to enable use of Controller in simulations by exposing
    a generic interface (`SimController`).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    

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
        
        print(self.health(user)/ 1e18, health / 1e18)
        while self.health(user) < health:
            self.repay(d_debt, user)
            # self.borrow_more(user, 0, d_debt)
            debt -= d_debt

        print("\nmax_debt", max_debt, "debt", debt, "health", self.health(user) / 1e18)

        self.AMM.revert_to_snapshot(pool_snapshot)
        self.revert_to_snapshot(controller_snapshot)

        return debt
