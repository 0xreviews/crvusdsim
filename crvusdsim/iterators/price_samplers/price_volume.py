import os
from datetime import timedelta
from curvesim.exceptions import NetworkError
from curvesim.logging import get_logger
from curvesim.price_data import get
from curvesim.templates.price_samplers import PriceSample, PriceSampler
from curvesim.utils import dataclass, override
import pandas as pd

from crvusdsim.pool.crvusd.conf import ALIAS_TO_ADDRESS

from multiprocessing import Pool as cpu_pool

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
    peg_prices : dict
        Price for each peg coin combination.
    """

    volumes: dict
    peg_prices: dict


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
        ncpu=1,
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
        addresses = assets.addresses
        if assets.symbols[0] == "crvUSD":
            addresses.reverse()  # should reverse address here

        if src == "local":
            filename = (
                f"{assets.addresses[0].lower()}-{assets.addresses[1].lower()}.csv"
            )
            filepath = os.path.join(data_dir, filename)

            try:
                local_data = pd.read_csv(filepath, index_col=0)
                local_data.index = pd.to_datetime(local_data.index)

                prices = pd.DataFrame(local_data["price"])
                volumes = pd.DataFrame(local_data["volume"])

            except Exception:
                raise NetworkError("Load or parse local prices data faild.")

        else:
            # Over 60 days, the interval between price data returned
            # by Coingecko API will increase significantly.
            prices, volumes, _ = get(
                assets.addresses,  # [collateral_address, crvUSD_address]
                chain=assets.chain,
                days=days,
                data_dir=data_dir,
                src=src,
                end=end,
            )

        self.data_dir = data_dir
        self.assets = assets
        self.days = days
        self.src = src
        self.end = end
        self.max_interval = max_interval
        self.ncpu = ncpu
        self.original_prices = prices.dropna().set_axis(
            assets.symbol_pairs, axis="columns"
        )
        self.original_volumes = volumes.dropna().set_axis(
            assets.symbol_pairs, axis="columns"
        )

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

            peg_prices = None
            if self.peg_prices is not None:
                peg_prices = {}
                for symbol, price_data in self.peg_prices.items():
                    if price_timestamp in price_data.index:
                        peg_prices[symbol] = {
                            symbol: price_data[
                                price_data.index == price_timestamp
                            ].iloc[0, 0]
                        }
                    else:
                        peg_prices[symbol] = None

            yield PriceVolumeSample(price_timestamp, prices, volumes, peg_prices)

    def load_pegcoins_prices(
        self, src="coingecko", pegcoins=None, prices=None, volumes=None
    ):
        if prices is not None:
            self.peg_prices = prices
            self.peg_volumes = volumes
            return

        if src == "local":
            if pegcoins is None:
                self.peg_prices = None
                self.peg_volumes = None
            else:
                peg_prices = {}
                peg_volumes = {}
                for pegcoin_asset in pegcoins:
                    _addresses = pegcoin_asset.addresses
                    if _addresses[1].lower() == ALIAS_TO_ADDRESS["crvUSD"].lower():
                        filename = (
                            f"{_addresses[1].lower()}-{_addresses[0].lower()}.csv"
                        )
                    else:
                        filename = (
                            f"{_addresses[0].lower()}-{_addresses[1].lower()}.csv"
                        )

                    filepath = os.path.join(self.data_dir, filename)

                    try:
                        local_data = pd.read_csv(filepath, index_col=0)

                    except Exception:
                        raise NetworkError(
                            "Load or parse local pegcoin prices data faild."
                        )

                    _symbols = (pegcoin_asset.symbols[0], "crvUSD")
                    local_data.index = pd.to_datetime(local_data.index)
                    peg_prices[_symbols] = pd.DataFrame(local_data["price"])
                    peg_volumes[_symbols] = pd.DataFrame(local_data["volume"])

                self.peg_prices = peg_prices
                self.peg_volumes = peg_volumes
        else:
            if pegcoins is None:
                self.peg_prices = None
                self.peg_volumes = None
            else:
                self.query_peg_prices(pegcoins)

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

    def query_peg_prices(self, pegcoins):
        peg_prices = {}
        peg_volumes = {}
        if self.ncpu > 1:
            args_list = [
                (
                    pegcoin_asset,
                    self.assets.chain,
                    self.days,
                    self.data_dir,
                    self.src,
                    self.end,
                )
                for pegcoin_asset in pegcoins
            ]
            with cpu_pool(self.ncpu) as clust:
                results = clust.starmap(get_peg_prices, args_list)
                clust.close()
                clust.join()  # coverage needs this
            for _symbols, _prices, _volumes in results:
                peg_prices[_symbols] = _prices
                peg_volumes[_symbols] = _volumes

        else:
            for pegcoin_asset in pegcoins:
                _symbols, _prices, _volumes = get_peg_prices(
                    pegcoin_asset,
                    self.assets.chain,
                    self.days,
                    self.data_dir,
                    self.src,
                    self.end,
                )
                peg_prices[_symbols] = _prices
                peg_volumes[_symbols] = _volumes

        self.peg_prices = peg_prices
        self.peg_volumes = peg_volumes


def get_peg_prices(pegcoin_asset, chain, days, data_dir, src, end):
    _prices, _volumes, _ = get(
        pegcoin_asset.addresses,  # [pegcoin_address, crvUSD_address]
        chain=chain,
        days=days,
        data_dir=data_dir,
        src=src,
        end=end,
    )
    _symbols = (pegcoin_asset.symbols[0], "crvUSD")

    return (_symbols, _prices, _volumes)
