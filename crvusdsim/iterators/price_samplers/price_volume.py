from datetime import timedelta
from curvesim.logging import get_logger
from curvesim.price_data import get
from curvesim.templates.price_samplers import PriceSample, PriceSampler
from curvesim.utils import dataclass, override
import pandas as pd


logger = get_logger(__name__)


@dataclass(slots=True)
class PriceVolumeSample(PriceSample):
    """
    Attributes
    -----------
    timestamp : datetime.datetime
        Timestamp for the current price/volume.
    prices : dict
        Price for each pairwise coin combination.
    volumes : dict
        Volume for each pairwise coin combination.
    """

    volumes: dict


class PriceVolume(PriceSampler):
    """
    An iterator that retrieves price/volume and iterates over timepoints in the data.
    """

    def __init__(
        self,
        assets,
        *,
        days=60,
        max_interval=5 * 60,
        data_dir="data",
        src="coingecko",
        end=None,
    ):
        """
        Retrieves price/volume data and prepares it for iteration.

        Parameters
        ----------
        assets: SimAssets
            Object giving the properties of the assets for simulation
            (e.g., symbols, addresses, chain)

        days: int, defaults to 60
            Number of days to pull data for.

        max_interval: int, default to 5 * 60 s
            Number of max interval, this effect on ema oracle price.

        data_dir: str, defaults to "data"
            Relative path to saved data folder.

        src: str, defaults to "coingecko"
            Identifies pricing source: coingecko or local.

        """
        prices, volumes, _ = get(
            assets.addresses,
            chain=assets.chain,
            days=days,
            data_dir=data_dir,
            src=src,
            end=end,
        )

        # @remind
        prices = prices[:5000]

        self.assets = assets
        self.max_interval = max_interval
        self.original_prices = prices.set_axis(assets.symbol_pairs, axis="columns")
        self.original_volumes = volumes.set_axis(assets.symbol_pairs, axis="columns")

        self.insert_prices_volumes()

    @override
    def __iter__(self) -> PriceVolumeSample:
        """
        Yields
        -------
        :class:`PriceVolumeSample`
        """
        for price_row, volume_row in zip(
            self.prices.iterrows(), self.volumes.iterrows()
        ):
            price_timestamp, prices = price_row
            volume_timestamp, volumes = volume_row
            assert (
                price_timestamp == volume_timestamp
            ), "Price/volume timestamps don't match"

            prices = prices.to_dict()
            volumes = volumes.to_dict()

            yield PriceVolumeSample(price_timestamp, prices, volumes)

    def total_volumes(self):
        """
        Returns
        -------
        pandas.Series
            Total volume for each pairwise coin combination, summed accross timestamps.
        """
        return self.volumes.sum().to_dict()

    def insert_prices_volumes(self):

        last_ts = None
        last_price = None
        last_volume = None
        ts_list = []
        prices = []
        volumes = []
        for ts, _price, _volume in zip(
            self.original_prices.index,
            self.original_prices.iloc[:, 0].tolist(),
            self.original_volumes.iloc[:, 0].tolist(),
        ):
            if last_ts is None:
                last_ts = ts
                last_price = _price
                last_volume = _volume
            else:
                delta_ts = ts.timestamp() - last_ts.timestamp()
                if delta_ts > self.max_interval:
                    count = int(delta_ts // self.max_interval + 1)
                    if count > 1:
                        ts_interval = delta_ts / count
                        price_interval = (_price - last_price) / count
                        volume_interval = (_volume - last_volume) / count
                        for i in range(1, count):
                            ts_list.append(
                                last_ts + timedelta(seconds=int(i * ts_interval))
                            )
                            prices.append(last_price + i * price_interval)
                            volumes.append(last_volume + i * volume_interval)

            last_ts = ts
            last_price = _price
            last_volume = _volume

            ts_list.append(ts)
            prices.append(_price)
            volumes.append(_volume)

        self.prices = pd.DataFrame(
            prices, index=ts_list, columns=self.assets.symbol_pairs
        )
        self.volumes = pd.DataFrame(
            volumes, index=ts_list, columns=self.assets.symbol_pairs
        )

