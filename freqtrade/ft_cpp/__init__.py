"""
Freqtrade C++ acceleration wrappers.

Provides Python-accessible interfaces to C++ optimized routines.
Falls back gracefully to pure Python/numpy implementations if the
C++ extension is not compiled.

Usage:
    from freqtrade.ft_cpp import indicators, trade_math, ...

Build the extension:
    python setup_cpp.py build_ext --inplace
"""

try:
    from freqtrade._ft_cpp import (  # noqa: F401
        backtesting,
        data_processing,
        indicators,
        orderflow,
        report_gen,
        trade_math,
    )

    HAS_CPP = True
except ImportError:
    HAS_CPP = False


def is_available() -> bool:
    """Return True if the C++ extension is compiled and available."""
    return HAS_CPP
