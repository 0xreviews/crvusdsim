from crvusdsim.pool.crvusd import AggregateStablePrice
from curvesim.utils import override

class SimAggregateStablePrice(AggregateStablePrice):

    @override
    def prepare_for_run(self, prices):
        super().prepare_for_run(prices)
        # Get/set initial prices
        initial_price = int(prices.iloc[0, :].tolist()[0] * 10**18)
        init_ts = int(prices.index[0].timestamp())

        self.last_price = initial_price
        self.last_timestamp = init_ts
