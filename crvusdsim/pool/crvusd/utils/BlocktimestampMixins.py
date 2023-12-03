
from time import time


def _get_unix_timestamp():
    """Get the timestamp in Unix time."""
    return int(time())

class BlocktimestampMixins:
    def __init__(self, **kwargs):
        self._block_timestamp = _get_unix_timestamp()

    def _increment_timestamp(self, timestamp=None, timedelta=None, blocks=1):
        """Update the internal clock used to mimic the block timestamp."""
        if timestamp:
            if isinstance(timestamp, float):
                timestamp = int(timestamp)
            if not isinstance(timestamp, int):
                timestamp = int(timestamp.timestamp())  # unix timestamp in seconds
            self._block_timestamp = timestamp
            return
        if timedelta:
            self._block_timestamp += timedelta
            return

        self._block_timestamp += 12 * blocks
    
    def prepare_for_run(self, prices):
        """
        Sets init _block_timestamp attribute to current sim time.

        Parameters
        ----------
        prices : pandas.DataFrame
            The price time_series, price_sampler.prices.
        """
        # Get/set initial prices
        init_ts = int(prices.index[0].timestamp())
        self._increment_timestamp(timestamp=init_ts)

    def prepare_for_trades(self, timestamp):
        """
        Updates the _block_timestamp attribute to current sim time.

        Parameters
        ----------
        timestamp : datetime.datetime
            The current timestamp in the simulation.
        """

        if isinstance(timestamp, float):
            timestamp = int(timestamp)
        if not isinstance(timestamp, int):
            timestamp = int(timestamp.timestamp())  # unix timestamp in seconds
        self._increment_timestamp(timestamp=timestamp)