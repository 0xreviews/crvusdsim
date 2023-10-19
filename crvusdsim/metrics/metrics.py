"""
Specific metric classes for use in simulations.
"""


__all__ = [
    "ArbMetrics",
    "PoolBalance",
    "PoolVolume",
    "PoolValue",
    "PriceDepth",
    "Timestamp",
]

from copy import deepcopy

from altair import Axis, Scale, X, Y
from numpy import where, exp, log, timedelta64
from pandas import DataFrame, concat

from curvesim.utils import cache, get_pairs
from curvesim.metrics.base import Metric, PoolMetric, PoolPricingMetric, PricingMetric

from crvusdsim.pool.sim_interface import SimLLAMMAPool


class ArbMetrics(PricingMetric):
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
                    "price_error": "median",
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
                    "price_error": {
                        "title": "Price Error",
                        "style": "histogram",
                        "encoding": {
                            "x": {
                                "title": "Price Error (binned)",
                                "shorthand": "price_error",
                                "scale": Scale(domain=[0, 0.05], clamp=True),
                            },
                        },
                    },
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
                    "price_error": {
                        "title": "Price Error (median)",
                        "style": "point_line",
                    },
                },
            },
        }

    def __init__(self, pool, **kwargs):
        super().__init__(pool.assets.symbols)

    def compute_arb_metrics(self, **kwargs):
        """Computes all metrics for each timestamp in an individual run."""
        price_sample = kwargs["price_sample"]
        trade_data = kwargs["trade_data"]

        prices = DataFrame(price_sample.prices.to_list(), index=price_sample.index)

        profits = self._compute_profits(prices, trade_data.trades)
        price_error = trade_data.price_errors.apply(
            lambda errors: sum(abs(e) for e in errors)
        )

        results = concat([profits, price_error], axis=1)
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
                if trade.coin_in == numeraire:
                    market_price = 1 / market_price

                arb = trade.amount_out - trade.amount_in * market_price
                fee = trade.fee

                price = prices.iloc[0]
                if trade.coin_out != numeraire:
                    arb *= price
                if trade.coin_in != numeraire:
                    fee *= price

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


class PoolVolume(PoolPricingMetric):
    """
    Records total trade volume for each timestamp.
    """

    @property
    @cache
    def pool_config(self):
        base = {
            "functions": {"summary": {"pool_volume": "sum"}},
            "plot": {
                "metrics": {
                    "pool_volume": {
                        "title": "Daily Volume",
                        "style": "time_series",
                        "resample": "sum",
                    },
                },
                "summary": {
                    "pool_volume": {
                        "title": "Total Volume",
                        "style": "point_line",
                    },
                },
            },
        }

        functions = {
            SimLLAMMAPool: self.get_llamma_pool_volume,
        }

        units = {
            SimLLAMMAPool: "(of Any Coin)",
        }

        config = {}
        for pool in functions:
            cfg = deepcopy(base)
            cfg["functions"]["metrics"] = functions[pool]
            _units = units[pool]
            cfg["plot"]["metrics"]["pool_volume"]["title"] = "Daily Volume " + _units
            cfg["plot"]["summary"]["pool_volume"]["title"] = "Total Volume " + _units
            config[pool] = cfg

        return config

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


