import os

from curvesim.iterators.param_samplers import ParameterizedPoolIterator
from curvesim.iterators.price_samplers import PriceVolume
from curvesim.metrics.results import make_results
from curvesim.pipelines import run_pipeline
from curvesim.pool.cryptoswap.pool import CurveCryptoPool

from crvusdsim.metrics import init_metrics
from crvusdsim.pipelines.common import DEFAULT_METRICS
from crvusdsim.iterators.params_samplers.pool_mixins import LLAMMAPoolMixin
from crvusdsim.pipelines.common import DEFAULT_PARAMS, TEST_PARAMS
from crvusdsim.pipelines.simple.strategy import SimpleStrategy
from crvusdsim.pool import get_sim_pool
from crvusdsim.pool.sim_interface.llamma import SimLLAMMAPool
from crvusdsim.pool_data.cache import PoolDataCache




# @todo
def pipeline(  # pylint: disable=too-many-locals
    pool_metadata,
    pool_data_cache=None,
    *,
    chain="mainnet",
    variable_params=None,
    fixed_params=None,
    test=False,
    end_ts=None,
    days=60,
    src="coingecko",
    data_dir="data",
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
    fixed_params = fixed_params or {} # @todo

    default_params = DEFAULT_PARAMS.copy()
    for key in DEFAULT_PARAMS:
        if key in fixed_params:
            del default_params[key]

    variable_params = variable_params or DEFAULT_PARAMS

    # if pool_data_cache is None:
    #     pool_data_cache = PoolDataCache(pool_metadata, days=days, end=end_ts)

    pool = get_sim_pool(pool_metadata, pool_data_cache=pool_data_cache, end_ts=end_ts)

    if test:
        fixed_params = {}
        variable_params = TEST_PARAMS

    sim_assets = pool.assets
    price_sampler = PriceVolume(
        sim_assets, days=days, end=end_ts, data_dir=data_dir, src=src
    )

    param_sampler = ParameterizedPoolIterator(
        pool, variable_params, fixed_params, pool_map=CRVUSD_POOL_MAP
    )

    _metrics = init_metrics(DEFAULT_METRICS, pool=pool)
    strategy = SimpleStrategy(_metrics)
    

    output = run_pipeline(param_sampler, price_sampler, strategy, ncpu=ncpu)
    results = make_results(*output, _metrics)
    return results


class ParameterizedLLAMMAPoolIterator(LLAMMAPoolMixin, ParameterizedPoolIterator):
    """
    :class:`ParameterizedPoolIterator` parameter sampler specialized
    for Curve pools.
    """


CRVUSD_POOL_MAP = {SimLLAMMAPool: ParameterizedLLAMMAPoolIterator}
