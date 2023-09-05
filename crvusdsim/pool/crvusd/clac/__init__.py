__all__ = [
    "ln_int",
]

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
