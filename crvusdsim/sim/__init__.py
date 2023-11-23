"""
A simulation runs trades against Curve pools, using a strategy that may
utilize different types of informed or noise trades.

The :mod:`simulation pipeline framework <crvusdsim.pipelines>` allows the
user to build custom strategies for simulation.

Most users will want to use the `autosim` function, which supports
"optimal" arbitrages via the
:func:`volume-limited arbitrage pipeline <curvesim.pipelines.vol_limited_arb.pipeline>`.
The primary use-case is to determine optimal amplitude (A) and fee
parameters given historical price and volume feeds.
"""
from curvesim.logging import get_logger

from crvusdsim.pipelines.simple import pipeline
from crvusdsim.pool_data import get_metadata
from crvusdsim.pool_data.metadata.bands_strategy import (
    IinitYBandsStrategy,
    OneUserBandsStrategy,
    UserLoansBandsStrategy,
)


logger = get_logger(__name__)


def autosim(
    pool=None,
    pool_metadata=None,
    sim_mode="pool",
    **kwargs,
):
    """
    The autosim() function simulates existing Curve pools with a range of
    parameters (e.g., the amplitude parameter, A, and/or the exchange fee).

    The function fetches pool properties (e.g., current pool size) and 2
    months of price/volume data and runs multiple simulations in parallel.

    Curve pools from any chain supported by the Convex Community Subgraphs
    can be simulated directly by inputting the pool's address.

    Parameters
    ----------
    pool: str, optional
        This 0x-prefixed string identifies the LLAMMA pool by address or
        collateral's symbol of market.

        .. note::
            Either `pool` or `pool_metadata` must be provided.

    pool_metadata: PoolMetaDataInterface, optional
        Pool state and metadata necessary to instantiate a pool object.

        .. note::
            Either `pool` or `pool_metadata` must be provided.

    A: int or iterable of int, optional
        Amplification coefficient.  This controls the curvature of the
        stableswap bonding curve.  Increased values makes the curve
        flatter in a greater neighborhood of equal balances.

        For basepool, use **A_base**.

    fee: int or iterable of int, optional
        Fees taken for both liquidity providers and the DAO.

        Units are in fixed-point so that 10**10 is 100%,
        e.g. 4 * 10**6 is 4 bps and 2 * 10**8 is 2%.

        For basepool, use **fee_base**.

    test: bool, default=False
        Overrides variable_params to use four test values:

        .. code-block::

            {"A": [50, 100], "fee": [6 * 10**15]}

    prices_max_interval: int, default=int(10 * 60)
        prices data maximum time interval, if the input time
        interval is greater than this value, linear interpolation.

    days: int, default=60
        Number of days to fetch data for.

    src: str, default='coingecko'
        Valid values for data source are 'coingecko' or 'local'

    data_dir: str, default=None
        Relative path to saved data folder.

    end_ts: int, optional
        Posix timestamp indicating the datetime of the metadata snapshot.

    ncpu : int, default=os.cpu_count()
        Number of cores to use.

    env: str, default='prod'
        Environment for the Curve subgraph, which pulls pool and volume snapshots.

    Returns
    -------
    dict
        Dictionary of results, each value being a pandas.Series.
    """
    assert any([pool, pool_metadata]), "Must input 'pool' or 'pool_metadata'"

    # pool_metadata = pool_metadata or get_metadata(
    #     pool, data_dir=data_dir, end_ts=end_ts
    # )
    p_var, bands_strategy_class, rest_of_params = _parse_arguments(
        pool_metadata, sim_mode, **kwargs
    )

    results = pipeline(
        pool_metadata=pool if pool else pool_metadata,
        sim_mode=sim_mode,
        variable_params=p_var,
        bands_strategy_class=bands_strategy_class,
        **rest_of_params,
    )

    return results


def _parse_arguments(pool_metadata, sim_mode, **kwargs):
    input_args = []
    bands_strategy_class = None

    if sim_mode == "pool":
        input_args = [
            "A",
            "fee",
            "admin_fee",
        ]
        bands_strategy_class = IinitYBandsStrategy
    elif sim_mode == "controller":
        input_args = ["loan_discount", "liquidation_discount"]
        bands_strategy_class = UserLoansBandsStrategy
    elif sim_mode == "N":
        input_args = ["N"]
        bands_strategy_class = OneUserBandsStrategy

    variable_params = {}
    rest_of_params = {}

    for key, val in kwargs.items():
        if key in input_args:
            if all(isinstance(v, int) for v in val):
                variable_params[key] = val
            else:
                raise TypeError(f"Argument {key} must be an int or iterable of ints")
        else:
            rest_of_params[key] = val

    return variable_params, bands_strategy_class, rest_of_params
