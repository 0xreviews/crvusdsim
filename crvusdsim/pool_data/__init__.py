"""
Tools for fetching pool state and metadata.

Currently supports stableswap pools, metapools, rebasing (RAI) metapools,
and 2-token cryptopools.
"""

__all__ = [
    "from_address",
    "get_data_cache",
    "get_metadata",
    "simple_bands_strategy",
]

import json
from crvusdsim.pool_data.cache import PoolDataCache

from crvusdsim.pool.sim_interface.llamma import SimLLAMMAPool
from crvusdsim.pool.crvusd import LLAMMAPool
from .metadata import MarketMetaData, simple_bands_strategy
from .queries import from_address


def get_data_cache(address, chain="mainnet", days=60, end=None):
    """
    Fetch historical volume and redemption price data and return
    in a cache object.

    Deprecation warning: this will likely be removed in a future release.

    Parameters
    ----------
    address : str
        Pool address prefixed with “0x”.

    chain : str
        Chain identifier, e.g. “mainnet”.

    Returns
    -------
    :class:`PoolDataCache`

    """
    # TODO: validate function arguments
    metadata_dict = from_address(address, chain, end_ts=end)
    pool_data = PoolDataCache(metadata_dict, days=days, end=end)

    return pool_data


def get_metadata(
    address,
    end_ts=None,
    save_dir=None,
):
    """
    Pulls pool state and metadata from daily snapshot.

    Parameters
    ----------
    address : str
        Pool address prefixed with “0x”.

    Returns
    -------
    :class:`~crvusdsim.pool_data.metadata.PoolMetaDataInterface`

    """
    # TODO: validate function arguments
    metadata_dict = from_address(address, end_ts=end_ts)
    metadata = MarketMetaData(metadata_dict, LLAMMAPool, SimLLAMMAPool)

    if save_dir is not None:
        with open(save_dir, "w") as outfile:
            outfile.write(json.dumps(metadata_dict, indent=4))

    return metadata
