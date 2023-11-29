"""
Module to house the `StateLog`, a generic class to record changing pool states
during simulations.
"""
from pandas import DataFrame, concat

from curvesim.metrics.base import PoolMetric
from crvusdsim.metrics.state_log.controller_state import get_controller_state

from crvusdsim.metrics.state_log.controller_state import get_controller_state
from crvusdsim.pool import SimMarketInstance

from .pool_parameters import get_N_parameters, get_pool_parameters, get_controller_parameters
from .pool_state import get_pool_state


class StateLog:
    """
    Logger that records simulation/pool state throughout each simulation run and
    computes metrics at the end of each run.
    """

    __slots__ = [
        "metrics",
        "sim_market",
        "state_per_run",
        "state_per_trade",
        "sim_mode",
    ]

    def __init__(self, sim_market: SimMarketInstance, metrics, parameters, sim_mode="pool"):
        (
            pool,
            controller,
            collateral_token,
            stablecoin,
            aggregator,
            price_oracle,
            stableswap_pools,
            peg_keepers,
            policy,
            factory,
        ) = sim_market
        self.sim_market = sim_market
        self.metrics = metrics
        self.sim_mode = sim_mode
        self.state_per_trade = []
        if sim_mode == "pool":
            self.state_per_run = get_parameters_func[sim_mode](pool)
        elif sim_mode == "controller":
            self.state_per_run = get_parameters_func[sim_mode](controller)
        elif sim_mode == "N":
            self.state_per_run = get_parameters_func[sim_mode](parameters)

    def update(self, **kwargs):
        """Records pool state and any keyword arguments provided."""

        (
            pool,
            controller,
            collateral_token,
            stablecoin,
            aggregator,
            price_oracle,
            stableswap_pools,
            peg_keepers,
            policy,
            factory,
        ) = self.sim_market
        if self.sim_mode == "pool":
            self.state_per_trade.append({"state_data": get_pool_state(pool), **kwargs})
        elif self.sim_mode == "controller":
            self.state_per_trade.append({"state_data": get_controller_state(pool, controller), **kwargs})
        if self.sim_mode == "N":
            self.state_per_trade.append({"state_data": get_controller_state(pool, controller), **kwargs})

    def get_logs(self):
        """Returns the accumulated log data."""

        df = DataFrame(self.state_per_trade)
        
        times = [state["price_sample"].timestamp for state in self.state_per_trade]
        state_per_trade = {col: DataFrame(df[col].to_list(), index=times) for col in df}

        return {
            "sim_parameters": DataFrame(self.state_per_run, index=[0]),
            **state_per_trade,
        }

    def compute_metrics(self):
        """Computes metrics from the accumulated log data."""

        state_logs = self.get_logs()
        metric_data = [metric.compute(state_logs) for metric in self.metrics]
        data_per_trade, summary_data = tuple(zip(*metric_data))  # transpose tuple list
        
        return (
            state_logs["sim_parameters"],
            concat(data_per_trade, axis=1),
            concat(summary_data, axis=1),
            state_logs["state_data"],
        )


get_parameters_func = {
    "pool": get_pool_parameters,
    "controller": get_controller_parameters,
    "N": get_N_parameters,
}