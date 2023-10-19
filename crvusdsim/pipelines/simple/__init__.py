import os

from crvusdsim.iterators.params_samplers import (
    CRVUSD_POOL_MAP,
    ParameterizedLLAMMAPoolIterator,
)
from crvusdsim.pipelines import run_pipeline
from crvusdsim.metrics import init_metrics, make_results
from crvusdsim.pipelines.common import DEFAULT_METRICS
from crvusdsim.pipelines.common import DEFAULT_POOL_PARAMS, TEST_PARAMS
from crvusdsim.pipelines.simple.strategy import SimpleStrategy
from crvusdsim.pool import get_sim_market
from crvusdsim.iterators.price_samplers import PriceVolume
from crvusdsim.pool_data.cache import PoolDataCache


def pipeline(  # pylint: disable=too-many-locals
    pool_metadata,
    pool_data_cache=None,
    *,
    chain="mainnet",
    pool_params=None,
    controller_params=None,
    fixed_params=None,
    bands_strategy=None,
    test=False,
    end_ts=None,
    days=60,
    src="coingecko",
    data_dir="data",
    prices_max_interval=5 * 60,
    profit_threshold=50 * 10**18,
    ncpu=None,
):
    """
    Implements the simple arbitrage pipeline.  This is a very simplified version
    of :func:`curvesim.pipelines.vol_limited_arb.pipeline`.

    At each timestep, the pool is arbitraged as close to the prevailing market
    price as possible for the coin pair generating the largest arbitrage profit.

    Parameters
    ----------
    pool_address : str
        '0x'-prefixed string representing the pool address.

    chain: str
        Identifier for blockchain or layer2.  Supported values are:
        "mainnet"

    variable_params : dict, defaults to broad range of A/fee values
        Pool parameters to vary across simulations.
        keys: pool parameters, values: iterables of ints

        Example
        --------
        >>> variable_params = {"A": [100], "fee": [6 * 10**15], "admin_fee": [0]}
    
    controller_params : dict, defaults to broad range of loan_discount values

        Example
        --------
        >>> controller_params = {"loan_discount": [int(0.09 * 10**18)]}

    fixed_params : dict, optional
        Pool parameters set before all simulations.
        keys: pool parameters, values: ints

        Example
        --------
        >>> fixed_params = {"A": 100}

    test : bool, optional
        Overrides variable_params to use four test values:

        .. code-block::

            {"A": [100, 200], "fee": [3 * 10**15, 6 * 10**15], "admin_fee": [0, 0]}

    end_ts : int, optional
        End timestamp in Unix time.  Defaults to 30 minutes before midnight of the
        current day in UTC.

    days : int, default=60
        Number of days to pull price/volume data for.

    src : str, default="coingecko"
        Source for price/volume data: "coingecko" or "local".

    data_dir : str, default="data"
        relative path to saved price data folder

    ncpu : int, default=os.cpu_count()
        Number of cores to use.

    Returns
    -------
    :class:`~curvesim.metrics.SimResults`

    """
    ncpu = ncpu or os.cpu_count()
    fixed_params = fixed_params or {}  # @todo

    default_params = DEFAULT_POOL_PARAMS.copy()
    for key in DEFAULT_POOL_PARAMS:
        if key in fixed_params:
            del default_params[key]

    # pool_params = pool_params or DEFAULT_POOL_PARAMS

    # if pool_data_cache is None:
    #     pool_data_cache = PoolDataCache(pool_metadata, days=days, end=end_ts)

    (
        pool,
        controller,
        collateral_token,
        stablecoin,
        aggregator,
        peg_keepers,
        policy,
        factory,
    ) = get_sim_market(pool_metadata, pool_data_cache=pool_data_cache, end_ts=end_ts)

    if test:
        fixed_params = {}
        pool_params = TEST_PARAMS

    sim_assets = pool.assets
    price_sampler = PriceVolume(
        sim_assets,
        days=days,
        end=end_ts,
        data_dir=data_dir,
        src=src,
        max_interval=prices_max_interval,
    )

    param_sampler = ParameterizedLLAMMAPoolIterator(
        pool,
        controller,
        aggregator,
        peg_keepers,
        policy,
        factory,
        pool_params=pool_params,
        controller_params=controller_params,
        fixed_params=fixed_params,
    )

    _metrics = init_metrics(DEFAULT_METRICS, pool=pool)
    strategy = SimpleStrategy(
        _metrics, bands_strategy=bands_strategy, profit_threshold=profit_threshold
    )

    output = run_pipeline(param_sampler, price_sampler, strategy, ncpu=ncpu)

    results = make_results(*output, _metrics)
    return results
