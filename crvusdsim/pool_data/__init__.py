"""
Tools for fetching pool state and metadata.

Currently supports stableswap pools, metapools, rebasing (RAI) metapools,
and 2-token cryptopools.
"""

__all__ = [
    "from_address",
    "get_metadata",
    "init_y_bands_strategy",
]

import json

from crvusdsim.pool.sim_interface.sim_llamma import SimLLAMMAPool
from crvusdsim.pool.crvusd import LLAMMAPool
from .metadata import MarketMetaData, init_y_bands_strategy
from .queries import ALIAS_TO_ADDRESS, from_address, from_symbol, valid_collateral_symbol

def get_metadata(
    address,
    use_band_snapshot=False,
    use_user_snapshot=False,
    src="subgraph",
    end_ts=None,
    data_dir=None,
):
    """
    Pulls pool state and metadata from daily snapshot.

    Parameters
    ----------
    address : str
        Pool address prefixed with “0x” or collateral symbol (e.g. wsteth).

    src : default="subgraph"
        Source for market subgraph data: "subgraph" or "local".

    Returns
    -------
    :class:`~crvusdsim.pool_data.metadata.PoolMetaDataInterface`

    """
    use_symbol = valid_collateral_symbol(address)

    if src == "local" and data_dir is not None:
        if use_symbol:
            address = ALIAS_TO_ADDRESS[address.lower()]
        with open(data_dir + "/pool_metadata_%s.json" % (address)) as openfile:
            metadata_dict = json.load(openfile)
    else:
        # TODO: validate function arguments
        if use_symbol:
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

        if data_dir is not None:
            with open(data_dir + "/pool_metadata_%s.json" % (address), "w") as outfile:
                outfile.write(json.dumps(metadata_dict, indent=4))

    metadata = MarketMetaData(metadata_dict, LLAMMAPool, SimLLAMMAPool)

    return metadata
