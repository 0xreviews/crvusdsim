from curvesim.pool.snapshot import Snapshot

# @todo 
class LLAMMASnapshot(Snapshot):
    """Snapshot that saves pool bands, oracle price, user shares, etc..."""

    def __init__(
        self,
        active_band,
        min_band,
        max_band,
        rate,
        rate_mul,
        bands_x,
        bands_y,
        admin_fees_x,
        admin_fees_y,
        total_shares,
        user_shares,
        _block_timestamp,
        prev_p_o_time,
        rate_time,
    ):
        self.active_band = active_band
        self.min_band = min_band
        self.max_band = max_band
        self.rate = rate
        self.rate_mul = rate_mul
        self.bands_x = bands_x
        self.bands_y = bands_y
        self.admin_fees_x = admin_fees_x
        self.admin_fees_y = admin_fees_y
        self._block_timestamp = _block_timestamp
        self.prev_p_o_time = prev_p_o_time
        self.rate_time = rate_time
        self.total_shares = total_shares
        self.user_shares = user_shares
        
        

    @classmethod
    def create(cls, pool):
        active_band = pool.active_band
        min_band = pool.min_band
        max_band = pool.max_band
        rate = pool.rate
        rate_mul = pool.rate_mul
        bands_x = pool.bands_x.copy()
        bands_y = pool.bands_y.copy()
        admin_fees_x = pool.admin_fees_x
        admin_fees_y = pool.admin_fees_y
        total_shares = pool.total_shares.copy()
        user_shares = pool.user_shares.copy()
        _block_timestamp = pool._block_timestamp
        prev_p_o_time = pool.prev_p_o_time
        rate_time = pool.rate_time
       
        return cls(
            active_band,
            min_band,
            max_band,
            rate,
            rate_mul,
            bands_x,
            bands_y,
            admin_fees_x,
            admin_fees_y,
            total_shares,
            user_shares,
            _block_timestamp,
            prev_p_o_time,
            rate_time,
        )

    def restore(self, pool):
        pool.active_band = self.active_band
        pool.min_band = self.min_band
        pool.max_band = self.max_band
        pool.rate = self.rate
        pool.rate_mul = self.rate_mul
        pool.bands_x = self.bands_x.copy()
        pool.bands_y = self.bands_y.copy()
        pool.admin_fees_x = self.admin_fees_x
        pool.admin_fees_y = self.admin_fees_y
        pool.total_shares = self.total_shares.copy()
        pool.user_shares = self.user_shares.copy()
        pool._block_timestamp = self._block_timestamp
        pool.prev_p_o_time = self.prev_p_o_time
        pool.rate_time = self.rate_time
        