from curvesim.exceptions import CurvesimValueError
from crvusdsim.pool.crvusd.LLAMMA import LLAMMAPool
from crvusdsim.pool.crvusd.conf import (
    AGGREGATOR_CONF,
    MONETARY_POLICY_CONF,
    PEG_KEEPER_CONF,
)
from crvusdsim.pool.crvusd.controller import Controller
from crvusdsim.pool.crvusd.controller_factory import ControllerFactory
from crvusdsim.pool.crvusd.mpolicies.monetary_policy import MonetaryPolicy
from crvusdsim.pool.crvusd.price_oracle.aggregate_stable_price import (
    AggregateStablePrice,
)
from crvusdsim.pool.crvusd.price_oracle.price_oracle import PriceOracle
from crvusdsim.pool.crvusd.stabilizer.peg_keeper import PegKeeper
from crvusdsim.pool.crvusd.stablecoin import StableCoin
from crvusdsim.pool.crvusd.stableswap import CurveStableSwapPool
from crvusdsim.pool.sim_interface.llamma import SimLLAMMAPool
from crvusdsim.pool_data import get_metadata
from curvesim.pool_data.metadata import PoolMetaDataInterface
from crvusdsim.pool_data.metadata.market import MarketMetaData
from curvesim.logging import get_logger

logger = get_logger(__name__)


def get_sim_market(
    pool_metadata,
    *,
    bands=True,
    pool_data_cache=None,
    end_ts=None,
):
    """
    Effectively the same as the `get_pool` function but returns
    an object in the `SimPool` hierarchy.
    """
    if isinstance(pool_metadata, str):
        pool_metadata = get_metadata(pool_metadata, end_ts=end_ts)
    elif isinstance(pool_metadata, dict):
        if end_ts:
            raise CurvesimValueError(
                "`end_ts` has no effect unless pool address is used."
            )
        pool_metadata = MarketMetaData(pool_metadata)
    elif isinstance(pool_metadata, PoolMetaDataInterface):
        if end_ts:
            raise CurvesimValueError(
                "`end_ts` has no effect unless pool address is used."
            )
    else:
        raise CurvesimValueError(
            "`pool_metadata` must be of type `str`, `dict`, or `PoolMetaDataInterface`."
        )

    (
        pool_kwargs,
        controller_kwargs,
        monetary_policy_kwargs,
        stableswap_pools_kwargs,
        peg_keepers_kwargs,
    ) = pool_metadata.init_kwargs(bands)
    logger.debug(
        pool_kwargs, controller_kwargs, monetary_policy_kwargs, peg_keepers_kwargs
    )

    pool = SimLLAMMAPool(**pool_kwargs)
    stablecoin = pool.BORROWED_TOKEN
    factory = ControllerFactory(stablecoin=stablecoin)
    collateral_token = pool.COLLATERAL_TOKEN
    price_oracle = pool.price_oracle_contract
    aggregator = AggregateStablePrice(
        stablecoin=stablecoin, sigma=AGGREGATOR_CONF["sigma"]
    )
    stableswap_pools = [
        CurveStableSwapPool(**pool_kwargs) for pool_kwargs in stableswap_pools_kwargs
    ]
    peg_keepers = [
        PegKeeper(
            _pool=stableswap_pools[i],
            _index=PEG_KEEPER_CONF["index"],
            _caller_share=PEG_KEEPER_CONF["caller_share"],
            _factory=factory,
            _aggregator=aggregator,
            _address=peg_keepers_kwargs[i]["address"],
            debt=peg_keepers_kwargs[i]["debt"],
        )
        for i in range(len(peg_keepers_kwargs))
    ]
    policy = MonetaryPolicy(
        price_oracle_contract=price_oracle,
        controller_factory_contract=factory,
        peg_keepers=peg_keepers,
        rate0=monetary_policy_kwargs["rate0"],
        sigma=monetary_policy_kwargs["sigma"],
        target_debt_fraction=monetary_policy_kwargs["fraction"],
    )
    controller = Controller(
        stablecoin=stablecoin,
        factory=factory,
        collateral_token=collateral_token,
        monetary_policy=policy,
        amm=pool,
        **controller_kwargs,
    )

    pool.metadata = pool_metadata._dict  # pylint: disable=protected-access
    pool.metadata["address"] = pool_metadata._dict["llamma_params"]["address"]
    pool.metadata["chain"] = "mainnet"

    return (
        pool,
        controller,
        stablecoin,
        collateral_token,
        stablecoin,
        aggregator,
        peg_keepers,
        policy,
        factory,
    )
