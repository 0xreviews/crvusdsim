"""
Tools for fetching pool state and metadata.

Currently supports stableswap pools, metapools, rebasing (RAI) metapools,
and 2-token cryptopools.
"""

__all__ = [
    "from_address",
    "get_data_cache",
    "get_metadata",
]

from crvusdsim.pool.sim_interface.llamma import SimLLAMMAPool
from crvusdsim.pool.crvusd import LLAMMAPool
from .metadata import PoolMetaData
from .queries import from_address
# from .cache import PoolDataCache


# def get_data_cache(address, chain="mainnet", days=60, end=None):
#     """
#     Fetch historical volume and redemption price data and return
#     in a cache object.

#     Deprecation warning: this will likely be removed in a future release.

#     Parameters
#     ----------
#     address : str
#         Pool address prefixed with “0x”.

#     chain : str
#         Chain/layer2 identifier, e.g. “mainnet”, “arbitrum”, “optimism".

#     Returns
#     -------
#     :class:`PoolDataCache`

#     """
#     # TODO: validate function arguments
#     metadata_dict = from_address(address, chain, end_ts=end)
#     pool_data = PoolDataCache(metadata_dict, days=days, end=end)

#     return pool_data


def get_metadata(
    address,
    end_ts=None,
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
    metadata = PoolMetaData(metadata_dict, LLAMMAPool, SimLLAMMAPool)

    return metadata
