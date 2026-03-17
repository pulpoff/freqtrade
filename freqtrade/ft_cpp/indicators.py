"""
Python wrapper for C++ indicator functions with pure-Python fallback.
"""

import numpy as np
import pandas as pd

from freqtrade.ft_cpp import HAS_CPP


if HAS_CPP:
    from freqtrade._ft_cpp.indicators import (  # noqa: F401
        ema,
        heikinashi,
        rolling_max,
        rolling_mean,
        rolling_min,
        rolling_std,
        rolling_sum,
    )
else:

    def heikinashi(open_, high, low, close):
        o, h, l, c = np.asarray(open_), np.asarray(high), np.asarray(low), np.asarray(close)
        n = len(o)
        ha_close = (o + h + l + c) / 4.0
        ha_open = np.empty(n)
        ha_open[0] = (o[0] + c[0]) / 2.0
        for i in range(1, n):
            ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2.0
        ha_high = np.maximum(np.maximum(h, ha_open), ha_close)
        ha_low = np.minimum(np.minimum(l, ha_open), ha_close)
        return ha_open, ha_high, ha_low, ha_close

    def rolling_mean(data, window):
        return pd.Series(data).rolling(window).mean().values

    def rolling_std(data, window):
        return pd.Series(data).rolling(window).std().values

    def rolling_sum(data, window):
        return pd.Series(data).rolling(window).sum().values

    def rolling_min(data, window):
        return pd.Series(data).rolling(window).min().values

    def rolling_max(data, window):
        return pd.Series(data).rolling(window).max().values

    def ema(data, period):
        return pd.Series(data).ewm(span=period, adjust=False).mean().values


def heikinashi_df(bars: pd.DataFrame) -> pd.DataFrame:
    """
    Drop-in replacement for qtpylib.indicators.heikinashi().
    Takes a DataFrame with open/high/low/close columns and returns
    a DataFrame with Heikin Ashi values.
    """
    ha_open, ha_high, ha_low, ha_close = heikinashi(
        bars["open"].values, bars["high"].values,
        bars["low"].values, bars["close"].values
    )
    return pd.DataFrame(
        index=bars.index,
        data={
            "open": ha_open,
            "high": ha_high,
            "low": ha_low,
            "close": ha_close,
        },
    )
