"""Provides the WBTC price oracle."""
from typing import List
from .base import Oracle

PRECISION = 10**18


class OracleWBTC(Oracle):
    """
    WBTC Price oracle.
    Currently matches the base implementation
    """
