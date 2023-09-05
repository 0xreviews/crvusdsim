from curvesim.pool.snapshot import Snapshot

# @todo 
class LLAMMABandsSnapshot(Snapshot):
    """Snapshot that saves pool balances and admin balances."""

    def __init__(
        self,
        bands,
    ):
        self.bands = bands
        

    @classmethod
    def create(cls, pool):
        bands = pool.bands.copy()
       
        return cls(
            bands,
        )

    def restore(self, pool):
        bands = self.bands.copy()
        