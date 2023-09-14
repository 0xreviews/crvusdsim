"""
Peg Keeper for pool with equal decimals of coins
"""

from curvesim.pool.cryptoswap import CurveCryptoPool

from crvusdsim.pool.crvusd.controller_factory import ControllerFactory
from crvusdsim.pool.crvusd.price_oracle.aggregate_stable_price import AggregateStablePrice

# Time between providing/withdrawing coins
ACTION_DELAY = 15 * 60
ADMIN_ACTIONS_DELAY = 3 * 86400

PRECISION = 10 ** 18
# Calculation error for profit
PROFIT_THRESHOLD = 10 ** 18

SHARE_PRECISION = 10 ** 5
SHARE_PRECISION = 10 ** 5

class PegKeeper:

    __all__ = [
        "POOL",
        "I",
        "PEGGED",
        "IS_INVERSE",
        "PEG_MUL",
        "AGGREGATOR",
        "last_change",
        "debt",
        "caller_share",
        "admin",
        "future_admin",
        "receiver",
        "future_receiver",
        "new_admin_deadline",
        "new_receiver_deadline",
    ]

    def __init__(
        _pool: CurveCryptoPool,
        _index: int,
        _caller_share: int,
        _factory : ControllerFactory,
        _aggregator : AggregateStablePrice,
        _receiver: str = "",
    ):
        """
        Contract constructor

        Parameters
        ----------
        _pool : CurveCryptoPool
            Contract pool address
        _index : int
            Index of the pegged
        _receiver : str
            Receiver of the profit
        _caller_share : int
            Caller's share of profit
        _factory : ControllerFactory
            Factory which should be able to take coins away
        _aggregator : AggregateStablePrice
            Price aggregator which shows the price of pegged in real "dollars"
        _admin : str
            Admin account
        """
        pass