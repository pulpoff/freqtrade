/**
 * Orderflow module — fast trade aggregation into volume profiles.
 *
 * Targets:
 *   - trades_to_volumeprofile_with_total_delta_bid_ask() (orderflow.py:191-218)
 *   - trades_orderflow_to_imbalances()                   (orderflow.py:221-242)
 *   - stacked_imbalance()                                (orderflow.py:245-265)
 *   - Per-candle bid/ask/delta aggregation               (orderflow.py:161-177)
 */

#include "common.h"

namespace orderflow {

// ─────────────────────────────────────────────────────────────────────
//  Volume profile aggregation
// ─────────────────────────────────────────────────────────────────────

struct VolumeLevel {
    double price;
    double bid_amount;
    double ask_amount;
    int bid_count;
    int ask_count;
    double delta;
    double total_volume;
    int total_trades;
};

/**
 * Aggregate trades into volume profile (price levels binned by scale).
 *
 * prices:     trade prices
 * amounts:    trade amounts
 * is_sell:    boolean array (true = sell/bid, false = buy/ask)
 * scale:      price bin size (e.g., 0.5)
 *
 * Returns vector of VolumeLevel structs sorted by price.
 * Replaces trades_to_volumeprofile_with_total_delta_bid_ask().
 */
std::vector<VolumeLevel> volume_profile(
    py::array_t<double> prices,
    py::array_t<double> amounts,
    py::array_t<bool> is_sell,
    double scale
) {
    auto p = prices.unchecked<1>();
    auto a = amounts.unchecked<1>();
    auto s = is_sell.unchecked<1>();
    ssize_t n = p.shape(0);

    // Accumulate into price bins
    std::unordered_map<int64_t, VolumeLevel> bins;

    for (ssize_t i = 0; i < n; ++i) {
        // Round price to nearest scale multiple
        double binned_price = std::round(p(i) / scale) * scale;
        int64_t key = static_cast<int64_t>(std::round(binned_price * 1e8));  // avoid float key issues

        auto& level = bins[key];
        level.price = binned_price;

        if (s(i)) {
            level.bid_amount += a(i);
            level.bid_count++;
        } else {
            level.ask_amount += a(i);
            level.ask_count++;
        }
    }

    // Finalize and collect
    std::vector<VolumeLevel> result;
    result.reserve(bins.size());

    for (auto& [key, level] : bins) {
        level.delta = level.ask_amount - level.bid_amount;
        level.total_volume = level.ask_amount + level.bid_amount;
        level.total_trades = level.ask_count + level.bid_count;
        result.push_back(level);
    }

    // Sort by price
    std::sort(result.begin(), result.end(),
              [](const VolumeLevel& a, const VolumeLevel& b) { return a.price < b.price; });

    return result;
}

// ─────────────────────────────────────────────────────────────────────
//  Imbalance detection
// ─────────────────────────────────────────────────────────────────────

struct ImbalanceLevel {
    double price;
    bool bid_imbalance;
    bool ask_imbalance;
};

/**
 * Detect bid/ask imbalances from volume profile.
 *
 * levels:           volume profile sorted by price
 * imbalance_ratio:  minimum ratio for imbalance (e.g., 3.0)
 * imbalance_volume: minimum volume threshold
 *
 * Replaces trades_orderflow_to_imbalances() — compares diagonally
 * (bid at level N vs ask at level N+1).
 */
std::vector<ImbalanceLevel> detect_imbalances(
    const std::vector<VolumeLevel>& levels,
    double imbalance_ratio,
    double imbalance_volume
) {
    ssize_t n = static_cast<ssize_t>(levels.size());
    std::vector<ImbalanceLevel> result(n);

    for (ssize_t i = 0; i < n; ++i) {
        result[i].price = levels[i].price;
        result[i].bid_imbalance = false;
        result[i].ask_imbalance = false;

        if (levels[i].total_volume < imbalance_volume) continue;

        if (i + 1 < n) {
            double bid = levels[i].bid_amount;
            double ask_next = levels[i + 1].ask_amount;

            // Bid imbalance: bid[i] / ask[i+1] > ratio
            if (ask_next > 0.0 && (bid / ask_next) > imbalance_ratio) {
                result[i].bid_imbalance = true;
            }
            // Ask imbalance: ask[i+1] / bid[i] > ratio
            if (bid > 0.0 && (ask_next / bid) > imbalance_ratio) {
                result[i].ask_imbalance = true;
            }
        }
    }
    return result;
}

// ─────────────────────────────────────────────────────────────────────
//  Stacked imbalance detection
// ─────────────────────────────────────────────────────────────────────

/**
 * Find stacked imbalances (consecutive imbalance levels).
 *
 * imbalances:              vector of ImbalanceLevel
 * use_bid:                 true = check bid_imbalance, false = check ask_imbalance
 * stacked_imbalance_range: minimum consecutive count
 *
 * Returns vector of starting price levels where stacked imbalances occur.
 */
std::vector<double> find_stacked_imbalances(
    const std::vector<ImbalanceLevel>& imbalances,
    bool use_bid,
    int stacked_imbalance_range
) {
    ssize_t n = static_cast<ssize_t>(imbalances.size());
    std::vector<double> result;

    int consecutive = 0;
    for (ssize_t i = 0; i < n; ++i) {
        bool has_imbalance = use_bid ? imbalances[i].bid_imbalance : imbalances[i].ask_imbalance;

        if (has_imbalance) {
            consecutive++;
            if (consecutive >= stacked_imbalance_range) {
                // Return the starting price of the stacked range
                ssize_t start_idx = i - (stacked_imbalance_range - 1);
                if (start_idx >= 0) {
                    result.push_back(imbalances[start_idx].price);
                }
            }
        } else {
            consecutive = 0;
        }
    }
    return result;
}

// ─────────────────────────────────────────────────────────────────────
//  Per-candle bid/ask/delta aggregation
// ─────────────────────────────────────────────────────────────────────

struct CandleAggregation {
    double bid_sum;
    double ask_sum;
    double delta;
    double max_delta;
    double min_delta;
    int total_trades;
};

/**
 * Aggregate trades for a single candle into bid/ask/delta.
 * Replaces the per-candle aggregation at orderflow.py:161-177.
 */
CandleAggregation aggregate_candle_trades(
    py::array_t<double> amounts,
    py::array_t<bool> is_sell
) {
    auto a = amounts.unchecked<1>();
    auto s = is_sell.unchecked<1>();
    ssize_t n = a.shape(0);

    CandleAggregation result = {0.0, 0.0, 0.0, 0.0, 0.0, static_cast<int>(n)};
    double cumulative_delta = 0.0;

    for (ssize_t i = 0; i < n; ++i) {
        double bid = s(i) ? a(i) : 0.0;
        double ask = s(i) ? 0.0 : a(i);
        result.bid_sum += bid;
        result.ask_sum += ask;

        cumulative_delta += (ask - bid);
        if (cumulative_delta > result.max_delta) result.max_delta = cumulative_delta;
        if (cumulative_delta < result.min_delta) result.min_delta = cumulative_delta;
    }
    result.delta = result.ask_sum - result.bid_sum;
    return result;
}

}  // namespace orderflow


