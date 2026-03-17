/**
 * Backtesting engine — compiled trade simulation loop.
 *
 * Targets:
 *   - backtest_loop()          (backtesting.py:1453-1513)
 *   - _get_close_rate_for_stoploss() (backtesting.py:545-597)
 *   - _get_close_rate_for_roi()      (backtesting.py:599-664)
 *   - ROI / stoploss evaluation per candle
 *
 * This module provides a fast "simulate_trades" function that processes
 * OHLCV + signal arrays and returns trade results, replacing the inner
 * Python loop which is the #1 bottleneck.
 */

#include "common.h"
#include <tuple>
#include <optional>
#include <cfloat>

namespace backtesting {

// Column indices matching HEADERS in backtesting.py
enum ColIdx {
    DATE_IDX = 0,    // date (as int64 timestamp)
    OPEN_IDX = 1,
    HIGH_IDX = 2,
    LOW_IDX = 3,
    CLOSE_IDX = 4,
    LONG_IDX = 5,    // enter_long signal
    ELONG_IDX = 6,   // exit_long signal
    SHORT_IDX = 7,   // enter_short signal
    ESHORT_IDX = 8,  // exit_short signal
    ENTER_TAG_IDX = 9,
    EXIT_TAG_IDX = 10,
};

// ROI entry: (minutes_threshold, roi_percentage)
using RoiEntry = std::pair<int, double>;

// Trade state during simulation
struct SimTrade {
    int open_candle_idx;
    double open_rate;
    double amount;
    double stake_amount;
    double stop_loss;
    double stop_loss_pct;
    bool is_short;
    bool is_open;
    double fee_open;
    double fee_close;
    double leverage;
    int open_timestamp;  // candle index when opened

