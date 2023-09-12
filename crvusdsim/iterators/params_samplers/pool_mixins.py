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
        # @todo
        return {}