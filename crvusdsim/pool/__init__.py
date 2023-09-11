from curvesim.exceptions import CurvesimValueError
from crvusdsim.pool_data import get_metadata
from curvesim.pool_data.metadata import PoolMetaDataInterface
from crvusdsim.pool_data.metadata.llamma import PoolMetaData
from curvesim.logging import get_logger

logger = get_logger(__name__)


def get_sim_pool(
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
        pool_metadata = PoolMetaData(pool_metadata)
    elif isinstance(pool_metadata, PoolMetaDataInterface):
        if end_ts:
            raise CurvesimValueError(
                "`end_ts` has no effect unless pool address is used."
            )
    else:
        raise CurvesimValueError(
            "`pool_metadata` must be of type `str`, `dict`, or `PoolMetaDataInterface`."
        )

    pool_kwargs, controller_kwargs = pool_metadata.init_kwargs(bands, normalize=True)
    logger.debug(pool_kwargs, controller_kwargs)

    pool_type = pool_metadata.sim_pool_type

    pool = pool_type(**pool_kwargs)
    # @todo controller = (**controller_kwargs)

    pool.metadata = pool_metadata._dict  # pylint: disable=protected-access
    pool.metadata["address"] = pool_metadata._dict["amm"]["id"]
    pool.metadata["chain"] = "mainnet"

    return pool


