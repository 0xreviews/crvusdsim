from abc import ABC, abstractmethod
from typing import List

from curvesim.logging import get_logger
from crvusdsim.iterators.price_samplers.price_volume import PriceVolumeSample
from crvusdsim.templates import Trader

from crvusdsim.pool import SimMarketInstance
from crvusdsim.pool.sim_interface.sim_stableswap import SimCurveStableSwapPool

logger = get_logger(__name__)


class Strategy(ABC):
    """
    A Strategy defines the trading approach used during each step of a simulation.
    It executes the trades using an injected `Trader` class and then logs the
    changes using the injected `StateLog` class.

    Class Attributes
    ----------------
    llamma_trader_class : :class:`~crvusdsim.pipelines.templates.Trader`
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
    llamma_trader_class = None
    stableswap_trader_class = None
    pegkeeper_caller_class = None
    state_log_class = None

    def __init__(self, metrics, sim_mode="rate", bands_strategy_class=None, bands_strategy_kwargs=None):
        """
        Parameters
        ----------
        metrics : List[Metric]
            A list of metrics used to evaluate the performance of the strategy.
        """
        self.metrics = metrics
        self.sim_mode = sim_mode
        self.bands_strategy_class = bands_strategy_class
        self.bands_strategy_kwargs = bands_strategy_kwargs

    def __call__(self, sim_market: SimMarketInstance, parameters, price_sampler):
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
        assert pool == controller.AMM, "`controller.AMM` is not `pool`"
        assert pool.BORROWED_TOKEN == controller.STABLECOIN
        assert pool.COLLATERAL_TOKEN == controller.COLLATERAL_TOKEN

        llamma_trader = self.llamma_trader_class(pool)
        stableswap_traders = {}
        for stable_pool in stableswap_pools:
            _symbols = (stable_pool.assets.symbols[0], "crvUSD")
            stableswap_traders[_symbols] = self.stableswap_trader_class(stable_pool)

        state_log = self.state_log_class(
            sim_market,
            self.metrics,
            parameters=parameters,
            sim_mode=self.sim_mode,
        )
        # TODO: stableswap_trader_class, pegkeeper_caller_class

        logger.info("[%s] Simulating with %s", pool.symbol, parameters)

        prices = price_sampler.prices

        if self.bands_strategy_class is not None:
            _kwargs = {}
            if self.bands_strategy_kwargs is not None:
                _kwargs = self.bands_strategy_kwargs
            # close exchange fees when adjust bands
            pool.fees_switch = False
            bands_strategy = self.bands_strategy_class(
                pool,
                prices,
                controller,
                parameters,
                **_kwargs,
            )
            bands_strategy.do_strategy()

            pool.fees_switch = True

        aggregator.prepare_for_run(price_sampler)
        for pk in sim_market.peg_keepers:
            pk.prepare_for_run(prices)
        pool.prepare_for_run(prices)
        controller.prepare_for_run(prices)

        if price_sampler.peg_prices is not None:
            for stable_pool in stableswap_pools:
                _symbols = (stable_pool.assets.symbols[0], "crvUSD")
                stable_pool.prepare_for_run(price_sampler.peg_prices[_symbols])

        for sample in price_sampler:
            stableswap_trade_datas = []
            if sample.peg_prices is not None:
                stableswap_trade_datas = self._process_stableswap(
                    stableswap_pools, sample, stableswap_traders
                )

            _ts = sample.timestamp.timestamp()
            aggregator.prepare_for_trades(_ts)
            for pk in sim_market.peg_keepers:
                pk.prepare_for_trades(_ts)

            _p = int(list(sample.prices.values())[0] * 10**18)
            pool.price_oracle_contract.set_price(_p)
            pool.prepare_for_trades(_ts)
            controller.prepare_for_trades(_ts)

            trader_args = self._get_trader_inputs(sample)
            trade_data = llamma_trader.process_time_sample(*trader_args)

            controller.after_trades(do_liquidate=self.sim_mode in ["controller"])
            state_log.update(
                price_sample=sample,
                trade_data=trade_data,
                stableswap_trade_datas=stableswap_trade_datas,
            )

        return state_log.compute_metrics()

    @abstractmethod
    def _get_trader_inputs(self, sample):
        """
        Process the price sample into appropriate inputs for the
        trader instance.
        """
        raise NotImplementedError

    def _process_stableswap(
        self,
        stableswap_pools: List[SimCurveStableSwapPool],
        sample: PriceVolumeSample,
        traders: dict,
    ):
        stableswap_trade_datas = {}
        for stable_pool in stableswap_pools:
            _symbols = (stable_pool.assets.symbols[0], "crvUSD")
            if _symbols not in sample.peg_prices or sample.peg_prices[_symbols] is None:
                stableswap_trade_datas[_symbols] = []
                continue
            _peg_p = sample.peg_prices[_symbols]
            stable_pool.prepare_for_trades(sample.timestamp)
            trader_args = (_peg_p, 0)  # profit_threshold = 0
            trade_data = traders[_symbols].process_time_sample(*trader_args)
            stableswap_trade_datas[_symbols] = trade_data

        return stableswap_trade_datas
