/**
 * Data processing module — fast FreqAI feature engineering and NaN filtering.
 *
 * Targets:
 *   - filter_features()                     (data_kitchen.py:213-299)
 *   - populate_features() shift/concat      (data_kitchen.py:765-770)
 *   - backtesting_fit_live_predictions()     (freqai_interface.py:892-911)
 *   - reduce_dataframe_footprint()          (converter.py:280-301)
 */

#include "common.h"
#include <cstring>

namespace data_processing {

// ─────────────────────────────────────────────────────────────────────
//  NaN filtering (replaces pd.isnull().any(axis=1) + boolean indexing)
// ─────────────────────────────────────────────────────────────────────

/**
 * Create a boolean mask indicating rows with NO NaN values.
 * Input: 2D array [n_rows, n_cols] (float64)
 * Output: 1D boolean array [n_rows] — true = row is clean (no NaN)
 *
 * Replaces: pd.isnull(filtered_df).any(axis=1) chain in filter_features()
 */
py::array_t<bool> nan_mask(py::array_t<double> data) {
    auto buf = data.unchecked<2>();
    ssize_t n_rows = buf.shape(0);
    ssize_t n_cols = buf.shape(1);

    py::array_t<bool> result(n_rows);
    auto res = result.mutable_unchecked<1>();

    for (ssize_t i = 0; i < n_rows; ++i) {
        bool clean = true;
        for (ssize_t j = 0; j < n_cols; ++j) {
            double v = buf(i, j);
            if (std::isnan(v) || std::isinf(v)) {
                clean = false;
                break;
            }
        }
        res(i) = clean;
    }
    return result;
}

/**
 * Combined NaN mask for features AND labels.
 * Returns mask where both feature row and label row have no NaN/inf.
 */
py::array_t<bool> combined_nan_mask(
    py::array_t<double> features,
    py::array_t<double> labels
) {
    auto feat = features.unchecked<2>();
    auto lab = labels.unchecked<2>();
    ssize_t n_rows = feat.shape(0);
    ssize_t n_feat_cols = feat.shape(1);
    ssize_t n_lab_cols = lab.shape(1);

    py::array_t<bool> result(n_rows);
    auto res = result.mutable_unchecked<1>();

    for (ssize_t i = 0; i < n_rows; ++i) {
        bool clean = true;
        for (ssize_t j = 0; j < n_feat_cols; ++j) {
            double v = feat(i, j);
            if (std::isnan(v) || std::isinf(v)) { clean = false; break; }
        }
        if (clean) {
            for (ssize_t j = 0; j < n_lab_cols; ++j) {
                double v = lab(i, j);
                if (std::isnan(v) || std::isinf(v)) { clean = false; break; }
            }
        }
        res(i) = clean;
    }
    return result;
}

/**
 * Count NaN values per column.
 * Useful for finding the worst indicator.
 */
py::array_t<int64_t> nan_count_per_column(py::array_t<double> data) {
    auto buf = data.unchecked<2>();
    ssize_t n_rows = buf.shape(0);
    ssize_t n_cols = buf.shape(1);

    py::array_t<int64_t> result(n_cols);
    auto res = result.mutable_unchecked<1>();

    for (ssize_t j = 0; j < n_cols; ++j) {
        int64_t count = 0;
        for (ssize_t i = 0; i < n_rows; ++i) {
            double v = buf(i, j);
            if (std::isnan(v) || std::isinf(v)) count++;
        }
        res(j) = count;
    }
    return result;
}

// ─────────────────────────────────────────────────────────────────────
//  Feature shifting (replaces DataFrame.shift(n) + concat in loop)
// ─────────────────────────────────────────────────────────────────────

/**
 * Shift columns and concatenate for multiple shift values.
 * Input: 2D array [n_rows, n_feature_cols]
 * shifts: list of shift amounts [1, 2, 3, ...]
 * Output: 2D array [n_rows, n_feature_cols * len(shifts)]
 *
 * Replaces the loop at data_kitchen.py:765-770:
 *   for n in range(...):
 *       df_shift = informative_df[indicators].shift(n)
 *       informative_df = pd.concat((informative_df, df_shift), axis=1)
 */
py::array_t<double> shift_features(
    py::array_t<double> data,
    std::vector<int> shifts
) {
    auto buf = data.unchecked<2>();
    ssize_t n_rows = buf.shape(0);
    ssize_t n_cols = buf.shape(1);
    ssize_t n_shifts = static_cast<ssize_t>(shifts.size());

    py::array_t<double> result({n_rows, n_cols * n_shifts});
    auto res = result.mutable_unchecked<2>();

    for (ssize_t s = 0; s < n_shifts; ++s) {
        int shift = shifts[s];
        ssize_t col_offset = s * n_cols;

        for (ssize_t i = 0; i < n_rows; ++i) {
            ssize_t src_row = i - shift;
            for (ssize_t j = 0; j < n_cols; ++j) {
                if (src_row < 0 || src_row >= n_rows) {
                    res(i, col_offset + j) = std::numeric_limits<double>::quiet_NaN();
                } else {
                    res(i, col_offset + j) = buf(src_row, j);
                }
            }
        }
    }
    return result;
}

// ─────────────────────────────────────────────────────────────────────
//  Fill NaN with zero (prediction mode)
// ─────────────────────────────────────────────────────────────────────

/**
 * Replace NaN/inf values with 0.0 in-place and return a do_predict mask.
 * Replaces: filtered_df.fillna(0, inplace=True) + do_predict logic
 */
py::array_t<int> fillna_and_predict_mask(py::array_t<double, py::array::c_style> data) {
    auto buf = data.mutable_unchecked<2>();
    ssize_t n_rows = buf.shape(0);
    ssize_t n_cols = buf.shape(1);

    py::array_t<int> do_predict(n_rows);
    auto pred = do_predict.mutable_unchecked<1>();

    for (ssize_t i = 0; i < n_rows; ++i) {
        bool has_nan = false;
        for (ssize_t j = 0; j < n_cols; ++j) {
            double v = buf(i, j);
            if (std::isnan(v) || std::isinf(v)) {
                buf(i, j) = 0.0;
                has_nan = true;
            }
        }
        pred(i) = has_nan ? 0 : 1;
    }
    return do_predict;
}

// ─────────────────────────────────────────────────────────────────────
//  Float64 → Float32 conversion (reduce_dataframe_footprint)
// ─────────────────────────────────────────────────────────────────────

/**
 * Convert float64 array to float32, returning the result.
 * Replaces: df.astype({'col': 'float32'}) for each column
 */
py::array_t<float> downcast_float64_to_float32(py::array_t<double> data) {
    auto buf = data.unchecked<2>();
    ssize_t n_rows = buf.shape(0);
    ssize_t n_cols = buf.shape(1);

    py::array_t<float> result({n_rows, n_cols});
    auto res = result.mutable_unchecked<2>();

    for (ssize_t i = 0; i < n_rows; ++i) {
        for (ssize_t j = 0; j < n_cols; ++j) {
            res(i, j) = static_cast<float>(buf(i, j));
        }
    }
    return result;
}

}  // namespace data_processing


void register_data_processing(py::module_& m) {
    auto dp = m.def_submodule("data_processing", "Fast data processing for FreqAI");

    dp.def("nan_mask", &data_processing::nan_mask,
           py::arg("data"),
           "Return boolean mask: True for rows with NO NaN/inf values.");

    dp.def("combined_nan_mask", &data_processing::combined_nan_mask,
           py::arg("features"), py::arg("labels"),
           "Return boolean mask: True where both feature and label rows are clean.");

    dp.def("nan_count_per_column", &data_processing::nan_count_per_column,
           py::arg("data"),
           "Count NaN/inf values per column.");

    dp.def("shift_features", &data_processing::shift_features,
           py::arg("data"), py::arg("shifts"),
           "Shift feature columns by multiple amounts and concatenate horizontally.");

    dp.def("fillna_and_predict_mask", &data_processing::fillna_and_predict_mask,
           py::arg("data"),
           "Fill NaN/inf with 0 in-place and return do_predict mask (1=clean, 0=had NaN).");

    dp.def("downcast_float64_to_float32", &data_processing::downcast_float64_to_float32,
           py::arg("data"),
           "Convert float64 2D array to float32.");
}
