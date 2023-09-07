class PriceOracle:
    def __init__(self, p: int):
        self._price = p


    def set_price(self, p: int):
        self._price = p


    def price_w(self):
        return self._price


    def price(self):
        return self._price
