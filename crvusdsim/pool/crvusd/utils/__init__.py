import time

__all__ = [
    "_get_unix_timestamp",
    "BlocktimestampMixins",
]


def _get_unix_timestamp():
    """Get the timestamp in Unix time."""
    return int(time.time())


class BlocktimestampMixins:
    def __init__(self):
        self._block_timestamp = _get_unix_timestamp()

    def _increment_timestamp(self, blocks=1, timestamp=None):
        """Update the internal clock used to mimic the block timestamp."""
        if timestamp:
            self._block_timestamp = timestamp
            return

        self._block_timestamp += 12 * blocks
