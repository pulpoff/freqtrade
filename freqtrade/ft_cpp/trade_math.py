"""
Python wrapper for C++ trade math functions with pure-Python fallback.

These functions replace FtPrecise string-based math with native C++ doubles.
"""

import numpy as np

from freqtrade.ft_cpp import HAS_CPP


if HAS_CPP:
    from freqtrade._ft_cpp.trade_math import (  # noqa: F401
        ProfitResult,
        RecalcResult,
        batch_calc_profit_ratio,
        calc_close_rate_for_roi,
        calc_close_trade_value,
        calc_open_trade_value,
        calc_profit_ratio,
        calculate_profit,
        recalc_trade_from_orders,
    )
else:
    # Pure Python fallback

    def _round8(x):
        return round(x, 8)

    def calc_open_trade_value(amount, open_rate, fee_open, is_short):
        if is_short:
            return amount * open_rate * (1.0 - fee_open)
        return amount * open_rate * (1.0 + fee_open)

    def calc_close_trade_value(amount, close_rate, fee_close, is_short, funding_fees=0.0):
        if is_short:
            val = amount * close_rate * (1.0 + fee_close)
        else:
            val = amount * close_rate * (1.0 - fee_close)
        return val + funding_fees

    def calc_profit_ratio(close_trade_value, open_trade_value, is_short, leverage):
        if open_trade_value == 0.0:
            return 0.0
        if is_short:
            ratio = (1.0 - (close_trade_value / open_trade_value)) * leverage
        else:
            ratio = ((close_trade_value / open_trade_value) - 1.0) * leverage
        return _round8(ratio)

    def calc_close_rate_for_roi(target_roi, leverage, is_short,
                                amount, open_rate, fee_open, fee_close,
                                funding_fees=0.0):
        lev = leverage or 1.0
        deleveraged_roi = target_roi / lev
        open_value = calc_open_trade_value(amount, open_rate, fee_open, is_short)
        value_at_0 = calc_close_trade_value(amount, 0.0, fee_close, is_short, funding_fees)
        value_at_1 = calc_close_trade_value(amount, 1.0, fee_close, is_short, funding_fees)
        alpha = value_at_1 - value_at_0
        beta = value_at_0
        s = -1.0 if is_short else 1.0
        adj = 1.0 + (deleveraged_roi / s)
        return (adj * open_value - beta) / alpha

    def batch_calc_profit_ratio(close_rates, amount, open_rate,
                                fee_open, fee_close, is_short, leverage,
                                funding_fees=0.0):
        open_value = calc_open_trade_value(amount, open_rate, fee_open, is_short)
        result = np.empty(len(close_rates))
        for i, cr in enumerate(close_rates):
            cv = calc_close_trade_value(amount, cr, fee_close, is_short, funding_fees)
            if open_value == 0.0:
                result[i] = 0.0
            elif is_short:
                result[i] = _round8((1.0 - cv / open_value) * leverage)
            else:
                result[i] = _round8((cv / open_value - 1.0) * leverage)
        return result
