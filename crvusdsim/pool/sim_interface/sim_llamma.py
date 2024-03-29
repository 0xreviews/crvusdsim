"""Module to house the `SimPool` extension of the `LLAMMAPool`."""

from collections import defaultdict
from math import isqrt
from typing import Tuple

from curvesim.exceptions import SimPoolError
from curvesim.templates import SimAssets
from curvesim.utils import cache, override
from curvesim.pool.sim_interface.asset_indices import AssetIndicesMixin
from crvusdsim.pool.crvusd.conf import ARBITRAGUR_ADDRESS

from crvusdsim.pool.crvusd.vyper_func import unsafe_div, unsafe_sub

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

        # The band liquidity ratio at both ends of the ending. Used to 
        # accurately calculate the PoolValue within the price fluctuation range.
        # will set in band_strategy
        self.min_band_liquidity_scale = 1
        self.max_band_liquidity_scale = 1


    @property
    @cache
    def asset_names(self):
        """Return list of asset names."""
        return self.coin_names

    @property
    def _asset_balances(self):
        """Return list of asset balances in same order as asset_names."""
        return [sum(self.bands_x), sum(self.bands_y)]
    
    @property
    @cache
    def rates(self):
        """Return list of precision and rate adjustments."""
        return [10**(36-int(d)) for d in self.coin_decimals]

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
        if coin_in == 0 or coin_in == "crvUSD":
            return p
        else:
            return 10**36 // p

    def trade(self, coin_in, coin_out, size, snapshot=True):
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
        if size == 0:
            return 0, 0, 0
            
        self._before_exchange(snapshot)

        # i, j = self.get_asset_indices(coin_in, coin_out)
        pump = coin_in == "crvUSD" or coin_in == 0
        i, j = 0, 1
        if not pump:
            i, j = 1, 0

        if i == 0:
            self.BORROWED_TOKEN._mint(ARBITRAGUR_ADDRESS, size)
        else:
            self.COLLATERAL_TOKEN._mint(ARBITRAGUR_ADDRESS, size)

        in_amount_done, out_amount_done, fees = self.exchange(i, j, size, min_amount=0)

        self._after_exchange(snapshot)

        return in_amount_done, out_amount_done, fees

    @override
    def prepare_for_trades(self, timestamp):
        """
        Updates the pool's _block_timestamp attribute to current sim time.

        Parameters
        ----------
        timestamp : datetime.datetime
            The current timestamp in the simulation.
        """
        super().prepare_for_trades(timestamp)
        self.price_oracle_contract._increment_timestamp(timestamp=timestamp)

    
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
        
        self.prev_p_o_time = init_ts
        self.rate_time = init_ts
        self.old_p_o = initial_price
        self.price_oracle_contract.set_price(initial_price)
        self.price_oracle_contract._price_oracle = initial_price
        self.price_oracle_contract._price_last = initial_price
        self.price_oracle_contract._increment_timestamp(timestamp=init_ts)
        self.price_oracle_contract.last_prices_timestamp = init_ts

        self.bands_x_benchmark = self.bands_x.copy()
        self.bands_y_benchmark = self.bands_y.copy()


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
            list(self.coin_names),
            list(self.coin_addresses),
            self.chain,
        )

    def _before_exchange(self, snapshot):
        if snapshot:
            self.last_active_band = self.active_band
            self.bands_x_snapshot_tmp = self.bands_x.copy()
            self.bands_y_snapshot_tmp = self.bands_y.copy()

    def _after_exchange(self, snapshot):
        if snapshot:
            index = self.last_active_band
            delta_i = -1 if self.active_band < self.last_active_band else 1
            snapshot = {}
            while True:
                snapshot[index] = {
                    "x": self.bands_x[index] - self.bands_x_snapshot_tmp[index],
                    "y": self.bands_y[index] - self.bands_y_snapshot_tmp[index],
                }
                index += delta_i
                if index == self.active_band + delta_i:
                    break

            self.bands_x_snapshot_tmp = None
            self.bands_y_snapshot_tmp = None
            self.bands_delta_snapshot[self._block_timestamp] = snapshot
            self.last_active_band = None
    
    def get_band_snapshot(self, index: int, timestamp=None):
        if timestamp is None:
            timestamp = max(self.bands_delta_snapshot.keys()) + 1
        
        x = self.bands_x[index]
        y = self.bands_y[index]

        for ts in self.bands_delta_snapshot:
            if ts >= timestamp:
                _snapshot = self.bands_delta_snapshot[ts]
                if index in _snapshot:
                    x -= _snapshot[index]["x"]
                    y -= _snapshot[index]["y"]
        
        return {
            "x": x,
            "y": y,
        }

    def get_band_xy_up(self, index: int, x: int, y: int, use_y: bool, p_o: int = None):
        if p_o is None:
            p_o = self.price_oracle()

        # p_o_up: int = self._p_oracle_up(n)
        p_o_up: int = self.p_oracle_up(index)
        # p_o_down = self._p_oracle_up(n + 1)
        p_o_down: int = self.p_oracle_down(index)

        if x == 0 and y == 0:
            return 0

        # Also this will revert if p_o_down is 0, and p_o_down is 0 if p_o_up is 0
        p_current_mid: int = unsafe_div(p_o**2 // p_o_down * p_o, p_o_up)

        # Cases when special conversion is not needed (to save on computations)
        if x == 0 or y == 0:
            if p_o > p_o_up:  # p_o < p_current_down
                # all to y at constant p_o, then to target currency adiabatically
                y_equiv: int = y
                if y == 0:
                    y_equiv = x * 10**18 // p_current_mid
                if use_y:
                    return y_equiv
                else:
                    return unsafe_div(y_equiv * p_o_up, self.SQRT_BAND_RATIO)

            elif p_o < p_o_down:  # p_o > p_current_up
                # all to x at constant p_o, then to target currency adiabatically
                x_equiv: int = x
                if x == 0:
                    x_equiv = unsafe_div(y * p_current_mid, 10**18)
                if use_y:
                    return unsafe_div(x_equiv * self.SQRT_BAND_RATIO, p_o_up)
                else:
                    return x_equiv

        y0: int = self._get_y0(x, y, p_o, p_o_up)
        f: int = unsafe_div(unsafe_div(self.A * y0 * p_o, p_o_up) * p_o, 10**18)
        g: int = unsafe_div(self.Aminus1 * y0 * p_o_up, p_o)
        # (f + x)(g + y) = const = p_top * A**2 * y0**2 = I
        Inv: int = (f + x) * (g + y)
        # p = (f + x) / (g + y) => p * (g + y)**2 = I or (f + x)**2 / p = I

        # First, "trade" in this band to p_oracle
        x_o: int = 0
        y_o: int = 0

        if p_o > p_o_up:  # p_o < p_current_down, all to y
            # x_o = 0
            y_o = unsafe_sub(max(Inv // f, g), g)
            if use_y:
                return y_o
            else:
                return unsafe_div(y_o * p_o_up, self.SQRT_BAND_RATIO)

        elif p_o < p_o_down:  # p_o > p_current_up, all to x
            # y_o = 0
            x_o = unsafe_sub(max(Inv // g, f), f)
            if use_y:
                return unsafe_div(x_o * self.SQRT_BAND_RATIO, p_o_up)
            else:
                return x_o

        else:
            # Equivalent from Chainsecurity (which also has less numerical errors):
            y_o = unsafe_div(self.A * y0 * unsafe_sub(p_o, p_o_down), p_o)
            # x_o = unsafe_div(A * y0 * p_o, p_o_up) * unsafe_sub(p_o_up, p_o)
            # Old math
            # y_o = unsafe_sub(max(isqrt(unsafe_div(Inv * 10**18, p_o)), g), g)
            x_o = unsafe_sub(max(Inv // (g + y_o), f), f)

            # Now adiabatic conversion from definitely in-band
            if use_y:
                return y_o + x_o * 10**18 // isqrt(p_o_up * p_o)

            else:
                return x_o + unsafe_div(y_o * isqrt(p_o_down * p_o), 10**18)

    def get_total_xy_up(self, use_y: bool = True):
        XY = 0
        for i in range(self.min_band, self.max_band + 1):
            x = self.bands_x[i]
            y = self.bands_y[i]
            XY += self.get_band_xy_up(i, x, y, use_y)
        return XY

    def get_sum_within_fluctuation_range(self):
        bands_x_sum = sum(self.bands_x.values())
        bands_y_sum = sum(self.bands_y.values())
        bands_x_benchmark = sum(self.bands_x_benchmark.values())
        bands_y_benchmark = sum(self.bands_y_benchmark.values())

        bands_x_sum -= self.bands_x[self.min_band] * (1 - self.min_band_liquidity_scale)
        bands_x_sum -= self.bands_x[self.max_band] * (1 - self.max_band_liquidity_scale)

        bands_y_sum -= self.bands_y[self.min_band] * (1 - self.min_band_liquidity_scale)
        bands_y_sum -= self.bands_y[self.max_band] * (1 - self.max_band_liquidity_scale)

        bands_x_benchmark -= self.bands_x_benchmark[self.min_band] * (1 - self.min_band_liquidity_scale)
        bands_x_benchmark -= self.bands_x_benchmark[self.max_band] * (1 - self.max_band_liquidity_scale)

        bands_y_benchmark -= self.bands_y_benchmark[self.min_band] * (1 - self.min_band_liquidity_scale)
        bands_y_benchmark -= self.bands_y_benchmark[self.max_band] * (1 - self.max_band_liquidity_scale)

        return bands_x_sum, bands_y_sum, bands_x_benchmark, bands_y_benchmark

    def get_max_trade_size(self, i: int, j: int) -> int:
        """
        Calculate an upper bound of coin we can swap
        "in" to the pool. The actual amount out done
        will be less than the `out` used here, given
        LLAMMA limits (such as `MAX_TICKS`).

        Parameters
        ----------
        i : int
            Index of "in" coin.
        j : int
            Index of "out" coin.

        Returns
        -------
        int
            The upper bound on "in" coin.
        """
        # Get absolute max amount we could get "out"
        if i == 0:
            out = sum(self.bands_y.values())
        else:
            out = sum(self.bands_x.values())

        _, in_amt_done, _ = self.get_dydx(i, j, out)
        return in_amt_done
