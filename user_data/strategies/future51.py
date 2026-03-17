from functools import reduce
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter
from skopt.space import Integer, Real, Categorical, Dimension

class future51(IStrategy):
  minimal_roi = {
      "0": 0.05,
      "20": 0.02,
      "30": 0.01,
      "40": 0,
      "60": -0.01
  }

  stoploss = -0.08
  trailing_stop = True
  trailing_stop_positive = 0.05
  trailing_stop_positive_offset = 0.07
  trailing_only_offset_is_reached = True

  use_exit_signal = True
  process_only_new_candles = True

  leverage_param = IntParameter(2, 10, default=5, space="buy", optimize=True)
  
  buy_rsi = IntParameter(30, 50, default=47, space="buy", optimize=True)
  sell_rsi_upper = IntParameter(60, 85, default=79, space="sell", optimize=True)
  sell_rsi_lower = IntParameter(20, 40, default=21, space="sell", optimize=True)
  
  macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
  macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
  macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
  
  ema_short_period = IntParameter(5, 15, default=8, space="both", optimize=True)
  ema_long_period = IntParameter(15, 30, default=21, space="both", optimize=True)
  
  price_extension_pct = DecimalParameter(0.003, 0.01, default=0.006, space="sell", optimize=True)
  
  quick_profit_target = DecimalParameter(0.01, 0.03, default=0.02, space="sell", optimize=True)
  medium_profit_target = DecimalParameter(0.008, 0.025, default=0.015, space="sell", optimize=True)
  longer_profit_target = DecimalParameter(0.005, 0.02, default=0.01, space="sell", optimize=True)
  
  exit_rsi_threshold = IntParameter(15, 30, default=20, space="sell", optimize=True)
  
  timeframe = '5m'
  
  entry_timeframe = CategoricalParameter(['5m', '15m', '30m'], default='5m', space='buy', optimize=True)
  
  startup_candle_count = 100
  can_short = True
  can_long = False

  atr_period = IntParameter(10, 25, default=14, space="both", optimize=True)
  atr_stop_multiplier = DecimalParameter(1.5, 4.0, default=2.5, space="sell", optimize=True)
  
  volatility_lookback = IntParameter(20, 100, default=50, space="both", optimize=True)
  
  adaptive_vol_stop_scaling = DecimalParameter(0.5, 2.0, default=1.0, space="sell", optimize=True)
  
  market_regime_threshold = IntParameter(90, 160, default=120, space="both", optimize=True)
  max_volatility_pct = DecimalParameter(0.5, 3.0, default=1.5, space="buy", optimize=True)

  _last_candle_seen_time = {}
  _coin_list = []
  _coin_parameters = {}
  _coin_roi = {}
  _coin_trailing_stop = {}
  _max_profits = {}
  _volatility_metrics = {}
  _market_regimes = {}
  
  freqai_config = {
      "enabled": True,
      "feature_parameters": {
          "include_timeframes": ["5m", "15m", "1h"],
          "include_corr_pairlist": [
              "ETH/USDT:USDT",
              "BTC/USDT:USDT"
          ],
          "label_period_candles": 20,
          "include_shifted_candles": 3,
          "DI_threshold": 0.0,
          "weight_factor": 0.9,
          "principal_component_analysis": False,
          "use_SVM_to_remove_outliers": True,
          "stratify_training_data": 0,
          "indicator_periods_candles": [3, 6, 12, 24, 48],
          "plot_feature_importances": 0,
      },
      "data_split_parameters": {
          "test_size": 0.25,
          "random_state": 1,
          "shuffle": True,
      },
      "feature_pipeline": {
          "random_state": 42,
          "outlier_protection_percentage": 30.0,
          "normalize_features": True,
          "fill_infinite_values": 0,
          "fill_nan_values": 0,
      },
      "model_training_parameters": {
          "n_estimators": 200,
          "lags": 12,
          "learning_rate": 0.01,
          "gamma": 0,
          "subsample": 0.7,
          "max_depth": 6,
          "verbosity": 0,
          "random_state": 0,
          "updatable": True,
          "conv_width": 8,
          "kernel_size": 3,
      },
      "threads": -1,
      "identifier": "future51",
      "live_retrain_hours": 0.5,
      "expiration_hours": 4,
      "activation": "sigmoid",
      "keras": False,
      "purge_old_models": False,
      "model_save_type": "joblib",
      "conv_width": 10,
  }

  def __init__(self, config: dict) -> None:
      super().__init__(config)
      self._last_candle_seen_time = {}
      self._coin_list = []
      self._coin_parameters = {}
      self._coin_roi = {}
      self._coin_trailing_stop = {}
      self._max_profits = {}
      self._volatility_metrics = {}
      self._market_regimes = {}
      
      if 'exchange' in config and 'pair_whitelist' in config['exchange']:
          for pair in config['exchange']['pair_whitelist']:
              coin = self.get_coin_from_pair(pair)
              if coin and coin not in self._coin_list:
                  self._coin_list.append(coin)
      
      self.initialize_coin_parameters()
      
  def initialize_coin_parameters(self):
      for coin in self._coin_list:
          self._coin_parameters[coin] = {}
          
          setattr(self, f"{coin}_leverage_param", IntParameter(1, 5, default=2, space="buy", optimize=True))
          self._coin_parameters[coin]['leverage_param'] = getattr(self, f"{coin}_leverage_param")
          
          setattr(self, f"{coin}_buy_rsi", IntParameter(40, 50, default=47, space="buy", optimize=True))
          self._coin_parameters[coin]['buy_rsi'] = getattr(self, f"{coin}_buy_rsi")
          
          setattr(self, f"{coin}_sell_rsi_upper", IntParameter(70, 85, default=79, space="sell", optimize=True))
          self._coin_parameters[coin]['sell_rsi_upper'] = getattr(self, f"{coin}_sell_rsi_upper")
          
          setattr(self, f"{coin}_sell_rsi_lower", IntParameter(20, 30, default=21, space="sell", optimize=True))
          self._coin_parameters[coin]['sell_rsi_lower'] = getattr(self, f"{coin}_sell_rsi_lower")
          
          setattr(self, f"{coin}_price_extension_pct", DecimalParameter(0.004, 0.008, default=0.006, space="sell", optimize=True))
          self._coin_parameters[coin]['price_extension_pct'] = getattr(self, f"{coin}_price_extension_pct")
          
          setattr(self, f"{coin}_macd_fast", IntParameter(8, 16, default=12, space="both", optimize=True))
          self._coin_parameters[coin]['macd_fast'] = getattr(self, f"{coin}_macd_fast")
          
          setattr(self, f"{coin}_macd_slow", IntParameter(18, 32, default=26, space="both", optimize=True))
          self._coin_parameters[coin]['macd_slow'] = getattr(self, f"{coin}_macd_slow")
          
          setattr(self, f"{coin}_macd_signal", IntParameter(6, 12, default=9, space="both", optimize=True))
          self._coin_parameters[coin]['macd_signal'] = getattr(self, f"{coin}_macd_signal")
          
          setattr(self, f"{coin}_ema_short_period", IntParameter(5, 15, default=8, space="both", optimize=True))
          self._coin_parameters[coin]['ema_short_period'] = getattr(self, f"{coin}_ema_short_period")
          
          setattr(self, f"{coin}_ema_long_period", IntParameter(15, 30, default=21, space="both", optimize=True))
          self._coin_parameters[coin]['ema_long_period'] = getattr(self, f"{coin}_ema_long_period")
          
          setattr(self, f"{coin}_entry_timeframe", CategoricalParameter(['5m', '15m'], default='5m', space='buy', optimize=True))
          self._coin_parameters[coin]['entry_timeframe'] = getattr(self, f"{coin}_entry_timeframe")
          
          setattr(self, f"{coin}_quick_profit_target", DecimalParameter(0.01, 0.03, default=0.02, space="sell", optimize=True))
          self._coin_parameters[coin]['quick_profit_target'] = getattr(self, f"{coin}_quick_profit_target")
          
          setattr(self, f"{coin}_medium_profit_target", DecimalParameter(0.008, 0.025, default=0.015, space="sell", optimize=True))
          self._coin_parameters[coin]['medium_profit_target'] = getattr(self, f"{coin}_medium_profit_target")
          
          setattr(self, f"{coin}_longer_profit_target", DecimalParameter(0.005, 0.02, default=0.01, space="sell", optimize=True))
          self._coin_parameters[coin]['longer_profit_target'] = getattr(self, f"{coin}_longer_profit_target")
          
          setattr(self, f"{coin}_exit_rsi_threshold", IntParameter(15, 30, default=20, space="sell", optimize=True))
          self._coin_parameters[coin]['exit_rsi_threshold'] = getattr(self, f"{coin}_exit_rsi_threshold")
          
          setattr(self, f"{coin}_atr_period", IntParameter(10, 25, default=14, space="both", optimize=True))
          self._coin_parameters[coin]['atr_period'] = getattr(self, f"{coin}_atr_period")
          
          setattr(self, f"{coin}_atr_stop_multiplier", DecimalParameter(1.5, 4.0, default=2.5, space="sell", optimize=True))
          self._coin_parameters[coin]['atr_stop_multiplier'] = getattr(self, f"{coin}_atr_stop_multiplier")
          
          setattr(self, f"{coin}_adaptive_vol_stop_scaling", DecimalParameter(0.5, 2.0, default=1.0, space="sell", optimize=True))
          self._coin_parameters[coin]['adaptive_vol_stop_scaling'] = getattr(self, f"{coin}_adaptive_vol_stop_scaling")
          
          setattr(self, f"{coin}_volatility_lookback", IntParameter(20, 100, default=50, space="both", optimize=True))
          self._coin_parameters[coin]['volatility_lookback'] = getattr(self, f"{coin}_volatility_lookback")
          
          setattr(self, f"{coin}_market_regime_threshold", IntParameter(90, 160, default=120, space="both", optimize=True))
          self._coin_parameters[coin]['market_regime_threshold'] = getattr(self, f"{coin}_market_regime_threshold")
          
          setattr(self, f"{coin}_max_volatility_pct", DecimalParameter(0.5, 3.0, default=1.5, space="buy", optimize=True))
          self._coin_parameters[coin]['max_volatility_pct'] = getattr(self, f"{coin}_max_volatility_pct")
          
          self._coin_roi[coin] = {}
          
          setattr(self, f"{coin}_roi_t1", IntParameter(1, 15, default=3, space="sell", optimize=True))
          self._coin_roi[coin]['t1'] = getattr(self, f"{coin}_roi_t1")
          
          setattr(self, f"{coin}_roi_t2", IntParameter(16, 40, default=15, space="sell", optimize=True))
          self._coin_roi[coin]['t2'] = getattr(self, f"{coin}_roi_t2")
          
          setattr(self, f"{coin}_roi_t3", IntParameter(41, 100, default=34, space="sell", optimize=True))
          self._coin_roi[coin]['t3'] = getattr(self, f"{coin}_roi_t3")
          
          setattr(self, f"{coin}_roi_p1", DecimalParameter(0.01, 0.05, default=0.02, space="sell", optimize=True))
          self._coin_roi[coin]['p1'] = getattr(self, f"{coin}_roi_p1")
          
          setattr(self, f"{coin}_roi_p2", DecimalParameter(0.005, 0.02, default=0.015, space="sell", optimize=True))
          self._coin_roi[coin]['p2'] = getattr(self, f"{coin}_roi_p2")
          
          setattr(self, f"{coin}_roi_p3", DecimalParameter(0.001, 0.01, default=0.007, space="sell", optimize=True))
          self._coin_roi[coin]['p3'] = getattr(self, f"{coin}_roi_p3")
          
          self._coin_trailing_stop[coin] = {}
          
          setattr(self, f"{coin}_trailing_stop", CategoricalParameter([True, False], default=True, space="sell", optimize=True))
          self._coin_trailing_stop[coin]['trailing_stop'] = getattr(self, f"{coin}_trailing_stop")
          
          setattr(self, f"{coin}_trailing_stop_positive", DecimalParameter(0.01, 0.35, default=0.16, space="sell", optimize=True))
          self._coin_trailing_stop[coin]['trailing_stop_positive'] = getattr(self, f"{coin}_trailing_stop_positive")
          
          setattr(self, f"{coin}_trailing_stop_positive_offset", DecimalParameter(0.01, 0.35, default=0.213, space="sell", optimize=True))
          self._coin_trailing_stop[coin]['trailing_stop_positive_offset'] = getattr(self, f"{coin}_trailing_stop_positive_offset")
          
          setattr(self, f"{coin}_trailing_only_offset_is_reached", CategoricalParameter([True, False], default=True, space="sell", optimize=True))
          self._coin_trailing_stop[coin]['trailing_only_offset_is_reached'] = getattr(self, f"{coin}_trailing_only_offset_is_reached")
          
          setattr(self, f"{coin}_stoploss", DecimalParameter(-0.2, -0.01, default=-0.05, space="sell", optimize=True))
          self._coin_trailing_stop[coin]['stoploss'] = getattr(self, f"{coin}_stoploss")
  
  def get_coin_from_pair(self, pair: str) -> str:
      if '/' in pair:
          return pair.split('/')[0]
      return "UNKNOWN"
  
  def get_param_value(self, coin: str, param_name: str):
      if coin in self._coin_parameters and param_name in self._coin_parameters[coin]:
          return self._coin_parameters[coin][param_name].value
      
      if hasattr(self, param_name):
          return getattr(self, param_name).value
      
      defaults = {
          'leverage_param': 2,
          'buy_rsi': 47,
          'sell_rsi_upper': 79,
          'sell_rsi_lower': 21,
          'price_extension_pct': 0.006,
          'macd_fast': 12,
          'macd_slow': 26,
          'macd_signal': 9,
          'ema_short_period': 8,
          'ema_long_period': 21,
          'entry_timeframe': '5m',
          'quick_profit_target': 0.02,
          'medium_profit_target': 0.015,
          'longer_profit_target': 0.01,
          'exit_rsi_threshold': 20,
          'atr_period': 14,
          'atr_stop_multiplier': 2.5,
          'adaptive_vol_stop_scaling': 1.0,
          'volatility_lookback': 50,
          'market_regime_threshold': 120,
          'max_volatility_pct': 1.5
      }
      return defaults.get(param_name, 1.0)
  
  def get_roi_table_for_coin(self, coin: str) -> Dict[str, float]:
      if coin in self._coin_roi:
          t1 = int(self._coin_roi[coin]['t1'].value)
          t2 = int(self._coin_roi[coin]['t2'].value)
          t3 = int(self._coin_roi[coin]['t3'].value)
          
          p1 = float(self._coin_roi[coin]['p1'].value)
          p2 = float(self._coin_roi[coin]['p2'].value)
          p3 = float(self._coin_roi[coin]['p3'].value)
          
          return {
              "0": p1,
              str(t1): p2,
              str(t2): p3,
              str(t3): 0,
              str(t3+25): -0.01
          }
      
      return {
          "0": 0.02,
          "10": 0.015,
          "30": 0.007,
          "60": 0,
          "90": -0.01
      }
  
  def get_trailing_stop_for_coin(self, coin: str) -> Dict[str, Any]:
      if coin in self._coin_trailing_stop:
          return {
              'trailing_stop': self._coin_trailing_stop[coin]['trailing_stop'].value,
              'trailing_stop_positive': self._coin_trailing_stop[coin]['trailing_stop_positive'].value,
              'trailing_stop_positive_offset': self._coin_trailing_stop[coin]['trailing_stop_positive_offset'].value,
              'trailing_only_offset_is_reached': self._coin_trailing_stop[coin]['trailing_only_offset_is_reached'].value,
              'stoploss': self._coin_trailing_stop[coin]['stoploss'].value
          }
      
      return {
          'trailing_stop': self.trailing_stop,
          'trailing_stop_positive': self.trailing_stop_positive,
          'trailing_stop_positive_offset': self.trailing_stop_positive_offset,
          'trailing_only_offset_is_reached': self.trailing_only_offset_is_reached,
          'stoploss': self.stoploss
      }

  def informative_pairs(self):
      pairs = self.dp.current_whitelist()
      informative_pairs = []
      
      for pair in pairs:
          informative_pairs.append((pair, '1m'))
          informative_pairs.append((pair, '1h'))
          informative_pairs.append((pair, '4h'))
          informative_pairs.append((pair, '1d'))
          
          coin = self.get_coin_from_pair(pair)
          if coin in self._coin_parameters and 'entry_timeframe' in self._coin_parameters[coin]:
              entry_tf = self._coin_parameters[coin]['entry_timeframe'].value
              if entry_tf != self.timeframe:
                  informative_pairs.append((pair, entry_tf))
      
      return informative_pairs

  def feature_engineering_expand_all(self, dataframe: DataFrame, period: int, metadata: dict) -> DataFrame:
     coin = self.get_coin_from_pair(metadata['pair'])
     
     ema_short_period = int(self.get_param_value(coin, 'ema_short_period'))
     ema_long_period = int(self.get_param_value(coin, 'ema_long_period'))
     macd_fast = int(self.get_param_value(coin, 'macd_fast'))
     macd_slow = int(self.get_param_value(coin, 'macd_slow'))
     macd_signal = int(self.get_param_value(coin, 'macd_signal'))
     atr_period = int(self.get_param_value(coin, 'atr_period'))
     volatility_lookback = int(self.get_param_value(coin, 'volatility_lookback'))
     
     dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
     dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=ema_short_period)
     dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=ema_long_period)
     
     macd = ta.MACD(dataframe, 
                  fastperiod=macd_fast,
                  slowperiod=macd_slow, 
                  signalperiod=macd_signal)
     dataframe['macd'] = macd['macd']
     dataframe['macdsignal'] = macd['macdsignal']
     dataframe['macdhist'] = macd['macdhist']
     
     dataframe['price_change'] = dataframe['close'].pct_change()
     dataframe['volatility'] = dataframe['close'].rolling(14).std()
     
     dataframe['dist_from_ema_short'] = (dataframe['close'] / dataframe['ema_short']) - 1
     dataframe['dist_from_ema_long'] = (dataframe['close'] / dataframe['ema_long']) - 1
     
     dataframe['volume_change'] = dataframe['volume'].pct_change()
     
     bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
     dataframe['bb_upperband'] = bollinger['upper']
     dataframe['bb_middleband'] = bollinger['mid']
     dataframe['bb_lowerband'] = bollinger['lower']
     dataframe['bb_width'] = (bollinger['upper'] - bollinger['lower']) / bollinger['mid']
     dataframe['bb_pct'] = (dataframe['close'] - bollinger['lower']) / (bollinger['upper'] - bollinger['lower'])
     
     dataframe['market_trend'] = (dataframe['close'] > dataframe['ema_long']).astype(float)
     dataframe['trend_strength'] = abs(dataframe['dist_from_ema_long'])
     
     dataframe['price_peak'] = ((dataframe['high'] > dataframe['high'].shift(1)) & 
                               (dataframe['high'] > dataframe['high'].shift(-1))).astype(float)
     
     dataframe['price_valley'] = ((dataframe['low'] < dataframe['low'].shift(1)) & 
                                (dataframe['low'] < dataframe['low'].shift(-1))).astype(float)
     
     dataframe['hlc3'] = (dataframe['high'] + dataframe['low'] + dataframe['close']) / 3
     
     dataframe['atr'] = ta.ATR(dataframe, timeperiod=atr_period)
     
     dataframe['historical_volatility'] = dataframe['close'].pct_change().rolling(volatility_lookback).std() * np.sqrt(365 * 24 * (60 / self.timeframe_to_minutes(self.timeframe)))
     
     dataframe['daily_range_pct'] = (dataframe['high'] - dataframe['low']) / dataframe['low']
     dataframe['daily_range_pct_ma'] = dataframe['daily_range_pct'].rolling(volatility_lookback).mean()
     
     dataframe['price_momentum'] = dataframe['close'].pct_change(3)
     dataframe['volume_momentum'] = dataframe['volume'].pct_change(3)
     dataframe['rsi_momentum'] = dataframe['rsi'].diff(3)
     
     dataframe['macd_cross'] = (dataframe['macd'] > dataframe['macdsignal']).astype(float)
     dataframe['macd_above_zero'] = (ataframe['macd'] > 0).astype(float)
     
     dataframe['ema_cross'] = (dataframe['ema_short'] > dataframe['ema_long']).astype(float)
     
     dataframe['close_above_ema_short'] = (dataframe['close'] > dataframe['ema_short']).astype(float)
     dataframe['close_above_ema_long'] = (dataframe['close'] > dataframe['ema_long']).astype(float)
     
     for period in [3, 6, 12, 24]:
         dataframe[f'rsi_sma_{period}'] = dataframe['rsi'].rolling(period).mean()
         dataframe[f'volume_sma_{period}'] = dataframe['volume'].rolling(period).mean()
         dataframe[f'close_sma_{period}'] = dataframe['close'].rolling(period).mean()
     
     for period in [3, 6, 12]:
         dataframe[f'close_change_{period}'] = dataframe['close'].pct_change(period)
         dataframe[f'volume_change_{period}'] = dataframe['volume'].pct_change(period)
         dataframe[f'rsi_change_{period}'] = dataframe['rsi'].diff(period)
     
     for i in range(1, 4):
         dataframe[f'close_shift_{i}'] = dataframe['close'].shift(i)
         dataframe[f'high_shift_{i}'] = dataframe['high'].shift(i)
         dataframe[f'low_shift_{i}'] = dataframe['low'].shift(i)
         dataframe[f'volume_shift_{i}'] = dataframe['volume'].shift(i)
         dataframe[f'rsi_shift_{i}'] = dataframe['rsi'].shift(i)
     
     return dataframe
     
  def feature_engineering_expand_basic(self, dataframe: DataFrame, period: int, metadata: dict) -> DataFrame:
     dataframe['hour'] = dataframe['date'].dt.hour
     dataframe['day_of_week'] = dataframe['date'].dt.dayofweek
     
     for window in [5, 10, 20]:
         dataframe[f'return_{window}'] = dataframe['close'].pct_change(window)
         dataframe[f'volatility_{window}'] = dataframe['close'].rolling(window).std()
         
     for n in range(1, 5):
         dataframe[f'close_shift_{n}'] = dataframe['close'].shift(n)
         dataframe[f'volume_shift_{n}'] = dataframe['volume'].shift(n)
         dataframe[f'rsi_shift_{n}'] = dataframe['rsi'].shift(n)
         
     return dataframe

  def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
     coin = self.get_coin_from_pair(metadata['pair'])
     
     sell_rsi_upper = float(self.get_param_value(coin, 'sell_rsi_upper'))
     price_extension_pct = float(self.get_param_value(coin, 'price_extension_pct'))
     
     dataframe['high_last_3'] = dataframe['high'].rolling(3).max()
     
     # Create multiple target types for different patterns/scenarios
     
     # Target based on future price drop for short entries
     dataframe['future_price_5'] = dataframe['close'].shift(-5)
     dataframe['future_price_10'] = dataframe['close'].shift(-10)
     dataframe['future_price_20'] = dataframe['close'].shift(-20)
     
     dataframe['price_drop_5'] = (dataframe['future_price_5'] / dataframe['close']) - 1.0
     dataframe['price_drop_10'] = (dataframe['future_price_10'] / dataframe['close']) - 1.0
     dataframe['price_drop_20'] = (dataframe['future_price_20'] / dataframe['close']) - 1.0
     
     # Negative for price drops (better for shorts)
     dataframe['target_short_5'] = -1 * dataframe['price_drop_5']
     dataframe['target_short_10'] = -1 * dataframe['price_drop_10']
     dataframe['target_short_20'] = -1 * dataframe['price_drop_20']
     
     # Combined features for peak pattern detection
     dataframe['rsi_high'] = (dataframe['rsi'] > sell_rsi_upper).astype(float)
     dataframe['price_extended'] = (dataframe['close'] > dataframe['ema_short'] * (1 + price_extension_pct)).astype(float)
     dataframe['local_high'] = (dataframe['high'] >= dataframe['high_last_3'] * 0.995).astype(float)
     
     # Create binary targets based on the patterns
     price_peak = (
         (dataframe['high'] >= dataframe['high_last_3'] * 0.995) &
         (dataframe['high'] > dataframe['high'].shift(1)) &
         (dataframe['close'] > dataframe['ema_short']) &
         (dataframe['rsi'] > sell_rsi_upper)
     )
     
     price_reversal = (
         (dataframe['close'].shift(2) < dataframe['close'].shift(1)) &
         (dataframe['close'] < dataframe['close'].shift(1)) &
         (dataframe['close'].shift(1) > dataframe['close'].shift(1).rolling(3).max().shift(1)) &
         (dataframe['rsi'] > sell_rsi_upper * 0.9)
     )
     
     macd_reversal = (
         (dataframe['macdhist'].shift(2) < dataframe['macdhist'].shift(1)) &
         (dataframe['macdhist'] < dataframe['macdhist'].shift(1)) &
         (dataframe['macdhist'].shift(1) > 0) &
         (dataframe['close'] > dataframe['ema_short'])
     )
     
     # Define multiple targets for pattern
     dataframe['target_peak_pattern'] = price_peak.astype(float)
     dataframe['target_reversal_pattern'] = price_reversal.astype(float)
     dataframe['target_macd_pattern'] = macd_reversal.astype(float)
     
     # Create composite target score
     dataframe['composite_pattern_score'] = (
         dataframe['target_peak_pattern'] * 0.4 + 
         dataframe['target_reversal_pattern'] * 0.3 + 
         dataframe['target_macd_pattern'] * 0.3
     )
     
     # Combine all information into a final target
     dataframe['target'] = (
         dataframe['target_short_20'] * 0.6 + 
         dataframe['composite_pattern_score'] * 0.4
     )
     
     # Clip the target values
     dataframe['target'] = dataframe['target'].clip(0, 1)
     
     # Add historical signal information for backtesting comparison
     entry_signal = (
         (price_peak | price_reversal | macd_reversal) &
         (dataframe['rsi'] > sell_rsi_upper * 0.9) &
         (dataframe['close'] > dataframe['ema_short'] * (1 + price_extension_pct))
     )
     
     dataframe['historical_signal'] = entry_signal.astype(int)
     
     # Additional targets for market regime and volatility
     dataframe['market_trend_target'] = (dataframe['close'].shift(-10) < dataframe['close']).astype(float)
     
     dataframe['volatility_feature'] = dataframe['atr'] / dataframe['close']
     dataframe['volatility_regime'] = dataframe['historical_volatility'].rolling(10).mean() / dataframe['historical_volatility'].rolling(60).mean()
     
     return dataframe

  def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
     coin = self.get_coin_from_pair(metadata['pair'])
     
     ema_short_period = int(self.get_param_value(coin, 'ema_short_period'))
     ema_long_period = int(self.get_param_value(coin, 'ema_long_period'))
     macd_fast = int(self.get_param_value(coin, 'macd_fast'))
     macd_slow = int(self.get_param_value(coin, 'macd_slow'))
     macd_signal = int(self.get_param_value(coin, 'macd_signal'))
     sell_rsi_upper = float(self.get_param_value(coin, 'sell_rsi_upper'))
     sell_rsi_lower = float(self.get_param_value(coin, 'sell_rsi_lower'))
     price_extension_pct = float(self.get_param_value(coin, 'price_extension_pct'))
     exit_rsi_threshold = int(self.get_param_value(coin, 'exit_rsi_threshold'))
     atr_period = int(self.get_param_value(coin, 'atr_period'))
     volatility_lookback = int(self.get_param_value(coin, 'volatility_lookback'))
     market_regime_threshold = int(self.get_param_value(coin, 'market_regime_threshold'))
     
     entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
     
     dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
     dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=ema_short_period)
     dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=ema_long_period)
     dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
     
     macd = ta.MACD(dataframe, 
                  fastperiod=macd_fast,
                  slowperiod=macd_slow, 
                  signalperiod=macd_signal)
     dataframe['macd'] = macd['macd']
     dataframe['macdsignal'] = macd['macdsignal']
     dataframe['macdhist'] = macd['macdhist']
     
     bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
     dataframe['bb_upperband'] = bollinger['upper']
     dataframe['bb_middleband'] = bollinger['mid']
     dataframe['bb_lowerband'] = bollinger['lower']
     dataframe['bb_width'] = (bollinger['upper'] - bollinger['lower']) / bollinger['mid']
     
     dataframe['local_valley'] = (
         (dataframe['low'] < dataframe['low'].shift(2)) &
         (dataframe['low'] < dataframe['low'].shift(1)) &
         (dataframe['low'] < dataframe['low'].shift(-1)) &
         (dataframe['low'] < dataframe['low'].shift(-2))
     )
     
     dataframe['volume_ma'] = dataframe['volume'].rolling(window=20).mean()
     dataframe['high_volume'] = dataframe['volume'] > (dataframe['volume_ma'] * 1.5)
     
     dataframe['price_increased'] = dataframe['close'] > dataframe['close'].shift(1)
     
     dataframe['sequential_rises_3'] = (
         dataframe['price_increased'] & 
         dataframe['price_increased'].shift(1) & 
         dataframe['price_increased'].shift(2)
     )
     
     dataframe['macd_cross_above'] = qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal'])
     
     dataframe['atr'] = ta.ATR(dataframe, timeperiod=atr_period)
     dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']
     
     dataframe['historical_volatility'] = dataframe['close'].pct_change().rolling(volatility_lookback).std() * np.sqrt(365 * 24 * (60 / self.timeframe_to_minutes(self.timeframe)))
     dataframe['daily_range_pct'] = (dataframe['high'] - dataframe['low']) / dataframe['low']
     dataframe['daily_range_pct_ma'] = dataframe['daily_range_pct'].rolling(volatility_lookback).mean()
     
     dataframe['rma_close'] = ta.SMA(dataframe['close'], timeperiod=market_regime_threshold)
     dataframe['rma_volume'] = ta.SMA(dataframe['volume'], timeperiod=market_regime_threshold)
     
     dataframe['volatility_regime'] = dataframe['historical_volatility'].rolling(10).mean() / dataframe['historical_volatility'].rolling(60).mean()
     
     dataframe['exit_signal'] = (
         (dataframe['local_valley']) &
         (dataframe['rsi'] < exit_rsi_threshold) &
         (dataframe['macd_cross_above'] | dataframe['high_volume'])
     )
     
     if self.dp:
         try:
             informative_1m = self.dp.get_pair_dataframe(
                 pair=metadata['pair'], 
                 timeframe='1m'
             )
             
             informative_1m['rsi'] = ta.RSI(informative_1m, timeperiod=14)
             informative_1m['ema_short'] = ta.EMA(informative_1m, timeperiod=ema_short_period)
             
             bollinger_1m = qtpylib.bollinger_bands(qtpylib.typical_price(informative_1m), window=20, stds=2)
             informative_1m['bb_lowerband'] = bollinger_1m['lower']
             
             macd_1m = ta.MACD(informative_1m, 
                             fastperiod=macd_fast,
                             slowperiod=macd_slow, 
                             signalperiod=macd_signal)
             informative_1m['macd'] = macd_1m['macd']
             informative_1m['macdsignal'] = macd_1m['macdsignal']
             
             informative_1m['deep_oversold'] = (
                 (informative_1m['rsi'] < exit_rsi_threshold) &
                 (informative_1m['close'] < informative_1m['bb_lowerband'] * 1.01)
             )
             
             informative_1m['strong_reversal'] = (
                 qtpylib.crossed_above(informative_1m['macd'], informative_1m['macdsignal']) &
                 (informative_1m['close'] > informative_1m['open']) &
                 (informative_1m['volume'] > informative_1m['volume'].rolling(20).mean() * 1.5)
             )
             
             informative_1m['short_exit_signal'] = (
                 informative_1m['deep_oversold'] | 
                 informative_1m['strong_reversal']
             ).astype(int)
             
             dataframe = merge_informative_pair(
                 dataframe, 
                 informative_1m[['short_exit_signal']], 
                 self.timeframe, 
                 '1m', 
                 ffill=True, 
                 append_timeframe=False,
                 suffix='_1m'
             )
             
         except Exception as e:
             dataframe['short_exit_signal_1m'] = 0
         
         if entry_timeframe != self.timeframe:
             try:
                 informative = self.dp.get_pair_dataframe(
                     pair=metadata['pair'], 
                     timeframe=entry_timeframe
                 )
                 
                 informative['rsi'] = ta.RSI(informative, timeperiod=14)
                 
                 macd = ta.MACD(informative, 
                             fastperiod=macd_fast,
                             slowperiod=macd_slow, 
                             signalperiod=macd_signal)
                 informative['macd'] = macd['macd']
                 informative['macdsignal'] = macd['macdsignal']
                 informative['macdhist'] = macd['macdhist']
                 
                 informative['macdhist_prev1'] = informative['macdhist'].shift(1)
                 informative['macdhist_prev2'] = informative['macdhist'].shift(2)
                 
                 informative['ema_short'] = ta.EMA(informative, timeperiod=ema_short_period)
                 
                 for i in range(1, 4):
                     informative[f'close_prev{i}'] = informative['close'].shift(i)
                     informative[f'high_prev{i}'] = informative['high'].shift(i)
                 
                 informative['high_last_3'] = informative['high'].rolling(3).max()
                 
                 informative['price_peak'] = (
                     (informative['high'] >= informative['high_last_3'] * 0.995) &
                     (informative['high'] > informative['high_prev1']) &
                     (informative['close'] > informative['ema_short']) &
                     (informative['rsi'] > sell_rsi_upper)
                 )
                 
                 informative['price_reversal'] = (
                     (informative['close_prev2'] < informative['close_prev1']) &
                     (informative['close'] < informative['close_prev1']) &
                     (informative['close_prev1'] > informative['close_prev1'].rolling(3).max().shift(1)) &
                     (informative['rsi'] > sell_rsi_upper * 0.9)
                 )
                 
                 informative['macd_reversal'] = (
                     (informative['macdhist_prev2'] < informative['macdhist_prev1']) &
                     (informative['macdhist'] < informative['macdhist_prev1']) &
                     (informative['macdhist_prev1'] > 0) &
                     (informative['close'] > informative['ema_short'])
                 )
                 
                 informative['short_entry_signal'] = (
                     (informative['price_peak'] | informative['price_reversal'] | informative['macd_reversal']) &
                     (informative['rsi'] > sell_rsi_upper * 0.9) &
                     (informative['close'] > informative['ema_short'] * (1 + price_extension_pct))
                 )
                 
                 for col in ['short_entry_signal', 'price_peak', 'price_reversal', 'macd_reversal']:
                     informative[col] = informative[col].astype(int)
                 
                 dataframe = merge_informative_pair(
                     dataframe, 
                     informative, 
                     self.timeframe, 
                     entry_timeframe, 
                     ffill=True, 
                     append_timeframe=False,
                     suffix=f'_{entry_timeframe}'
                 )
             except Exception as e:
                 pass
         
         try:
             informative_1h = self.dp.get_pair_dataframe(
                 pair=metadata['pair'], 
                 timeframe='1h'
             )
             
             informative_1h['ema_200'] = ta.EMA(informative_1h, timeperiod=200)
             informative_1h['market_phase'] = (informative_1h['close'] > informative_1h['ema_200']).astype(float)
             
             informative_1h['atr'] = ta.ATR(informative_1h, timeperiod=atr_period)
             informative_1h['historical_volatility'] = informative_1h['close'].pct_change().rolling(volatility_lookback).std() * np.sqrt(365 * 24)
             
             dataframe = merge_informative_pair(
                 dataframe, 
                 informative_1h[['market_phase', 'atr', 'historical_volatility']], 
                 self.timeframe, 
                 '1h', 
                 ffill=True, 
                 append_timeframe=False,
                 suffix='_1h'
             )
         except Exception as e:
             pass
             
         try:
             informative_4h = self.dp.get_pair_dataframe(
                 pair=metadata['pair'], 
                 timeframe='4h'
             )
             
             informative_4h['atr'] = ta.ATR(informative_4h, timeperiod=atr_period)
             informative_4h['rma_close'] = ta.SMA(informative_4h['close'], timeperiod=market_regime_threshold)
             informative_4h['rma_volume'] = ta.SMA(informative_4h['volume'], timeperiod=market_regime_threshold)
             
             choppiness_period = 14
             informative_4h['choppiness'] = 100 * np.log10(
                 np.sum(np.sqrt(
                     np.power(informative_4h['high'].shift(1) - informative_4h['low'].shift(1), 2) +
                     np.power(informative_4h['close'].shift(1) - informative_4h['close'].shift(2), 2)
                 )) / (informative_4h['high'].rolling(choppiness_period).max() - informative_4h['low'].rolling(choppiness_period).min())
             ) / np.log10(choppiness_period)
             
             informative_4h['historical_volatility'] = informative_4h['close'].pct_change().rolling(volatility_lookback//4).std() * np.sqrt(365 * 6)
             
             informative_4h['trend_strength'] = abs(informative_4h['close'] - informative_4h['rma_close']) / (informative_4h['atr'] * 5)
             informative_4h['is_trending'] = (informative_4h['trend_strength'] > 0.5) & (informative_4h['choppiness'] < 61.8).astype(float)
             informative_4h['is_chopping'] = (informative_4h['choppiness'] > 61.8).astype(float)
             
             informative_4h['volatility_regime'] = informative_4h['historical_volatility'].rolling(10).mean() / informative_4h['historical_volatility'].rolling(30).mean()
             
             dataframe = merge_informative_pair(
                 dataframe, 
                 informative_4h[['atr', 'choppiness', 'historical_volatility', 'is_trending', 'is_chopping', 'volatility_regime']], 
                 self.timeframe, 
                 '4h', 
                 ffill=True, 
                 append_timeframe=False,
                 suffix='_4h'
             )
             
         except Exception as e:
             pass
             
         try:
             informative_1d = self.dp.get_pair_dataframe(
                 pair=metadata['pair'], 
                 timeframe='1d'
             )
             
             informative_1d['atr'] = ta.ATR(informative_1d, timeperiod=atr_period)
             informative_1d['historical_volatility'] = informative_1d['close'].pct_change().rolling(volatility_lookback//12).std() * np.sqrt(365)
             informative_1d['yearly_volatility'] = informative_1d['historical_volatility'] * 100
             
             dataframe = merge_informative_pair(
                 dataframe, 
                 informative_1d[['atr', 'historical_volatility', 'yearly_volatility']], 
                 self.timeframe, 
                 '1d', 
                 ffill=True, 
                 append_timeframe=False,
                 suffix='_1d'
             )
             
         except Exception as e:
             pass
     
     dataframe['high_last_3'] = dataframe['high'].rolling(3).max()
     
     dataframe['price_peak'] = (
         (dataframe['high'] >= dataframe['high_last_3'] * 0.995) &
         (dataframe['high'] > dataframe['high'].shift(1)) &
         (dataframe['close'] > dataframe['ema_short']) &
         (dataframe['rsi'] > sell_rsi_upper)
     )
     
     dataframe['price_reversal'] = (
         (dataframe['close'].shift(2) < dataframe['close'].shift(1)) &
         (dataframe['close'] < dataframe['close'].shift(1)) &
         (dataframe['close'].shift(1) > dataframe['close'].shift(1).rolling(3).max().shift(1)) &
         (dataframe['rsi'] > sell_rsi_upper * 0.9)
     )
     
     dataframe['macd_reversal'] = (
         (dataframe['macdhist'].shift(2) < dataframe['macdhist'].shift(1)) &
         (dataframe['macdhist'] < dataframe['macdhist'].shift(1)) &
         (dataframe['macdhist'].shift(1) > 0) &
         (dataframe['close'] > dataframe['ema_short'])
     )
    
     dataframe['short_entry_signal'] = (
        (dataframe['price_peak'] | dataframe['price_reversal'] | dataframe['macd_reversal']) &
        (dataframe['rsi'] > sell_rsi_upper * 0.9) &
        (dataframe['close'] > dataframe['ema_short'] * (1 + price_extension_pct))
     )
    
     dataframe[f'short_entry_signal_{self.timeframe}'] = dataframe['short_entry_signal'].astype(int)
     
     pair_key = f"{metadata['pair']}_market_regime"
     self._market_regimes[pair_key] = "unknown"
     
     if 'is_trending_4h' in dataframe.columns and 'is_chopping_4h' in dataframe.columns and len(dataframe) > 0:
         is_trending = dataframe['is_trending_4h'].iloc[-1] > 0.5
         is_chopping = dataframe['is_chopping_4h'].iloc[-1] > 0.5
         vol_regime = dataframe['volatility_regime_4h'].iloc[-1] if 'volatility_regime_4h' in dataframe.columns else 1.0
         
         if is_trending and vol_regime > 1.1:
             self._market_regimes[pair_key] = "trending_volatile"
         elif is_trending:
             self._market_regimes[pair_key] = "trending_normal"
         elif is_chopping and vol_regime < 0.9:
             self._market_regimes[pair_key] = "choppy_lowvol"
         elif is_chopping:
             self._market_regimes[pair_key] = "choppy_normal"
         else:
             self._market_regimes[pair_key] = "neutral"
             
         dataframe['market_regime'] = self._market_regimes[pair_key]
    
     pair_key = f"{metadata['pair']}_volatility"
     
     if 'historical_volatility_1d' in dataframe.columns and len(dataframe) > 0:
         base_volatility = dataframe['historical_volatility_1d'].iloc[-1]
         self._volatility_metrics[pair_key] = base_volatility
     else:
         self._volatility_metrics[pair_key] = 0.5
    
     return dataframe

  def adjust_parameters_from_model(self, dataframe: DataFrame, metadata: dict) -> Dict:
    coin = self.get_coin_from_pair(metadata['pair'])
    
    adjusted_params = {
        'leverage_param': self.get_param_value(coin, 'leverage_param'),
        'buy_rsi': self.get_param_value(coin, 'buy_rsi'),
        'sell_rsi_upper': self.get_param_value(coin, 'sell_rsi_upper'),
        'sell_rsi_lower': self.get_param_value(coin, 'sell_rsi_lower'),
        'price_extension_pct': self.get_param_value(coin, 'price_extension_pct'),
        'exit_rsi_threshold': self.get_param_value(coin, 'exit_rsi_threshold'),
        'quick_profit_target': self.get_param_value(coin, 'quick_profit_target'),
        'medium_profit_target': self.get_param_value(coin, 'medium_profit_target'),
        'longer_profit_target': self.get_param_value(coin, 'longer_profit_target')
    }
    
    pair = metadata['pair']
    pair_key = f"{pair}_market_regime"
    market_regime = self._market_regimes.get(pair_key, "unknown")
    
    base_leverage = adjusted_params['leverage_param']
    leverage_modifiers = {
        "trending_volatile": 1.2,
        "trending_normal": 1.0,
        "neutral": 0.8,
        "choppy_normal": 0.6,
        "choppy_lowvol": 0.4,
        "unknown": 0.7
    }
    
    vol_pair_key = f"{pair}_volatility"
    vol_metric = self._volatility_metrics.get(vol_pair_key, 0.5)
    
    max_vol_pct = float(self.get_param_value(coin, 'max_volatility_pct'))
    
    if 'historical_volatility_1d' in dataframe.columns and len(dataframe) > 0:
        vol_scaling = min(max_vol_pct / vol_metric, 1.0) if vol_metric > 0 else 0.5
    else:
        vol_scaling = 0.8
    
    if 'prediction_probability' in dataframe.columns and len(dataframe) > 0:
        prob = dataframe['prediction_probability'].iloc[-1]
        
        confidence_scaling = np.clip(prob * 2, 0.5, 1.5)
        
        adjusted_params['leverage_param'] = min(max(round(base_leverage * levrage_modifiers.get(market_regime, 0.7) * vol_scaling * confidence_scaling), 1), 5)
        
        profit_multiplier = min(max(0.8 + (prob - 0.5) * 0.8, 0.7), 1.3)
        
        adjusted_params['quick_profit_target'] *= profit_multiplier
        adjusted_params['medium_profit_target'] *= profit_multiplier
        adjusted_params['longer_profit_target'] *= profit_multiplier
            
        if 'market_phase_1h' in dataframe.columns:
            market_phase = dataframe['market_phase_1h'].iloc[-1]
            if market_phase > 0.5:
                adjusted_params['sell_rsi_upper'] = min(adjusted_params['sell_rsi_upper'] + 5, 85)
            else:
                adjusted_params['sell_rsi_upper'] = max(adjusted_params['sell_rsi_upper'] - 5, 70)
    else:
        adjusted_params['leverage_param'] = max(round(base_leverage * leverage_modifiers.get(market_regime, 0.7) * vol_scaling), 1)
    
    return adjusted_params

  def timeframe_to_minutes(self, timeframe: str) -> int:
      if timeframe.endswith('m'):
          return int(timeframe[:-1])
      elif timeframe.endswith('h'):
          return int(timeframe[:-1]) * 60
      elif timeframe.endswith('d'):
          return int(timeframe[:-1]) * 60 * 24
      return 5

  def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    dataframe['enter_long'] = 0
    dataframe['enter_short'] = 0
    
    coin = self.get_coin_from_pair(metadata['pair'])
    max_volatility_pct = float(self.get_param_value(coin, 'max_volatility_pct'))
    
    pair = metadata['pair']
    pair_key = f"{pair}_market_regime"
    market_regime = self._market_regimes.get(pair_key, "unknown")
    
    base_threshold = 0.7
    regime_threshold_modifiers = {
        "trending_volatile": 0.75,
        "trending_normal": 0.7,
        "neutral": 0.75,
        "choppy_normal": 0.8,
        "choppy_lowvol": 0.9,
        "unknown": 0.8
    }
    
    prediction_threshold = regime_threshold_modifiers.get(market_regime, base_threshold)
    
    if hasattr(self, 'freqai') and self.freqai and 'prediction' in dataframe.columns:
        if 'yearly_volatility_1d' in dataframe.columns:
            volatility_filter = dataframe['yearly_volatility_1d'] < max_volatility_pct * 100
        else:
            volatility_filter = pd.Series([True] * len(dataframe))
            
        if 'is_chopping_4h' in dataframe.columns:
            avoid_chop = ~(dataframe['is_chopping_4h'] > 0.5 & dataframe['historical_volatility_4h'] < 0.3)
        else:
            avoid_chop = pd.Series([True] * len(dataframe))
        
        if 'market_phase_1h' in dataframe.columns:
            dataframe.loc[dataframe['market_phase_1h'] > 0.7, 'prediction_threshold'] = prediction_threshold * 1.1
            dataframe.loc[dataframe['market_phase_1h'] < 0.3, 'prediction_threshold'] = prediction_threshold * 0.9
        else:
            dataframe['prediction_threshold'] = prediction_threshold
        
        dataframe.loc[
            (dataframe['prediction'] > dataframe['prediction_threshold']) & 
            (dataframe['volume'] > 0) &
            volatility_filter &
            avoid_chop,
            'enter_short'
        ] = 1
    else:
        entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
        
        entry_signal_col = f'short_entry_signal_{entry_timeframe}'
        
        if entry_signal_col in dataframe.columns:
            if 'volatility_regime_4h' in dataframe.columns:
                regime_filter = (dataframe['volatility_regime_4h'] < 1.5)
            else:
                regime_filter = pd.Series([True] * len(dataframe))
                
            if 'yearly_volatility_1d' in dataframe.columns:
                volatility_filter = dataframe['yearly_volatility_1d'] < max_volatility_pct * 100
            else:
                volatility_filter = pd.Series([True] * len(dataframe))
                
            if 'is_chopping_4h' in dataframe.columns:
                choppiness_filter = ~(dataframe['is_chopping_4h'] > 0.8)
            else:
                choppiness_filter = pd.Series([True] * len(dataframe))
                
            dataframe.loc[
                (dataframe[entry_signal_col] > 0) &
                regime_filter &
                volatility_filter &
                choppiness_filter,
                'enter_short'
            ] = 1
    
    return dataframe

  def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
     dataframe['exit_long'] = 0
     dataframe['exit_short'] = 0
     
     if 'short_exit_signal_1m' in dataframe.columns and dataframe['short_exit_signal_1m'].sum() > 0:
         dataframe.loc[dataframe['short_exit_signal_1m'] > 0, 'exit_short'] = 1
     elif 'exit_signal' in dataframe.columns:
         dataframe.loc[dataframe['exit_signal'], 'exit_short'] = 1
     
     return dataframe

  def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                       time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                       side: str, **kwargs) -> bool:
    if side != 'short':
        return True
        
    coin = self.get_coin_from_pair(pair)
    
    cooldown_minutes = 5
    if pair in self._last_candle_seen_time:
        last_time = self._last_candle_seen_time[pair]
        if current_time - last_time < timedelta(minutes=cooldown_minutes):
            return False
    
    dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
    
    if 'yearly_volatility_1d' in dataframe.columns and len(dataframe) > 0:
        max_volatility_pct = float(self.get_param_value(coin, 'max_volatility_pct'))
        if dataframe['yearly_volatility_1d'].iloc[-1] > max_volatility_pct * 100:
            return False
            
    if 'is_chopping_4h' in dataframe.columns and 'historical_volatility_4h' in dataframe.columns and len(dataframe) > 0:
        if dataframe['is_chopping_4h'].iloc[-1] > 0.5 and dataframe['historical_volatility_4h'].iloc[-1] < 0.3:
            return False
    
    if hasattr(self, 'freqai') and self.freqai and len(dataframe) > 0:
        adjusted_params = self.adjust_parameters_from_model(dataframe, {'pair': pair})
        
        if coin in self._coin_parameters and 'leverage_param' in adjusted_params:
            self._coin_parameters[coin]['leverage_param'].value = adjusted_params['leverage_param']
        
        if 'prediction_probability' in dataframe.columns:
            latest_prob = dataframe['prediction_probability'].iloc[-1]
            if latest_prob < 0.3:
                return False
    
    self._last_candle_seen_time[pair] = current_time
    
    return True

  def calculate_dynamic_trailing_stop(self, pair: str, trade: Trade, current_time: datetime, current_rate: float, current_profit: float) -> float:
      coin = self.get_coin_from_pair(pair)
      
      adaptive_vol_stop_scaling = float(self.get_param_value(coin, 'adaptive_vol_stop_scaling'))
      
      trailing_stop_percent = self.trailing_stop_percent(pair)
      
      try:
          dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
          
          if len(dataframe) == 0:
              return trailing_stop_percent
          
          if 'historical_volatility_1h' in dataframe.columns:
              current_volatility = dataframe['historical_volatility_1h'].iloc[-1]
          elif 'atr_pct' in dataframe.columns:
              current_volatility = dataframe['atr_pct'].iloc[-1] * 20
          else:
              return trailing_stop_percent
          
          if current_volatility > 0:
              trade_duration = (current_time - trade.open_date_utc).total_seconds() / 60
              
              if current_profit > 0.02:
                  vol_factor = max(0.8, min(1.5, adaptive_vol_stop_scaling * current_volatility * 30))
                  profit_factor = min(current_profit * 10, 2.0)
                  
                  adjusted_stop = trailing_stop_percent * (1.0 / profit_factor) * vol_factor
                  
                  return max(adjusted_stop, trailing_stop_percent * 0.5)
              elif trade_duration > 240:
                  vol_factor = max(1.0, min(1.5, adaptive_vol_stop_scaling * current_volatility * 20))
                  return trailing_stop_percent * vol_factor
          
      except Exception as e:
          pass
          
      return trailing_stop_percent

  def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
     if trade.is_short:
         try:
             coin = self.get_coin_from_pair(pair)
             
             quick_profit_target = float(self.get_param_value(coin, 'quick_profit_target'))
             medium_profit_target = float(self.get_param_value(coin, 'medium_profit_target'))
             longer_profit_target = float(self.get_param_value(coin, 'longer_profit_target'))
             
             trade_duration = (current_time - trade.open_date_utc).total_seconds() / 60
             
             max_profit_key = f"{pair}_max_profit"
             if not hasattr(self, '_max_profits'):
                 self._max_profits = {}
                 
             if max_profit_key not in self._max_profits:
                 self._max_profits[max_profit_key] = current_profit
             elif current_profit > self._max_profits[max_profit_key]:
                 self._max_profits[max_profit_key] = current_profit
             
             profit_drawdown = 0
             if max_profit_key in self._max_profits and self._max_profits[max_profit_key] > 0:
                 profit_drawdown = 1 - (current_profit / self._max_profits[max_profit_key])
             
             volatility_adjusted_drawdown = 0.1
             
             try:
                 dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                 if len(dataframe) > 0:
                     adaptive_vol_stop_scaling = float(self.get_param_value(coin, 'adaptive_vol_stop_scaling'))
                     
                     if 'historical_volatility_1h' in dataframe.columns:
                         current_volatility = dataframe['historical_volatility_1h'].iloc[-1]
                         base_vol = 0.5
                         vol_ratio = current_volatility / base_vol
                         
                         vol_adjusted_factor = np.sqrt(vol_ratio) * adaptive_vol_stop_scaling
                         volatility_adjusted_drawdown = min(0.2, max(0.05, 0.1 * vol_adjusted_factor))
                         
                         if trade_duration < 30:
                             volatility_adjusted_drawdown *= 0.8
                         elif trade_duration > 120:
                             volatility_adjusted_drawdown *= 1.2
             except Exception as e:
                 pass
                 
             if self._max_profits[max_profit_key] > quick_profit_target:
                 if trade_duration > 60 and profit_drawdown > volatility_adjusted_drawdown * 1.5:
                     return 'vol_adj_drawdown_protection_long'
                 elif trade_duration > 30 and profit_drawdown > volatility_adjusted_drawdown * 1.2:
                     return 'vol_adj_drawdown_protection_medium'
                 elif profit_drawdown > volatility_adjusted_drawdown:
                     return 'vol_adj_drawdown_protection_quick'
             
             if trade_duration < 15:
                 if current_profit > quick_profit_target:
                     return 'quick_short_profit'
             elif trade_duration < 60:
                 if current_profit > medium_profit_target:
                     return 'medium_short_profit'
             else:
                 if current_profit > longer_profit_target:
                     return 'longer_short_profit'
             
             pair_key = f"{pair}_market_regime"
             market_regime = self._market_regimes.get(pair_key, "unknown")
             
             if market_regime == "choppy_lowvol" and current_profit > longer_profit_target * 0.7 and trade_duration > 30:
                 return 'regime_choppy_lowvol_exit'
             
             roi_table = self.get_roi_table_for_coin(coin)
             roi_threshold = None
             for time_threshold, roi_value in sorted(roi_table.items(), key=lambda x: int(x[0]) if x[0] != "0" else 0):
                 if trade_duration >= int(time_threshold):
                     roi_threshold = roi_value
             
             if roi_threshold is not None and current_profit > roi_threshold:
                 dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                 if len(dataframe) > 0:
                     last_candle = dataframe.iloc[-1]
                     if last_candle.get('sequential_rises_3', False):
                         return 'roi_with_reversal'
                     
                     return f'{coin}_roi_reached'
             
             if current_profit > 0.008:
                 dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                 if len(dataframe) > 0:
                     last_candle = dataframe.iloc[-1]
                     
                     if last_candle.get('local_valley', False) and last_candle.get('macd_cross_above', False):
                         return 'valley_with_macd_cross'
                     
                     if last_candle.get('high_volume', False) and last_candle.get('rsi', 50) < self.get_param_value(coin, 'exit_rsi_threshold'):
                         return 'volume_spike_with_profit'
         
         except Exception as e:
             pass
     
     return None

  def leverage(self, pair: str, current_time: datetime, current_rate: float,
            proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
            **kwargs) -> float:
    coin = self.get_coin_from_pair(pair)
    
    dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
    
    if hasattr(self, 'freqai') and self.freqai and len(dataframe) > 0:
        adjusted_params = self.adjust_parameters_from_model(dataframe, {'pair': pair})
        
        if 'leverage_param' in adjusted_params:
            return float(adjusted_params['leverage_param'])
    
    base_leverage = float(self.get_param_value(coin, 'leverage_param'))
    
    if len(dataframe) > 0:
        if 'volatility_regime_4h' in dataframe.columns:
            vol_regime = dataframe['volatility_regime_4h'].iloc[-1]
            if vol_regime > 1.5:
                return max(1, base_leverage * 0.7)
            elif vol_regime < 0.7:
                return min(max_leverage, base_leverage * 1.2)
        
        pair_key = f"{pair}_market_regime"
        market_regime = self._market_regimes.get(pair_key, "unknown")
        
        regime_leverage_modifiers = {
            "trending_volatile": 0.8,
            "trending_normal": 1.0,
            "neutral": 0.9,
            "choppy_normal": 0.7,
            "choppy_lowvol": 0.6,
            "unknown": 0.8
        }
        
        return float(base_leverage * regime_leverage_modifiers.get(market_regime, 0.8))
    
    return float(base_leverage)

  def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime, current_rate: float, current_profit: float, **kwargs) -> float:
    coin = self.get_coin_from_pair(pair)
    
    coin_ts = self.get_trailing_stop_for_coin(coin)
    base_stoploss = coin_ts['stoploss']
    
    try:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            atr_period = int(self.get_param_value(coin, 'atr_period'))
            atr_stop_multiplier = float(self.get_param_value(coin, 'atr_stop_multiplier'))
            
            if 'atr' in dataframe.columns and trade.is_short:
                last_atr = dataframe['atr'].iloc[-1]
                entry_price = trade.open_rate
                atr_stop_pct = (last_atr * atr_stop_multiplier) / entry_price
                
                atr_stoploss = -1 * atr_stop_pct
                
                return max(atr_stoploss, base_stoploss)
    except Exception as e:
        pass
    
    return base_stoploss

  def trailing_stop_percent(self, pair: str, **kwargs) -> float:
    coin = self.get_coin_from_pair(pair)
    coin_ts = self.get_trailing_stop_for_coin(coin)
    return abs(coin_ts['stoploss'])

  def trailing_stop_positive_percentage(self, pair: str, **kwargs) -> float:
    coin = self.get_coin_from_pair(pair)
    coin_ts = self.get_trailing_stop_for_coin(coin)
    return coin_ts['trailing_stop_positive']

  def trailing_stop_positive_offset_percentage(self, pair: str, **kwargs) -> float:
    coin = self.get_coin_from_pair(pair)
    coin_ts = self.get_trailing_stop_for_coin(coin)
    return coin_ts['trailing_stop_positive_offset']

  def trailing_only_offset_is_reached_percentage(self, pair: str, **kwargs) -> bool:
    coin = self.get_coin_from_pair(pair)
    coin_ts = self.get_trailing_stop_for_coin(coin)
    return coin_ts['trailing_only_offset_is_reached']

  def use_trailing_stop(self, pair: str, **kwargs) -> bool:
    coin = self.get_coin_from_pair(pair)
    coin_ts = self.get_trailing_stop_for_coin(coin)
    return coin_ts['trailing_stop']

  def get_strategy_parameters(self) -> Dict[str, Any]:
    params = {
        'leverage_param': self.leverage_param.value,
        'buy_rsi': self.buy_rsi.value,
        'sell_rsi_upper': self.sell_rsi_upper.value,
        'sell_rsi_lower': self.sell_rsi_lower.value,
        'price_extension_pct': self.price_extension_pct.value,
        'macd_fast': self.macd_fast.value,
        'macd_slow': self.macd_slow.value, 
        'macd_signal': self.macd_signal.value,
        'ema_short_period': self.ema_short_period.value,
        'ema_long_period': self.ema_long_period.value,
        'entry_timeframe': self.entry_timeframe.value,
        'exit_rsi_threshold': self.exit_rsi_threshold.value,
        'quick_profit_target': self.quick_profit_target.value,
        'medium_profit_target': self.medium_profit_target.value,
        'longer_profit_target': self.longer_profit_target.value,
        'atr_period': self.atr_period.value,
        'atr_stop_multiplier': self.atr_stop_multiplier.value,
        'adaptive_vol_stop_scaling': self.adaptive_vol_stop_scaling.value,
        'volatility_lookback': self.volatility_lookback.value,
        'market_regime_threshold': self.market_regime_threshold.value,
        'max_volatility_pct': self.max_volatility_pct.value
    }
    
    for coin in self._coin_list:
        if coin in self._coin_parameters:
            for param_name, param_obj in self._coin_parameters[coin].items():
                params[f"{coin}_{param_name}"] = param_obj.value
                
        if coin in self._coin_roi:
            for param_name, param_obj in self._coin_roi[coin].items():
                params[f"{coin}_roi_{param_name}"] = param_obj.value
        
        if coin in self._coin_trailing_stop:
            for param_name, param_obj in self._coin_trailing_stop[coin].items():
                params[f"{coin}_{param_name}"] = param_obj.value
    
    return params
