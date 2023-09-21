"""
crvUSD Stablecoin
"""
from collections import defaultdict
from typing import List

class ERC20:
    __slots__ = (
        "address",
        "name",
        "symbol",
        "decimals",
        "balanceOf",
        "totalSupply",
    )

    def __init__(
        self,
        address: str,
        name: str,
        symbol: str,
        decimals: int,
    ):
        self.address = address
        self.name = name
        self.symbol = symbol
        self.decimals = decimals
        self.balanceOf = defaultdict(int)
        self.totalSupply = 0

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
        self.balanceOf[_to] += _value
        self.totalSupply += _value

    def _burn(self, _to: str, _value: int):
        assert self.balanceOf[_to] - _value >= 0, "insufficient balance"
        self.balanceOf[_to] -= _value
        self.totalSupply -= _value
    
    def mint(self, _to: str, _value: int):
        """
        ERC20 mint

        Parameters
        ----------
        _to : str
            Address of to user
        _value : int
            mint amount
        """
        self._mint(_to, _value)
    
    def burnFrom(self, _from: str, _value: int) -> bool:
        """
        ERC20 _burn

        Parameters
        ----------
        _to : str
            Address of to user
        _value : int
            burn amount
        """
        self._burn(_from, _value)
