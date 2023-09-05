
class PriceOracle():  # pylint: disable=too-many-instance-attributes
    
    def __init__(self, p: int):
        self._price = p

    
    def update_price(self, p: int):
        self._price = p
    

    def price(self):
        return self._price
        