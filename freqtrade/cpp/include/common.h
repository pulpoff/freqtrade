#pragma once

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <vector>
#include <cmath>
#include <algorithm>
#include <numeric>
#include <string>
#include <unordered_map>
#include <limits>
#include <cstdint>

namespace py = pybind11;

// Round to 8 decimal places (matching Python's float(f"{x:.8f}"))
inline double round8(double x) {
    return std::round(x * 1e8) / 1e8;
}

// Safe division that returns 0 on divide-by-zero
inline double safe_div(double num, double den) {
    return (den == 0.0) ? 0.0 : num / den;
}

// Forward declarations for submodule registration
void register_backtesting(py::module_& m);
void register_trade_math(py::module_& m);
void register_data_processing(py::module_& m);
void register_report_gen(py::module_& m);
void register_orderflow(py::module_& m);
void register_indicators(py::module_& m);
