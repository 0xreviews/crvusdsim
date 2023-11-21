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
from crvusdsim.pool.sim_interface.sim_stableswap import SimCurveStableSwapPool
from crvusdsim.pool.sim_interface.sim_controller import SimController
from crvusdsim.pool.sim_interface.sim_llamma import SimLLAMMAPool
from crvusdsim.pool_data import get_metadata
from curvesim.pool_data.metadata import PoolMetaDataInterface
from crvusdsim.pool_data.metadata.market import MarketMetaData
from curvesim.logging import get_logger

__all__ = [
    "SimLLAMMAPool",
    "get_sim_market",
    "get",
]

logger = get_logger(__name__)

MARKET_DEBT_CEILING = 10**7 * 10**18  # 10M


def get_sim_market(
    pool_metadata,
    *,
    bands_data=None,
    pool_data_cache=None,
    end_ts=None,
    src=None,
    data_dir=None,
):
    """
    Factory function for creating related entities (e.g. SimLLAMMAPool, SimController)
    in the same market based on metadata pulled from on-chain.

    Parameters
    ----------
    pool_metadata : Union[str, dict, PoolMetaDataInterface]
        pool address prefixed with "0x" or already pulled metadata in the form
        of a dict or :class:`PoolMetaDataInterface`.

    chain: str, default="mainnet"
        chain identifier, only "mainnet" for now.

    bands_data: "pool" | "controller" | None, default=None
        bands data initialization method
        pool: init bands_x and bands_y in LLAMMAPool with metadata,
        controller: init bands_x, bands_y and user_shares in LLAMMAPool with metadata,
        init loan, loans, loan_ix, n_loans, total_debt, minted, redeemed in controller.

    end_ts: int, optional
        Posix timestamp indicating the datetime of the metadata snapshot.
        Only used when `pool_metadata` is an address.

    Returns
    -------
    Tuple: (
        pool: `SimLLAMMAPool`,
        controller: `SimController`,
        collateral_token: `ERC20`,
        stablecoin: `StableCoin`,
        aggregator: `AggregateStablePrice`,
        stableswap_pools: `List[CurveStableSwapPool]`,
        peg_keepers: `List[PegKeeper]`,
        policy: `MonetaryPolicy`,
        factory: `ControllerFactory`,
    )

    Examples
    --------
    >>> import curvesim
    >>> pool_address = "wsteth"
    >>> pool = curvesim.pool.get(pool_address, bands_data="pool")
    """

    use_band_snapshot = False
    use_user_snapshot = False

    if bands_data:
        if bands_data == "pool":
            use_band_snapshot = True
        elif bands_data == "controller":
            use_band_snapshot = True
            use_user_snapshot = True

    if isinstance(pool_metadata, str):
        pool_metadata = get_metadata(
            pool_metadata,
            use_band_snapshot,
            use_user_snapshot,
            src=src,
            data_dir=data_dir,
            end_ts=end_ts,
        )
    elif isinstance(pool_metadata, dict):
        if end_ts:
            raise CurvesimValueError(
                "`end_ts` has no effect unless pool address is used."
            )
        pool_metadata = MarketMetaData(pool_metadata, LLAMMAPool, SimLLAMMAPool)
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
    ) = pool_metadata.init_kwargs(bands_data=bands_data)
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

    stableswap_pools = []
    for i in range(len(stableswap_pools_kwargs)):
        pool_kwargs = stableswap_pools_kwargs[i]
        pool_kwargs["coins"] = [
            StableCoin(**coin_kwargs) for coin_kwargs in pool_kwargs["coins"]
        ]
        stableswap_pools.append(SimCurveStableSwapPool(**pool_kwargs))

    peg_keepers = [
        PegKeeper(
            _pool=stableswap_pools[i],
            _index=int(PEG_KEEPER_CONF["index"]),
            _caller_share=int(PEG_KEEPER_CONF["caller_share"]),
            _factory=factory,
            _aggregator=aggregator,
            _address=peg_keepers_kwargs[i]["address"],
            debt=int(peg_keepers_kwargs[i]["debt"]),
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
    controller = SimController(
        stablecoin=stablecoin,
        factory=factory,
        collateral_token=collateral_token,
        monetary_policy=policy,
        amm=pool,
        **controller_kwargs,
    )
    # set debt ceil
    factory.set_debt_ceiling(controller.address, MARKET_DEBT_CEILING)

    pool.metadata = pool_metadata._dict  # pylint: disable=protected-access
    pool.metadata["address"] = pool_metadata._dict["llamma_params"]["address"]
    pool.metadata["chain"] = "mainnet"

    return (
        pool,
        controller,
        collateral_token,
        stablecoin,
        aggregator,
        stableswap_pools,
        peg_keepers,
        policy,
        factory,
    )


get = get_sim_market
