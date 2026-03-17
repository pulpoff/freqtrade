/**
 * Indicators module — fast technical indicator calculations.
 *
 * Targets:
 *   - heikinashi()              (indicators.py:102-122)
 *   - numpy_rolling_mean/std    (indicators.py:33-62)
 *   - Rolling window operations used by strategy indicators
 */

#include "common.h"

namespace indicators {

// ─────────────────────────────────────────────────────────────────────
//  Heikin Ashi
//  Replaces the row-by-row .at[i] loop in qtpylib/indicators.py:108-109
// ─────────────────────────────────────────────────────────────────────

/**
 * Compute Heikin Ashi candles from OHLC data.
 *
 * Input:  4 arrays of length N: open, high, low, close
 * Output: 4 arrays: ha_open, ha_high, ha_low, ha_close
 *
 * ha_close = (O + H + L + C) / 4
 * ha_open[0] = (O[0] + C[0]) / 2
 * ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2
 * ha_high = max(H, ha_open, ha_close)
 * ha_low  = min(L, ha_open, ha_close)
 */
std::tuple<py::array_t<double>, py::array_t<double>, py::array_t<double>, py::array_t<double>>
heikinashi(
    py::array_t<double> open_,
    py::array_t<double> high,
    py::array_t<double> low,
    py::array_t<double> close
) {
    auto o = open_.unchecked<1>();
    auto h = high.unchecked<1>();
    auto l = low.unchecked<1>();
    auto c = close.unchecked<1>();
    ssize_t n = o.shape(0);

    py::array_t<double> ha_open(n), ha_high(n), ha_low(n), ha_close(n);
    auto hao = ha_open.mutable_unchecked<1>();
    auto hah = ha_high.mutable_unchecked<1>();
    auto hal = ha_low.mutable_unchecked<1>();
    auto hac = ha_close.mutable_unchecked<1>();

    // ha_close (fully vectorizable)
    for (ssize_t i = 0; i < n; ++i) {
        hac(i) = (o(i) + h(i) + l(i) + c(i)) / 4.0;
    }

    // ha_open (sequential dependency — the bottleneck in Python)
    hao(0) = (o(0) + c(0)) / 2.0;
    for (ssize_t i = 1; i < n; ++i) {
        hao(i) = (hao(i - 1) + hac(i - 1)) / 2.0;
    }

    // ha_high, ha_low
    for (ssize_t i = 0; i < n; ++i) {
        hah(i) = std::max({h(i), hao(i), hac(i)});
        hal(i) = std::min({l(i), hao(i), hac(i)});
    }

    return std::make_tuple(ha_open, ha_high, ha_low, ha_close);
}

// ─────────────────────────────────────────────────────────────────────
//  Rolling statistics
// ─────────────────────────────────────────────────────────────────────

/**
 * Rolling mean with NaN padding for initial elements.
 * Replaces numpy_rolling_mean in indicators.py.
 */
py::array_t<double> rolling_mean(py::array_t<double> data, int window) {
    auto d = data.unchecked<1>();
    ssize_t n = d.shape(0);

    py::array_t<double> result(n);
    auto res = result.mutable_unchecked<1>();

    double sum = 0.0;
    for (ssize_t i = 0; i < n; ++i) {
        sum += d(i);
        if (i >= window) {
            sum -= d(i - window);
        }
        if (i >= window - 1) {
            res(i) = sum / window;
        } else {
            res(i) = std::numeric_limits<double>::quiet_NaN();
        }
    }
    return result;
}

/**
 * Rolling standard deviation with NaN padding.
 * Uses Welford's online algorithm for numerical stability.
 */
py::array_t<double> rolling_std(py::array_t<double> data, int window) {
    auto d = data.unchecked<1>();
    ssize_t n = d.shape(0);

    py::array_t<double> result(n);
    auto res = result.mutable_unchecked<1>();

    // Two-pass within window for accuracy
    for (ssize_t i = 0; i < n; ++i) {
        if (i < window - 1) {
            res(i) = std::numeric_limits<double>::quiet_NaN();
            continue;
        }

        // Calculate mean
        double sum = 0.0;
        ssize_t start = i - window + 1;
        for (ssize_t j = start; j <= i; ++j) {
            sum += d(j);
        }
        double mean = sum / window;

        // Calculate variance
        double var_sum = 0.0;
        for (ssize_t j = start; j <= i; ++j) {
            double diff = d(j) - mean;
            var_sum += diff * diff;
        }
        // ddof=1 (sample std)
        res(i) = std::sqrt(var_sum / (window - 1));
    }
    return result;
}

/**
 * Rolling sum.
 */
py::array_t<double> rolling_sum(py::array_t<double> data, int window) {
    auto d = data.unchecked<1>();
    ssize_t n = d.shape(0);

    py::array_t<double> result(n);
    auto res = result.mutable_unchecked<1>();

    double sum = 0.0;
    for (ssize_t i = 0; i < n; ++i) {
        sum += d(i);
        if (i >= window) {
            sum -= d(i - window);
        }
        if (i >= window - 1) {
            res(i) = sum;
        } else {
            res(i) = std::numeric_limits<double>::quiet_NaN();
        }
    }
    return result;
}

/**
 * Rolling min/max.
 */
py::array_t<double> rolling_min(py::array_t<double> data, int window) {
    auto d = data.unchecked<1>();
    ssize_t n = d.shape(0);

    py::array_t<double> result(n);
    auto res = result.mutable_unchecked<1>();

    for (ssize_t i = 0; i < n; ++i) {
        if (i < window - 1) {
            res(i) = std::numeric_limits<double>::quiet_NaN();
            continue;
        }
        double mn = d(i);
        ssize_t start = i - window + 1;
        for (ssize_t j = start; j <= i; ++j) {
            if (d(j) < mn) mn = d(j);
        }
        res(i) = mn;
    }
    return result;
}

py::array_t<double> rolling_max(py::array_t<double> data, int window) {
    auto d = data.unchecked<1>();
    ssize_t n = d.shape(0);

    py::array_t<double> result(n);
    auto res = result.mutable_unchecked<1>();

    for (ssize_t i = 0; i < n; ++i) {
        if (i < window - 1) {
            res(i) = std::numeric_limits<double>::quiet_NaN();
            continue;
        }
        double mx = d(i);
        ssize_t start = i - window + 1;
        for (ssize_t j = start; j <= i; ++j) {
            if (d(j) > mx) mx = d(j);
        }
        res(i) = mx;
    }
    return result;
}

// ─────────────────────────────────────────────────────────────────────
//  Exponential Moving Average
// ─────────────────────────────────────────────────────────────────────

py::array_t<double> ema(py::array_t<double> data, int period) {
    auto d = data.unchecked<1>();
    ssize_t n = d.shape(0);

    py::array_t<double> result(n);
    auto res = result.mutable_unchecked<1>();

    double multiplier = 2.0 / (period + 1.0);

    // Initialize with NaN until we have enough data
    for (ssize_t i = 0; i < period - 1 && i < n; ++i) {
        res(i) = std::numeric_limits<double>::quiet_NaN();
    }

    if (n >= period) {
        // First EMA value is SMA of first 'period' values
        double sum = 0.0;
        for (ssize_t i = 0; i < period; ++i) {
            sum += d(i);
        }
        res(period - 1) = sum / period;

        // Calculate EMA for remaining values
        for (ssize_t i = period; i < n; ++i) {
            res(i) = (d(i) - res(i - 1)) * multiplier + res(i - 1);
        }
    }

    return result;
}

}  // namespace indicators


