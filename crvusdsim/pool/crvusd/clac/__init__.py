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

MAX_EXP = 1000 * 10**18

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

def exp(power: int) -> int:
    if power <= -42139678854452767551:
        return 0

    if power >= 135305999368893231589:
        # Return MAX_EXP when we are in overflow mode
        return MAX_EXP

    x: int = unsafe_div(unsafe_mul(power, 2**96), 10**18)

    k: int = unsafe_div(
        unsafe_add(
            unsafe_div(unsafe_mul(x, 2**96), 54916777467707473351141471128),
            2**95),
        2**96)
    x = unsafe_sub(x, unsafe_mul(k, 54916777467707473351141471128))

    y: int = unsafe_add(x, 1346386616545796478920950773328)
    y = unsafe_add(unsafe_div(unsafe_mul(y, x), 2**96), 57155421227552351082224309758442)
    p: int = unsafe_sub(unsafe_add(y, x), 94201549194550492254356042504812)
    p = unsafe_add(unsafe_div(unsafe_mul(p, y), 2**96), 28719021644029726153956944680412240)
    p = unsafe_add(unsafe_mul(p, x), (4385272521454847904659076985693276 * 2**96))

    q: int = x - 2855989394907223263936484059900
    q = unsafe_add(unsafe_div(unsafe_mul(q, x), 2**96), 50020603652535783019961831881945)
    q = unsafe_sub(unsafe_div(unsafe_mul(q, x), 2**96), 533845033583426703283633433725380)
    q = unsafe_add(unsafe_div(unsafe_mul(q, x), 2**96), 3604857256930695427073651918091429)
    q = unsafe_sub(unsafe_div(unsafe_mul(q, x), 2**96), 14423608567350463180887372962807573)
    q = unsafe_add(unsafe_div(unsafe_mul(q, x), 2**96), 26449188498355588339934803723976023)

    return shift(
        unsafe_mul(unsafe_div(p, q), 3822833074963236453042738258902158003155416615667),
        unsafe_sub(k, 195))