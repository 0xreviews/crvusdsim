from abc import ABC, abstractmethod
from collections.abc import Iterable

from pandas import DataFrame, MultiIndex, Series
from numpy import timedelta64, log, exp
from altair import Axis, Scale

from curvesim.exceptions import MetricError
from curvesim.utils import cache, override

from .base import MarketMetric


class RatePegKeeper(MarketMetric):
    """
    Records annualized rate for different rate0.
    """

    @property
    @cache
    def config(self):
        return {
            "functions": {
                "metrics": self.get_borrow_rate,
                "summary": {
                    "annualized_rate": "mean",
                    "users_debt": "mean",
                    "crvusd_price": "mean",
                    "agg_price": "mean",
                },
            },
            "plot": {
                "metrics": {
                    "annualized_rate": {
                        "title": f"Annualized Rate",
                        "style": "time_series",
                        "resample": "last",
                        "encoding": {
                            "y": {"axis": Axis(format="%"), "scale": Scale(zero=True)}
                        },
                    },
                    "users_debt": {
                        "title": f"Users Total Debt",
                        "style": "time_series",
                        "resample": "last",
                        # "encoding": {"y": {"axis": Axis(format="%")}},
                    },
                    "crvusd_price": {
                        "title": f"crvUSD Price(mean)",
                        "style": "time_series",
                        "resample": "last",
                    },
                    "agg_price": {
                        "title": f"Aggregator Price",
                        "style": "time_series",
                        "resample": "last",
                    }
                },
                "summary": {
                    "annualized_rate": {
                        "title": f"Annualized Rate(avg)",
                        "style": "point_line",
                        "encoding": {"y": {"axis": Axis(format="%")}},
                    },
                    "users_debt": {
                        "title": f"Users Total Debt(mean)",
                        "style": "point_line",
                    },
                    "crvusd_price": {
                        "title": f"crvUSD Price",
                        "style": "point_line",
                    },
                    "agg_price": {
                        "title": f"Aggregator Price",
                        "style": "point_line",
                    },
                },
            },
        }

    def get_borrow_rate(self, **kwargs):
        """
        Computes all metrics for each timestamp in an individual run.
        Used for non-meta users.
        """
        state_data = kwargs["state_data"]
        results = state_data[["annualized_rate", "total_debt", "stableswap_mean_price", "agg_price"]].set_axis(
            ["annualized_rate", "users_debt", "crvusd_price", "agg_price"], axis=1
        )
        results.columns = list(self.config["plot"]["metrics"])
        return results.astype("float64")
