"""
Getters for pool parameters of different pool types.

Used for the `StateLog`.
"""

from curvesim.exceptions import UnregisteredPoolError
from crvusdsim.pool.sim_interface import SimLLAMMAPool

def get_pool_parameters(pool):
    """
    Returns pool parameters for the input pool. Functions for each pool type are
    specified in the `pool_parameter_functions` dict. Returned values are recorded
    at the start of each simulation run.
    """
    try:
        return pool_parameter_functions[type(pool)](pool)
    except KeyError as e:
        raise UnregisteredPoolError(
            f"Parameter getter not implemented for pool type '{type(pool)}'."
        ) from e


# @todo
def get_llamma_pool_params(pool):
    """Returns pool parameters for cryptoswap non-meta pools."""
    params = {
        "A": pool.A,
    }
    return params


pool_parameter_functions = {
    SimLLAMMAPool: get_llamma_pool_params,
}
