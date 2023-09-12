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
    """Returns pool state for stableswap non-meta pools."""
    return {
        "A": pool.A,
    }



pool_state_functions = {
    SimLLAMMAPool: get_llamma_pool_state,
}
