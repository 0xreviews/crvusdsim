__all__ = [
    "ln_int",
    "log2",
]

from ..vyper_func import (
    shift,
    unsafe_add,
    unsafe_div,
    unsafe_mul,
    unsafe_sub,
)

def ln_int(_x: int) -> int:
    """
    @notice Logarithm ln() function based on log2. Not very gas-efficient but brief
    """
    # adapted from: https://medium.com/coinmonks/9aef8515136e
    # and vyper log implementation
    # This can be much more optimal but that's not important here
    x: int = _x
    res: int = 0
    for i in range(8):
        t: int = 2**(7 - i)
        p: int = 2**t
        if x >= p * 10**18:
            x //= p
            res += t * 10**18
    d: int = 10**18
    for i in range(59):  # 18 decimals: math.log2(10**10) == 59.7
        if (x >= 2 * 10**18):
            res += d
            x //= 2
        x = x * x // 10**18
        d //= 2
    # Now res = log2(x)
    # ln(x) = log2(x) / log2(e)
    return res * 10**18 // 1442695040888963328


def log2(_x: int) -> int:
    """
    @notice int(1e18 * log2(_x / 1e18))
    """
    # adapted from: https://medium.com/coinmonks/9aef8515136e
    # and vyper log implementation
    # Might use more optimal solmate's log
    inverse: bool = _x < 10**18
    res: int = 0
    x: int = _x
    if inverse:
        x = 10**36 // x
    t: int = 2**7
    for i in range(8):
        p: int = t ** 2
        if x >= unsafe_mul(p, 10**18):
            x = unsafe_div(x, p)
            res = unsafe_add(unsafe_mul(t, 10**18), res)
        t = unsafe_div(t, 2)
    d: int = 10**18
    for i in range(34):  # 10 decimals: math.log(10**10, 2) == 33.2. Need more?
        if (x >= 2 * 10**18):
            res = unsafe_add(res, d)
            x = unsafe_div(x, 2)
        x = unsafe_div(unsafe_mul(x, x), 10**18)
        d = unsafe_div(d, 2)

    if inverse:
        return -res
    else:
        return res
