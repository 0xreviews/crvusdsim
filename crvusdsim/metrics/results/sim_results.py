from pandas import concat

from curvesim.plot.altair import result_plotter as altair_plotter
from curvesim.metrics import SimResults as BaseSimResults


class SimResults(BaseSimResults):
    """
    Results container with methods to plot or return metrics as DataFrames.
    """

    __slots__ = [
        "data_per_run",
        "data_per_trade",
        "summary_data",
        "state_data",
        "factors",
        "plot_config",
        "plotter",
    ]

    def __init__(
        self,
        state_data,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.state_data = state_data

