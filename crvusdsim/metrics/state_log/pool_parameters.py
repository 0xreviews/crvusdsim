"""
Getters for pool parameters of different pool types.

Used for the `StateLog`.
"""

from curvesim.exceptions import UnregisteredPoolError
from crvusdsim.pool import SimMarketInstance
from crvusdsim.pool.sim_interface import SimLLAMMAPool


def get_pool_parameters(pool):
    """
    Returns pool parameters for the input pool. Returned values are recorded
    at the start of each simulation run.
    """
    params = {
        "A": pool.A,
        "Fee": pool.fee / 1e18,
    }
    return params


def get_controller_parameters(controller):
    """
    Returns controller parameters for the input controller. Returned values are recorded
    at the start of each simulation run.
    """
    params = {
        "loan_discount": round(controller.loan_discount / 1e18, 3),
        "liquidation_discount": round(controller.liquidation_discount / 1e18, 3),
    }
    return params


def get_N_parameters(parameters):
    """
    Returns controller parameters for the input controller. Returned values are recorded
    at the start of each simulation run.
    """
    params = {
        "N": parameters["N"],
    }
    return params

def get_rate_parameters(sim_market: SimMarketInstance):
    """
    Returns controller parameters for the input MonetaryPolicy. Returned values are recorded
    at the start of each simulation run.
    """
    params = {
        "rate0": sim_market.policy.rate0,
    }
    return params