void register_indicators(py::module_& m) {
    auto ind = m.def_submodule("indicators", "Fast technical indicator calculations");

    ind.def("heikinashi", &indicators::heikinashi,
            py::arg("open"), py::arg("high"), py::arg("low"), py::arg("close"),
            "Compute Heikin Ashi candles. Returns (ha_open, ha_high, ha_low, ha_close).");

    ind.def("rolling_mean", &indicators::rolling_mean,
            py::arg("data"), py::arg("window"),
            "Rolling mean with NaN padding for initial elements.");

    ind.def("rolling_std", &indicators::rolling_std,
            py::arg("data"), py::arg("window"),
            "Rolling standard deviation (ddof=1) with NaN padding.");

    ind.def("rolling_sum", &indicators::rolling_sum,
            py::arg("data"), py::arg("window"),
            "Rolling sum with NaN padding.");

    ind.def("rolling_min", &indicators::rolling_min,
            py::arg("data"), py::arg("window"),
            "Rolling minimum with NaN padding.");

    ind.def("rolling_max", &indicators::rolling_max,
            py::arg("data"), py::arg("window"),
            "Rolling maximum with NaN padding.");

    ind.def("ema", &indicators::ema,
            py::arg("data"), py::arg("period"),
            "Exponential Moving Average.");
}
