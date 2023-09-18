"""
StableSwap
@notice 2 coin pool implementation with no lending
@dev ERC20 support for return True/revert, return True/False, return None
"""

from collections import defaultdict
from typing import List

from curvesim.pool.stableswap.pool import CurvePool

from crvusdsim.pool.crvusd.stablecoin import StableCoin


class CurveStableSwapPool(CurvePool):
    __slots__ = (
        "address",
        "name",
        "symbol",
        "balanceOf",
        "totalSupply",
        "coins",
        "precisions",
    )

    def __init__(
        self,
        address: str = None,
        name: str = "crvUSD/USDC",
        symbol: str = "crvUSD-USDC",
        coins: List[StableCoin] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.address = address if address is not None else name
        self.name = name
        self.symbol = symbol + "-f"
        self.coins = coins if coins is not None else [
            StableCoin(),
            StableCoin(
                address="%s_address" % name.split("/")[1],
                name="%s" % name.split("/")[1],
                symbol="%s_address" % name.split("/")[1],
                decimals=18
            )
        ]
        self.precisions = [10**(18 - coin.decimals) for coin in self.coins]

        self.balanceOf = defaultdict(int)
        self.totalSupply = self.D()

    def add_liquidity(self, amounts: List[int], _for: str):
        """
        Deposit coin amounts for LP token.

        Parameters
        ----------
        amounts: list of int
            Coin amounts to deposit
        _for : str
            Address of user

        Returns
        -------
        int
            LP token amount received for the deposit amounts.
        """
        mint_amount = super().add_liquidity(amounts)
        self._mint(_for, mint_amount)
        return mint_amount

    def remove_liquidity(
        self, _burn_amount: int, _min_amounts: List[int], _receiver: str
    ) -> List[int]:
        """
        Withdraw coins from the pool
        @dev Withdrawal amounts are based on current deposit ratios

        Parameters
        ----------
        _burn_amount : int
            Quantity of LP tokens to burn in the withdrawal
        _min_amounts : List[int]
            Minimum amounts of underlying coins to receive
        _receiver : str
            Address that receives the withdrawn coins
        Returns
        -------
        List[int]
            List of amounts of coins that were withdrawn
        """
        total_supply: int = self.totalSupply
        amounts: List[int] = [0] * self.n

        for i in range(self.n):
            old_balance: int = self.balances[i]
            value: int = old_balance * _burn_amount // total_supply
            assert (
                value >= _min_amounts[i]
            ), "Withdrawal resulted in fewer coins than expected"
            self.balances[i] = old_balance - value
            amounts[i] = value
            # assert ERC20(self.coins[i]).transfer(_receiver, value, default_return_value=True)  # dev: failed transfer

        total_supply -= _burn_amount
        self.balanceOf[_receiver] -= _burn_amount
        self.totalSupply = total_supply

        return amounts

    # def _ma_price # @todo

    def transfer(self, _from: str, _to: str, _value: int) -> bool:
        """
        ERC20 transfer

        Parameters
        ----------
        _from : str
            Address of from user
        _to : str
            Address of to user
        _value : int
            transfer amount

        Returns
        -------
        bool
            wether transfering is success or not
        """
        assert self.balanceOf[_from] - _value >= 0, "insufficient balance"
        self.balanceOf[_from] -= _value
        self.balanceOf[_to] += _value
        return True

    def transferFrom(self, _from: str, _to: str, _value: int) -> bool:
        """
        ERC20 transferFrom

        Parameters
        ----------
        _from : str
            Address of from user
        _to : str
            Address of to user
        _value : int
            transfer amount

        Returns
        -------
        bool
            wether transfering is success or not
        """
        assert self.balanceOf[_from] - _value >= 0, "insufficient balance"
        self.balanceOf[_from] -= _value
        self.balanceOf[_to] += _value
        # self.allowances[_from][msg.sender] -= _value
        return True

    def _mint(self, _to: str, _value: int):
        """
        ERC20 _mint

        Parameters
        ----------
        _to : str
            Address of to user
        _value : int
            mint amount
        """
        self.balanceOf[_to] += _value
        self.totalSupply += _value

    def _burn(self, _to: str, _value: int):
        """
        ERC20 _burn

        Parameters
        ----------
        _to : str
            Address of to user
        _value : int
            burn amount
        """
        assert self.balanceOf[_to] - _value >= 0, "insufficient balance"
        self.balanceOf[_to] -= _value
        self.totalSupply -= _value
