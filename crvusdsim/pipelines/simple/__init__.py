import os

from curvesim.logging import get_logger
from curvesim.templates import SimAssets

from crvusdsim.iterators.params_samplers import (
    CRVUSD_POOL_MAP,
    ParameterizedLLAMMAPoolIterator,
)
from crvusdsim.metrics.results.sim_results import SimResults
from crvusdsim.pipelines import run_pipeline
from crvusdsim.metrics import init_metrics, make_results
from crvusdsim.pipelines.common import (
    DEFAULT_CONTROLLER_METRICS,
    DEFAULT_CONTROLLER_PARAMS,
    DEFAULT_N_METRICS,
    DEFAULT_N_PARAMS,
    DEFAULT_POOL_METRICS,
    DEFAULT_RATE_METRICS,
    DEFAULT_RATE_PARAMS,
)
from crvusdsim.pipelines.common import DEFAULT_POOL_PARAMS, TEST_PARAMS
from crvusdsim.pipelines.simple.strategy import SimpleStrategy
from crvusdsim.pool import get_sim_market
from crvusdsim.iterators.price_samplers import PriceVolume

logger = get_logger(__name__)


def pipeline(  # pylint: disable=too-many-locals
    pool_metadata,
    pool_data_cache=None,
    *,
    chain="mainnet",
    sim_mode="pool",
    variable_params=None,
    fixed_params=None,
    bands_strategy_class=None,
    bands_strategy_kwargs=None,
    pegcoins_prices_strategy_class=None,
    test=False,
    end_ts=None,
    days=60,
    src="coingecko",
    data_dir="data",
    prices_max_interval=10 * 60,
    profit_threshold=0 * 10**18,
    ncpu=None,
) -> SimResults:
    """
    Implements the simple arbitrage pipeline.  This is a very simplified version
    of :func:`crvusdsim.pipelines.simple.pipeline`.

    At each timestep, the pool is arbitraged as close to the prevailing market
    price as possible for the coin pair generating the largest arbitrage profit.

    Parameters
    ----------
    pool_address : str
        '0x'-prefixed string representing the pool address.

    chain: str
        Identifier for blockchain or layer2.  Supported values are:
        "mainnet"

    sim_mode: str (default=rate)
        For different modes, the comparison dimensions are different.
        Supported values are: "rate", "pool", "controller", "N"

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

    prices_max_interval: int, default=10 * 60 (10m)
        The maximum interval for pricing data. If the time interval between two
        adjacent data exceeds this value, interpolation processing will be performed automatically.

    profit_threshold: int, default=0
        Profit threshold for arbitrageurs, trades with profits below this value will not be executed



    Returns
    -------
    :class:`~crvusdsim.metrics.SimResults`

    """
    logger.info("Simulating mode: %s", sim_mode)

    ncpu = ncpu or os.cpu_count()
    fixed_params = fixed_params or {}  # @todo

    default_params = DEFAULT_POOL_PARAMS.copy()
    for key in DEFAULT_POOL_PARAMS:
        if key in fixed_params:
            del default_params[key]

    if not variable_params:
        if sim_mode == "pool":
            variable_params = DEFAULT_POOL_PARAMS
        elif sim_mode == "controller":
            variable_params = DEFAULT_CONTROLLER_PARAMS
        elif sim_mode == "N":
            variable_params = DEFAULT_N_PARAMS
        elif sim_mode == "rate":
            variable_params = DEFAULT_RATE_PARAMS

    sim_market = get_sim_market(
        pool_metadata,
        pool_data_cache=pool_data_cache,
        src=src if src == "local" else None,
        data_dir=data_dir,
        end_ts=None if isinstance(pool_metadata, str) else end_ts,
    )

    if test:
        fixed_params = {}
        pool_params = TEST_PARAMS

    sim_assets = sim_market.pool.assets
    price_sampler = PriceVolume(
        sim_assets,
        days=days,
        end=end_ts,
        data_dir=data_dir,
        src=src,
        max_interval=prices_max_interval,
        ncpu=ncpu, # if coingecko limits the APIs connections, set this 1
    )

    if pegcoins_prices_strategy_class:
        pegcoins_prices_strategy = pegcoins_prices_strategy_class(sim_market, price_sampler)
        pegcoins_prices_strategy.do_strategy()
    else:
        pegcoins = [stable_pool.assets for stable_pool in sim_market.stableswap_pools]
        price_sampler.load_pegcoins_prices(src=src, pegcoins=pegcoins)

    param_sampler = ParameterizedLLAMMAPoolIterator(
        sim_market,
        sim_mode=sim_mode,
        variable_params=variable_params,
        fixed_params=fixed_params,
    )

    if sim_mode == "pool":
        default_metrics = DEFAULT_POOL_METRICS
    elif sim_mode == "controller":
        default_metrics = DEFAULT_CONTROLLER_METRICS
    elif sim_mode == "N":
        default_metrics = DEFAULT_N_METRICS
    elif sim_mode == "rate":
        default_metrics = DEFAULT_RATE_METRICS

    _metrics = init_metrics(default_metrics, sim_market=sim_market)
    strategy = SimpleStrategy(
        _metrics,
        bands_strategy_class=bands_strategy_class,
        bands_strategy_kwargs=bands_strategy_kwargs,
        sim_mode=sim_mode,
        profit_threshold=profit_threshold,
    )

    output = run_pipeline(param_sampler, price_sampler, strategy, ncpu=ncpu)

    results = make_results(
        *output, _metrics, prices=price_sampler.prices, sim_mode=sim_mode
    )

    return results