    // For trailing stoploss
    double highest_high;  // or lowest_low for shorts
    bool trailing_activated;
};

// Result of a closed trade
struct TradeResult {
    int open_idx;
    int close_idx;
    double open_rate;
    double close_rate;
    double profit_ratio;
    double profit_abs;
    bool is_short;
    int exit_reason;  // 0=signal, 1=roi, 2=stoploss, 3=trailing_stop
};

// ─────────────────────────────────────────────────────────────────────
//  Stoploss evaluation
// ─────────────────────────────────────────────────────────────────────

/**
 * Check if stoploss was hit on this candle.
 * Returns (hit, exit_rate).
 */
std::pair<bool, double> check_stoploss(
    const SimTrade& trade,
    double open_, double high, double low, double close,
    int candle_idx
) {
    double sl = trade.stop_loss;
    bool is_short = trade.is_short;

    if (is_short) {
        // Short: stoploss triggers when price goes UP to sl
        if (high >= sl) {
            // Check if stoploss was already above high (cancelled order scenario)
            if (sl < low) return {false, 0.0};
            return {true, sl};
        }
    } else {
        // Long: stoploss triggers when price goes DOWN to sl
        if (low <= sl) {
            if (sl > high) return {false, 0.0};
            return {true, sl};
        }
    }
    return {false, 0.0};
}

/**
 * Update trailing stoploss based on current candle.
 */
void update_trailing_stop(
    SimTrade& trade,
    double high, double low,
    double trailing_stop_pct,
    double trailing_stop_positive,
    double trailing_stop_positive_offset,
    bool trailing_only_offset_is_reached
) {
    double current_profit;
    double new_stop;

    if (trade.is_short) {
        // For shorts, track the lowest low
        if (low < trade.highest_high || trade.highest_high == 0.0) {
            trade.highest_high = low;
        }
        current_profit = (trade.open_rate - trade.highest_high) / trade.open_rate;

        double stop_pct = trailing_stop_pct;
        if (trailing_stop_positive > 0.0 && current_profit >= trailing_stop_positive_offset) {
            stop_pct = trailing_stop_positive;
            trade.trailing_activated = true;
        }

        if (trailing_only_offset_is_reached && !trade.trailing_activated) return;

        new_stop = trade.highest_high * (1.0 + stop_pct / trade.leverage);
        if (new_stop < trade.stop_loss || trade.stop_loss == 0.0) {
            trade.stop_loss = new_stop;
        }
    } else {
        // For longs, track the highest high
        if (high > trade.highest_high) {
            trade.highest_high = high;
        }
        current_profit = (trade.highest_high - trade.open_rate) / trade.open_rate;

        double stop_pct = trailing_stop_pct;
        if (trailing_stop_positive > 0.0 && current_profit >= trailing_stop_positive_offset) {
            stop_pct = trailing_stop_positive;
            trade.trailing_activated = true;
        }

        if (trailing_only_offset_is_reached && !trade.trailing_activated) return;

        new_stop = trade.highest_high * (1.0 - stop_pct / trade.leverage);
        if (new_stop > trade.stop_loss) {
            trade.stop_loss = new_stop;
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
//  ROI evaluation
// ─────────────────────────────────────────────────────────────────────

/**
 * Check if any ROI threshold is reached.
 * Returns (hit, roi_value, close_rate).
 */
struct RoiResult {
    bool hit;
    double close_rate;
};

RoiResult check_roi(
    const SimTrade& trade,
    const std::vector<RoiEntry>& roi_table,
    int trade_dur_candles,
    int timeframe_min,
    double open_, double high, double low, double close,
    double fee_open, double fee_close, double funding_fees
) {
    int trade_dur = trade_dur_candles * timeframe_min;

    // Find the applicable ROI entry (last entry where minutes <= trade_dur)
    double roi = -999.0;
    int roi_entry_minutes = -1;
    for (const auto& [minutes, pct] : roi_table) {
        if (minutes <= trade_dur) {
            roi = pct;
            roi_entry_minutes = minutes;
        }
    }
    if (roi < -900.0) return {false, 0.0};

    // Calculate the close rate needed for this ROI
    double leverage = (trade.leverage == 0.0) ? 1.0 : trade.leverage;
    double deleveraged_roi = roi / leverage;
    double open_value;
    if (trade.is_short) {
        open_value = trade.amount * trade.open_rate * (1.0 - fee_open);
    } else {
        open_value = trade.amount * trade.open_rate * (1.0 + fee_open);
    }

    double val0, val1;
    if (trade.is_short) {
        val0 = trade.amount * 0.0 * (1.0 + fee_close) + funding_fees;
        val1 = trade.amount * 1.0 * (1.0 + fee_close) + funding_fees;
    } else {
        val0 = trade.amount * 0.0 * (1.0 - fee_close) + funding_fees;
        val1 = trade.amount * 1.0 * (1.0 - fee_close) + funding_fees;
    }
    double alpha = val1 - val0;
    double beta = val0;

    double s = trade.is_short ? -1.0 : 1.0;
    double adj = 1.0 + (deleveraged_roi / s);
    double close_rate = (adj * open_value - beta) / alpha;

    // Check if the candle can reach this close_rate
    bool reached;
    if (trade.is_short) {
        reached = (low <= close_rate);
    } else {
        reached = (high >= close_rate);
    }

    if (reached) {
        // Handle force exit (roi == -1)
        if (roi == -1.0 && roi_entry_minutes % timeframe_min == 0) {
            return {true, open_};
        }

        // Clamp close_rate within candle range
        close_rate = std::min(std::max(close_rate, low), high);
        return {true, close_rate};
    }
    return {false, 0.0};
}

// ─────────────────────────────────────────────────────────────────────
//  Main simulation function
// ─────────────────────────────────────────────────────────────────────

/**
 * Fast trade simulation over OHLCV + signal data for a single pair.
 *
 * This replaces the inner Python backtest_loop for simple strategies
 * (no DCA, no custom callbacks, no position stacking).
 *
 * Parameters:
 *   ohlcv:              2D array [n_candles, 5] (open, high, low, close, volume)
 *   signals:            2D array [n_candles, 4] (enter_long, exit_long, enter_short, exit_short)
 *   roi_table:          list of (minutes, percentage) pairs, sorted by minutes
 *   stoploss:           stoploss percentage (negative, e.g. -0.1 for 10%)
 *   trailing_stop:      whether trailing stop is enabled
 *   trailing_stop_pct:  trailing stop percentage (positive)
 *   trailing_stop_positive: tighter trailing stop after reaching offset
 *   trailing_stop_positive_offset: profit threshold to activate positive trailing
 *   trailing_only_offset_is_reached: only trail after offset
 *   fee_open/fee_close: trading fees
 *   leverage:           leverage multiplier
 *   timeframe_min:      timeframe in minutes
 *   stake_amount:       stake per trade
 *   can_short:          whether shorting is allowed
 *   max_open_trades:    maximum concurrent open trades (-1 = unlimited)
 *
 * Returns: list of TradeResult structs
 */
std::vector<TradeResult> simulate_trades(
    py::array_t<double> ohlcv,
    py::array_t<int> signals,
    std::vector<std::pair<int, double>> roi_table,
    double stoploss,
    bool trailing_stop,
    double trailing_stop_pct,
    double trailing_stop_positive,
    double trailing_stop_positive_offset,
    bool trailing_only_offset_is_reached,
    double fee_open,
    double fee_close,
    double leverage,
    int timeframe_min,
    double stake_amount,
    bool can_short,
    int max_open_trades
) {
    auto ohlcv_buf = ohlcv.unchecked<2>();
    auto sig_buf = signals.unchecked<2>();
    ssize_t n_candles = ohlcv_buf.shape(0);

    // Sort ROI table by minutes ascending
    std::sort(roi_table.begin(), roi_table.end());

    std::vector<SimTrade> open_trades;
    std::vector<TradeResult> results;

    double sl_pct = std::abs(stoploss);

    for (ssize_t i = 0; i < n_candles; ++i) {
        double o = ohlcv_buf(i, 0);
        double h = ohlcv_buf(i, 1);
        double l = ohlcv_buf(i, 2);
        double c = ohlcv_buf(i, 3);

        int enter_long = sig_buf(i, 0);
        int exit_long = sig_buf(i, 1);
        int enter_short = sig_buf(i, 2);
        int exit_short = sig_buf(i, 3);

        // ── Process existing trades ──
        // Iterate in reverse so we can remove closed trades
        for (int j = static_cast<int>(open_trades.size()) - 1; j >= 0; --j) {
            auto& trade = open_trades[j];
            int trade_dur_candles = static_cast<int>(i) - trade.open_candle_idx;

            // Update trailing stop
            if (trailing_stop) {
                update_trailing_stop(
                    trade, h, l,
                    trailing_stop_pct > 0.0 ? trailing_stop_pct : sl_pct,
                    trailing_stop_positive,
                    trailing_stop_positive_offset,
                    trailing_only_offset_is_reached
                );
            }

            // Check exit signal
            bool signal_exit = false;
            if (trade.is_short) {
                signal_exit = (exit_short != 0);
            } else {
                signal_exit = (exit_long != 0);
            }

            // Check stoploss
            auto [sl_hit, sl_rate] = check_stoploss(trade, o, h, l, c, static_cast<int>(i));

            // Check ROI
            auto roi_result = check_roi(
                trade, roi_table, trade_dur_candles, timeframe_min,
                o, h, l, c, fee_open, fee_close, 0.0
            );

            // Determine exit: priority is stoploss > roi > signal
            bool should_exit = false;
            double close_rate = o;
            int exit_reason = 0;

            if (sl_hit) {
                should_exit = true;
                close_rate = sl_rate;
                exit_reason = trailing_stop && trade.trailing_activated ? 3 : 2;
            } else if (roi_result.hit) {
                should_exit = true;
                close_rate = roi_result.close_rate;
                exit_reason = 1;
            } else if (signal_exit) {
                should_exit = true;
                close_rate = o;  // exit at open of signal candle
                exit_reason = 0;
            }

            if (should_exit) {
                // Calculate profit
                double open_value, close_value;
                if (trade.is_short) {
                    open_value = trade.amount * trade.open_rate * (1.0 - fee_open);
                    close_value = trade.amount * close_rate * (1.0 + fee_close);
                } else {
                    open_value = trade.amount * trade.open_rate * (1.0 + fee_open);
                    close_value = trade.amount * close_rate * (1.0 - fee_close);
                }

                double profit_abs, profit_ratio;
                if (trade.is_short) {
                    profit_abs = open_value - close_value;
                    profit_ratio = (open_value != 0.0)
                        ? (1.0 - close_value / open_value) * leverage : 0.0;
                } else {
                    profit_abs = close_value - open_value;
                    profit_ratio = (open_value != 0.0)
                        ? (close_value / open_value - 1.0) * leverage : 0.0;
                }

                results.push_back({
                    trade.open_candle_idx,
                    static_cast<int>(i),
                    trade.open_rate,
                    close_rate,
                    round8(profit_ratio),
                    round8(profit_abs),
                    trade.is_short,
                    exit_reason
                });

                open_trades.erase(open_trades.begin() + j);
            }
        }

        // ── Check for new entries (skip last candle) ──
        if (i >= n_candles - 1) continue;

        bool can_open = (max_open_trades < 0 ||
                         static_cast<int>(open_trades.size()) < max_open_trades);
        if (!can_open) continue;

        // Only one open trade at a time (no position stacking)
        if (!open_trades.empty()) continue;

        bool open_long = (enter_long != 0);
        bool open_short = can_short && (enter_short != 0);

        if (open_long || open_short) {
            bool is_short = open_short && !open_long;  // long takes priority
            double entry_rate = o;
            double amount = stake_amount / entry_rate;

            SimTrade t;
            t.open_candle_idx = static_cast<int>(i);
            t.open_rate = entry_rate;
            t.amount = amount;
            t.stake_amount = stake_amount;
            t.is_short = is_short;
            t.is_open = true;
            t.fee_open = fee_open;
            t.fee_close = fee_close;
            t.leverage = leverage;

            // Set initial stoploss
            if (is_short) {
                t.stop_loss = entry_rate * (1.0 + sl_pct / leverage);
                t.highest_high = l;  // track lowest for shorts
            } else {
                t.stop_loss = entry_rate * (1.0 - sl_pct / leverage);
                t.highest_high = h;
            }
            t.stop_loss_pct = stoploss;
            t.trailing_activated = false;

            open_trades.push_back(t);
        }
    }

    return results;
}

}  // namespace backtesting


void register_backtesting(py::module_& m) {
    auto bt = m.def_submodule("backtesting", "Fast backtesting simulation engine");

    py::class_<backtesting::TradeResult>(bt, "TradeResult")
        .def_readonly("open_idx", &backtesting::TradeResult::open_idx)
        .def_readonly("close_idx", &backtesting::TradeResult::close_idx)
        .def_readonly("open_rate", &backtesting::TradeResult::open_rate)
        .def_readonly("close_rate", &backtesting::TradeResult::close_rate)
        .def_readonly("profit_ratio", &backtesting::TradeResult::profit_ratio)
        .def_readonly("profit_abs", &backtesting::TradeResult::profit_abs)
        .def_readonly("is_short", &backtesting::TradeResult::is_short)
        .def_readonly("exit_reason", &backtesting::TradeResult::exit_reason);

    bt.def("simulate_trades", &backtesting::simulate_trades,
           py::arg("ohlcv"), py::arg("signals"),
           py::arg("roi_table"),
           py::arg("stoploss"),
           py::arg("trailing_stop") = false,
           py::arg("trailing_stop_pct") = 0.0,
           py::arg("trailing_stop_positive") = 0.0,
           py::arg("trailing_stop_positive_offset") = 0.0,
           py::arg("trailing_only_offset_is_reached") = false,
           py::arg("fee_open") = 0.001,
           py::arg("fee_close") = 0.001,
           py::arg("leverage") = 1.0,
           py::arg("timeframe_min") = 5,
           py::arg("stake_amount") = 100.0,
           py::arg("can_short") = false,
           py::arg("max_open_trades") = -1,
           "Simulate trades over OHLCV + signal arrays.\n"
           "Returns list of TradeResult with open/close indices, rates, and profit.");
}
