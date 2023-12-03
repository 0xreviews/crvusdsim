from math import isqrt
from copy import deepcopy
from typing import overload
from itertools import product

from curvesim.utils import override
from curvesim.exceptions import ParameterSamplerError
from crvusdsim.pool import SimMarketInstance

from crvusdsim.pool.crvusd.clac import ln_int
from curvesim.iterators.param_samplers import ParameterizedPoolIterator
from crvusdsim.iterators.params_samplers.pool_mixins import LLAMMAPoolMixin
from crvusdsim.pool.sim_interface.sim_llamma import SimLLAMMAPool


class ParameterizedLLAMMAPoolIterator(LLAMMAPoolMixin):
    """
    :class:`ParameterizedPoolIterator` parameter sampler specialized
    for Curve pools.
    """

    # pylint: disable-next=unused-argument
    def __new__(
        cls,
        sim_market: SimMarketInstance,
        sim_mode="rate",
        variable_params=None,
        fixed_params=None,
        pool_map=None,
    ):
        """
        Returns a pool-specific ParameterizedPoolIterator subclass.

        Parameters
        ----------
        sim_market : :class:`crvusdsim.pool.SimMarketInstance`

        sim_mode: str (default=rate)
            For different modes, the comparison dimensions are different.
            Supported values are: "rate", "pool", "controller", "N"

        Returns
        -------
            :class:`.ParameterizedPoolIterator` subclass

        """
        pool_map = pool_map or CRVUSD_POOL_MAP

        if cls is not ParameterizedPoolIterator:
            return super().__new__(cls)

        try:
            pool_type = type(sim_market.pool)
            subclass = pool_map[pool_type]

        except KeyError as e:
            pool_type_name = pool_type.__name__
            raise ParameterSamplerError(
                f"No subclass for pool type `{pool_type_name}` found in "
                "ParameterizedPoolIterator pool map."
            ) from e

        return super().__new__(subclass)

    def __init__(
        self,
        sim_market: SimMarketInstance,
        sim_mode="pool",
        variable_params=None,
        *args,
        **kwargs,
    ):
        self.sim_market_template = sim_market
        self.sim_mode = sim_mode
        self.parameter_sequence = self.make_parameter_sequence(variable_params)

    def __iter__(self):
        """
        Yields
        -------
        sim_market : :class:`~crvusdsim.pool.SimMarketInstance`
            A Market object with the current variable parameters set.

        params : dict
            A dictionary of the pool parameters set on this iteration.
        """
        for params in self.parameter_sequence:
            sim_market = self.sim_market_template.copy()

            if self.sim_mode == "pool":
                self.set_pool_attributes(sim_market.pool, params)
            elif self.sim_mode == "controller":
                self.set_controller_attributes(sim_market.controller, params)
            elif self.sim_mode == "rate":
                self.set_rate_attributes(sim_market, params)

            yield sim_market, params

    def make_parameter_sequence(self, variable_params):
        """
        Returns a list of dicts for each possible combination of the input parameters.

        Parameters
        ----------
        variable_params: dict
            Pool parameters to vary across simulations.

            Keys: pool parameters, Values: iterable of values

        Returns
        -------
        List(dict)
            A list of dicts defining the parameters for each iteration.
        """
        if not variable_params:
            return []

        keys, values = zip(*variable_params.items())
        # self._validate_attributes(self.pool_template, keys)

        sequence = []
        for vals in product(*values):
            params = dict(zip(keys, vals))
            sequence.append(params)

        return sequence

    def set_pool_attributes(self, pool, attribute_dict):
        """
        Sets the pool attributes defined in attribute_dict.

        Supports setting attributes with :python:`setattr(pool, key, value)` or
        specialized setters defined in the 'setters' property:
        :python:`self.setters[key](pool, value)`

        For metapools, basepool parameters can be referenced by appending "_base" to
        an attribute's name.

        Parameters
        ----------
        pool : :class:`~curvesim.templates.SimPool`
            The pool object to be modified.

        attribute_dict : dict
            A dict mapping attribute names to values.
        """
        if attribute_dict is None:
            return

        self._validate_attributes(pool, attribute_dict)

        for attribute, value in attribute_dict.items():
            self._set_pool_attribute(pool, attribute, value)

    def set_controller_attributes(self, controller, attribute_dict):
        """
        Sets the controller attributes defined in attribute_dict.
        """
        if attribute_dict is None:
            return

        for attribute, value in attribute_dict.items():
            self._set_controller_attribute(controller, attribute, value)

    def set_rate_attributes(self, sim_market: SimMarketInstance, attribute_dict):
        """
        Sets the policy attributes defined in attribute_dict.
        """
        if attribute_dict is None:
            return

        for attribute, value in attribute_dict.items():
            self._set_rate_attribute(sim_market, attribute, value)

    def _set_pool_attribute(self, pool, attr, value):
        """
        Sets a single pool attribute.

        Supports setting attributes with :python:`setattr(pool, attr, value)` or
        specialized setters defined in the 'setters' property:
        :python:`self.setters[attr](pool, value)`

        For metapools, basepool parameters can be referenced by appending "_base" to
        an attribute's name.

        Parameters
        ----------
        pool : :class:`~curvesim.templates.SimPool`
            The pool object to be modified.

        attr : str
            The attribute to be set.

        value :
            The value to be set for the attribute.
        """
        if attr in self.setters:
            self.setters[attr](pool, value)
        else:
            pool_attr = (pool, attr)
            setattr(*pool_attr, value)

    def _set_controller_attribute(self, controller, attr, value):
        if attr in self.controller_setters:
            self.controller_setters[attr](controller, value)
        else:
            controller_attr = (controller, attr)
            setattr(*controller_attr, value)

    def _set_rate_attribute(self, sim_market: SimMarketInstance, attr, value):
        if attr in self.rate_setters:
            if isinstance(value, float) and value < 1:
                value = int(((1 + value) ** (1 / (365 * 86400)) - 1) * 10**18)
            self.rate_setters[attr](sim_market.policy, value)
        else:
            rate_attr = (sim_market.policy, attr)
            setattr(*rate_attr, value)

    def _validate_attributes(self, pool, attributes):
        """
        Raises error if attributes are not present in self.setters or pool attributes.

        Parameters
        ----------
        pool : :class:`~curvesim.templates.SimPool`
            The pool object to be modified.

        attributes : Iterable[str]
            Iterable of attribute names.

        Raises
        ------
        ParameterSamplerError

        """
        missing = []
        for attribute in attributes:
            pool_attr = (pool, attribute)

            if attribute not in self.setters and not hasattr(*pool_attr):
                missing.append(attribute)

        if missing:
            pool_class = pool.__class__.__name__
            self_class = self.__class__.__name__

            raise ParameterSamplerError(
                f"Input parameters not found in '{self_class}.setters' "
                f"or '{pool_class}' attributes: {missing}"
            )


CRVUSD_POOL_MAP = {SimLLAMMAPool: ParameterizedLLAMMAPoolIterator}
