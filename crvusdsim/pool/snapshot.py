from curvesim.pool.snapshot import Snapshot

class Loan:
    def __init__(self):
        self.initial_debt = 0
        self.rate_mul = 0

class LLAMMASnapshot(Snapshot):
    """Snapshot that saves pool bands, oracle price, user shares, etc..."""

    def __init__(
        self,
        active_band,
        min_band,
        max_band,
        old_p_o,
        rate,
        rate_mul,
        bands_x,
        bands_y,
        old_dfee,
        admin_fees_x,
        admin_fees_y,
        total_shares,
        user_shares,
        _block_timestamp,
        prev_p_o_time,
        rate_time,
        bands_fees_x,
        bands_fees_y,
        bands_x_benchmark,
        bands_y_benchmark,
        bands_delta_snapshot,
    ):
        self.active_band = active_band
        self.min_band = min_band
        self.max_band = max_band
        self.old_p_o = old_p_o
        self.rate = rate
        self.rate_mul = rate_mul
        self.bands_x = bands_x
        self.bands_y = bands_y
        self.old_dfee = old_dfee
        self.admin_fees_x = admin_fees_x
        self.admin_fees_y = admin_fees_y
        self._block_timestamp = _block_timestamp
        self.prev_p_o_time = prev_p_o_time
        self.rate_time = rate_time
        self.total_shares = total_shares
        self.user_shares = user_shares

        self.bands_fees_x = bands_fees_x
        self.bands_fees_y = bands_fees_y

        self.bands_x_benchmark = bands_x_benchmark
        self.bands_y_benchmark = bands_y_benchmark

        self.bands_delta_snapshot = bands_delta_snapshot

    @classmethod
    def create(cls, pool):
        active_band = pool.active_band
        min_band = pool.min_band
        max_band = pool.max_band
        old_p_o = pool.old_p_o
        rate = pool.rate
        rate_mul = pool.rate_mul
        bands_x = pool.bands_x.copy()
        bands_y = pool.bands_y.copy()
        old_dfee = pool.old_dfee
        admin_fees_x = pool.admin_fees_x
        admin_fees_y = pool.admin_fees_y
        total_shares = pool.total_shares.copy()
        user_shares = pool.user_shares.copy()
        _block_timestamp = pool._block_timestamp
        prev_p_o_time = pool.prev_p_o_time
        rate_time = pool.rate_time

        bands_fees_x = pool.bands_fees_x.copy()
        bands_fees_y = pool.bands_fees_y.copy()

        bands_x_benchmark = pool.bands_x_benchmark.copy()
        bands_y_benchmark = pool.bands_y_benchmark.copy()

        bands_delta_snapshot = pool.bands_delta_snapshot.copy()

        return cls(
            active_band,
            min_band,
            max_band,
            old_p_o,
            rate,
            rate_mul,
            bands_x,
            bands_y,
            old_dfee,
            admin_fees_x,
            admin_fees_y,
            total_shares,
            user_shares,
            _block_timestamp,
            prev_p_o_time,
            rate_time,
            bands_fees_x,
            bands_fees_y,
            bands_x_benchmark,
            bands_y_benchmark,
            bands_delta_snapshot,
        )

    def restore(self, pool):
        pool.active_band = self.active_band
        pool.min_band = self.min_band
        pool.max_band = self.max_band
        pool.old_p_o = self.old_p_o
        pool.rate = self.rate
        pool.rate_mul = self.rate_mul
        pool.bands_x = self.bands_x.copy()
        pool.bands_y = self.bands_y.copy()
        pool.old_dfee = self.old_dfee
        pool.admin_fees_y = self.admin_fees_y
        pool.total_shares = self.total_shares.copy()
        pool.user_shares = self.user_shares.copy()
        pool._block_timestamp = self._block_timestamp
        pool.prev_p_o_time = self.prev_p_o_time
        pool.rate_time = self.rate_time

        pool.bands_fees_x = self.bands_fees_x.copy()
        pool.bands_fees_y = self.bands_fees_y.copy()

        pool.bands_x_benchmark = self.bands_x_benchmark.copy()
        pool.bands_y_benchmark = self.bands_y_benchmark.copy()

        pool.bands_delta_snapshot = self.bands_delta_snapshot.copy()


class ControllerSnapshot(Snapshot):
    """Snapshot that saves Controller loans, loan_ix, n_loans, etc..."""

    def __init__(
        self,
        loan,
        liquidation_discounts,
        _total_debt,
        loans,
        loan_ix,
        n_loans,
        minted,
        redeemed,
        liquidation_discount,
        loan_discount,
    ):
        self.loan = loan
        self.liquidation_discounts = liquidation_discounts
        self._total_debt = Loan()
        self._total_debt.initial_debt = _total_debt.initial_debt
        self._total_debt.rate_mul = _total_debt.rate_mul
        self.loans = loans
        self.loan_ix = loan_ix
        self.n_loans = n_loans

        self.minted = minted
        self.redeemed = redeemed

        self.liquidation_discount = liquidation_discount
        self.loan_discount = loan_discount

    @classmethod
    def create(cls, controller):
        loan = controller.loan.copy()
        liquidation_discounts = controller.liquidation_discounts.copy()
        _total_debt = Loan()
        _total_debt.initial_debt = controller._total_debt.initial_debt
        _total_debt.rate_mul = controller._total_debt.rate_mul
        loans = controller.loans.copy()
        loan_ix = controller.loan_ix.copy()
        n_loans = controller.n_loans

        minted = controller.minted
        redeemed = controller.redeemed

        liquidation_discount = controller.liquidation_discount
        loan_discount = controller.loan_discount

        return cls(
            loan,
            liquidation_discounts,
            _total_debt,
            loans,
            loan_ix,
            n_loans,
            minted,
            redeemed,
            liquidation_discount,
            loan_discount,
        )

    def restore(self, controller):
        controller.loan = self.loan
        controller.liquidation_discounts = self.liquidation_discounts.copy()
        controller._total_debt.initial_debt = self._total_debt.initial_debt
        controller._total_debt.rate_mul = self._total_debt.rate_mul
        controller.loans = self.loans.copy()
        controller.loan_ix = self.loan_ix.copy()
        controller.n_loans = self.n_loans

        controller.minted = self.minted
        controller.redeemed = self.redeemed

        controller.liquidation_discount = self.liquidation_discount
        controller.loan_discount = self.loan_discount
