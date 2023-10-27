from abc import ABC, abstractmethod

from curvesim.logging import get_logger

logger = get_logger(__name__)


class Strategy(ABC):
    """
    A Strategy defines the trading approach used during each step of a simulation.
    It executes the trades using an injected `Trader` class and then logs the
    changes using the injected `StateLog` class.

    Class Attributes
    ----------------
    trader_class : :class:`~curvesim.pipelines.templates.Trader`
        Class for creating trader instances.
    state_log_class : :class:`~curvesim.metrics.StateLog`
        Class for creating state logger instances.

    Attributes
    ----------
    metrics : List[Metric]
        A list of metrics used to evaluate the performance of the strategy.
    """

    # These classes should be injected in child classes
    # to create the desired behavior.
    trader_class = None
    state_log_class = None

    def __init__(self, metrics, sim_mode="pool", bands_strategy=None):
        """
        Parameters
        ----------
        metrics : List[Metric]
            A list of metrics used to evaluate the performance of the strategy.
        """
        self.metrics = metrics
        self.sim_mode = sim_mode
        self.bands_strategy = bands_strategy

    def __call__(self, pool, controller, parameters, price_sampler):
        """
        Computes and executes trades at each timestep.

        Parameters
        ----------
        pool : :class:`~crvusdsim.pipelines.templates.SimPool`
            The pool to be traded against.

        controller : :class `~crvusdsim.pool.Controller`

        parameters : dict
            Current pool parameters from the param_sampler (only used for
            logging/display).

        price_sampler : iterable
            Iterable that for each timestep returns market data used by
            the trader.


        Returns
        -------
        metrics : tuple of lists

        """
        # pylint: disable=not-callable
        assert pool == controller.AMM, "`controller.AMM` is not `pool`"
        assert pool.BORROWED_TOKEN == controller.STABLECOIN
        assert pool.COLLATERAL_TOKEN == controller.COLLATERAL_TOKEN

        trader = self.trader_class(pool)
        state_log = self.state_log_class(
            pool,
            controller,
            self.metrics,
            parameters=parameters,
            sim_mode=self.sim_mode,
        )

        logger.info("[%s] Simulating with %s", pool.symbol, parameters)

        if self.bands_strategy is not None:
            self.bands_strategy(
                pool,
                price_sampler.prices,
                controller,
                parameters,
            )
        
        pool.prepare_for_run(price_sampler.prices)
        controller.prepare_for_run(price_sampler.prices)

        for sample in price_sampler:
            pool.price_oracle_contract.set_price(
                int(list(sample.prices.values())[0] * 10**18)
            )
            pool.prepare_for_trades(sample.timestamp)
            controller.prepare_for_trades(sample.timestamp)
            trader_args = self._get_trader_inputs(sample)
            trade_data = trader.process_time_sample(*trader_args)
            state_log.update(price_sample=sample, trade_data=trade_data)

        # @todo liquidation in Controller

        return state_log.compute_metrics()

    @abstractmethod
    def _get_trader_inputs(self, sample):
        """
        Process the price sample into appropriate inputs for the
        trader instance.
        """
        raise NotImplementedError
