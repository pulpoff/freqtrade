/**
 * Report generation module — fast signal candle extraction and pair metrics.
 *
 * Targets:
 *   - generate_trade_signal_candles()  (optimize_reports.py:32-52)
 *   - generate_rejected_signals()      (optimize_reports.py:55-73)
 *   - _generate_result_line() profit aggregation
 *   - calculate_max_drawdown()         (metrics.py:206-269)
 */

#include "common.h"

namespace report_gen {

// ─────────────────────────────────────────────────────────────────────
//  Signal candle extraction
//  Replaces iterrows() + concat-in-loop pattern
// ─────────────────────────────────────────────────────────────────────

/**
 * For each trade, find the index of the last candle BEFORE the trade date.
 *
 * candle_dates: sorted int64 array of candle timestamps (ns or ms)
 * trade_dates:  int64 array of trade entry timestamps
 *
 * Returns: int64 array of candle indices (-1 if no candle found)
 *
 * Uses binary search for O(T * log(C)) instead of O(T * C).
 */
py::array_t<int64_t> find_signal_candle_indices(
    py::array_t<int64_t> candle_dates,
    py::array_t<int64_t> trade_dates
) {
    auto cd = candle_dates.unchecked<1>();
    auto td = trade_dates.unchecked<1>();
    ssize_t n_candles = cd.shape(0);
    ssize_t n_trades = td.shape(0);

    py::array_t<int64_t> result(n_trades);
    auto res = result.mutable_unchecked<1>();

    for (ssize_t i = 0; i < n_trades; ++i) {
        int64_t target = td(i);

        // Binary search: find last candle_date < target
        ssize_t lo = 0, hi = n_candles - 1;
        ssize_t best = -1;

        while (lo <= hi) {
            ssize_t mid = lo + (hi - lo) / 2;
            if (cd(mid) < target) {
                best = mid;
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }
        res(i) = best;
    }
    return result;
}

/**
 * For each rejected signal, find the index of the candle with EXACT date match.
 *
 * candle_dates: sorted int64 array of candle timestamps
 * signal_dates: int64 array of rejected signal timestamps
 *
 * Returns: int64 array of candle indices (-1 if not found)
 */
py::array_t<int64_t> find_exact_candle_indices(
    py::array_t<int64_t> candle_dates,
    py::array_t<int64_t> signal_dates
) {
    auto cd = candle_dates.unchecked<1>();
    auto sd = signal_dates.unchecked<1>();
    ssize_t n_candles = cd.shape(0);
    ssize_t n_signals = sd.shape(0);

    py::array_t<int64_t> result(n_signals);
    auto res = result.mutable_unchecked<1>();

    for (ssize_t i = 0; i < n_signals; ++i) {
        int64_t target = sd(i);

        // Binary search for exact match
        ssize_t lo = 0, hi = n_candles - 1;
        ssize_t found = -1;

        while (lo <= hi) {
            ssize_t mid = lo + (hi - lo) / 2;
            if (cd(mid) == target) {
                found = mid;
                break;
            } else if (cd(mid) < target) {
                lo = mid + 1;
            } else {
                hi = mid - 1;
            }
        }
        res(i) = found;
    }
    return result;
}

// ─────────────────────────────────────────────────────────────────────
//  Drawdown calculation
//  Replaces _calc_drawdown_series (metrics.py:129-161)
// ─────────────────────────────────────────────────────────────────────

struct DrawdownResult {
    double max_drawdown;          // maximum drawdown (absolute)
    double max_drawdown_rel;      // maximum relative drawdown
    int64_t high_idx;             // index of the peak before max drawdown
    int64_t low_idx;              // index of the trough of max drawdown
    py::array_t<double> drawdown_series;  // cumulative drawdown at each point
};

/**
 * Calculate max drawdown from a series of profit values.
 *
 * profits:           array of per-trade profits (absolute)
 * starting_balance:  initial account balance
 *
 * Returns DrawdownResult with max drawdown and the drawdown series.
 */
DrawdownResult calculate_max_drawdown(
    py::array_t<double> profits,
    double starting_balance
) {
    auto p = profits.unchecked<1>();
    ssize_t n = p.shape(0);

    py::array_t<double> dd_series(n);
    auto dd = dd_series.mutable_unchecked<1>();

    // Cumulative sum
    std::vector<double> cum_profit(n);
    double running = 0.0;
    for (ssize_t i = 0; i < n; ++i) {
        running += p(i);
        cum_profit[i] = running;
    }

    // Running maximum of cumulative profit
    std::vector<double> cum_max(n);
    double running_max = cum_profit[0];
    cum_max[0] = running_max;
    for (ssize_t i = 1; i < n; ++i) {
        running_max = std::max(running_max, cum_profit[i]);
        cum_max[i] = running_max;
    }

    // Drawdown = cumulative max - cumulative profit
    for (ssize_t i = 0; i < n; ++i) {
        dd(i) = cum_max[i] - cum_profit[i];
    }

    // Find max absolute drawdown
    double max_dd = 0.0;
    ssize_t max_dd_idx = 0;
    for (ssize_t i = 0; i < n; ++i) {
        if (dd(i) > max_dd) {
            max_dd = dd(i);
            max_dd_idx = i;
        }
    }

    // Find the peak before the max drawdown
    ssize_t peak_idx = 0;
    double peak_val = cum_profit[0];
    for (ssize_t i = 0; i <= max_dd_idx; ++i) {
        if (cum_profit[i] >= peak_val) {
            peak_val = cum_profit[i];
            peak_idx = i;
        }
    }

    // Relative drawdown
    double peak_balance = starting_balance + peak_val;
    double max_dd_rel = (peak_balance > 0.0) ? max_dd / peak_balance : 0.0;

    DrawdownResult result;
    result.max_drawdown = max_dd;
    result.max_drawdown_rel = max_dd_rel;
    result.high_idx = peak_idx;
    result.low_idx = max_dd_idx;
    result.drawdown_series = dd_series;
    return result;
}

// ─────────────────────────────────────────────────────────────────────
//  Profit aggregation helpers
// ─────────────────────────────────────────────────────────────────────

struct PairMetrics {
    int trade_count;
    double profit_abs_sum;
    double profit_ratio_mean;
    int win_count;
    int loss_count;
    double avg_duration_seconds;
};

/**
 * Calculate per-group aggregated metrics from trade results.
 *
 * group_ids:     int array mapping each trade to a group (e.g., pair index)
 * profit_abs:    double array of absolute profit per trade
 * profit_ratio:  double array of profit ratio per trade
 * durations:     double array of trade duration in seconds
 * n_groups:      number of distinct groups
 */
std::vector<PairMetrics> aggregate_pair_metrics(
    py::array_t<int> group_ids,
    py::array_t<double> profit_abs,
    py::array_t<double> profit_ratio,
    py::array_t<double> durations,
    int n_groups
) {
    auto gid = group_ids.unchecked<1>();
    auto pabs = profit_abs.unchecked<1>();
    auto prat = profit_ratio.unchecked<1>();
    auto dur = durations.unchecked<1>();
    ssize_t n = gid.shape(0);

    std::vector<PairMetrics> metrics(n_groups);
    for (int i = 0; i < n_groups; ++i) {
        metrics[i] = {0, 0.0, 0.0, 0, 0, 0.0};
    }

    for (ssize_t i = 0; i < n; ++i) {
        int g = gid(i);
        if (g < 0 || g >= n_groups) continue;

        auto& m = metrics[g];
        m.trade_count++;
        m.profit_abs_sum += pabs(i);
        m.profit_ratio_mean += prat(i);
        if (pabs(i) > 0) m.win_count++;
        else if (pabs(i) < 0) m.loss_count++;
        m.avg_duration_seconds += dur(i);
    }

    // Finalize averages
    for (int i = 0; i < n_groups; ++i) {
        auto& m = metrics[i];
        if (m.trade_count > 0) {
            m.profit_ratio_mean /= m.trade_count;
            m.avg_duration_seconds /= m.trade_count;
        }
    }

    return metrics;
}

// ─────────────────────────────────────────────────────────────────────
//  Expectancy calculation (metrics.py:307-335)
// ─────────────────────────────────────────────────────────────────────

std::pair<double, double> calculate_expectancy(py::array_t<double> profit_abs) {
    auto p = profit_abs.unchecked<1>();
    ssize_t n = p.shape(0);

    double win_sum = 0.0, loss_sum = 0.0;
    int win_count = 0, loss_count = 0;

    for (ssize_t i = 0; i < n; ++i) {
        if (p(i) > 0.0) { win_sum += p(i); win_count++; }
        else if (p(i) < 0.0) { loss_sum += p(i); loss_count++; }
    }

    double avg_win = (win_count > 0) ? win_sum / win_count : 0.0;
    double avg_loss = (loss_count > 0) ? std::abs(loss_sum / loss_count) : 0.0;
    double win_rate = (n > 0) ? static_cast<double>(win_count) / n : 0.0;
    double loss_rate = 1.0 - win_rate;

    double expectancy = (avg_win * win_rate) - (avg_loss * loss_rate);
    double expectancy_ratio = (avg_loss > 0.0) ? avg_win / avg_loss : 999.0;

    return {expectancy, expectancy_ratio};
}

}  // namespace report_gen


void register_report_gen(py::module_& m) {
    auto rg = m.def_submodule("report_gen", "Fast report generation and metrics");

    rg.def("find_signal_candle_indices", &report_gen::find_signal_candle_indices,
           py::arg("candle_dates"), py::arg("trade_dates"),
           "Binary search for signal candle indices (last candle before each trade date).");

    rg.def("find_exact_candle_indices", &report_gen::find_exact_candle_indices,
           py::arg("candle_dates"), py::arg("signal_dates"),
           "Binary search for exact date matches.");

    py::class_<report_gen::DrawdownResult>(rg, "DrawdownResult")
        .def_readonly("max_drawdown", &report_gen::DrawdownResult::max_drawdown)
        .def_readonly("max_drawdown_rel", &report_gen::DrawdownResult::max_drawdown_rel)
        .def_readonly("high_idx", &report_gen::DrawdownResult::high_idx)
        .def_readonly("low_idx", &report_gen::DrawdownResult::low_idx)
        .def_readonly("drawdown_series", &report_gen::DrawdownResult::drawdown_series);

    rg.def("calculate_max_drawdown", &report_gen::calculate_max_drawdown,
           py::arg("profits"), py::arg("starting_balance") = 0.0,
           "Calculate maximum drawdown from profit series.");

    py::class_<report_gen::PairMetrics>(rg, "PairMetrics")
        .def_readonly("trade_count", &report_gen::PairMetrics::trade_count)
        .def_readonly("profit_abs_sum", &report_gen::PairMetrics::profit_abs_sum)
        .def_readonly("profit_ratio_mean", &report_gen::PairMetrics::profit_ratio_mean)
        .def_readonly("win_count", &report_gen::PairMetrics::win_count)
        .def_readonly("loss_count", &report_gen::PairMetrics::loss_count)
        .def_readonly("avg_duration_seconds", &report_gen::PairMetrics::avg_duration_seconds);

    rg.def("aggregate_pair_metrics", &report_gen::aggregate_pair_metrics,
           py::arg("group_ids"), py::arg("profit_abs"),
           py::arg("profit_ratio"), py::arg("durations"),
           py::arg("n_groups"),
           "Aggregate trade metrics by group (pair, tag, etc.).");

    rg.def("calculate_expectancy", &report_gen::calculate_expectancy,
           py::arg("profit_abs"),
           "Calculate expectancy and expectancy ratio from profit array.");
}
