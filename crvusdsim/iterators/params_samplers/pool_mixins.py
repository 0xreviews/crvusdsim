from math import isqrt
from crvusdsim.pool.crvusd.clac import ln_int, log2
from crvusdsim.pool.crvusd.vyper_func import unsafe_div, unsafe_sub
from crvusdsim.pool.sim_interface.llamma import SimLLAMMAPool


class LLAMMAPoolMixin:
    """
    Parameter sampler mixin for Curve LLAMMA pools.
    Defines special attribute setters.
    """

    @property
    def _pool_type(self):
        return SimLLAMMAPool

    @property
    def setters(self):
        """
        Returns
        -------
        dict
            A dictionary containing the special setters for the pool parameters.
        """
        return {
            "A": llamma_A_params,
        }
    
    @property
    def controller_setters(self):
        """
        Returns
        -------
        dict
            A dictionary containing the special setters for the pool parameters.
        """
        return {
            "A": controller_A_params,
        }


def llamma_A_params(pool, A):
    pool.Aminus1 = A - 1
    pool.A2 = A**2
    pool.Aminus12 = (A - 1) ** 2

    A_ratio = 10**18 * A // (A - 1)
    pool.SQRT_BAND_RATIO = isqrt(A_ratio * 10**18)
    pool.LOG_A_RATIO = ln_int(A_ratio)
    # (A / (A - 1)) ** 50
    pool.MAX_ORACLE_DN_POW = (
        int(A**25 * 10**18 // (pool.Aminus1 ** 25)) ** 2 // 10**18
    )


def controller_A_params(controller, A):
    controller.Aminus1 = A - 1
    controller.SQRT_BAND_RATIO = isqrt(unsafe_div(10**36 * A, unsafe_sub(A, 1)))
    controller.LOG2_A_RATIO = log2(A * 10**18 // unsafe_sub(A, 1))
