from curvesim.exceptions import UnregisteredPoolError
from crvusdsim.pool.sim_interface import SimLLAMMAPool


def get_pool_state(pool):
    """
    Returns pool state for the input pool. Functions for each pool type are
    specified in the `pool_state_functions` dict. Each function returns the
    values necessary to reconstruct pool state throughout a simulation run.
    """
    try:
        return pool_state_functions[type(pool)](pool)
    except KeyError as e:
        raise UnregisteredPoolError(
            f"State getter not implemented for pool type '{type(pool)}'."
        ) from e


# @todo
def get_llamma_pool_state(pool):
    """Returns pool state for llamma pools."""
    return {
        "A": pool.A,
        "active_band": pool.active_band,
        "min_band": pool.min_band,
        "max_band": pool.max_band,
        "rate": pool.rate,
        "rate_mul": pool.rate_mul,
        "fee": pool.fee,
        "admin_fee": pool.admin_fee,
        "oracle_price": pool.price_oracle_contract.price(),
        "bands_x_sum": sum(pool.bands_x.values()),
        "bands_y_sum": sum(pool.bands_y.values()),
    }



pool_state_functions = {
    SimLLAMMAPool: get_llamma_pool_state,
}
