from abc import ABC, abstractmethod
from collections.abc import Iterable

from pandas import DataFrame, MultiIndex, Series
from numpy import timedelta64, log, exp, mean
from altair import Axis, Scale

from curvesim.exceptions import MetricError
from curvesim.utils import cache, override

from .base import MarketMetric


class ControllerMetric(MarketMetric):
    """
    :class:`Metric`
    """

    def set_controller(self, controller):
        self._controller = controller

    def set_controller_state(self, controller_state):
        for attr, val in controller_state.items():
            setattr(self._controller, attr, val)


class UsersHealth(ControllerMetric):
    """
    Records annualized returns for different range N.
    """

    @property
    @cache
    def config(self):
        return {
            "functions": {
                "summary": {
                    "averange_user_health": "mean",
                    "liquidations_count": "max",
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
                    "liquidations_count": {
                        "title": f"Liquidations Count",
                        "style": "time_series",
                        "resample": "last",
                        "encoding": {"y": {"scale": Scale(padding=10)}},
                    },
                },
                "summary": {
                    "averange_user_health": {
                        "title": f"Averange Users Health",
                        "style": "point_line",
                        "encoding": {"y": {"axis": Axis(format="%")}},
                    },
                    "liquidations_count": {
                        "title": f"Liquidations Count",
                        "style": "point_line",
                        # "encoding": {"y": {"axis": Axis(format="%")}},
                    },
                },
            },
        }

    def averange_user_health(self, **kwargs):
        """
        Computes all metrics for each timestamp in an individual run.
        Used for non-meta users.
        """
        state_data = kwargs["state_data"]
        results = DataFrame(
            {
                "users_health": [mean(row) for row in state_data["users_health"]],
                "liquidation_count": state_data["liquidation_count"],
            },
            index=state_data["users_health"].index,
        )
        results.columns = list(self.config["plot"]["metrics"])
        return results.astype("float64")


class LiquidationVolume(ControllerMetric):
    """
    Records total trade volume for each timestamp.
    """

    @property
    def config(self):
        config = {
            "functions": {
                "summary": {"liquidation_volume": "sum"},
                "metrics": self.get_liquidation_volume,
            },
            "plot": {
                "metrics": {
                    "liquidation_volume": {
                        "title": "Liquidation Volume",
                        "style": "time_series",
                        "resample": "last",
                    },
                },
                "summary": {
                    "liquidation_volume": {
                        "title": "Liquidation Total Volume",
                        "style": "point_line",
                    },
                },
            },
        }

        return config

    def get_liquidation_volume(self, **kwargs):
        """
        Records trade volume for Controller Liquidation.
        """
        state_data = kwargs["state_data"]
        results = DataFrame(
            state_data["liquidation_volume"],
            index=state_data["liquidation_volume"].index,
        )
        results.columns = list(self.config["plot"]["metrics"])
        return results.astype("float64")
