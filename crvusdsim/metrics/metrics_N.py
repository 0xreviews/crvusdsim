from abc import ABC, abstractmethod
from collections.abc import Iterable

from pandas import DataFrame, MultiIndex, Series
from numpy import timedelta64, log, exp
from altair import Axis

from curvesim.exceptions import MetricError
from curvesim.utils import cache, override

from curvesim.metrics.base import Metric


class RangeNReturns(Metric):
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
                    "user_value": {
                        "annualized_returns": self.compute_annualized_returns
                    }
                },
                "metrics": self.get_user_value,
            },
            "plot": {
                "metrics": {
                    "user_value": {
                        "title": f"User Value",
                        "style": "time_series",
                        "resample": "last",
                        "encoding": {"y": {"axis": Axis(format="%")}},
                    },
                },
                "summary": {
                    "user_value": {
                        "title": f"Annualized Returns",
                        "style": "point_line",
                        "encoding": {"y": {"axis": Axis(format="%")}},
                    },
                },
            },
        }

        return config

    def get_user_value(self, **kwargs):
        """
        Computes all metrics for each timestamp in an individual run.
        Used for non-meta users.
        """
        state_data = kwargs["state_data"]
        first_value = state_data["users_init_y"].iloc[0][0]
        results = DataFrame(
            [row[0] / first_value for row in state_data["users_y"]],
            index=state_data["users_y"].index,
        )
        results.columns = list(self.config["plot"]["metrics"])
        return results.astype("float64")

    def compute_annualized_returns(self, data):
        """Computes annualized returns from a series of pool values."""
        year_multipliers = timedelta64(365, "D") / data.index.to_series().diff()
        log_returns = log(data).diff()  # pylint: disable=no-member
        return exp((log_returns * year_multipliers).mean()) - 1
