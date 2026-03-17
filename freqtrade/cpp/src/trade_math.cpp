/**
 * Trade math module — replaces FtPrecise string-based math and Python profit calculations
 * with native double-precision C++ arithmetic.
 *
 * Targets:
 *   - calculate_profit()        (trade_model.py:1130-1179)
 *   - calc_profit_ratio()       (trade_model.py:1181-1209)
 *   - calc_close_rate_for_roi() (trade_model.py:1211-1238)
 *   - recalc_trade_from_orders()(trade_model.py:1240-1317)
 *   - _calc_open_trade_value()  / calc_close_trade_value()
 */

#include "common.h"

namespace trade_math {

// ─────────────────────────────────────────────────────────────────────
//  Core value calculations
// ─────────────────────────────────────────────────────────────────────

/**
 * Calculate the open trade value (cost basis including fees).
 *   SPOT long:  amount * open_rate * (1 + fee)
 *   SPOT short: amount * open_rate * (1 - fee)
 */
double calc_open_trade_value(double amount, double open_rate, double fee_open, bool is_short) {
    if (is_short) {
        return amount * open_rate * (1.0 - fee_open);
    }
    return amount * open_rate * (1.0 + fee_open);
}

/**
 * Calculate the close trade value.
 *   SPOT long:  amount * close_rate * (1 - fee)
 *   SPOT short: amount * close_rate * (1 + fee)
 * For futures, funding_fees are added.
 */
double calc_close_trade_value(double amount, double close_rate, double fee_close,
                              bool is_short, double funding_fees) {
    double val;
    if (is_short) {
        val = amount * close_rate * (1.0 + fee_close);
    } else {
        val = amount * close_rate * (1.0 - fee_close);
    }
    return val + funding_fees;
}

// ─────────────────────────────────────────────────────────────────────
//  Profit calculations
// ─────────────────────────────────────────────────────────────────────

struct ProfitResult {
    double profit_abs;
    double profit_ratio;
    double total_profit;
    double total_profit_ratio;
};

/**
 * Vectorised calculate_profit matching trade_model.py:1130-1179
 */
ProfitResult calculate_profit(
    double open_trade_value,
    double close_trade_value,
    bool is_short,
    double leverage,
    double realized_profit,
    double max_stake_amount,
    double fee_open
) {
    ProfitResult r;

    if (is_short) {
        r.profit_abs = open_trade_value - close_trade_value;
    } else {
        r.profit_abs = close_trade_value - open_trade_value;
    }

    if (open_trade_value == 0.0) {
        r.profit_ratio = 0.0;
    } else if (is_short) {
        r.profit_ratio = (1.0 - (close_trade_value / open_trade_value)) * leverage;
    } else {
        r.profit_ratio = ((close_trade_value / open_trade_value) - 1.0) * leverage;
    }
    r.profit_ratio = round8(r.profit_ratio);

    r.total_profit = round8(r.profit_abs + realized_profit);

    if (max_stake_amount > 0.0) {
        double max_stake = max_stake_amount * (is_short ? (1.0 - fee_open) : (1.0 + fee_open));
        r.total_profit_ratio = round8(r.total_profit / max_stake);
    } else {
        r.total_profit_ratio = 0.0;
    }
    r.profit_abs = round8(r.profit_abs);

    return r;
}

/**
 * Scalar calc_profit_ratio matching trade_model.py:1181-1209
 */
double calc_profit_ratio(
    double close_trade_value,
    double open_trade_value,
    bool is_short,
    double leverage
) {
    if (open_trade_value == 0.0) return 0.0;
    double ratio;
    if (is_short) {
        ratio = (1.0 - (close_trade_value / open_trade_value)) * leverage;
    } else {
        ratio = ((close_trade_value / open_trade_value) - 1.0) * leverage;
    }
    return round8(ratio);
}

/**
 * calc_close_rate_for_roi matching trade_model.py:1211-1238
 * Uses the affine probing trick: close_value(rate) = alpha*rate + beta
 */
double calc_close_rate_for_roi(
    double target_roi, double leverage, bool is_short,
    double amount, double open_rate, double fee_open, double fee_close,
    double funding_fees
) {
    double lev = (leverage == 0.0) ? 1.0 : leverage;
    double deleveraged_roi = target_roi / lev;

    double open_value = calc_open_trade_value(amount, open_rate, fee_open, is_short);
    double value_at_0 = calc_close_trade_value(amount, 0.0, fee_close, is_short, funding_fees);
    double value_at_1 = calc_close_trade_value(amount, 1.0, fee_close, is_short, funding_fees);

    double alpha = value_at_1 - value_at_0;
    double beta = value_at_0;

    double s = is_short ? -1.0 : 1.0;
    double adj = 1.0 + (deleveraged_roi / s);
    return (adj * open_value - beta) / alpha;
}

// ─────────────────────────────────────────────────────────────────────
//  Batch profit ratio for arrays (vectorized backtest use)
// ─────────────────────────────────────────────────────────────────────

/**
 * Batch calculate profit ratios for arrays of close rates.
 * Useful for vectorized backtesting where we process many candles at once.
 */
py::array_t<double> batch_calc_profit_ratio(
    py::array_t<double> close_rates,
    double amount, double open_rate,
    double fee_open, double fee_close,
    bool is_short, double leverage,
    double funding_fees
) {
    auto cr = close_rates.unchecked<1>();
    ssize_t n = cr.shape(0);

    py::array_t<double> result(n);
    auto res = result.mutable_unchecked<1>();

    double open_value = calc_open_trade_value(amount, open_rate, fee_open, is_short);

    for (ssize_t i = 0; i < n; ++i) {
        double close_value = calc_close_trade_value(amount, cr(i), fee_close, is_short, funding_fees);
        double ratio;
        if (open_value == 0.0) {
            ratio = 0.0;
        } else if (is_short) {
            ratio = (1.0 - (close_value / open_value)) * leverage;
        } else {
            ratio = ((close_value / open_value) - 1.0) * leverage;
        }
        res(i) = round8(ratio);
    }
    return result;
}

// ─────────────────────────────────────────────────────────────────────
//  Recalculate trade from orders (replaces FtPrecise string math)
// ─────────────────────────────────────────────────────────────────────

struct RecalcResult {
    double open_rate;
    double amount;
    double stake_amount;
    double fee_open_cost;
    double max_stake_amount;
    double close_profit;
    double close_profit_abs;
    double realized_profit;
    double funding_fees;
    bool is_open;
};

/**
 * Recalculate trade from orders using native double math
 * instead of FtPrecise string-based arithmetic.
 *
 * order_amounts:         safe_amount_after_fee for each order
 * order_prices:          safe_price for each order
 * order_is_exit:         whether each order is an exit
 * order_filled:          whether each order was filled
 * order_is_open:         whether order is still open (ft_is_open)
 * order_funding_fees:    funding fee per order
 */
RecalcResult recalc_trade_from_orders(
    py::array_t<double> order_amounts,
    py::array_t<double> order_prices,
    py::array_t<bool> order_is_exit,
    py::array_t<bool> order_filled,
    py::array_t<bool> order_is_open,
    py::array_t<double> order_funding_fees,
    bool is_short,
    double fee_open,
    double fee_close,
    double leverage,
    bool is_closing
) {
    auto amounts = order_amounts.unchecked<1>();
    auto prices = order_prices.unchecked<1>();
    auto is_exit = order_is_exit.unchecked<1>();
    auto filled = order_filled.unchecked<1>();
    auto is_open = order_is_open.unchecked<1>();
    auto fund_fees = order_funding_fees.unchecked<1>();
    ssize_t n = amounts.shape(0);

    double current_amount = 0.0;
    double current_stake = 0.0;
    double max_stake = 0.0;
    double avg_price = 0.0;
    double total_stake = 0.0;
    double close_profit = 0.0;
    double close_profit_abs = 0.0;
    double funding_fees = 0.0;
    ssize_t ordercount = n - 1;

    for (ssize_t i = 0; i < n; ++i) {
        if (is_open(i) || !filled(i)) continue;

        funding_fees += fund_fees(i);

        double tmp_amount = amounts(i);
        double tmp_price = prices(i);
        bool exit_order = is_exit(i);
        double side = exit_order ? -1.0 : 1.0;

        if (tmp_amount > 0.0) {
            double price = exit_order ? avg_price : tmp_price;
            current_amount += tmp_amount * side;
            current_stake += price * tmp_amount * side;

            if (current_amount > 0.0 && !exit_order) {
                avg_price = current_stake / current_amount;
            }
        }

        if (exit_order) {
            double exit_rate = tmp_price;
            double exit_amount = tmp_amount;
            // Calculate profit for this exit
            double open_value = calc_open_trade_value(exit_amount, avg_price, fee_open, is_short);
            double close_value = calc_close_trade_value(exit_amount, exit_rate, fee_close, is_short,
                                                        (i == ordercount && is_closing) ? funding_fees : 0.0);
            double prof;
            if (is_short) {
                prof = open_value - close_value;
            } else {
                prof = close_value - open_value;
            }
            close_profit_abs += round8(prof);

            if (total_stake > 0.0) {
                close_profit = (close_profit_abs / total_stake) * leverage;
            }
        } else {
            double open_val = calc_open_trade_value(tmp_amount, exit_order ? avg_price : tmp_price,
                                                    fee_open, is_short);
            total_stake += open_val;
            max_stake += tmp_amount * (exit_order ? avg_price : tmp_price);
        }
    }

    RecalcResult r;
    r.funding_fees = funding_fees;
    r.max_stake_amount = (leverage > 0.0) ? max_stake / leverage : max_stake;
    r.close_profit = close_profit;
    r.close_profit_abs = close_profit_abs;
    r.realized_profit = close_profit_abs;

    if (current_amount > 0.0) {
        r.open_rate = current_stake / current_amount;
        r.amount = current_amount;
        r.stake_amount = (leverage > 0.0) ? current_stake / leverage : current_stake;
        r.fee_open_cost = fee_open * max_stake;
        r.is_open = true;
    } else {
        r.open_rate = 0.0;
        r.amount = 0.0;
        r.stake_amount = 0.0;
        r.fee_open_cost = 0.0;
        r.is_open = false;
    }

    return r;
}

}  // namespace trade_math


