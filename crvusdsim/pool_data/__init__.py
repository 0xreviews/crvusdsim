"""
Tools for fetching pool state and metadata.

Currently supports stableswap pools, metapools, rebasing (RAI) metapools,
and 2-token cryptopools.
"""

__all__ = [
    "from_address",
    "get_data_cache",
    "get_metadata",
    "init_y_bands_strategy",
]

import json
from crvusdsim.pool_data.cache import PoolDataCache

from crvusdsim.pool.sim_interface.sim_llamma import SimLLAMMAPool
from crvusdsim.pool.crvusd import LLAMMAPool
from .metadata import MarketMetaData, init_y_bands_strategy
from .queries import from_address, from_symbol, valid_collateral_symbol


def get_data_cache(
    address,
    chain="mainnet",
    days=60,
    use_band_snapshot=False,
    use_user_snapshot=False,
    end=None,
):
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
    metadata_dict = from_address(
        address,
        chain,
        end_ts=end,
        use_band_snapshot=use_band_snapshot,
        use_user_snapshot=use_user_snapshot,
    )
    pool_data = PoolDataCache(metadata_dict, days=days, end=end)

    return pool_data


def get_metadata(
    address,
    end_ts=None,
    use_band_snapshot=False,
    use_user_snapshot=False,
    save_dir=None,
):
    """
    Pulls pool state and metadata from daily snapshot.

    Parameters
    ----------
    address : str
        Pool address prefixed with “0x” or collateral symbol (e.g. wsteth).

    Returns
    -------
    :class:`~crvusdsim.pool_data.metadata.PoolMetaDataInterface`

    """
    # TODO: validate function arguments
    if valid_collateral_symbol(address):
        metadata_dict = from_symbol(
            address,
            end_ts=end_ts,
            use_band_snapshot=use_band_snapshot,
            use_user_snapshot=use_user_snapshot,
        )
    else:
        metadata_dict = from_address(
            address,
            end_ts=end_ts,
            use_band_snapshot=use_band_snapshot,
            use_user_snapshot=use_user_snapshot,
        )
    metadata = MarketMetaData(metadata_dict, LLAMMAPool, SimLLAMMAPool)

    if save_dir is not None:
        with open(save_dir, "w") as outfile:
            outfile.write(json.dumps(metadata_dict, indent=4))

    return metadata
