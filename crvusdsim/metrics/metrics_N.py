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

    def __init__(self, pool, controller,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pool = pool
        self._controller = controller
        self.numeraire = pool.coin_names[0]

    @property
    @cache
    def config(self):
        config = {
            "functions": {
                "summary": {"annualized_returns": "sum"},
                "metrics": {"annualized_returns": self.compute_annualized_returns},
            },
            "plot": {
                "metrics": {
                    "pool_value": {
                        "title": f"Pool Value (in {self.numeraire})",
                        "style": "time_series",
                        "resample": "last",
                    },
                },
                "summary": {
                    "pool_value": {
                        "title": f"Annualized Returns (in {self.numeraire})",
                        "style": "point_line",
                        "encoding": {"y": {"axis": Axis(format="%")}},
                    },
                },
            },
        }

        return config

    def compute_annualized_returns(self, data):
        """Computes annualized returns from a series of pool values."""
        year_multipliers = timedelta64(365, "D") / data.index.to_series().diff()
        log_returns = log(data).diff()  # pylint: disable=no-member

        return exp((log_returns * year_multipliers).mean()) - 1
