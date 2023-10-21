from typing import List
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
        y_per_band = collateral_amount // N
        ns: List[int] = [n1, n2]
        ticks: List[int] = [0] * N

        bands_x_snapshot = self.AMM.bands_x.copy()
        bands_y_snapshot = self.AMM.bands_y.copy()
        total_shares_snapshot = self.AMM.total_shares.copy()

        for i in range(N):
            band_index = n1 + i
            y: int = y_per_band
            if i == 0:
                y = collateral_amount * self.COLLATERAL_PRECISION - y * (N - 1)

            ds = unsafe_div(
                (self.AMM.total_shares[band_index] + DEAD_SHARES) * y,
                self.AMM.bands_y[band_index] + 1,
            )
            ticks[i] = ds
            self.AMM.total_shares[band_index] += ds
            self.AMM.bands_y[band_index] += y

        x_max = self.AMM._get_xy_up_by_ticks(ns, ticks, False)

        self.AMM.bands_x = bands_x_snapshot
        self.AMM.bands_y = bands_y_snapshot
        self.AMM.total_shares = total_shares_snapshot

        debt = int(x_max * (10**18 - self.loan_discount) // (10**18 + health))
        print("\nx_max", x_max / 1e18, debt / 1e18, "health", health / 1e18)

        return debt