void register_orderflow(py::module_& m) {
    auto of = m.def_submodule("orderflow", "Fast orderflow analysis");

    py::class_<orderflow::VolumeLevel>(of, "VolumeLevel")
        .def_readonly("price", &orderflow::VolumeLevel::price)
        .def_readonly("bid_amount", &orderflow::VolumeLevel::bid_amount)
        .def_readonly("ask_amount", &orderflow::VolumeLevel::ask_amount)
        .def_readonly("bid_count", &orderflow::VolumeLevel::bid_count)
        .def_readonly("ask_count", &orderflow::VolumeLevel::ask_count)
        .def_readonly("delta", &orderflow::VolumeLevel::delta)
        .def_readonly("total_volume", &orderflow::VolumeLevel::total_volume)
        .def_readonly("total_trades", &orderflow::VolumeLevel::total_trades);

    py::class_<orderflow::ImbalanceLevel>(of, "ImbalanceLevel")
        .def_readonly("price", &orderflow::ImbalanceLevel::price)
        .def_readonly("bid_imbalance", &orderflow::ImbalanceLevel::bid_imbalance)
        .def_readonly("ask_imbalance", &orderflow::ImbalanceLevel::ask_imbalance);

    py::class_<orderflow::CandleAggregation>(of, "CandleAggregation")
        .def_readonly("bid_sum", &orderflow::CandleAggregation::bid_sum)
        .def_readonly("ask_sum", &orderflow::CandleAggregation::ask_sum)
        .def_readonly("delta", &orderflow::CandleAggregation::delta)
        .def_readonly("max_delta", &orderflow::CandleAggregation::max_delta)
        .def_readonly("min_delta", &orderflow::CandleAggregation::min_delta)
        .def_readonly("total_trades", &orderflow::CandleAggregation::total_trades);

    of.def("volume_profile", &orderflow::volume_profile,
           py::arg("prices"), py::arg("amounts"), py::arg("is_sell"), py::arg("scale"),
           "Aggregate trades into binned volume profile.");

    of.def("detect_imbalances", &orderflow::detect_imbalances,
           py::arg("levels"), py::arg("imbalance_ratio"), py::arg("imbalance_volume"),
           "Detect bid/ask imbalances from volume profile (diagonal comparison).");

    of.def("find_stacked_imbalances", &orderflow::find_stacked_imbalances,
           py::arg("imbalances"), py::arg("use_bid"), py::arg("stacked_imbalance_range"),
           "Find stacked (consecutive) imbalances.");

    of.def("aggregate_candle_trades", &orderflow::aggregate_candle_trades,
           py::arg("amounts"), py::arg("is_sell"),
           "Aggregate bid/ask/delta for a single candle's trades.");
}
