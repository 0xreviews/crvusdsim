
from abc import ABC, abstractmethod
from collections.abc import Iterable

from pandas import DataFrame, MultiIndex, Series
from numpy import timedelta64, log, exp, mean
from altair import Axis

from curvesim.exceptions import MetricError
from curvesim.utils import cache, override

from curvesim.metrics.base import Metric

class ControllerMetric(Metric):
    """
    :class:`Metric`
    """

    __slots__ = ["_controller"]

    def __init__(self, controller, **kwargs):
        """
        Parameters
        ----------
        controller : Controller object
            A controller simulation interface. Used to select the controller's configuration from
            :func:`controller_config` and stored as :python:`self._controller` for access during
            metric computations.
        """
        self._controller = controller
        super().__init__(**kwargs)  # kwargs are ignored

    @property
    @abstractmethod
    def controller_config(self):
        """
        Raises :python:`NotImplementedError` if property is not defined.
        """
        raise NotImplementedError

    def set_controller(self, controller):
        self._controller = controller

    def set_controller_state(self, controller_state):
        for attr, val in controller_state.items():
            setattr(self._controller, attr, val)

    @property
    @override
    @cache
    def config(self):
        """
        Returns the config corresponding to the controller's type in :func:`controller_config`.

        Generally, this property should be left "as is", with controller-specific configs
        defined in :func:`controller_config`.
        """
        try:
            return self.controller_config[type(self._controller)]
        except KeyError as e:
            metric_type = self.__class__.__name__
            controller_type = self._controller.__class__.__name__
            raise MetricError(
                f"Pool type {controller_type} not found in {metric_type} controller_config.)"
            ) from e

class UsersHealth(ControllerMetric):
    """
    Records annualized returns for different range N.
    """

    def __init__(self, pool, controller, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pool = pool
        self._controller = controller

    @property
    @cache
    def config(self):
        config = {
            "functions": {
                "summary": {
                    "averange_user_health": "mean",
                },
                "metrics": self.averange_user_health,
            },
            "plot": {
                "metrics": {
                    "averange_user_health": {
                        "title": f"Averange Users Health",
                        "style": "time_series",
                        "resample": "last",
                        "encoding": {"y": {"axis": Axis(format="%")}},
                    },
                },
                "summary": {
                    "averange_user_health": {
                        "title": f"Averange Users Health",
                        "style": "point_line",
                        "encoding": {"y": {"axis": Axis(format="%")}},
                    },
                },
            },
        }

        return config

    def averange_user_health(self, **kwargs):
        """
        Computes all metrics for each timestamp in an individual run.
        Used for non-meta users.
        """
        state_data = kwargs["state_data"]
        results = DataFrame(
            [mean(row) for row in state_data["users_health"]],
            index=state_data["users_health"].index,
        )
        results.columns = list(self.config["plot"]["metrics"])
        return results.astype("float64")



class LiquidationVolume(ControllerMetric):
    """
    Records total trade volume for each timestamp.
    """

    @property
    @cache
    def pool_config(self):
        config = {
            "functions": {
                "summary": {"liquidation_volume": "sum"},
                "metrics": {"liquidation_volume": self.get_llamma_liquidation_volume}
            },
            "plot": {
                "metrics": {
                    "liquidation_volume": {
                        "title": "Daily Volume",
                        "style": "time_series",
                        "resample": "sum",
                    },
                },
                "summary": {
                    "liquidation_volume": {
                        "title": "Total Volume",
                        "style": "point_line",
                    },
                },
            },
        }

        return config

    # @todo
    def get_llamma_liquidation_volume(self, **kwargs):
        """
        Records trade volume for stableswap non-meta-pools.
        """
        trade_data = kwargs["trade_data"]

        def per_timestamp_function(trade_data):
            trades = trade_data.trades
            return sum(trade.amount_in for trade in trades) / 10**18

        return self._get_volume(trade_data, per_timestamp_function)

    def _get_volume(self, trade_data, per_timestamp_function):
        volume = trade_data.apply(per_timestamp_function, axis=1)
        results = DataFrame(volume)
        results.columns = ["liquidation_volume"]
        return results