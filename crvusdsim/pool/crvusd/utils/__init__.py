import time

__all__ = [
    "_get_unix_timestamp",
    "BlocktimestampMixins",
    "ERC20",
]

from .ERC20 import ERC20


def _get_unix_timestamp():
    """Get the timestamp in Unix time."""
    return int(time.time())


class BlocktimestampMixins:
    def __init__(self, **kwargs):
        self._block_timestamp = _get_unix_timestamp()

    def _increment_timestamp(self, timestamp=None, blocks=1):
        """Update the internal clock used to mimic the block timestamp."""
        if timestamp:
            self._block_timestamp += timestamp
            return

        self._block_timestamp += 12 * blocks
