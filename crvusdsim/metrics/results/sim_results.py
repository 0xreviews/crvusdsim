from pandas import concat

from curvesim.plot.altair import result_plotter as altair_plotter
from curvesim.metrics import SimResults as BaseSimResults

from crvusdsim.plot.bands_arb_profits_plot import make_bands_arb_profits_plot
from altair import vconcat, hconcat


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
        "prices",
        "sim_mode",
    ]

    def __init__(
        self,
        state_data,
        prices=None,
        sim_mode="pool",
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.state_data = state_data
        self.prices = prices
        self.sim_mode = sim_mode

    def plot(self, summary=True, data=True, save_as=None):
        """
        Returns and optionally saves a plot of the results data.

        Parameters
        ----------
        summary : bool, default=True
            If true, includes summary data in the plot.

        data : bool, default=True
            If true, includes timeseries data in the plot.

        save_as : str, optional
            Path to save plot output to. Typically an .html file. See
            `Altair docs <https://altair-viz.github.io/user_guide/saving_charts.html>`_
            for additional options.

        bands_plot : bool, default=False
            If true, includes bands arbitrageur profits data in the plot.


        Returns
        -------
        altair.VConcatChart

        """
        if self.sim_mode == "N":
            chart = super().plot(summary, data, save_as=None)
            bands_arb_profits_chart = make_bands_arb_profits_plot(self.state_data, self.prices)
            page = vconcat(chart, bands_arb_profits_chart).resolve_scale(
                color="independent"
            )
            
            if save_as:
                page.save(save_as)

            return page
        else:
            return super().plot(summary, data, save_as=save_as)
