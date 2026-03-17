"""
Python wrapper for C++ report generation functions with pure-Python fallback.
"""

import numpy as np

from freqtrade.ft_cpp import HAS_CPP


if HAS_CPP:
    from freqtrade._ft_cpp.report_gen import (  # noqa: F401
        DrawdownResult,
        PairMetrics,
        aggregate_pair_metrics,
        calculate_expectancy,
        calculate_max_drawdown,
        find_exact_candle_indices,
        find_signal_candle_indices,
    )
else:

    def find_signal_candle_indices(candle_dates, trade_dates):
        result = np.empty(len(trade_dates), dtype=np.int64)
        cd = np.asarray(candle_dates)
        for i, td in enumerate(trade_dates):
            idx = np.searchsorted(cd, td, side="left") - 1
            result[i] = idx if idx >= 0 else -1
        return result

    def find_exact_candle_indices(candle_dates, signal_dates):
        result = np.empty(len(signal_dates), dtype=np.int64)
        cd = np.asarray(candle_dates)
        for i, sd in enumerate(signal_dates):
            idx = np.searchsorted(cd, sd, side="left")
            if idx < len(cd) and cd[idx] == sd:
                result[i] = idx
            else:
                result[i] = -1
        return result

    def calculate_max_drawdown(profits, starting_balance=0.0):
        p = np.asarray(profits)
        cum = np.cumsum(p)
        cum_max = np.maximum.accumulate(cum)
        dd = cum_max - cum
        max_dd_idx = np.argmax(dd)
        peak_idx = np.argmax(cum[:max_dd_idx + 1]) if max_dd_idx > 0 else 0
        peak_balance = starting_balance + cum[peak_idx]
        max_dd_rel = dd[max_dd_idx] / peak_balance if peak_balance > 0 else 0.0

        class _DD:
            pass

        r = _DD()
        r.max_drawdown = dd[max_dd_idx]
        r.max_drawdown_rel = max_dd_rel
        r.high_idx = int(peak_idx)
        r.low_idx = int(max_dd_idx)
        r.drawdown_series = dd
        return r

    def calculate_expectancy(profit_abs):
        p = np.asarray(profit_abs)
        wins = p[p > 0]
        losses = p[p < 0]
        avg_win = np.mean(wins) if len(wins) > 0 else 0.0
        avg_loss = abs(np.mean(losses)) if len(losses) > 0 else 0.0
        win_rate = len(wins) / len(p) if len(p) > 0 else 0.0
        loss_rate = 1.0 - win_rate
        expectancy = (avg_win * win_rate) - (avg_loss * loss_rate)
        exp_ratio = avg_win / avg_loss if avg_loss > 0 else 999.0
        return (expectancy, exp_ratio)