void register_trade_math(py::module_& m) {
    auto tm = m.def_submodule("trade_math", "Fast trade profit/loss calculations");

    py::class_<trade_math::ProfitResult>(tm, "ProfitResult")
        .def_readonly("profit_abs", &trade_math::ProfitResult::profit_abs)
        .def_readonly("profit_ratio", &trade_math::ProfitResult::profit_ratio)
        .def_readonly("total_profit", &trade_math::ProfitResult::total_profit)
        .def_readonly("total_profit_ratio", &trade_math::ProfitResult::total_profit_ratio);

    py::class_<trade_math::RecalcResult>(tm, "RecalcResult")
        .def_readonly("open_rate", &trade_math::RecalcResult::open_rate)
        .def_readonly("amount", &trade_math::RecalcResult::amount)
        .def_readonly("stake_amount", &trade_math::RecalcResult::stake_amount)
        .def_readonly("fee_open_cost", &trade_math::RecalcResult::fee_open_cost)
        .def_readonly("max_stake_amount", &trade_math::RecalcResult::max_stake_amount)
        .def_readonly("close_profit", &trade_math::RecalcResult::close_profit)
        .def_readonly("close_profit_abs", &trade_math::RecalcResult::close_profit_abs)
        .def_readonly("realized_profit", &trade_math::RecalcResult::realized_profit)
        .def_readonly("funding_fees", &trade_math::RecalcResult::funding_fees)
        .def_readonly("is_open", &trade_math::RecalcResult::is_open);

    tm.def("calc_open_trade_value", &trade_math::calc_open_trade_value,
           py::arg("amount"), py::arg("open_rate"), py::arg("fee_open"), py::arg("is_short"));

    tm.def("calc_close_trade_value", &trade_math::calc_close_trade_value,
           py::arg("amount"), py::arg("close_rate"), py::arg("fee_close"),
           py::arg("is_short"), py::arg("funding_fees") = 0.0);

    tm.def("calculate_profit", &trade_math::calculate_profit,
           py::arg("open_trade_value"), py::arg("close_trade_value"),
           py::arg("is_short"), py::arg("leverage"),
           py::arg("realized_profit"), py::arg("max_stake_amount"),
           py::arg("fee_open"));

    tm.def("calc_profit_ratio", &trade_math::calc_profit_ratio,
           py::arg("close_trade_value"), py::arg("open_trade_value"),
           py::arg("is_short"), py::arg("leverage"));

    tm.def("calc_close_rate_for_roi", &trade_math::calc_close_rate_for_roi,
           py::arg("target_roi"), py::arg("leverage"), py::arg("is_short"),
           py::arg("amount"), py::arg("open_rate"),
           py::arg("fee_open"), py::arg("fee_close"),
           py::arg("funding_fees") = 0.0);

    tm.def("batch_calc_profit_ratio", &trade_math::batch_calc_profit_ratio,
           py::arg("close_rates"), py::arg("amount"), py::arg("open_rate"),
           py::arg("fee_open"), py::arg("fee_close"),
           py::arg("is_short"), py::arg("leverage"),
           py::arg("funding_fees") = 0.0);

    tm.def("recalc_trade_from_orders", &trade_math::recalc_trade_from_orders,
           py::arg("order_amounts"), py::arg("order_prices"),
           py::arg("order_is_exit"), py::arg("order_filled"),
           py::arg("order_is_open"), py::arg("order_funding_fees"),
           py::arg("is_short"), py::arg("fee_open"), py::arg("fee_close"),
           py::arg("leverage"), py::arg("is_closing") = false);
}
