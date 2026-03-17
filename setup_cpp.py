"""
Build script for the Freqtrade C++ extension module (_ft_cpp).

Usage:
    pip install -e ".[cpp]"
    # or
    python setup_cpp.py build_ext --inplace
"""

import os
import sys

from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup


cpp_dir = os.path.join(os.path.dirname(__file__), "freqtrade", "cpp")

ext_modules = [
    Pybind11Extension(
        "freqtrade._ft_cpp",
        sources=[
            os.path.join(cpp_dir, "src", "module.cpp"),
            os.path.join(cpp_dir, "src", "backtesting_engine.cpp"),
            os.path.join(cpp_dir, "src", "trade_math.cpp"),
            os.path.join(cpp_dir, "src", "data_processing.cpp"),
            os.path.join(cpp_dir, "src", "report_gen.cpp"),
            os.path.join(cpp_dir, "src", "orderflow.cpp"),
            os.path.join(cpp_dir, "src", "indicators.cpp"),
        ],
        include_dirs=[os.path.join(cpp_dir, "include")],
        cxx_std=17,
        extra_compile_args=["-O3"],
    ),
]

setup(
    name="freqtrade-cpp",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
)
