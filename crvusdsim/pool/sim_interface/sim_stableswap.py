from curvesim.templates import SimAssets
from curvesim.exceptions import SimPoolError
from curvesim.templates.sim_pool import SimPool
from curvesim.utils import cache, override
from curvesim.pool.sim_interface.asset_indices import AssetIndicesMixin
from crvusdsim.pool.crvusd.conf import ARBITRAGUR_ADDRESS

from ..crvusd.stableswap import CurveStableSwapPool


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
        return self.dydx(i, j, use_fee=use_fee)

    @override
    def trade(self, i, j, size, user=ARBITRAGUR_ADDRESS):
        """
        Perform an exchange between two coins.

        Coin IDs should be strings but as a legacy feature integer indices
        corresponding to the pool implementation are allowed (caveat lector).

        Note that all amounts are normalized to be in the same units as
        pool value, e.g. for Curve Stableswap pools, the same units as `D`.
        This simplifies cross-token comparisons and creation of metrics.


        Parameters
        ----------
        i : int
            ID of "in" coin.
        j : int
            ID of "out" coin.
        size : int
            Amount of coin `i` being exchanged.

        Returns
        -------
        (int, int)
            (amount of coin `j` received, trading fee)
        """
        if size == 0:
            return 0, 0
        self.coins[i]._mint(user, size)
        amount_out = self.exchange(i, j, size)
        return amount_out

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

        in_amount = self.get_y(j, i, xp_j, xp) - xp[i]
        return in_amount

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
