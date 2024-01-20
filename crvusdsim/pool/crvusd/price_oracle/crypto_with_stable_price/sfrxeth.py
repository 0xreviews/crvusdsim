"""Provides the sfrxETH price oracle."""
from typing import List
from .base import Oracle, SimpleOracle

PRECISION = 10**18


class OracleSFRXETH(Oracle):
    """Oracle for sfrxETH"""

    def __init__(self, staked_oracle: SimpleOracle | None = None, **kwargs):
        super().__init__(**kwargs)
        self.staked_oracle = staked_oracle or SimpleOracle()

    def _raw_price(self, tvls: List[int], agg_price: int, *args, **kwargs) -> int:
        """
        Get the price of the underlying asset from TriCrypto and StableSwap
        pools (e.g. ETH price).

        Convert this price to the staked asset price using staked oracle price.
        (e.g. ETH -> sfrxETH).

        NOTE: don't need to apply chainlink limit here since the staked_oracle
        price is already the simulated (i.e. market) price.
        """
        crv_p = super()._raw_price(tvls, agg_price, *args, **kwargs)
        crv_p = int(self.staked_oracle.price * crv_p // PRECISION)
        self.last_price = crv_p
        return crv_p

    def update_staked_oracle(self, new: int) -> None:
        """Update the staked oracle price."""
        self.staked_oracle.update(new)
