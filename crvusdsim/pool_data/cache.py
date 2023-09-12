from curvesim.exceptions import CurvesimValueError
from curvesim.logging import get_logger
from curvesim.network.subgraph import redemption_prices_sync as _redemption_prices
from curvesim.network.subgraph import volume_sync as _volume
from curvesim.pool_data.metadata.base import PoolMetaDataInterface

from .metadata import PoolMetaData

logger = get_logger(__name__)


class PoolDataCache:
    """
    Container for fetching and caching historical volume and redemption price data.

    Deprecation warning: this will likely be removed in a future release.
    """

    def __init__(self, metadata_dict, cache_data=False, days=60, end=None):
        """
        Parameters
        ----------
        metadata_dict : dict, :class:`PoolMetaDataInterface`
            Pool metadata in the format returned by
            :func:`curvesim.network.subgraph.pool_snapshot`.

        cache_data : bool, optional
            If True, fetches and caches historical volume and redemption price.

        days : int, default=60
            Number of days to pull data for if caching.

        """
        if isinstance(metadata_dict, dict):
            self.metadata = PoolMetaData(metadata_dict)
        elif isinstance(metadata_dict, PoolMetaDataInterface):
            self.metadata = metadata_dict
        else:
            raise CurvesimValueError(
                "Metadata must be of type dict or PoolMetaDataInterface."
            )

        self.days = days
        self.end = end

        self._cached_volume = None

        if cache_data:
            self.set_cache()

    def set_cache(self):
        """
        Fetches and caches historical volume and redemption price data.

        Parameters
        ----------
        days : int, default=60
            number of days to pull data for
        """
        self._cached_volume = self._get_volume()

    def clear_cache(self):
        """
        Clears any cached data.
        """
        self._cached_volume = None

    @property
    def volume(self):
        """
        Fetches the pool's historical volume over the specified number of days.

        Parameters
        ----------
        days : int, default=60
            Number of days to pull data for.

        store : bool, default=False
            If true, caches the fetched data.

        get_cache : bool, default=True
            If true, returns cached data when available.

        Returns
        -------
        numpy.ndarray
            Total volume summed across the specified number of days.

        """
        if self._cached_volume is not None:
            logger.info("Getting cached historical volume...")
            return self._cached_volume

        return self._get_volume()

    def _get_volume(self):
        logger.info("Fetching historical volume...")
        addresses = self.metadata.address
        chain = self.metadata.chain
        days = self.days
        end = self.end
        
        vol = _volume(addresses, chain, days=days, end=end)
        summed_vol = sum(vol)

        return summed_vol
