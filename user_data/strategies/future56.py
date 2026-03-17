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

class future56(IStrategy):
    minimal_roi = {
        "0": 100.0,
        "1440": 100.0
    }

    stoploss = -0.05
    trailing_stop = True
    trailing_stop_positive = 0.16
    trailing_stop_positive_offset = 0.213
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    process_only_new_candles = True

    leverage_param = IntParameter(1, 6, default=2, space="buy", optimize=True)
    
    buy_rsi = IntParameter(30, 50, default=47, space="buy", optimize=True)
    sell_rsi_upper = IntParameter(60, 85, default=79, space="sell", optimize=True)
    sell_rsi_lower = IntParameter(20, 40, default=21, space="sell", optimize=True)
    
    macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
    macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
    
    ema_short_period = IntParameter(5, 15, default=8, space="both", optimize=True)
    ema_long_period = IntParameter(15, 30, default=21, space="both", optimize=True)
    
    price_extension_pct = DecimalParameter(0.003, 0.01, default=0.006, space="sell", optimize=True)
    
    confluence_threshold = IntParameter(5, 9, default=6, space="buy", optimize=True)
    
    leverage_param_high_vol = IntParameter(1, 3, default=2, space="buy", optimize=True)
    leverage_param_medium_vol = IntParameter(2, 5, default=3, space="buy", optimize=True)
    leverage_param_low_vol = IntParameter(3, 7, default=5, space="buy", optimize=True)
    
    buy_rsi_aggressive = IntParameter(25, 40, default=35, space="buy", optimize=True)
    buy_rsi_conservative = IntParameter(40, 55, default=47, space="buy", optimize=True)
    
    sell_rsi_upper_bear = IntParameter(65, 80, default=72, space="sell", optimize=True)
    sell_rsi_upper_bull = IntParameter(75, 90, default=82, space="sell", optimize=True)
    
    price_extension_pct_conservative = DecimalParameter(0.004, 0.008, default=0.006, space="sell", optimize=True)
    price_extension_pct_aggressive = DecimalParameter(0.002, 0.006, default=0.004, space="sell", optimize=True)
    
    timeframe = '5m'
    
    entry_timeframe = CategoricalParameter(['5m', '15m'], default='5m', space='buy', optimize=True)
    
    startup_candle_count = 200
    can_short = True
    can_long = False

    _last_candle_seen_time = {}
    _coin_list = []
    _coin_parameters = {}
    _coin_roi = {}
    _coin_trailing_stop = {}
    _trade_start_reset_times = {}
    _coin_categories = {}
    _market_regime = "bear_high_vol"
    _regime_update_time = None

    COIN_CATEGORIES = {
        'high_vol': ['BTC', 'ETH', 'BNB', 'SOL', 'AVAX', 'MATIC', 'ATOM', 'FTM', 'NEAR'],
        'medium_vol': ['ADA', 'DOT', 'LINK', 'UNI', 'LTC', 'BCH', 'XLM', 'VET', 'ALGO'],
        'low_vol': ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDD', 'FRAX']
    }

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_candle_seen_time = {}
        self._coin_list = []
        self._coin_parameters = {}
        self._coin_roi = {}
        self._coin_trailing_stop = {}
        self._trade_start_reset_times = {}
        self._coin_categories = {}
        self._market_regime = "bear_high_vol"
        self._regime_update_time = None
        
        if 'exchange' in config and 'pair_whitelist' in config['exchange']:
            for pair in config['exchange']['pair_whitelist']:
                coin = self.get_coin_from_pair(pair)
                if coin and coin not in self._coin_list:
                    self._coin_list.append(coin)
        
        self.initialize_coin_categories()
        self.initialize_coin_parameters()
        
    def initialize_coin_categories(self):
        for category, coins in self.COIN_CATEGORIES.items():
            for coin in coins:
                self._coin_categories[coin] = category
        
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
            
            setattr(self, f"{coin}_confluence_threshold", IntParameter(4, 8, default=6, space="buy", optimize=True))
            self._coin_parameters[coin]['confluence_threshold'] = getattr(self, f"{coin}_confluence_threshold")
            
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
    
    def get_coin_category(self, coin: str) -> str:
        return self._coin_categories.get(coin, 'medium_vol')
    
    def detect_market_regime(self, dataframe: DataFrame) -> str:
        if len(dataframe) < 200:
            return self._market_regime
            
        ema_50 = ta.EMA(dataframe, timeperiod=50)
        ema_200 = ta.EMA(dataframe, timeperiod=200)
        
        volatility = dataframe['close'].rolling(20).std()
        avg_volatility = volatility.rolling(100).mean()
        
        current_trend = ema_50.iloc[-1] > ema_200.iloc[-1]
        current_volatility = volatility.iloc[-1] / avg_volatility.iloc[-1]
        
        if current_trend and current_volatility < 1.2:
            return 'bull_low_vol'
        elif current_trend and current_volatility >= 1.2:
            return 'bull_high_vol'
        elif not current_trend and current_volatility < 1.2:
            return 'bear_low_vol'
        else:
            return 'bear_high_vol'
    
    def get_param_value(self, coin: str, param_name: str):
        if coin in self._coin_parameters and param_name in self._coin_parameters[coin]:
            return self._coin_parameters[coin][param_name].value
        
        if hasattr(self, param_name):
            return getattr(self, param_name).value
        
        category = self.get_coin_category(coin)
        
        category_defaults = {
            'high_vol': {
                'leverage_param': self.leverage_param_high_vol.value,
                'buy_rsi': self.buy_rsi_aggressive.value,
                'price_extension_pct': self.price_extension_pct_aggressive.value
            },
            'medium_vol': {
                'leverage_param': self.leverage_param_medium_vol.value,
                'buy_rsi': self.buy_rsi_conservative.value,
                'price_extension_pct': self.price_extension_pct_conservative.value
            },
            'low_vol': {
                'leverage_param': self.leverage_param_low_vol.value,
                'buy_rsi': self.buy_rsi_conservative.value,
                'price_extension_pct': self.price_extension_pct_conservative.value
            }
        }
        
        if param_name in category_defaults[category]:
            return category_defaults[category][param_name]
        
        defaults = {
            'leverage_param': 2,
            'buy_rsi': 47,
            'sell_rsi_upper': self.sell_rsi_upper_bear.value if 'bear' in self._market_regime else self.sell_rsi_upper_bull.value,
            'sell_rsi_lower': self.sell_rsi_lower.value,
            'price_extension_pct': 0.006,
            'macd_fast': self.macd_fast.value,
            'macd_slow': self.macd_slow.value,
            'macd_signal': self.macd_signal.value,
            'ema_short_period': self.ema_short_period.value,
            'ema_long_period': self.ema_long_period.value,
            'entry_timeframe': self.entry_timeframe.value,
            'confluence_threshold': self.confluence_threshold.value
        }
        
        value = defaults.get(param_name, 1.0)
        
        regime_adjustments = {
            'bull_low_vol': {'leverage_mult': 0.7, 'rsi_adj': +8, 'ext_mult': 1.2},
            'bull_high_vol': {'leverage_mult': 0.5, 'rsi_adj': +12, 'ext_mult': 1.5},
            'bear_low_vol': {'leverage_mult': 1.3, 'rsi_adj': -3, 'ext_mult': 0.8},
            'bear_high_vol': {'leverage_mult': 1.0, 'rsi_adj': 0, 'ext_mult': 1.0}
        }
        
        adj = regime_adjustments.get(self._market_regime, regime_adjustments['bear_high_vol'])
        
        if param_name == 'leverage_param':
            value = max(1, int(value * adj['leverage_mult']))
        elif param_name == 'sell_rsi_upper':
            value += adj['rsi_adj']
        elif param_name == 'price_extension_pct':
            value *= adj['ext_mult']
        
        return value
    
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
                str(t3): 0
            }
        
        category = self.get_coin_category(coin)
        category_roi = {
            'high_vol': {"0": 0.025, "2": 0.02, "8": 0.01, "20": 0},
            'medium_vol': {"0": 0.02, "3": 0.015, "15": 0.007, "34": 0},
            'low_vol': {"0": 0.015, "5": 0.01, "25": 0.005, "60": 0}
        }
        
        return category_roi.get(category, self.minimal_roi)
    
    def get_trailing_stop_for_coin(self, coin: str) -> Dict[str, Any]:
        if coin in self._coin_trailing_stop:
            return {
                'trailing_stop': self._coin_trailing_stop[coin]['trailing_stop'].value,
                'trailing_stop_positive': self._coin_trailing_stop[coin]['trailing_stop_positive'].value,
                'trailing_stop_positive_offset': self._coin_trailing_stop[coin]['trailing_stop_positive_offset'].value,
                'trailing_only_offset_is_reached': self._coin_trailing_stop[coin]['trailing_only_offset_is_reached'].value,
                'stoploss': self._coin_trailing_stop[coin]['stoploss'].value
            }
        
        category = self.get_coin_category(coin)
        category_stops = {
            'high_vol': {
                'trailing_stop': True,
                'trailing_stop_positive': 0.12,
                'trailing_stop_positive_offset': 0.18,
                'trailing_only_offset_is_reached': True,
                'stoploss': -0.08
            },
            'medium_vol': {
                'trailing_stop': self.trailing_stop,
                'trailing_stop_positive': self.trailing_stop_positive,
                'trailing_stop_positive_offset': self.trailing_stop_positive_offset,
                'trailing_only_offset_is_reached': self.trailing_only_offset_is_reached,
                'stoploss': self.stoploss
            },
            'low_vol': {
                'trailing_stop': True,
                'trailing_stop_positive': 0.08,
                'trailing_stop_positive_offset': 0.12,
                'trailing_only_offset_is_reached': True,
                'stoploss': -0.03
            }
        }
        
        return category_stops.get(category, {
            'trailing_stop': self.trailing_stop,
            'trailing_stop_positive': self.trailing_stop_positive,
            'trailing_stop_positive_offset': self.trailing_stop_positive_offset,
            'trailing_only_offset_is_reached': self.trailing_only_offset_is_reached,
            'stoploss': self.stoploss
        })

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = []
        
        for pair in pairs:
            informative_pairs.append((pair, '1m'))
            
            coin = self.get_coin_from_pair(pair)
            entry_tf = self.get_param_value(coin, 'entry_timeframe')
            if entry_tf != self.timeframe:
                informative_pairs.append((pair, entry_tf))
        
        return informative_pairs

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int, 
                                     metadata: dict) -> DataFrame:
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
        
        return dataframe
        
    def feature_engineering_expand_basic(self, dataframe: DataFrame, period: int,
                                      metadata: dict) -> DataFrame:
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
        
        return dataframe

    def calculate_confluence_score(self, dataframe: DataFrame, coin: str) -> DataFrame:
        sell_rsi_upper = float(self.get_param_value(coin, 'sell_rsi_upper'))
        price_extension_pct = float(self.get_param_value(coin, 'price_extension_pct'))
        
        dataframe['volume_avg'] = dataframe['volume'].rolling(20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_avg']
        
        signals = {}
        signals['rsi_signal'] = (dataframe['rsi'] > sell_rsi_upper).astype(int) * 3
        signals['bb_signal'] = (dataframe['bb_pct'] > 0.85).astype(int) * 2
        signals['macd_signal'] = (
            (dataframe['macdhist'] < dataframe['macdhist'].shift(1)) &
            (dataframe['macdhist'].shift(1) > 0)
        ).astype(int) * 2
        signals['volume_signal'] = (dataframe['volume_ratio'] > 1.3).astype(int) * 1
        signals['trend_signal'] = (dataframe['close'] > dataframe['ema_short']).astype(int) * 1
        signals['extension_signal'] = (
            dataframe['close'] > dataframe['ema_short'] * (1 + price_extension_pct)
        ).astype(int) * 2
        signals['momentum_signal'] = (
            (dataframe['close'] > dataframe['close'].shift(1)) &
            (dataframe['close'].shift(1) > dataframe['close'].shift(2))
        ).astype(int) * 1
        
        dataframe['confluence_score'] = sum(signals.values())
        
        confluence_threshold = int(self.get_param_value(coin, 'confluence_threshold'))
        dataframe['high_confluence'] = dataframe['confluence_score'] >= confluence_threshold
        
        return dataframe
        
    def clean_up_old_trades(self):
        current_open_trade_ids = set(trade.id for trade in Trade.get_open_trades())
        if hasattr(self, '_trade_start_reset_times'):
            closed_trade_ids = set(self._trade_start_reset_times.keys()) - current_open_trade_ids
            for trade_id in closed_trade_ids:
                if trade_id in self._trade_start_reset_times:
                    del self._trade_start_reset_times[trade_id]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        self.clean_up_old_trades()
        
        if (self._regime_update_time is None or 
            datetime.now() - self._regime_update_time > timedelta(hours=4)):
            self._market_regime = self.detect_market_regime(dataframe)
            self._regime_update_time = datetime.now()
        
        coin = self.get_coin_from_pair(metadata['pair'])
        
        ema_short_period = int(self.get_param_value(coin, 'ema_short_period'))
        ema_long_period = int(self.get_param_value(coin, 'ema_long_period'))
        macd_fast = int(self.get_param_value(coin, 'macd_fast'))
        macd_slow = int(self.get_param_value(coin, 'macd_slow'))
        macd_signal = int(self.get_param_value(coin, 'macd_signal'))
        sell_rsi_upper = float(self.get_param_value(coin, 'sell_rsi_upper'))
        sell_rsi_lower = float(self.get_param_value(coin, 'sell_rsi_lower'))
        price_extension_pct = float(self.get_param_value(coin, 'price_extension_pct'))
        
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
        dataframe['bb_pct'] = (dataframe['close'] - bollinger['lower']) / (bollinger['upper'] - bollinger['lower'])
        
        if self.dp:
            try:
                informative_1m = self.dp.get_pair_dataframe(
                    pair=metadata['pair'], 
                    timeframe='1m'
                )
                
                informative_1m['rsi'] = ta.RSI(informative_1m, timeperiod=14)
                informative_1m['ema_short'] = ta.EMA(informative_1m, timeperiod=ema_short_period)
                informative_1m['ema_long'] = ta.EMA(informative_1m, timeperiod=ema_long_period)
                
                bollinger_1m = qtpylib.bollinger_bands(qtpylib.typical_price(informative_1m), window=20, stds=2)
                informative_1m['bb_upperband'] = bollinger_1m['upper']
                informative_1m['bb_middleband'] = bollinger_1m['mid']
                informative_1m['bb_lowerband'] = bollinger_1m['lower']
                
                macd_1m = ta.MACD(informative_1m, 
                                fastperiod=macd_fast,
                                slowperiod=macd_slow, 
                                signalperiod=macd_signal)
                informative_1m['macd'] = macd_1m['macd']
                informative_1m['macdsignal'] = macd_1m['macdsignal']
                informative_1m['macdhist'] = macd_1m['macdhist']
                
                informative_1m['deep_oversold'] = (
                    (informative_1m['rsi'] < sell_rsi_lower * 0.9) &
                    (informative_1m['close'] < informative_1m['bb_lowerband'] * 1.01) &
                    (informative_1m['close'] < informative_1m['ema_short'] * 0.99)
                )
                
                informative_1m['major_trend_reversal'] = (
                    qtpylib.crossed_above(informative_1m['macd'], informative_1m['macdsignal']) &
                    (informative_1m['macd'] < 0) &
                    (informative_1m['macdhist'] > informative_1m['macdhist'].shift(1) * 1.2) &
                    (informative_1m['close'] < informative_1m['ema_short'])
                )
                
                informative_1m['trend_reversal_1m'] = (
                    (informative_1m['macd'] > informative_1m['macdsignal']) &
                    (informative_1m['macdhist'] > 0) &
                    (informative_1m['macdhist'] > informative_1m['macdhist'].shift(1)) &
                    (informative_1m['close'] > informative_1m['ema_short']) &
                    (informative_1m['rsi'] > 40)
                )
                
                informative_1m['uptrend_breakout_1m'] = (
                    qtpylib.crossed_above(informative_1m['close'], informative_1m['ema_short']) &
                    (informative_1m['rsi'] > 45) &
                    (informative_1m['macdhist'] > informative_1m['macdhist'].shift(1) * 1.1)
                )
                
                informative_1m['short_exit_signal'] = (
                    informative_1m['deep_oversold'] | 
                    informative_1m['major_trend_reversal'] |
                    informative_1m['trend_reversal_1m'] |
                    informative_1m['uptrend_breakout_1m']
                )
                
                informative_1m['short_exit_signal'] = informative_1m['short_exit_signal'].astype(int)
                
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
                dataframe['trend_reversal_fallback'] = (
                    (dataframe['macd'] > dataframe['macdsignal']) &
                    (dataframe['macdhist'] > 0) &
                    (dataframe['macdhist'] > dataframe['macdhist'].shift(1)) &
                    (dataframe['close'] > dataframe['ema_short']) &
                    (dataframe['rsi'] > 40)
                )
                
                dataframe['uptrend_breakout_fallback'] = (
                    qtpylib.crossed_above(dataframe['close'], dataframe['ema_short']) &
                    (dataframe['rsi'] > 45) &
                    (dataframe['macdhist'] > dataframe['macdhist'].shift(1) * 1.1)
                )
                
                dataframe['short_exit_signal_1m'] = (
                    (dataframe['rsi'] < sell_rsi_lower * 0.9) &
                    (dataframe['close'] < dataframe['bb_lowerband'] * 1.01) &
                    (dataframe['close'] < dataframe['ema_short'] * 0.99)
                ) | (
                    qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal']) &
                    (dataframe['macd'] < 0) &
                    (dataframe['macdhist'] > dataframe['macdhist'].shift(1) * 1.2) &
                    (dataframe['close'] < dataframe['ema_short'])
                ) | (
                    dataframe['trend_reversal_fallback']
                ) | (
                    dataframe['uptrend_breakout_fallback']
                )
                dataframe['short_exit_signal_1m'] = dataframe['short_exit_signal_1m'].astype(int)
            
            if entry_timeframe != self.timeframe:
                try:
                    informative = self.dp.get_pair_dataframe(
                        pair=metadata['pair'], 
                        timeframe=entry_timeframe
                    )
                    
                    informative['rsi'] = ta.RSI(informative, timeperiod=14)
                    
                    stoch = ta.STOCH(informative, fastk_period=14, slowk_period=3, slowd_period=3)
                    informative['slowk'] = stoch['slowk']
                    informative['slowd'] = stoch['slowd']
                    
                    macd = ta.MACD(informative, 
                                fastperiod=macd_fast,
                                slowperiod=macd_slow, 
                                signalperiod=macd_signal)
                    informative['macd'] = macd['macd']
                    informative['macdsignal'] = macd['macdsignal']
                    informative['macdhist'] = macd['macdhist']
                    
                    informative['macdhist_prev1'] = informative['macdhist'].shift(1)
                    informative['macdhist_prev2'] = informative['macdhist'].shift(2)
                    
                    bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(informative), window=20, stds=2)
                    informative['bb_upperband'] = bollinger['upper']
                    informative['bb_middleband'] = bollinger['mid']
                    informative['bb_lowerband'] = bollinger['lower']
                    informative['bb_pct'] = (informative['close'] - bollinger['lower']) / (bollinger['upper'] - bollinger['lower'])
                    
                    informative['ema_short'] = ta.EMA(informative, timeperiod=ema_short_period)
                    informative['ema_long'] = ta.EMA(informative, timeperiod=ema_long_period)
                    
                    for i in range(1, 4):
                        informative[f'close_prev{i}'] = informative['close'].shift(i)
                        informative[f'high_prev{i}'] = informative['high'].shift(i)
                        informative[f'low_prev{i}'] = informative['low'].shift(i)
                    
                    informative = self.calculate_confluence_score(informative, coin)
                    
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
                    
                    informative['enhanced_short_entry'] = (
                        (informative['price_peak'] | informative['price_reversal'] | informative['macd_reversal']) &
                        informative['high_confluence'] &
                        (informative['close'] > informative['ema_short'] * (1 + price_extension_pct))
                    )
                    
                    for col in ['enhanced_short_entry', 'price_peak', 'price_reversal', 'macd_reversal', 'high_confluence']:
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
        
        dataframe = self.calculate_confluence_score(dataframe, coin)
        
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
       
        dataframe['enhanced_short_entry'] = (
           (dataframe['price_peak'] | dataframe['price_reversal'] | dataframe['macd_reversal']) &
           dataframe['high_confluence'] &
           (dataframe['close'] > dataframe['ema_short'] * (1 + price_extension_pct))
        )
       
        dataframe[f'enhanced_short_entry_{self.timeframe}'] = dataframe['enhanced_short_entry'].astype(int)
       
        return dataframe

    def adjust_parameters_from_model(self, dataframe: DataFrame, metadata: dict) -> Dict:
       coin = self.get_coin_from_pair(metadata['pair'])
       
       adjusted_params = {
           'leverage_param': self.get_param_value(coin, 'leverage_param'),
           'buy_rsi': self.get_param_value(coin, 'buy_rsi'),
           'sell_rsi_upper': self.get_param_value(coin, 'sell_rsi_upper'),
           'sell_rsi_lower': self.get_param_value(coin, 'sell_rsi_lower'),
           'price_extension_pct': self.get_param_value(coin, 'price_extension_pct')
       }
       
       if 'prediction_probability' in dataframe.columns and len(dataframe) > 0:
           prob = dataframe['prediction_probability'].iloc[-1]
           
           if prob > 0.8:
               adjusted_params['leverage_param'] = min(int(adjusted_params['leverage_param'] * 1.2), 5)
               adjusted_params['price_extension_pct'] = max(adjusted_params['price_extension_pct'] * 0.9, 0.004)
           elif prob < 0.4:
               adjusted_params['leverage_param'] = max(int(adjusted_params['leverage_param'] * 0.8), 1)
               adjusted_params['price_extension_pct'] = min(adjusted_params['price_extension_pct'] * 1.2, 0.008)
               
           if 'market_trend' in dataframe.columns:
               trend = dataframe['market_trend'].iloc[-1]
               if trend > 0.5:
                   adjusted_params['sell_rsi_upper'] = min(adjusted_params['sell_rsi_upper'] + 5, 85)
               else:
                   adjusted_params['sell_rsi_upper'] = max(adjusted_params['sell_rsi_upper'] - 5, 70)
       
       return adjusted_params

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
       dataframe['enter_long'] = 0
       dataframe['enter_short'] = 0
       
       coin = self.get_coin_from_pair(metadata['pair'])
       
       if hasattr(self, 'freqai') and self.freqai and 'prediction' in dataframe.columns:
           last_candle = dataframe.iloc[-1].squeeze() if len(dataframe) > 0 else None
           
           if last_candle is not None:
               prediction_value = last_candle['prediction']
               
               threshold = 0.7
               if 'market_trend' in dataframe.columns:
                   market_trend = last_candle['market_trend']
                   if market_trend > 0.7:
                       threshold = 0.8
                   elif market_trend < 0.3:
                       threshold = 0.6
               
               dataframe.loc[
                   (dataframe['prediction'] > threshold) & 
                   (dataframe['volume'] > 0),
                   'enter_short'
               ] = 1
       else:
           entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
           entry_signal_col = f'enhanced_short_entry_{entry_timeframe}'
           
           if entry_signal_col in dataframe.columns:
               dataframe.loc[dataframe[entry_signal_col] > 0, 'enter_short'] = 1
           else:
               dataframe.loc[dataframe['enhanced_short_entry'] > 0, 'enter_short'] = 1
       
       return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
       dataframe['exit_long'] = 0
       dataframe['exit_short'] = 0
       
       coin = self.get_coin_from_pair(metadata['pair'])
       
       dataframe['volume_avg_10'] = dataframe['volume'].rolling(10).mean()
       
       dataframe['trend_reversal_confirmed'] = (
           (dataframe['macd'] > dataframe['macdsignal']) &
           (dataframe['macdhist'] > 0) &
           (dataframe['macdhist'] > dataframe['macdhist'].shift(1)) &
           (dataframe['macdhist'].shift(1) > dataframe['macdhist'].shift(2)) &
           (dataframe['close'] > dataframe['ema_short']) &
           (dataframe['rsi'] > 45) &
           (dataframe['close'] > dataframe['close'].shift(1))
       )
       
       dataframe['volume_confirmed_reversal'] = (
           dataframe['trend_reversal_confirmed'] &
           (dataframe['volume'] > dataframe['volume_avg_10'] * 1.2)
       )
       
       dataframe['strong_uptrend_formation'] = (
           (dataframe['close'] > dataframe['ema_short'] * 1.01) &
           (dataframe['ema_short'] > dataframe['ema_long']) &
           (dataframe['close'] > dataframe['high'].shift(1)) &
           (dataframe['rsi'] > 50) &
           (dataframe['macdhist'] > dataframe['macdhist'].shift(1) * 1.3)
       )
       
       dataframe['emergency_reversal'] = (
           (dataframe['rsi'] > 65) &
           (dataframe['close'] > dataframe['bb_upperband']) &
           (dataframe['macdhist'] > dataframe['macdhist'].shift(1) * 1.5) &
           (dataframe['close'] > dataframe['close'].shift(1) * 1.005)
       )
       
       if 'short_exit_signal_1m' in dataframe.columns:
           dataframe.loc[
               (dataframe['short_exit_signal_1m'] > 0) |
               (dataframe['volume_confirmed_reversal']) |
               (dataframe['strong_uptrend_formation']) |
               (dataframe['emergency_reversal']),
               'exit_short'
           ] = 1
       else:
           dataframe.loc[
               (dataframe['volume_confirmed_reversal']) |
               (dataframe['strong_uptrend_formation']) |
               (dataframe['emergency_reversal']),
               'exit_short'
           ] = 1
       
       return dataframe
   
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                          time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                          side: str, **kwargs) -> bool:
       if side != 'short':
           return True
           
       coin = self.get_coin_from_pair(pair)
       
       cooldown_minutes = 3 if 'bull' in self._market_regime else 5
       if pair in self._last_candle_seen_time:
           last_time = self._last_candle_seen_time[pair]
           if current_time - last_time < timedelta(minutes=cooldown_minutes):
               return False
       
       dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
       
       if hasattr(self, 'freqai') and self.freqai and len(dataframe) > 0:
           adjusted_params = self.adjust_parameters_from_model(dataframe, {'pair': pair})
           
           if coin in self._coin_parameters and 'leverage_param' in adjusted_params:
               if 'leverage_param' in self._coin_parameters[coin]:
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
               
               if not hasattr(self, '_trade_start_reset_times'):
                   self._trade_start_reset_times = {}
               
               effective_start_time = self._trade_start_reset_times.get(trade.id, trade.open_date_utc)
               
               dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
               if len(dataframe) > 0:
                   last_candle = dataframe.iloc[-1]
                   
                   entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
                   entry_signal_col = f'enhanced_short_entry_{entry_timeframe}'
                   
                   if (entry_signal_col in last_candle and last_candle[entry_signal_col] > 0) or last_candle.get('enhanced_short_entry', 0) > 0:
                       if current_rate > trade.open_rate:
                           self._trade_start_reset_times[trade.id] = current_time
                           return None
               
               if len(dataframe) >= 3:
                   current_candle = dataframe.iloc[-1]
                   prev_candle = dataframe.iloc[-2]
                   prev2_candle = dataframe.iloc[-3]
                   
                   trend_reversal_confirmed = (
                       (current_candle['macd'] > current_candle['macdsignal']) &
                       (current_candle['macdhist'] > 0) &
                       (current_candle['macdhist'] > prev_candle['macdhist']) &
                       (prev_candle['macdhist'] > prev2_candle['macdhist']) &
                       (current_candle['close'] > current_candle['ema_short']) &
                       (current_candle['rsi'] > 45) &
                       (current_candle['close'] > prev_candle['close'])
                   )
                   
                   volume_confirmed_reversal = (
                       trend_reversal_confirmed &
                       (current_candle['volume'] > dataframe['volume'].rolling(10).mean().iloc[-1] * 1.2)
                   )
                   
                   strong_uptrend_formation = (
                       (current_candle['close'] > current_candle['ema_short'] * 1.01) &
                       (current_candle['ema_short'] > current_candle['ema_long']) &
                       (current_candle['close'] > prev_candle['high']) &
                       (current_candle['rsi'] > 50) &
                       (current_candle['macdhist'] > prev_candle['macdhist'] * 1.3)
                   )
                   
                   if volume_confirmed_reversal:
                       return 'downtrend_finished_volume_confirmed'
                   
                   if strong_uptrend_formation and current_profit > 0.005:
                       return 'strong_uptrend_formation'
                   
                   emergency_stop = (
                       (current_candle['close'] > trade.open_rate * 1.03) &
                       (current_candle['rsi'] > 65) &
                       (current_candle['close'] > current_candle['bb_upperband'])
                   )
                   
                   if emergency_stop:
                       return 'emergency_trend_reversal'
               
               if hasattr(self, 'freqai') and self.freqai and 'prediction' in dataframe.columns:
                   if 'prediction' in last_candle and last_candle['prediction'] < 0.15:
                       if current_profit > 0.015:
                           return 'freqai_strong_reversal_predicted'
               
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
           'confluence_threshold': self.confluence_threshold.value,
           'market_regime': self._market_regime
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
