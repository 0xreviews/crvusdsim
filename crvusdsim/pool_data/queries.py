import asyncio

from curvesim.network.web3 import underlying_coin_info_sync
from curvesim.exceptions import CurvesimValueError
from ..network.subgraph import market_snapshot_sync


ALIAS_TO_ADDRESS = {
    "sfrxeth_v1": "0x136e783846ef68c8bd00a3369f787df8d683a696",
    "sfrxeth": "0xfa96ad0a9e64261db86950e2da362f5572c5c6fd",
    "sfrxeth_v2": "0xfa96ad0a9e64261db86950e2da362f5572c5c6fd",
    "wsteth": "0x37417b2238aa52d0dd2d6252d989e728e8f706e4",
    "weth": "0x1681195c176239ac5e72d9aebacf5b2492e0c4ee",
    "wbtc": "0xe0438eb3703bf871e31ce639bd351109c88666ea",
    "tbtc": "0xf9bd9da2427a50908c4c6d1599d8e62837c2bcb0",
}


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


def from_symbol(symbol, end_ts=None, use_band_snapshot=False, use_user_snapshot=False):
    if symbol.lower() not in ALIAS_TO_ADDRESS:
        raise CurvesimValueError("`%s` is not a valid collateral symbol." % (symbol))

    amm_address = ALIAS_TO_ADDRESS[symbol.lower()]

    data = from_address(amm_address, end_ts, use_band_snapshot, use_user_snapshot)

    return data


def valid_collateral_symbol(symbol):
    if symbol.lower() in ALIAS_TO_ADDRESS:
        return True
    else:
        return False
