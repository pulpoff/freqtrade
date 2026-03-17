/**
 * _ft_cpp — Freqtrade C++ extension module.
 *
 * Submodules:
 *   _ft_cpp.backtesting     — Fast trade simulation engine
 *   _ft_cpp.trade_math      — Profit/loss calculations
 *   _ft_cpp.data_processing — FreqAI data ops, NaN filtering
 *   _ft_cpp.report_gen      — Report generation and metrics
 *   _ft_cpp.orderflow       — Orderflow analysis
 *   _ft_cpp.indicators      — Technical indicators (Heikin Ashi, rolling ops)
 */

#include "common.h"

PYBIND11_MODULE(_ft_cpp, m) {
    m.doc() = "Freqtrade C++ extension — high-performance replacements for CPU-intensive routines";

    register_backtesting(m);
    register_trade_math(m);
    register_data_processing(m);
    register_report_gen(m);
    register_orderflow(m);
    register_indicators(m);
}
