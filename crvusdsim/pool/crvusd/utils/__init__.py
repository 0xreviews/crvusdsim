import time

__all__ = [
    "_get_unix_timestamp"
]

def _get_unix_timestamp():
    """Get the timestamp in Unix time."""
    return int(time.time())