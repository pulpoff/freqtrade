"""
Python wrapper for C++ backtesting simulation engine with pure-Python fallback.
"""

from freqtrade.ft_cpp import HAS_CPP


if HAS_CPP:
    from freqtrade._ft_cpp.backtesting import (  # noqa: F401
        TradeResult,
        simulate_trades,
    )
