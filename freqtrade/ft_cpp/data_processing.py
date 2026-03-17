"""
Python wrapper for C++ data processing functions with pure-Python fallback.
"""

import numpy as np

from freqtrade.ft_cpp import HAS_CPP


if HAS_CPP:
    from freqtrade._ft_cpp.data_processing import (  # noqa: F401
        combined_nan_mask,
        downcast_float64_to_float32,
        fillna_and_predict_mask,
        nan_count_per_column,
        nan_mask,
        shift_features,
    )
else:

    def nan_mask(data):
        arr = np.asarray(data)
        return ~np.any(np.isnan(arr) | np.isinf(arr), axis=1)

    def combined_nan_mask(features, labels):
        feat_clean = ~np.any(np.isnan(features) | np.isinf(features), axis=1)
        lab_clean = ~np.any(np.isnan(labels) | np.isinf(labels), axis=1)
        return feat_clean & lab_clean

    def nan_count_per_column(data):
        arr = np.asarray(data)
        return np.sum(np.isnan(arr) | np.isinf(arr), axis=0).astype(np.int64)

    def shift_features(data, shifts):
        arr = np.asarray(data)
        n_rows, n_cols = arr.shape
        parts = []
        for s in shifts:
            shifted = np.empty_like(arr)
            if s > 0:
                shifted[:s] = np.nan
                shifted[s:] = arr[:-s]
            elif s < 0:
                shifted[s:] = np.nan
                shifted[:s] = arr[-s:]
            else:
                shifted[:] = arr
            parts.append(shifted)
        return np.hstack(parts)

    def fillna_and_predict_mask(data):
        mask = np.isnan(data) | np.isinf(data)
        has_nan = np.any(mask, axis=1)
        data[mask] = 0.0
        return np.where(has_nan, 0, 1).astype(np.int32)

    def downcast_float64_to_float32(data):
        return np.asarray(data, dtype=np.float32)
