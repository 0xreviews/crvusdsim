"""Module to house the `SimPool` extension of the `LLAMMAPool`."""

from curvesim.exceptions import SimPoolError
from curvesim.templates import SimAssets
from curvesim.utils import cache, override
from curvesim.pool.sim_interface.asset_indices import AssetIndicesMixin

from ..crvusd.pool import LLAMMAPool


class SimLLAMMAPool(AssetIndicesMixin, LLAMMAPool):
    """
    Class to enable use of LLAMMAPool in simulations by exposing
    a generic interface (`SimPool`).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.bands_x = kwargs["bands_x"]
        self.bands_y = kwargs["bands_y"]

    @property
    @cache
    def asset_names(self):
        """Return list of asset names."""
        return self.coin_names

    @property
    def _asset_balances(self):
        """Return list of asset balances in same order as asset_names."""
        return self.balances  # @todo

    def price(self, coin_in, coin_out, use_fee=True):
        """
        Returns the spot price of `coin_in` quoted in terms of `coin_out`,
        i.e. the ratio of output coin amount to input coin amount for
        an "infinitesimally" small trade.

        Coin IDs should be strings but as a legacy feature integer indices
        corresponding to the pool implementation are allowed (caveat lector).

        Parameters
        ----------
        coin_in : str, int
            ID of coin to be priced; in a swapping context, this is
            the "in"-token.
        coin_out : str, int
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
        if coin_in == 0:
            return p
        else:
            return 10**36 // p

    def trade(self, coin_in, coin_out, size):
        """
        Perform an exchange between two coins.

        Coin IDs should be strings but as a legacy feature integer indices
        corresponding to the pool implementation are allowed (caveat lector).

        Note that all amounts are normalized to be in the same units as
        pool value, i.e. `XCP`.  This simplifies cross-token comparisons
        and creation of metrics.


        Parameters
        ----------
        coin_in : str, int
            ID of "in" coin.
        coin_out : str, int
            ID of "out" coin.
        size : int
            Amount of coin `i` being exchanged.

        Returns
        -------
        [in_amount_done, out_amount_done] : [int, int]
            Amount of coins given in/out
        """
        i, j = self.get_asset_indices(coin_in, coin_out)
        in_amount_done, out_amount_done = self.exchange(i, j, size, min_amount=0)
        return in_amount_done, out_amount_done

    @override
    def prepare_for_trades(self, timestamp):
        """
        Updates the pool's _block_timestamp attribute to current sim time.

        Parameters
        ----------
        timestamp : datetime.datetime
            The current timestamp in the simulation.
        """

        timestamp = int(timestamp.timestamp())  # unix timestamp in seconds
        self._increment_timestamp(timestamp=timestamp)

    def prepare_for_run(self, prices):
        """
        Sets price parameters to the first simulation price and updates
        balances to be equally-valued.

        Balances are updated so that xcp(D) is preserved, but D may change.

        Parameters
        ----------
        timestamp : pandas.DataFrame
            The price time_series, price_sampler.prices.
        """
        # Get/set initial prices
        initial_price = prices.iloc.tolist()[0]
        self.price_oracle_contract.set_price(initial_price)

    @property
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
