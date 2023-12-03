from typing import Tuple
from curvesim.templates import SimAssets
from curvesim.exceptions import SimPoolError
from curvesim.templates.sim_pool import SimPool
from curvesim.utils import cache, override
from curvesim.pool.sim_interface.asset_indices import AssetIndicesMixin
from crvusdsim.pool.crvusd.conf import ARBITRAGUR_ADDRESS
from curvesim.exceptions import CurvesimValueError

from ..crvusd.stableswap import CurveStableSwapPool, PRECISION


class SimCurveStableSwapPool(SimPool, AssetIndicesMixin, CurveStableSwapPool):
    """
    Class to enable use of CurveStableSwapPool in simulations by exposing
    a generic interface (`SimPool`).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    @override
    @cache
    def asset_names(self):
        """Return list of asset names."""
        return self.coin_names

    @property
    @override
    def _asset_balances(self):
        """Return list of asset balances in same order as asset_names."""
        return self.balances

    @override
    def price(self, i, j, use_fee=True):
        """
        Returns the spot price of `coin_in` quoted in terms of `coin_out`,
        i.e. the ratio of output coin amount to input coin amount for
        an "infinitesimally" small trade.

        Coin IDs should be strings but as a legacy feature integer indices
        corresponding to the pool implementation are allowed (caveat lector).

        The indices are assumed to include base pool underlyer indices.

        Parameters
        ----------
        i : int
            ID of coin to be priced; in a swapping context, this is
            the "in"-token.
        j : int
            ID of quote currency; in a swapping context, this is the
            "out"-token.
        use_fee: bool, default=True
            Deduct fees.

        Returns
        -------
        float
            Price of `coin_in` quoted in `coin_out`
        """
        p = self.get_p()
        if j == 1 or j == "crvUSD":
            return p
        else:
            return 10**36 // p

    @override
    def trade(self, coin_in, coin_out, size, user=ARBITRAGUR_ADDRESS):
        """
        Perform an exchange between two coins.

        Coin IDs should be strings but as a legacy feature integer indices
        corresponding to the pool implementation are allowed (caveat lector).

        Note that all amounts are normalized to be in the same units as
        pool value, e.g. for Curve Stableswap pools, the same units as `D`.
        This simplifies cross-token comparisons and creation of metrics.


        Parameters
        ----------
        coin_in : int, str
            ID of "in" coin.
        coin_out : int, str
            ID of "out" coin.
        size : int
            Amount of coin `i` being exchanged.

        Returns
        -------
        (int, int)
            (amount of coin `j` received, trading fee)
        """
        if size == 0:
            return 0, 0, 0

        pump = coin_out == "crvUSD" or coin_in == 0

        i, j = 0, 1
        if not pump:
            i, j = 1, 0

        self.coins[i]._mint(user, size)
        amount_out, fees = self.exchange(i, j, size, _receiver=user)
        return (size, amount_out, fees)

    @override
    def get_max_trade_size(self, i, j, out_balance_perc=0.01):
        """
        Calculate the swap amount of the "in" coin needed to leave
        the specified percentage of the "out" coin.

        Parameters
        ----------
        i : int
            ID of "in" coin.
        j : int
            ID of "out" coin.
        out_balance_perc : float
            Percentage of the "out" coin balance that should remain
            after doing the swap.

        Returns
        -------
        int
            The amount of "in" coin needed.
        """
        xp = self._xp()
        xp_j = int(xp[j] * out_balance_perc)

        in_amount = self.get_y(j, i, xp_j, xp, 0, 0) - xp[i]
        return in_amount * PRECISION // self.rates[i]

    @override
    def get_min_trade_size(self, i):
        """
        Return the minimal trade size allowed for the pool.

        Parameters
        ----------
        i : int
            ID of "in" coin.

        Returns
        -------
        int
            The minimal trade size
        """
        return 0

    @property
    @override
    @cache
    def assets(self):
        """
        Return :class:`.SimAssets` object with the properties of the pool's assets.

        Returns
        -------
        SimAssets
            SimAssets object that stores the properties of the pool's assets.
        """
        return SimAssets(self.coin_names, self.coin_addresses, self.chain)

    def get_amount_for_price(self, target_price: int) -> Tuple[int, bool]:
        """
        Binary search to find the amount to trade to achieve the target price.

        Parameters
        ----------
        target_price : int
            The desired target price.

        Returns
        -------
        (amount_in, pump): Tuple[int, bool]
            A tuple containing the trade amount and trade direction.
        """
        current_price = self.get_p()
        pump = current_price <= target_price

        pool_snapshot = self.get_snapshot()

        if pump:
            i, j = 0, 1
        else:
            i, j = 1, 0

        # Tolerance for the target price
        epsilon = 10**12

        if abs(current_price - target_price) <= epsilon:
            self.revert_to_snapshot(pool_snapshot)
            return 0, True

        # Initial bounds for binary search
        lower_bound = 0
        upper_bound = sum(self._xp()) * 10**18 // self.rates[i]

        while lower_bound < upper_bound:
            amount = (lower_bound + upper_bound) // 2
            self.trade(i, j, amount)
            current_price = self.get_p()

            if abs(current_price - target_price) <= epsilon:
                self.revert_to_snapshot(pool_snapshot)
                return amount, pump

            if pump:
                adjust_flag = current_price < target_price
            else:
                adjust_flag = current_price > target_price

            if adjust_flag:
                lower_bound = amount + 1
            else:
                upper_bound = amount
            self.revert_to_snapshot(pool_snapshot)

        raise CurvesimValueError("get_amount_for_price faild.")

    @override
    def prepare_for_run(self, prices):
        """
        Sets price parameters to the first simulation price and updates
        balances to be equally-valued.

        Parameters
        ----------
        prices : pandas.DataFrame
            The price time_series, price_sampler.prices.
        """
        super().prepare_for_run(prices)
        # Get/set initial prices
        initial_price = int(prices.iloc[0, :].tolist()[0] * 10**18)
        init_ts = int(prices.index[0].timestamp())

        amount, pump = self.get_amount_for_price(initial_price)
        if pump:
            self.trade(0, 1, amount)
        else:
            self.trade(1, 0, amount)

        amm_p = self.get_p()
        assert abs(abs(amm_p / initial_price) - 1) < 1e-4

        self.last_price = amm_p
        self.ma_price = amm_p
        self.ma_last_time = init_ts

    def prepare_for_trades(self, timestamp):
        """
        Updates the pool's _block_timestamp attribute to current sim time.

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
