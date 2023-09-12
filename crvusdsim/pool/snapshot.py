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
    ):
        self.active_band = active_band
        self.min_band = min_band
        self.max_band = max_band
        self.rate = rate
        self.rate_mul = rate_mul
        self.bands_x = bands_x
        self.bands_y = bands_y
        

    @classmethod
    def create(cls, pool):
        active_band = pool.active_band
        min_band = pool.min_band
        max_band = pool.max_band
        rate = pool.rate
        rate_mul = pool.rate_mul
        bands_x = pool.bands_x.copy()
        bands_y = pool.bands_y.copy()
       
        return cls(
            active_band,
            min_band,
            max_band,
            rate,
            rate_mul,
            bands_x,
            bands_y,
        )

    def restore(self, pool):
        pool.active_band = self.active_band
        pool.min_band = self.min_band
        pool.max_band = self.max_band
        pool.rate = self.rate
        pool.rate_mul = self.rate_mul
        pool.bands_x = self.bands_x.copy()
        pool.bands_y = self.bands_y.copy()
        