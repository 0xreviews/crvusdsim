"""
MonetaryPolicy - monetary policy based on aggregated prices for crvUSD
"""

from typing import List

from crvusdsim.pool.crvusd.clac import exp
from ..stabilizer import PegKeeper
from ..controller import Controller

MAX_TARGET_DEBT_FRACTION = 10**18
MAX_SIGMA = 10**18
MIN_SIGMA = 10**14
MAX_EXP = 1000 * 10**18
MAX_RATE = 43959106799  # 300% APY
TARGET_REMAINDER = 10**17  # rate is x2 when 10% left before ceiling


class MonetaryPolicy:
    """AggMonetaryPolicy2 implementation in Python."""

    def __init__(
        self,
        price_oracle_contract: any,
        controller_factory_contract: any,
        peg_keepers: List[PegKeeper],
        rate0: int,
        sigma: int,
        target_debt_fraction: int,
    ):
        """
        Contract constructor

        Parameters
        ----------
        price_oracle_contract : AggregateStablePrice
            Contract AggregateStablePrice
        controller_factory_contract : ControllerFactory
            Contract ControllerFactory
        peg_keepers : List[PegKeeper]
            PegKeepers
        rate0 : int
            rate0
        sigma : int
            sigma
        target_debt_fraction : int
            target_debt_fraction
        """

        self.PRICE_ORACLE = price_oracle_contract
        self.CONTROLLER_FACTORY = controller_factory_contract
        self.peg_keepers = peg_keepers

        assert sigma >= MIN_SIGMA
        assert sigma <= MAX_SIGMA
        assert target_debt_fraction <= MAX_TARGET_DEBT_FRACTION
        assert rate0 <= MAX_RATE
        self.rate0 = rate0
        self.sigma = sigma
        self.target_debt_fraction = target_debt_fraction

    def set_admin(self, admin: str):
        pass

    def add_peg_keeper(self, pk: PegKeeper):
        # assert msg.sender == self.admin
        # assert pk.address != empty(address)
        for i in range(len(self.peg_keepers)):
            _pk: PegKeeper = self.peg_keepers[i]
            assert _pk != pk, "Already added"

        self.peg_keepers.append(pk)

    def remove_peg_keeper(self, pk: PegKeeper):
        # assert msg.sender == self.admin
        del_ix = -1
        for i in range(len(self.peg_keepers)):  # 1001th element is always 0x0
            _pk: PegKeeper = self.peg_keepers[i]
            if _pk == pk:
                del_ix = i
            break
        del self.peg_keepers[del_ix]

    def calculate_rate(self, _for: Controller, _price: int) -> int:
        sigma: int = self.sigma
        target_debt_fraction: int = self.target_debt_fraction

        p: int = _price
        pk_debt: int = 0
        for pk in self.peg_keepers:
            pk_debt += pk.debt

        power: int = int(
            (10**18 - p) * 10**18 // sigma
        )  # high price -> negative pow -> low rate
        
        if pk_debt > 0:
            total_debt: int = self.CONTROLLER_FACTORY.total_debt()
            if total_debt == 0:
                return 0
            else:
                power -= (
                    pk_debt * 10**18 // total_debt * 10**18 // target_debt_fraction
                )

        # Rate accounting for crvUSD price and PegKeeper debt
        rate: int = self.rate0 * min(exp(power), MAX_EXP) // 10**18
    
        # if _for is None, msg.sender is ControllerFactory
        if _for is not None:
            # Account for individual debt ceiling to dynamically tune rate depending on filling the market
            ceiling: int = self.CONTROLLER_FACTORY.debt_ceiling[_for.address]
            if ceiling > 0:
                f: int = min(
                    _for.total_debt() * 10**18 // ceiling,
                    10**18 - TARGET_REMAINDER // 1000,
                )
                rate = min(
                    rate
                    * (
                        (10**18 - TARGET_REMAINDER)
                        + TARGET_REMAINDER * 10**18 // (10**18 - f)
                    )
                    // 10**18,
                    MAX_RATE,
                )

        return rate

    def rate(self, _for: Controller) -> int:
        return self.calculate_rate(_for, self.PRICE_ORACLE.price())

    def rate_write(self, _for: Controller=None) -> int:
        # Not needed here but useful for more automated policies
        # which change rate0 - for example rate0 targeting some fraction pl_debt/total_debt
        return self.calculate_rate(_for, self.PRICE_ORACLE.price_w())

    def set_rate(self, rate: int):
        # assert msg.sender == self.admin
        assert rate <= MAX_RATE
        self.rate0 = rate

    def set_sigma(self, sigma: int):
        # assert msg.sender == self.admin
        assert sigma >= MIN_SIGMA
        assert sigma <= MAX_SIGMA

        self.sigma = sigma

    def set_target_debt_fraction(self, target_debt_fraction: int):
        # assert msg.sender == self.admin
        assert target_debt_fraction <= MAX_TARGET_DEBT_FRACTION

        self.target_debt_fraction = target_debt_fraction