class PoolValue(PoolPricingMetric):
    """
    Computes pool's value over time in virtual units and the chosen
    numeraire, `self.numeraire`. Each are summarized as annualized returns.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.numeraire = self.coin_names[0]

    @property
    @cache
    def pool_config(self):
        plot = {
            "metrics": {
                "pool_value": {
                    "title": f"Pool Value (in {self.numeraire})",
                    "style": "time_series",
                    "resample": "last",
                },
                "loss_percent": {
                    "title": f"Loss Value (in {self.numeraire})",
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
                "loss_percent": {
                    "title": f"Annualized loss percent",
                    "style": "point_line",
                    "encoding": {"y": {"axis": Axis(format="%")}},
                },
            },
        }

        summary_fns = {
            "pool_value": {"annualized_returns": self.compute_annualized_returns},
            "loss_percent": {"annualized_loss": self.compute_annualized_loss},
        }

        base = {
            "functions": {"summary": summary_fns},
            "plot": plot,
        }

        functions = {
            SimLLAMMAPool: self.get_llamma_pool_value,
        }

        config = {}
        for pool, fn in functions.items():
            config[pool] = deepcopy(base)
            config[pool]["functions"]["metrics"] = fn

        return config

    def get_llamma_pool_value(self, **kwargs):
        """
        Computes all metrics for each timestamp in an individual run.
        Used for non-meta stableswap pools.
        """
        return self._get_pool_value(kwargs["pool_state"])

    def _get_pool_value(self, pool_state):
        """
        Computes all metrics for each timestamp in an individual run.
        Used for non-meta pools.
        """
        results = pool_state[["pool_value", "loss_percent"]].set_axis(
            ["pool_value", "loss_value"], axis=1
        )
        results.columns = list(self.config["plot"]["metrics"])
        return results.astype("float64")

    def compute_annualized_returns(self, data):
        """Computes annualized returns from a series of pool values."""
        year_multipliers = timedelta64(365, "D") / data.index.to_series().diff()
        log_returns = log(data).diff()  # pylint: disable=no-member

        return exp((log_returns * year_multipliers).mean()) - 1

    def compute_annualized_loss(self, data):
        """Computes annualized loss from a series of loss percent."""
        data = 1 + data
        year_multipliers = timedelta64(365, "D") / data.index.to_series().diff()
        log_returns = log(data).diff()  # pylint: disable=no-member

        return exp((log_returns * year_multipliers).mean()) - 1


class PriceDepth(PoolMetric):
    """
    Computes metrics indicating a pool's price (liquidity) depth. Generally, uses
    liquidity density, % change in reserves per % change in price.
    """

    __slots__ = ["_factor"]

    @property
    @cache
    def pool_config(self):
        ss_config = {
            "functions": {
                "metrics": self.get_curve_LD,
                "summary": {"liquidity_density": ["median", "min"]},
            },
            "plot": {
                "metrics": {
                    "liquidity_density": {
                        "title": "Liquidity Density (Daily Median)",
                        "style": "time_series",
                        "resample": "median",
                        "encoding": {
                            "y": {"title": "Liquidity Density (Daily Median)"}
                        },
                    }
                },
                "summary": {
                    "liquidity_density": {
                        "title": "Liquidity Density",
                        "style": "point_line",
                    }
                },
            },
        }

        return dict.fromkeys(
            [SimLLAMMAPool],
            ss_config,
        )

    def __init__(self, pool, factor=10**8, **kwargs):
        self._factor = factor
        super().__init__(pool, **kwargs)

    def get_curve_LD(self, **kwargs):
        """
        Computes liquidity density for each timestamp in an individual run.
        Used for all Curve pools.
        """
        pool_state = kwargs["pool_state"]

        coin_pairs = get_pairs(
            self._pool.coin_names
        )  # for metapool, uses only meta assets
        LD = pool_state.apply(self._get_curve_LD_by_row, axis=1, coin_pairs=coin_pairs)
        return DataFrame(LD, columns=["liquidity_density"])

    def _get_curve_LD_by_row(self, pool_state_row, coin_pairs):
        """
        Computes liquidity density for a single row of data (i.e., a single timestamp).
        Used for all Curve pools.
        """
        self.set_pool_state(pool_state_row)

        LD = []
        for pair in coin_pairs:
            ld = self._compute_liquidity_density(*pair)
            LD.append(ld)
        return sum(LD) / len(LD)

    def _compute_liquidity_density(self, coin_in, coin_out):
        """
        Computes liquidity density for a single pair of coins.
        """
        factor = self._factor
        pool = self._pool
        post_trade_price = self._post_trade_price

        price_pre = pool.price(coin_in, coin_out, use_fee=False)
        price_post = post_trade_price(pool, coin_in, coin_out, factor)
        LD1 = price_pre / ((price_pre - price_post) * factor)

        price_pre = pool.price(coin_out, coin_in, use_fee=False)
        # pylint: disable-next=arguments-out-of-order
        price_post = post_trade_price(pool, coin_out, coin_in, factor)
        LD2 = price_pre / ((price_pre - price_post) * factor)

        return (LD1 + LD2) / 2

    @staticmethod
    def _post_trade_price(pool, coin_in, coin_out, factor, use_fee=False):
        """
        Computes price after executing a trade of size coin_in balances / factor.
        """

        size = pool.asset_balances[coin_in] // factor

        with pool.use_snapshot_context():
            pool.trade(coin_in, coin_out, size)
            price = pool.price(coin_in, coin_out, use_fee=use_fee)

        return price


class Timestamp(Metric):
    """Simple pass-through metric to record timestamps."""

    @property
    def config(self):
        return {"functions": {"metrics": self._get_timestamp}}

    def _get_timestamp(self, **kwargs):
        price_sample = kwargs["price_sample"]
        return DataFrame(price_sample.timestamp)
