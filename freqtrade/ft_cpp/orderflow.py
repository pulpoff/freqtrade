"""
Python wrapper for C++ orderflow functions with pure-Python fallback.
"""

from freqtrade.ft_cpp import HAS_CPP


if HAS_CPP:
    from freqtrade._ft_cpp.orderflow import (  # noqa: F401
        CandleAggregation,
        ImbalanceLevel,
        VolumeLevel,
        aggregate_candle_trades,
        detect_imbalances,
        find_stacked_imbalances,
        volume_profile,
    )
