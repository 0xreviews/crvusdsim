"""Module to house the `SimPool` extension of the `LLAMMAPool`."""

from collections import defaultdict
from typing import Tuple

from curvesim.exceptions import SimPoolError
from curvesim.templates import SimAssets
from curvesim.utils import cache, override
from curvesim.pool.sim_interface.asset_indices import AssetIndicesMixin

from ..crvusd.LLAMMA import LLAMMAPool


class SimLLAMMAPool(AssetIndicesMixin, LLAMMAPool):
    """
    Class to enable use of LLAMMAPool in simulations by exposing
    a generic interface (`SimPool`).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.last_active_band = None
        self.bands_x_snapshot_tmp = None
        self.bands_y_snapshot_tmp = None

        self.bands_delta_snapshot = {}

    @property
    @cache
    def asset_names(self):
        """Return list of asset names."""
        return self.coin_names

    @property
    def _asset_balances(self):
        """Return list of asset balances in same order as asset_names."""
        return [sum(self.bands_x), sum(self.bands_y)]

    def price(self, coin_in, coin_out):
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
        self._before_exchange()

        i, j = self.get_asset_indices(coin_in, coin_out)

        if i == 0:
            self.BORROWED_TOKEN._mint("ARBITRAGUR", size)
        else:
            self.COLLATERAL_TOKEN._mint("ARBITRAGUR", size)

        in_amount_done, out_amount_done = self.exchange(i, j, size, min_amount=0)
        
        self._after_exchange()
        
        return in_amount_done, out_amount_done

    def prepare_for_trades(self, timestamp):
        """
        Updates the pool's _block_timestamp attribute to current sim time.

        Parameters
        ----------
        timestamp : datetime.datetime
            The current timestamp in the simulation.
        """

        if  isinstance(timestamp, float):
            timestamp = int(timestamp)
        if not isinstance(timestamp, int):
            timestamp = int(timestamp.timestamp())  # unix timestamp in seconds
        self._increment_timestamp(timestamp=timestamp)
        # self.prev_p_o_time = timestamp
        # self.rate_time = timestamp

    def prepare_for_run(self, prices):
        """
        Sets price parameters to the first simulation price and updates
        balances to be equally-valued.

        Parameters
        ----------
        timestamp : pandas.DataFrame
            The price time_series, price_sampler.prices.
        """
        # Get/set initial prices
        initial_price = int(prices.iloc[0, :].tolist()[0] * 10**18)
        self.price_oracle_contract.set_price(initial_price)
        ts = int(prices.index[0].timestamp())
        self.prev_p_o_time = ts
        self.rate_time = ts

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
        return SimAssets(
            list(reversed(self.coin_names)),
            list(reversed(self.coin_addresses)),
            self.chain,
        )
    
    def _before_exchange(self):
        self.last_active_band = self.active_band
        self.bands_x_snapshot_tmp = self.bands_x.copy()
        self.bands_y_snapshot_tmp = self.bands_y.copy()
        pass

    def _after_exchange(self):
        price = self.price_oracle()
        index = self.last_active_band
        delta_i = -1 if self.active_band < self.last_active_band else 1
        snapshot = {}
        while True:
            prev_value = self.bands_x_snapshot_tmp[index] + self.bands_y_snapshot_tmp[index] * price // 10**18
            after_value = self.bands_x[index] + self.bands_y[index] * price // 10**18
            loss = prev_value - after_value
            snapshot[index] = {
                "x": self.bands_x[index] - self.bands_x_snapshot_tmp[index],
                "y": self.bands_y[index] - self.bands_y_snapshot_tmp[index],
                "loss": loss,
                "loss_percent": loss / prev_value if prev_value > 0 else 0
            }
            index += delta_i
            if index == self.active_band + delta_i:
                break


        self.bands_x_snapshot_tmp = None
        self.bands_y_snapshot_tmp = None
        self.bands_delta_snapshot[self._block_timestamp] = snapshot
        self.last_active_band = None

    def get_total_y0(self):
        total_y0 = 0
        for i in range(self.min_band, self.max_band + 1):
            if self.bands_x[i] == 0:
                total_y0 += self.bands_y[i]
            else:
                x = self.bands_x[i]
                y = self.bands_y[i]
                p_o = self.price_oracle()
                p_o_up = self.p_oracle_up(i)
                total_y0 += self._get_y0(x, y, p_o, p_o_up)
        return total_y0
