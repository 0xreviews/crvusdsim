import asyncio

from curvesim.network.web3 import underlying_coin_info_sync
from curvesim.exceptions import CurvesimValueError

from crvusdsim.pool.crvusd.conf import ALIAS_TO_ADDRESS
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
    end_ts: int, optional
        Posix timestamp indicating the datetime of the metadata snapshot.

    Returns
    -------
    Pool snapshot dictionary in the format returned by
    :func:`curvesim.network.subgraph.pool_snapshot`.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    data = market_snapshot_sync(
        llamma_address,
        end_ts=end_ts,
        use_band_snapshot=use_band_snapshot,
        use_user_snapshot=use_user_snapshot,
        event_loop=loop,
    )

    return data


def from_symbol(symbol, end_ts=None, use_band_snapshot=False, use_user_snapshot=False):
    if "llamma_%s" % symbol.lower() not in ALIAS_TO_ADDRESS:
        raise CurvesimValueError("`%s` is not a valid collateral symbol." % (symbol))

    amm_address = ALIAS_TO_ADDRESS["llamma_%s" % symbol.lower()]

    data = from_address(amm_address, end_ts, use_band_snapshot, use_user_snapshot)

    return data


def valid_collateral_symbol(symbol):
    if "llamma_%s" % symbol.lower() in ALIAS_TO_ADDRESS:
        return True
    else:
        return False
