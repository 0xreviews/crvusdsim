import asyncio

from curvesim.network.web3 import underlying_coin_info_sync
from ..network.subgraph import market_snapshot_sync


def from_address(
    llamma_address, end_ts=None, use_band_snapshot=False, use_user_snapshot=False
):
    """
    Returns

    Parameters
    ----------
    llamma_address: str
        Address prefixed with '0x'
    chain: str
        Chain name
    env: str
        Environment name for subgraph: 'prod' or 'staging'

    Returns
    -------
    Pool snapshot dictionary in the format returned by
    :func:`curvesim.network.subgraph.pool_snapshot`.
    """
    loop = asyncio.get_event_loop()
    data = market_snapshot_sync(
        llamma_address,
        end_ts=end_ts,
        use_band_snapshot=use_band_snapshot,
        use_user_snapshot=use_user_snapshot,
        event_loop=loop,
    )

    return data


def from_symbol(symbol, index=0):
    (amm_address, controller_address, policy_address) = market_snapshot_sync(
        symbol, index
    )

    data = from_address(amm_address)

    return data
