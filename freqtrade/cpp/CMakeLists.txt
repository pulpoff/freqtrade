cmake_minimum_required(VERSION 3.15)
project(_ft_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Optimization flags
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG -march=native")

find_package(pybind11 REQUIRED)

pybind11_add_module(_ft_cpp
    src/module.cpp
    src/backtesting_engine.cpp
    src/trade_math.cpp
    src/data_processing.cpp
    src/report_gen.cpp
    src/orderflow.cpp
    src/indicators.cpp
)

target_include_directories(_ft_cpp PRIVATE include)
