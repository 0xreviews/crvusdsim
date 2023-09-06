__all__ = [
    "shift",
    "unsafe_add",
    "unsafe_sub",
    "unsafe_mul",
    "unsafe_dev",
]


def shift(n: int, s: int) -> int:
    if s >= 0:
        return n << abs(s)
    else:
        return n >> abs(s)


def unsafe_add(x: int, y: int) -> int:
    return x + y


def unsafe_sub(x: int, y: int) -> int:
    return x - y


def unsafe_mul(x: int, y: int) -> int:
    return x * y


def unsafe_div(x: int, y: int) -> int:
    assert y != 0, "unsafe_div: divisor is zero"
    return x // y
