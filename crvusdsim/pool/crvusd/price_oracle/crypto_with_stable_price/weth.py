"""Provides the WETH price oracle."""
from typing import List
from .base import Oracle

PRECISION = 10**18


class OracleWETH(Oracle):
    """
    WETH Price oracle.
    Currently matches the base implementation
    """
