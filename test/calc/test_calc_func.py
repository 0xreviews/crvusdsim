from hypothesis import given, settings
from hypothesis import strategies as st
from math import log2
from crvusdsim.pool.crvusd.clac import log2 as vyper_log2
from ..utils import approx

@given(x=st.integers(min_value=1, max_value=10**12))
def test_log2(x):
    x *= 10**18
    assert approx(vyper_log2(x), int(1e18 * log2(x / 1e18)), 1e-10)