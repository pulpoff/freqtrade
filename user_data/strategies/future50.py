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

class future50(IStrategy):
    minimal_roi = {
        "0": 0.02,
        "3": 0.015,
        "15": 0.007,
        "34": 0,
        "60": -0.01
    }

    stoploss = -0.05
    trailing_stop = True
    trailing_stop_positive = 0.16
    trailing_stop_positive_offset = 0.213
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    process_only_new_candles = True

    leverage_param = IntParameter(1, 3, default=2, space="buy", optimize=True)
    
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
    
    entry_timeframe = CategoricalParameter(['5m', '15m'], default='5m', space='buy', optimize=True)
    
    startup_candle_count = 100
    can_short = True
    can_long = False

    _last_candle_seen_time = {}
    _coin_list = []
    _coin_parameters = {}
    _coin_roi = {}
    _coin_trailing_stop = {}
    _max_profits = {}
    
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
        "identifier": "future37",
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
            'exit_rsi_threshold': 20
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
       
       dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
       
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
       
       entry_signal = (
           (price_peak | price_reversal | macd_reversal) &
           (dataframe['rsi'] > sell_rsi_upper * 0.9) &
           (dataframe['close'] > dataframe['ema_short'] * (1 + price_extension_pct))
       )
       
       dataframe['future_price'] = dataframe['close'].shift(-20)
       dataframe['price_drop'] = (dataframe['future_price'] / dataframe['close']) - 1.0
       
       dataframe['target'] = -1 * dataframe['price_drop']
       
       dataframe['target'] = dataframe['target'].clip(0, 1)
       
       dataframe['historical_signal'] = entry_signal.astype(int)
       
       dataframe['market_trend_target'] = (dataframe['close'].shift(-10) < dataframe['close']).astype(float)
       
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
       
       entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
       
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
       
       bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
       dataframe['bb_upperband'] = bollinger['upper']
       dataframe['bb_middleband'] = bollinger['mid']
       dataframe['bb_lowerband'] = bollinger['lower']
       
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
               
               dataframe = merge_informative_pair(
                   dataframe, 
                   informative_1h[['market_phase']], 
                   self.timeframe, 
                   '1h', 
                   ffill=True, 
                   append_timeframe=False,
                   suffix='_1h'
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
      
      if 'prediction_probability' in dataframe.columns and len(dataframe) > 0:
          prob = dataframe['prediction_probability'].iloc[-1]
          
          if prob > 0.8:
              adjusted_params['leverage_param'] = min(adjusted_params['leverage_param'] * 1.2, 5)
              adjusted_params['quick_profit_target'] *= 1.1
              adjusted_params['medium_profit_target'] *= 1.1
              adjusted_params['longer_profit_target'] *= 1.1
          elif prob < 0.4:
              adjusted_params['leverage_param'] = max(adjusted_params['leverage_param'] * 0.8, 1)
              adjusted_params['quick_profit_target'] *= 0.9
              adjusted_params['medium_profit_target'] *= 0.9
              adjusted_params['longer_profit_target'] *= 0.9
              
          if 'market_phase_1h' in dataframe.columns:
              market_phase = dataframe['market_phase_1h'].iloc[-1]
              if market_phase > 0.5:
                  adjusted_params['sell_rsi_upper'] = min(adjusted_params['sell_rsi_upper'] + 5, 85)
              else:
                  adjusted_params['sell_rsi_upper'] = max(adjusted_params['sell_rsi_upper'] - 5, 70)
      
      return adjusted_params

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
      dataframe['enter_long'] = 0
      dataframe['enter_short'] = 0
      
      coin = self.get_coin_from_pair(metadata['pair'])
      
      if hasattr(self, 'freqai') and self.freqai and 'prediction' in dataframe.columns:
          dataframe['prediction_threshold'] = 0.7
          
          if 'market_phase_1h' in dataframe.columns:
              dataframe.loc[dataframe['market_phase_1h'] > 0.7, 'prediction_threshold'] = 0.8
              dataframe.loc[dataframe['market_phase_1h'] < 0.3, 'prediction_threshold'] = 0.6
          
          dataframe.loc[
              (dataframe['prediction'] > dataframe['prediction_threshold']) & 
              (dataframe['volume'] > 0),
              'enter_short'
          ] = 1
      else:
          entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
          
          entry_signal_col = f'short_entry_signal_{entry_timeframe}'
          
          if entry_signal_col in dataframe.columns:
              dataframe.loc[dataframe[entry_signal_col] > 0, 'enter_short'] = 1
      
      return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
       dataframe['exit_long'] = 0
       dataframe['exit_short'] = 0
       
       # Only create a small number of exit signals - keep them selective
       # This is important for preventing premature exits
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
               
               # Protect profits with trailing drawdown exit
               if self._max_profits[max_profit_key] > quick_profit_target:
                   if trade_duration > 60 and profit_drawdown > 0.15:
                       return 'drawdown_protection_long'
                   elif trade_duration > 30 and profit_drawdown > 0.12:
                       return 'drawdown_protection_medium'
                   elif profit_drawdown > 0.1:
                       return 'drawdown_protection_quick'
               
               # Duration-based profit targets
               if trade_duration < 15:
                   if current_profit > quick_profit_target:
                       return 'quick_short_profit'
               elif trade_duration < 60:
                   if current_profit > medium_profit_target:
                       return 'medium_short_profit'
               else:
                   if current_profit > longer_profit_target:
                       return 'longer_short_profit'
               
               # ROI-based exits
               roi_table = self.get_roi_table_for_coin(coin)
               roi_threshold = None
               for time_threshold, roi_value in sorted(roi_table.items(), key=lambda x: int(x[0]) if x[0] != "0" else 0):
                   if trade_duration >= int(time_threshold):
                       roi_threshold = roi_value
               
               if roi_threshold is not None and current_profit > roi_threshold:
                   dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                   if len(dataframe) > 0:
                       # Check if we've seen sequential rising candles
                       last_candle = dataframe.iloc[-1]
                       if last_candle.get('sequential_rises_3', False):
                           return 'roi_with_reversal'
                       
                       return f'{coin}_roi_reached'
               
               # Early profit with technical confirmation  
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
      
      return float(self.get_param_value(coin, 'leverage_param'))
  
    def custom_stoploss(self, pair: str, current_time: datetime, current_rate: float, current_profit: float, **kwargs) -> float:
      coin = self.get_coin_from_pair(pair)
      coin_ts = self.get_trailing_stop_for_coin(coin)
      return coin_ts['stoploss']
  
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
          'longer_profit_target': self.longer_profit_target.value
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
