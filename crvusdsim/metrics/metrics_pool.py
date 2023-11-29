"""
Specific metric classes for use in simulations.
"""


__all__ = [
    "ArbMetrics",
    "PoolVolume",
    "PoolValue",
    "Timestamp",
]

from copy import deepcopy

from altair import Axis, Scale, X, Y
from numpy import where, exp, log, timedelta64
from pandas import DataFrame, concat

from curvesim.utils import cache, get_pairs
from .base import MarketMetric, PricingMarketMetric

from crvusdsim.pool.sim_interface import SimLLAMMAPool


class ArbMetrics(PricingMarketMetric):
    """
    Computes metrics characterizing arbitrage trades: arbitrageur profits, pool fees,
    and post-trade price error between target and pool price.
    """

    @property
    def config(self):
        return {
            "functions": {
                "metrics": self.compute_arb_metrics,
                "summary": {
                    "arb_profit": "sum",
                    "pool_fees": "sum",
                    # "price_error": "median",
                },
            },
            "plot": {
                "metrics": {
                    "arb_profit": {
                        "title": f"Daily Arbitrageur Profit (in {self.numeraire})",
                        "style": "time_series",
                        "resample": "sum",
                    },
                    "pool_fees": {
                        "title": f"Daily Pool Fees (in {self.numeraire})",
                        "style": "time_series",
                        "resample": "sum",
                    },
                    # "price_error": {
                    #     "title": "Price Error",
                    #     "style": "histogram",
                    #     "encoding": {
                    #         "x": {
                    #             "title": "Price Error (binned)",
                    #             "shorthand": "price_error",
                    #             "scale": Scale(domain=[0, 0.05], clamp=True),
                    #         },
                    #     },
                    # },
                },
                "summary": {
                    "arb_profit": {
                        "title": f"Total Arbitrageur Profit (in {self.numeraire})",
                        "style": "point_line",
                    },
                    "pool_fees": {
                        "title": f"Total Pool Fees (in {self.numeraire})",
                        "style": "point_line",
                    },
                    # "price_error": {
                    #     "title": "Price Error (median)",
                    #     "style": "point_line",
                    # },
                },
            },
        }

    def compute_arb_metrics(self, **kwargs):
        """Computes all metrics for each timestamp in an individual run."""
        price_sample = kwargs["price_sample"]
        trade_data = kwargs["trade_data"]

        prices = DataFrame(price_sample.prices.to_list(), index=price_sample.index)

        profits = self._compute_profits(prices, trade_data.trades)
        # price_error = trade_data.price_errors.apply(
        #     lambda errors: sum(abs(e) for e in errors)
        # )

        # results = concat([profits, price_error], axis=1)
        results = concat([profits], axis=1)
        results.columns = list(self.config["plot"]["metrics"])

        return results

    def _compute_profits(self, price_df, trade_df):
        """
        Computes arbitrageur profits and pool fees for a single row of data (i.e.,
        a single timestamp) in units of the chosen numeraire, `self.numeraire`.
        """
        numeraire = self.numeraire

        profit = []
        for price_row, trade_row in zip(price_df.iterrows(), trade_df):
            timestamp, prices = price_row
            arb_profit = 0
            pool_profit = 0

            for trade in trade_row:
                market_price = prices.iloc[0]

                pump = trade.coin_in == numeraire

                if pump:
                    arb = trade.amount_out * market_price - trade.amount_in
                    fee = trade.fee
                else:
                    arb = trade.amount_out - trade.amount_in * market_price
                    fee = trade.fee * market_price

                if arb < 0:
                    pass

                arb_profit += arb
                pool_profit += fee

            profit.append(
                {
                    "timestamp": timestamp,
                    "arb_profit": arb_profit / 10**18,
                    "pool_profit": pool_profit / 10**18,
                }
            )

        return DataFrame(profit).set_index("timestamp")


class PoolVolume(PricingMarketMetric):
    """
    Records total trade volume for each timestamp.
    """

    @property
    @cache
    def config(self):
        return {
            "functions": {
                "metrics": self.get_llamma_pool_volume,
                "summary": {"pool_volume": "sum"},
            },
            "plot": {
                "metrics": {
                    "pool_volume": {
                        "title": "Daily Volume crvUSD",
                        "style": "time_series",
                        "resample": "sum",
                    },
                },
                "summary": {
                    "pool_volume": {
                        "title": "Total Volume crvUSD",
                        "style": "point_line",
                    },
                },
            },
        }

    def get_llamma_pool_volume(self, **kwargs):
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
        results.columns = ["pool_volume"]
        return results


class PoolValue(PricingMarketMetric):
    """
    Computes pool's value over time in virtual units and the chosen
    numeraire, `self.numeraire`. Each are summarized as annualized returns.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.numeraire = "crvUSD"

    @property
    @cache
    def config(self):
        return {
            "functions": {
                "metrics": self.get_llamma_pool_value,
                "summary": {
                    "pool_value": {
                        "annualized_returns": self.compute_annualized_returns
                    },
                    "loss_value": {
                        "annualized_arb_profits": self.compute_annualized_arb_profits
                    },
                },
            },
            "plot": {
                "metrics": {
                    "pool_value": {
                        "title": f"Pool Value (in {self.numeraire})",
                        "style": "time_series",
                        "resample": "last",
                        "encoding": {"y": {"scale": Scale(zero=True)}},
                    },
                    "loss_value": {
                        "title": f"Loss Value (in {self.numeraire})",
                        "style": "time_series",
                        "resample": "last",
                        "encoding": {
                            "y": {"axis": Axis(format="%"), "scale": Scale(zero=True)}
                        },
                    },
                },
                "summary": {
                    "pool_value": {
                        "title": f"Annualized Returns (in {self.numeraire})",
                        "style": "point_line",
                        "encoding": {
                            "y": {"axis": Axis(format="%"), "scale": Scale(zero=True)}
                        },
                    },
                    "loss_value": {
                        "title": f"Annualized Loss(%)",
                        "style": "point_line",
                        "encoding": {
                            "y": {"axis": Axis(format="%"), "scale": Scale(zero=True)}
                        },
                    },
                },
            },
        }

    def get_llamma_pool_value(self, **kwargs):
        """
        Computes all metrics for each timestamp in an individual run.
        Used for non-meta stableswap pools.
        """
        return self._get_pool_value(kwargs["state_data"])

    def _get_pool_value(self, state_data):
        """
        Computes all metrics for each timestamp in an individual run.
        Used for non-meta pools.
        """
        results = state_data[["pool_value", "arb_profits_percent"]].set_axis(
            ["pool_value", "loss_value"], axis=1
        )
        results.columns = list(self.config["plot"]["metrics"])
        return results.astype("float64")

    def compute_annualized_returns(self, data):
        """Computes annualized returns from a series of pool values."""
        year_multipliers = timedelta64(365, "D") / data.index.to_series().diff()
        log_returns = log(data).diff()  # pylint: disable=no-member

        return exp((log_returns * year_multipliers).mean()) - 1

    def compute_annualized_arb_profits(self, data):
        """Computes annualized loss from a series of loss percent."""
        data = 1 + data
        year_multipliers = timedelta64(365, "D") / data.index.to_series().diff()
        log_returns = log(data).diff()  # pylint: disable=no-member

        return exp((log_returns * year_multipliers).mean()) - 1


class Timestamp(MarketMetric):
    """Simple pass-through metric to record timestamps."""

    @property
    def config(self):
        return {"functions": {"metrics": self._get_timestamp}}

    def _get_timestamp(self, **kwargs):
        price_sample = kwargs["price_sample"]
        return DataFrame(price_sample.timestamp)
