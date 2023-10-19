"""
Getters for pool parameters of different pool types.

Used for the `StateLog`.
"""

from curvesim.exceptions import UnregisteredPoolError
from crvusdsim.pool.sim_interface import SimLLAMMAPool

def get_pool_parameters(pool, controller):
    """
    Returns pool parameters for the input pool. Returned values are recorded
    at the start of each simulation run.
    """
    params = {
        "A": pool.A,
        "Fee": pool.fee / 1e18,
    }
    return params


def get_controller_parameters(pool, controller):
    """
    Returns controller parameters for the input controller. Returned values are recorded
    at the start of each simulation run.
    """
    params = {
        "loan_discount": controller.loan_discount / 1e18
    }
    return params