"""
crvUSD ControllerFactory
"""
from collections import defaultdict
from math import isqrt
from typing import List, Tuple


from .clac import ln_int
from .stablecoin import StableCoin
from .price_oracle import PriceOracle
from .LLAMMA import LLAMMAPool
from .controller import Controller

MAX_CONTROLLERS = 50000
# Limits
MIN_A = 2
MAX_A = 10000
MIN_FEE = 10**6  # 1e-12, still needs to be above 0
MAX_FEE = 10**17  # 10%
MAX_ADMIN_FEE = 10**18  # 100%
MAX_LOAN_DISCOUNT = 5 * 10**17
MIN_LIQUIDATION_DISCOUNT = 10**16


class ControllerFactory:
    __slots__ = [
        "address",
        "STABLECOIN",
        "controllers",
        "amms",
        "fee_receiver",
        "n_collaterals",
        "collaterals",
        "collaterals_index",
        "debt_ceiling",
        "debt_ceiling_residual",
    ]

    def __init__(self, stablecoin: StableCoin, fee_receiver: str = ""):
        self.address = "controller_factory_address"
        self.STABLECOIN = stablecoin
        self.fee_receiver = fee_receiver

        self.controllers = defaultdict(None)
        self.amms = defaultdict(None)
        self.n_collaterals = 0
        self.collaterals = defaultdict(default_collateral)
        self.debt_ceiling = defaultdict(int)
        self.debt_ceiling_residual = defaultdict(int)
        self.collaterals_index = defaultdict(default_collaterals_index)

    def _set_debt_ceiling(self, addr: str, debt_ceiling: int, update: bool):
        """
        Set debt ceiling for a market

        Parameters
        ----------
        addr : str
            Controller address
        debt_ceiling : int
            Value for stablecoin debt ceiling
        update : bool
            Whether to actually update the debt ceiling (False is used for burning the residuals)
        """
        old_debt_residual: int = self.debt_ceiling_residual[addr]

        if debt_ceiling > old_debt_residual:
            to_mint: int = debt_ceiling - old_debt_residual
            self.STABLECOIN.mint(addr, to_mint)
            self.debt_ceiling_residual[addr] = debt_ceiling

        if debt_ceiling < old_debt_residual:
            diff: int = min(
                old_debt_residual - debt_ceiling, self.STABLECOIN.balanceOf(addr)
            )
            self.STABLECOIN.burnFrom(addr, diff)
            self.debt_ceiling_residual[addr] = old_debt_residual - diff

        if update:
            self.debt_ceiling[addr] = debt_ceiling

    def add_market(
        self,
        token: any,
        A: int,
        fee: int,
        admin_fee: int,
        _price_oracle_contract: PriceOracle,
        monetary_policy: any,
        loan_discount: int,
        liquidation_discount: int,
        debt_ceiling: int,
    ) -> Tuple[Controller, LLAMMAPool]:
        """
        Add a new market, creating an AMM and a Controller from a blueprint

        Parameters
        ----------
        token : { address: str, precision: int }
            Collateral token address
        A : int
            Amplification coefficient; one band size is 1/A
        fee : int
            AMM fee in the market's AMM
        admin_fee : int
            AMM admin fee
        _price_oracle_contract : PriceOracle
            Address of price oracle contract for this market
        monetary_policy : MonetaryPolicy
            Monetary policy for this market
        loan_discount : int
            Loan discount: allowed to borrow only up to x_down * (1 - loan_discount)
        liquidation_discount : int
            Discount which defines a bad liquidation threshold
        debt_ceiling : int
            Debt ceiling for this market

        Returns
        -------
        Tuple[Controller, LLAMMAPool]
            (Controller, AMM)
        """
        # assert msg.sender == self.admin, "Only admin"
        assert A >= MIN_A and A <= MAX_A, "Wrong A"
        assert fee <= MAX_FEE, "Fee too high"
        assert fee >= MIN_FEE, "Fee too low"
        assert admin_fee < MAX_ADMIN_FEE, "Admin fee too high"
        assert (
            liquidation_discount >= MIN_LIQUIDATION_DISCOUNT
        ), "Liquidation discount too low"
        assert loan_discount <= MAX_LOAN_DISCOUNT, "Loan discount too high"
        assert (
            loan_discount > liquidation_discount
        ), "need loan_discount>liquidation_discount"
        monetary_policy.rate_write(_for=None)

        p: int = _price_oracle_contract.price()  # This also validates price oracle ABI
        assert p > 0
        assert _price_oracle_contract.price_w() == p

        amm: LLAMMAPool = LLAMMAPool(
            A=A,
            fee=fee,
            admin_fee=admin_fee,
            BASE_PRICE=p,
            price_oracle_contract=_price_oracle_contract,
            collateral=token,  # <- This validates ERC20 ABI
            borrowed_token=self.STABLECOIN,
        )
        controller: Controller = Controller(
            stablecoin=self.STABLECOIN,
            factory=self,
            collateral_token=token["address"],
            monetary_policy=monetary_policy,
            loan_discount=loan_discount,
            liquidation_discount=liquidation_discount,
            amm=amm,
        )
        amm.set_admin(controller)
        self._set_debt_ceiling(
            addr=controller.address, debt_ceiling=debt_ceiling, update=True
        )

        N: int = self.n_collaterals
        self.collaterals[N] = token["address"]
        for i in range(1000):
            if self.collaterals_index[token["address"]][i] == 0:
                self.collaterals_index[token["address"]][i] = 2**128 + N
                break
            assert i != 999, "Too many controllers for same collateral"
        self.controllers[N] = controller
        self.amms[N] = amm
        self.n_collaterals = N + 1

        return controller, amm

    def total_debt(self) -> int:
        """
        Sum of all debts across controllers
        """
        total: int = 0
        n_collaterals: int = self.n_collaterals
        for i in range(MAX_CONTROLLERS):
            if i == n_collaterals:
                break
            total += self.controllers[i].total_debt()
        return total

    def get_controller(self, collateral: str, i: int = 0) -> str:
        """
        Get controller address for collateral

        Parameters
        ----------
        collateral : str
            Address of collateral token
        i : int
            Iterate over several controllers for collateral if needed
        """
        return self.controllers[self.collaterals_index[collateral][i] - 2**128]

    def get_amm(self, collateral: str, i: int = 0) -> str:
        """
        Get AMM address for collateral

        Parameters
        ----------
        collateral : str
            Address of collateral token
        i : int
            Iterate over several amms for collateral if needed
        """
        return self.amms[self.collaterals_index[collateral][i] - 2**128]

    def set_debt_ceiling(self, _to: str, debt_ceiling: int):
        """
        Set debt ceiling of the address - mint the token amount given for it

        Parameters
        ----------
        _to : str
            Address to allow borrowing for
        debt_ceiling : int
            Maximum allowed to be allowed to mint for it
        """
        # assert msg.sender == self.admin
        self._set_debt_ceiling(_to, debt_ceiling, True)

    def rug_debt_ceiling(self, _to: str):
        """
        Remove stablecoins above the debt ceiling from the address and burn them

        Parameters
        ----------
        _to : str
            Address to remove stablecoins from
        """
        self._set_debt_ceiling(_to, self.debt_ceiling[_to], False)

    # @todo
    def collect_fees_above_ceiling(self, _to: str):
        """
        If the receiver is the controller - increase the debt ceiling if it's not enough to claim admin fees
        and claim them


        Parameters
        ----------
        _to : str
            Address of the controller
        """
        # assert msg.sender == self.admin
        # old_debt_residual: int = self.debt_ceiling_residual[_to]
        # assert self.debt_ceiling[_to] > 0 or old_debt_residual > 0

        # admin_fees: int = Controller(_to).total_debt() + Controller(_to).redeemed() - Controller(_to).minted()
        # b: int = self.STABLECOIN.balanceOf(_to)
        # if admin_fees > b:
        #     to_mint: int = admin_fees - b
        #     self.STABLECOIN.mint(_to, to_mint)
        #     self.debt_ceiling_residual[_to] = old_debt_residual + to_mint
        # Controller(_to).collect_fees()
        pass


def default_collateral():
    return {
        "address": None,
        "symbol": None,
        "precision": 1,
    }


def default_collaterals_index():
    return defaultdict(int)
