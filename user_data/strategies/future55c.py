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

class future55c(IStrategy):
    minimal_roi = {
        "0": 0.05,
        "10": 0.04,
        "30": 0.02,
        "60": 0.01,
        "150": 0.005,
        "340": 0
    }

    stoploss = -0.30
    
    trailing_stop = True
    trailing_stop_positive = 0.08
    trailing_stop_positive_offset = 0.12
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    process_only_new_candles = True

    # Leverage Parameters
    leverage_param_high_vol = IntParameter(2, 5, default=3, space="buy", optimize=True)
    leverage_param_medium_vol = IntParameter(3, 6, default=4, space="buy", optimize=True)
    leverage_param_low_vol = IntParameter(4, 8, default=6, space="buy", optimize=True)
    
    # --- LONG (BUY) PARAMETERS ---
    buy_rsi_lower = IntParameter(20, 40, default=30, space="buy", optimize=True)
    buy_price_extension_pct = DecimalParameter(0.002, 0.008, default=0.004, space="buy", optimize=True)
    
    # Kept these for legacy compatibility or specific aggressive/conservative switching
    buy_rsi_aggressive = IntParameter(25, 40, default=35, space="buy", optimize=True)
    buy_rsi_conservative = IntParameter(40, 55, default=47, space="buy", optimize=True)
    
    # --- SHORT (SELL) PARAMETERS ---
    sell_rsi_upper_bear = IntParameter(65, 80, default=72, space="sell", optimize=True)
    sell_rsi_upper_bull = IntParameter(75, 90, default=82, space="sell", optimize=True)
    sell_rsi_lower = IntParameter(15, 35, default=25, space="sell", optimize=True)
    
    # --- FILTERS ---
    trend_strength_threshold = DecimalParameter(0.5, 0.8, default=0.65, space="buy", optimize=True)
    price_position_48h_threshold = DecimalParameter(0.15, 0.30, default=0.20, space="buy", optimize=True)
    price_position_48h_top_threshold = DecimalParameter(0.70, 0.90, default=0.80, space="buy", optimize=True) # Don't long if too high
    
    strong_uptrend_threshold = DecimalParameter(0.025, 0.05, default=0.03, space="buy", optimize=True)
    strong_downtrend_threshold = DecimalParameter(0.025, 0.05, default=0.03, space="buy", optimize=True) # Mirror for longs
    uptrend_period = IntParameter(20, 40, default=30, space="buy", optimize=True)
    
    # --- INDICATORS ---
    macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
    macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
    
    ema_short_period = IntParameter(5, 15, default=8, space="both", optimize=True)
    ema_long_period = IntParameter(15, 30, default=21, space="both", optimize=True)
    ema_trend_period = IntParameter(50, 100, default=75, space="both", optimize=True)
    
    # Short Extensions
    price_extension_pct_conservative = DecimalParameter(0.004, 0.008, default=0.006, space="sell", optimize=True)
    price_extension_pct_aggressive = DecimalParameter(0.002, 0.006, default=0.004, space="sell", optimize=True)
    
    confluence_threshold = IntParameter(6, 10, default=8, space="buy", optimize=True)
    volume_spike_threshold = DecimalParameter(1.5, 3.0, default=2.0, space="buy", optimize=True)
    
    timeframe = '5m'
    entry_timeframe = CategoricalParameter(['5m', '15m'], default='15m', space='buy', optimize=True)
    
    startup_candle_count = 600
    
    # ENABLE BOTH SIDES
    can_short = True
    can_long = True

    _last_candle_seen_time = {}
    _coin_list = []
    _coin_parameters = {}
    _coin_roi = {}
    _coin_trailing_stop = {}
    _trade_start_reset_times = {}
    _coin_categories = {}
    _market_regime = "bear_high_vol"
    _regime_update_time = None
    _trend_strength_cache = {}

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
        self._trend_strength_cache = {}
        
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
            
            setattr(self, f"{coin}_leverage_param", IntParameter(1, 6, default=3, space="buy", optimize=True))
            self._coin_parameters[coin]['leverage_param'] = getattr(self, f"{coin}_leverage_param")
            
            # Long params per coin
            setattr(self, f"{coin}_buy_rsi_lower", IntParameter(20, 45, default=30, space="buy", optimize=True))
            self._coin_parameters[coin]['buy_rsi_lower'] = getattr(self, f"{coin}_buy_rsi_lower")

            setattr(self, f"{coin}_buy_price_extension_pct", DecimalParameter(0.002, 0.008, default=0.004, space="buy", optimize=True))
            self._coin_parameters[coin]['buy_price_extension_pct'] = getattr(self, f"{coin}_buy_price_extension_pct")

            # Short params per coin
            setattr(self, f"{coin}_sell_rsi_upper", IntParameter(65, 85, default=75, space="sell", optimize=True))
            self._coin_parameters[coin]['sell_rsi_upper'] = getattr(self, f"{coin}_sell_rsi_upper")
            
            setattr(self, f"{coin}_sell_rsi_lower", IntParameter(15, 35, default=25, space="sell", optimize=True))
            self._coin_parameters[coin]['sell_rsi_lower'] = getattr(self, f"{coin}_sell_rsi_lower")
            
            setattr(self, f"{coin}_price_extension_pct", DecimalParameter(0.002, 0.006, default=0.003, space="sell", optimize=True))
            self._coin_parameters[coin]['price_extension_pct'] = getattr(self, f"{coin}_price_extension_pct")
            
            # General indicators per coin
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
            
            setattr(self, f"{coin}_ema_trend_period", IntParameter(50, 100, default=75, space="both", optimize=True))
            self._coin_parameters[coin]['ema_trend_period'] = getattr(self, f"{coin}_ema_trend_period")
            
            setattr(self, f"{coin}_entry_timeframe", CategoricalParameter(['5m', '15m'], default='5m', space='buy', optimize=True))
            self._coin_parameters[coin]['entry_timeframe'] = getattr(self, f"{coin}_entry_timeframe")
            
            setattr(self, f"{coin}_confluence_threshold", IntParameter(3, 6, default=4, space="buy", optimize=True))
            self._coin_parameters[coin]['confluence_threshold'] = getattr(self, f"{coin}_confluence_threshold")
            
            setattr(self, f"{coin}_volume_spike_threshold", DecimalParameter(1.5, 3.0, default=2.0, space="buy", optimize=True))
            self._coin_parameters[coin]['volume_spike_threshold'] = getattr(self, f"{coin}_volume_spike_threshold")
            
            # ROI and Trailing stop (Shared logic, can be split if needed)
            self._coin_roi[coin] = {}
            
            setattr(self, f"{coin}_roi_t1", IntParameter(10, 60, default=30, space="sell", optimize=True))
            self._coin_roi[coin]['t1'] = getattr(self, f"{coin}_roi_t1")
            
            setattr(self, f"{coin}_roi_t2", IntParameter(61, 180, default=90, space="sell", optimize=True))
            self._coin_roi[coin]['t2'] = getattr(self, f"{coin}_roi_t2")
            
            setattr(self, f"{coin}_roi_t3", IntParameter(181, 360, default=240, space="sell", optimize=True))
            self._coin_roi[coin]['t3'] = getattr(self, f"{coin}_roi_t3")
            
            setattr(self, f"{coin}_roi_p1", DecimalParameter(0.02, 0.08, default=0.05, space="sell", optimize=True))
            self._coin_roi[coin]['p1'] = getattr(self, f"{coin}_roi_p1")
            
            setattr(self, f"{coin}_roi_p2", DecimalParameter(0.01, 0.04, default=0.025, space="sell", optimize=True))
            self._coin_roi[coin]['p2'] = getattr(self, f"{coin}_roi_p2")
            
            setattr(self, f"{coin}_roi_p3", DecimalParameter(0.005, 0.02, default=0.012, space="sell", optimize=True))
            self._coin_roi[coin]['p3'] = getattr(self, f"{coin}_roi_p3")
            
            self._coin_trailing_stop[coin] = {}
            
            setattr(self, f"{coin}_trailing_stop", CategoricalParameter([True, False], default=True, space="sell", optimize=True))
            self._coin_trailing_stop[coin]['trailing_stop'] = getattr(self, f"{coin}_trailing_stop")
            
            setattr(self, f"{coin}_trailing_stop_positive", DecimalParameter(0.008, 0.25, default=0.12, space="sell", optimize=True))
            self._coin_trailing_stop[coin]['trailing_stop_positive'] = getattr(self, f"{coin}_trailing_stop_positive")
            
            setattr(self, f"{coin}_trailing_stop_positive_offset", DecimalParameter(0.01, 0.3, default=0.18, space="sell", optimize=True))
            self._coin_trailing_stop[coin]['trailing_stop_positive_offset'] = getattr(self, f"{coin}_trailing_stop_positive_offset")
            
            setattr(self, f"{coin}_trailing_only_offset_is_reached", CategoricalParameter([True, False], default=True, space="sell", optimize=True))
            self._coin_trailing_stop[coin]['trailing_only_offset_is_reached'] = getattr(self, f"{coin}_trailing_only_offset_is_reached")
            
            setattr(self, f"{coin}_stoploss", DecimalParameter(-0.4, -0.05, default=-0.15, space="sell", optimize=True))
            self._coin_trailing_stop[coin]['stoploss'] = getattr(self, f"{coin}_stoploss")
    
    def get_coin_from_pair(self, pair: str) -> str:
        if '/' in pair:
            return pair.split('/')[0]
        return "UNKNOWN"
    
    def get_coin_category(self, coin: str) -> str:
        return self._coin_categories.get(coin, 'medium_vol')
    
    def calculate_trend_strength(self, dataframe: DataFrame) -> float:
        if len(dataframe) < 100:
            return 0.5
            
        ema_short = ta.EMA(dataframe, timeperiod=8).iloc[-1]
        ema_long = ta.EMA(dataframe, timeperiod=21).iloc[-1]
        ema_trend = ta.EMA(dataframe, timeperiod=75).iloc[-1]
        
        close = dataframe['close'].iloc[-1]
        
        short_trend = 1 if close > ema_short else 0
        medium_trend = 1 if close > ema_long else 0
        long_trend = 1 if close > ema_trend else 0
        
        returns_5 = (close / dataframe['close'].iloc[-5] - 1) if len(dataframe) > 5 else 0
        returns_20 = (close / dataframe['close'].iloc[-20] - 1) if len(dataframe) > 20 else 0
        
        momentum_score = 0
        if returns_5 > 0.02:
            momentum_score += 0.5
        if returns_20 > 0.05:
            momentum_score += 0.5
            
        macd_trend = 1 if dataframe['macd'].iloc[-1] > dataframe['macdsignal'].iloc[-1] else 0
        volume_trend = 1 if dataframe['volume'].iloc[-1] > dataframe['volume'].rolling(20).mean().iloc[-1] else 0
        
        trend_strength = (
            short_trend * 0.25 +
            medium_trend * 0.25 +
            long_trend * 0.2 +
            momentum_score * 0.15 +
            macd_trend * 0.1 +
            volume_trend * 0.05
        )
        
        return trend_strength
    
    def detect_market_regime(self, dataframe: DataFrame) -> str:
        if len(dataframe) < 200:
            return self._market_regime
            
        ema_50 = ta.EMA(dataframe, timeperiod=50)
        ema_200 = ta.EMA(dataframe, timeperiod=200)
        
        volatility = dataframe['close'].rolling(20).std()
        avg_volatility = volatility.rolling(100).mean()
        
        current_trend = ema_50.iloc[-1] > ema_200.iloc[-1]
        current_volatility = volatility.iloc[-1] / avg_volatility.iloc[-1]
        
        recent_high = dataframe['high'].rolling(50).max().iloc[-1]
        recent_low = dataframe['low'].rolling(50).min().iloc[-1]
        price_position = (dataframe['close'].iloc[-1] - recent_low) / (recent_high - recent_low)
        
        if current_trend and current_volatility < 1.2 and price_position > 0.7:
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
        
        # Categorical Defaults
        category_defaults = {
            'high_vol': {
                'leverage_param': self.leverage_param_high_vol.value,
                'buy_rsi': self.buy_rsi_aggressive.value, # Used if specific buy_rsi_lower not set
                'price_extension_pct': self.price_extension_pct_aggressive.value,
                'volume_spike_threshold': self.volume_spike_threshold.value
            },
            'medium_vol': {
                'leverage_param': self.leverage_param_medium_vol.value,
                'buy_rsi': self.buy_rsi_conservative.value,
                'price_extension_pct': self.price_extension_pct_conservative.value,
                'volume_spike_threshold': self.volume_spike_threshold.value
            },
            'low_vol': {
                'leverage_param': self.leverage_param_low_vol.value,
                'buy_rsi': self.buy_rsi_conservative.value,
                'price_extension_pct': self.price_extension_pct_conservative.value,
                'volume_spike_threshold': self.volume_spike_threshold.value
            }
        }
        
        if param_name in category_defaults[category]:
            return category_defaults[category][param_name]
        
        defaults = {
            'leverage_param': 3,
            'buy_rsi_lower': 30, # Default for longs
            'buy_price_extension_pct': 0.004,
            'sell_rsi_upper': self.sell_rsi_upper_bear.value if 'bear' in self._market_regime else self.sell_rsi_upper_bull.value,
            'sell_rsi_lower': self.sell_rsi_lower.value,
            'price_extension_pct': 0.003,
            'macd_fast': self.macd_fast.value,
            'macd_slow': self.macd_slow.value,
            'macd_signal': self.macd_signal.value,
            'ema_short_period': self.ema_short_period.value,
            'ema_long_period': self.ema_long_period.value,
            'ema_trend_period': self.ema_trend_period.value,
            'entry_timeframe': self.entry_timeframe.value,
            'confluence_threshold': self.confluence_threshold.value,
            'volume_spike_threshold': self.volume_spike_threshold.value
        }
        
        value = defaults.get(param_name, 1.0)
        
        regime_adjustments = {
            'bull_low_vol': {'leverage_mult': 0.5, 'rsi_adj': +15, 'ext_mult': 1.5},
            'bull_high_vol': {'leverage_mult': 0.4, 'rsi_adj': +20, 'ext_mult': 2.0},
            'bear_low_vol': {'leverage_mult': 1.5, 'rsi_adj': -5, 'ext_mult': 0.7},
            'bear_high_vol': {'leverage_mult': 1.2, 'rsi_adj': -2, 'ext_mult': 0.9}
        }
        
        adj = regime_adjustments.get(self._market_regime, regime_adjustments['bear_high_vol'])
        
        if param_name == 'leverage_param':
            value = max(1, int(value * adj['leverage_mult']))
        elif param_name == 'sell_rsi_upper':
            value += adj['rsi_adj']
        elif param_name == 'price_extension_pct':
            value *= adj['ext_mult']
        
        return value

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = []
        
        for pair in pairs:
            informative_pairs.append((pair, '1m'))
            informative_pairs.append((pair, '1h'))
            
            coin = self.get_coin_from_pair(pair)
            entry_tf = self.get_param_value(coin, 'entry_timeframe')
            if entry_tf != self.timeframe:
                informative_pairs.append((pair, entry_tf))
        
        return informative_pairs

    def calculate_confluence_score(self, dataframe: DataFrame, coin: str) -> DataFrame:
        sell_rsi_upper = float(self.get_param_value(coin, 'sell_rsi_upper'))
        buy_rsi_lower = float(self.get_param_value(coin, 'buy_rsi_lower'))
        price_extension_pct = float(self.get_param_value(coin, 'price_extension_pct'))
        buy_price_extension_pct = float(self.get_param_value(coin, 'buy_price_extension_pct'))
        volume_spike_threshold = float(self.get_param_value(coin, 'volume_spike_threshold'))
        
        dataframe['volume_avg'] = dataframe['volume'].rolling(20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_avg']
        
        # --- SHORT SIGNALS ---
        short_signals = {}
        
        short_signals['rsi_signal'] = (dataframe['rsi'] > sell_rsi_upper).astype(int) * 3
        
        short_signals['rsi_divergence'] = (
            (dataframe['high'] > dataframe['high'].shift(1)) &
            (dataframe['rsi'] < dataframe['rsi'].shift(1)) &
            (dataframe['rsi'] > sell_rsi_upper - 5)
        ).astype(int) * 4
        
        short_signals['bb_signal'] = (dataframe['bb_pct'] > 0.90).astype(int) * 3
        
        short_signals['macd_signal'] = (
            (dataframe['macdhist'] < dataframe['macdhist'].shift(1)) &
            (dataframe['macdhist'].shift(1) > 0) &
            (dataframe['macdhist'].shift(1) > dataframe['macdhist'].shift(2))
        ).astype(int) * 3
        
        short_signals['volume_spike'] = (dataframe['volume_ratio'] > volume_spike_threshold).astype(int) * 2
        short_signals['trend_signal'] = (dataframe['close'] > dataframe['ema_short']).astype(int) * 1
        
        short_signals['extension_signal'] = (
            dataframe['close'] > dataframe['ema_short'] * (1 + price_extension_pct)
        ).astype(int) * 3
        
        short_signals['shooting_star'] = (
            ((dataframe['high'] - dataframe['close']) > 2 * abs(dataframe['close'] - dataframe['open'])) &
            ((dataframe['close'] - dataframe['low']) < 0.3 * (dataframe['high'] - dataframe['low']))
        ).astype(int) * 2
        
        dataframe['confluence_score'] = sum(short_signals.values())
        confluence_threshold = int(self.get_param_value(coin, 'confluence_threshold'))
        dataframe['high_confluence'] = dataframe['confluence_score'] >= confluence_threshold
        
        # --- LONG SIGNALS ---
        long_signals = {}
        
        long_signals['rsi_signal'] = (dataframe['rsi'] < buy_rsi_lower).astype(int) * 3
        
        long_signals['rsi_divergence'] = (
            (dataframe['low'] < dataframe['low'].shift(1)) &
            (dataframe['rsi'] > dataframe['rsi'].shift(1)) &
            (dataframe['rsi'] < buy_rsi_lower + 5)
        ).astype(int) * 4
        
        long_signals['bb_signal'] = (dataframe['bb_pct'] < 0.10).astype(int) * 3
        
        long_signals['macd_signal'] = (
            (dataframe['macdhist'] > dataframe['macdhist'].shift(1)) &
            (dataframe['macdhist'].shift(1) < 0) &
            (dataframe['macdhist'].shift(1) < dataframe['macdhist'].shift(2))
        ).astype(int) * 3
        
        long_signals['volume_spike'] = (dataframe['volume_ratio'] > volume_spike_threshold).astype(int) * 2
        long_signals['trend_signal'] = (dataframe['close'] < dataframe['ema_short']).astype(int) * 1
        
        long_signals['extension_signal'] = (
            dataframe['close'] < dataframe['ema_short'] * (1 - buy_price_extension_pct)
        ).astype(int) * 3
        
        long_signals['hammer'] = (
            ((dataframe['close'] - dataframe['low']) > 2 * abs(dataframe['close'] - dataframe['open'])) &
            ((dataframe['high'] - dataframe['close']) < 0.3 * (dataframe['high'] - dataframe['low']))
        ).astype(int) * 2
        
        dataframe['long_confluence_score'] = sum(long_signals.values())
        dataframe['long_high_confluence'] = dataframe['long_confluence_score'] >= confluence_threshold

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
            datetime.now() - self._regime_update_time > timedelta(hours=2)):
            self._market_regime = self.detect_market_regime(dataframe)
            self._regime_update_time = datetime.now()
        
        coin = self.get_coin_from_pair(metadata['pair'])
        
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=self.get_param_value(coin, 'ema_short_period'))
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=self.get_param_value(coin, 'ema_long_period'))
        dataframe['ema_trend'] = ta.EMA(dataframe, timeperiod=self.get_param_value(coin, 'ema_trend_period'))
        
        dataframe['tr'] = ta.ATR(dataframe, timeperiod=14)
        
        macd = ta.MACD(dataframe, 
                     fastperiod=self.get_param_value(coin, 'macd_fast'),
                     slowperiod=self.get_param_value(coin, 'macd_slow'), 
                     signalperiod=self.get_param_value(coin, 'macd_signal'))
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_pct'] = (dataframe['close'] - bollinger['lower']) / (bollinger['upper'] - bollinger['lower'])
        
        trend_strength = self.calculate_trend_strength(dataframe)
        self._trend_strength_cache[metadata['pair']] = trend_strength
        dataframe['trend_strength'] = trend_strength
        
        lookback_48h = 576
        dataframe['high_48h'] = dataframe['high'].rolling(window=lookback_48h, min_periods=1).max()
        dataframe['low_48h'] = dataframe['low'].rolling(window=lookback_48h, min_periods=1).min()
        
        dataframe['price_position_48h'] = (
            (dataframe['close'] - dataframe['low_48h']) / 
            (dataframe['high_48h'] - dataframe['low_48h'])
        ).fillna(0.5)
        
        uptrend_period = int(self.uptrend_period.value)
        dataframe['price_change_pct'] = (
            (dataframe['close'] - dataframe['close'].shift(uptrend_period)) / 
            dataframe['close'].shift(uptrend_period)
        ).fillna(0)
        
        dataframe['ema_rising'] = (
            dataframe['ema_short'] > dataframe['ema_short'].shift(5)
        ).astype(int)
        dataframe['ema_falling'] = (
            dataframe['ema_short'] < dataframe['ema_short'].shift(5)
        ).astype(int)
        
        dataframe['bullish_alignment'] = (
            (dataframe['close'] > dataframe['ema_short']) &
            (dataframe['ema_short'] > dataframe['ema_long'])
        ).astype(int)
        
        green_candles = (dataframe['close'] > dataframe['open']).astype(int)
        red_candles = (dataframe['close'] < dataframe['open']).astype(int)
        dataframe['consecutive_green'] = green_candles.rolling(window=5).sum()
        dataframe['consecutive_red'] = red_candles.rolling(window=5).sum()
        
        dataframe['strong_uptrend'] = (
            (dataframe['price_change_pct'] > self.strong_uptrend_threshold.value) &
            (dataframe['ema_rising'] == 1) &
            (dataframe['consecutive_green'] >= 3)
        ).astype(int)
        
        # Mirror strong downtrend for Long filters
        dataframe['strong_downtrend'] = (
            (dataframe['price_change_pct'] < -self.strong_downtrend_threshold.value) &
            (dataframe['ema_falling'] == 1) &
            (dataframe['consecutive_red'] >= 3)
        ).astype(int)
        
        if self.dp:
            # --- 1M INFORMATIVE ---
            try:
                informative_1m = self.dp.get_pair_dataframe(
                    pair=metadata['pair'], 
                    timeframe='1m'
                )
                
                informative_1m['rsi'] = ta.RSI(informative_1m, timeperiod=14)
                informative_1m['ema_short'] = ta.EMA(informative_1m, timeperiod=self.get_param_value(coin, 'ema_short_period'))
                
                bollinger_1m = qtpylib.bollinger_bands(qtpylib.typical_price(informative_1m), window=20, stds=2)
                informative_1m['bb_upperband'] = bollinger_1m['upper']
                informative_1m['bb_lowerband'] = bollinger_1m['lower']
                
                macd_1m = ta.MACD(informative_1m, 
                                fastperiod=self.get_param_value(coin, 'macd_fast'),
                                slowperiod=self.get_param_value(coin, 'macd_slow'), 
                                signalperiod=self.get_param_value(coin, 'macd_signal'))
                informative_1m['macd'] = macd_1m['macd']
                informative_1m['macdsignal'] = macd_1m['macdsignal']
                informative_1m['macdhist'] = macd_1m['macdhist']
                
                sell_rsi_lower = float(self.get_param_value(coin, 'sell_rsi_lower'))
                buy_rsi_lower = float(self.get_param_value(coin, 'buy_rsi_lower')) # Reuse or use specific upper exit for longs
                
                # Short Exit Signals
                informative_1m['deep_oversold'] = (
                    (informative_1m['rsi'] < sell_rsi_lower * 0.8) &
                    (informative_1m['close'] < informative_1m['bb_lowerband'] * 1.02) &
                    (informative_1m['close'] < informative_1m['ema_short'] * 0.98)
                )
                
                informative_1m['major_trend_reversal'] = (
                    qtpylib.crossed_above(informative_1m['macd'], informative_1m['macdsignal']) &
                    (informative_1m['macd'] < 0) &
                    (informative_1m['macdhist'] > informative_1m['macdhist'].shift(1) * 1.1) &
                    (informative_1m['close'] < informative_1m['ema_short'])
                )
                
                informative_1m['short_exit_signal'] = (
                    informative_1m['deep_oversold'] | 
                    informative_1m['major_trend_reversal']
                ).astype(int)
                
                # Long Exit Signals (Mirror of Short Exit)
                # Exit if RSI high (70+) and price touches upper band
                informative_1m['deep_overbought'] = (
                    (informative_1m['rsi'] > 70) & # Generic high RSI for exit
                    (informative_1m['close'] > informative_1m['bb_upperband'] * 0.98)
                )
                
                informative_1m['major_trend_reversal_bear'] = (
                    qtpylib.crossed_below(informative_1m['macd'], informative_1m['macdsignal']) &
                    (informative_1m['macd'] > 0)
                )
                
                informative_1m['long_exit_signal'] = (
                    informative_1m['deep_overbought'] |
                    informative_1m['major_trend_reversal_bear']
                ).astype(int)
                
                dataframe = merge_informative_pair(
                    dataframe, 
                    informative_1m[['short_exit_signal', 'long_exit_signal']], 
                    self.timeframe, 
                    '1m', 
                    ffill=True, 
                    append_timeframe=False,
                    suffix='_1m'
                )
                
            except Exception as e:
                dataframe['short_exit_signal_1m'] = 0
                dataframe['long_exit_signal_1m'] = 0
            
            # --- 1H INFORMATIVE ---
            try:
                informative_1h = self.dp.get_pair_dataframe(
                    pair=metadata['pair'], 
                    timeframe='1h'
                )
                
                informative_1h['rsi'] = ta.RSI(informative_1h, timeperiod=14)
                informative_1h['ema_50'] = ta.EMA(informative_1h, timeperiod=50)
                informative_1h['ema_200'] = ta.EMA(informative_1h, timeperiod=200)
                
                # For Shorts: Don't short if strong uptrend
                informative_1h['strong_uptrend'] = (
                    (informative_1h['close'] > informative_1h['ema_50']) &
                    (informative_1h['ema_50'] > informative_1h['ema_200']) &
                    (informative_1h['rsi'] > 50) &
                    (informative_1h['rsi'] < 70)
                )
                
                # For Longs: Don't long if strong downtrend
                informative_1h['strong_downtrend'] = (
                    (informative_1h['close'] < informative_1h['ema_50']) &
                    (informative_1h['ema_50'] < informative_1h['ema_200']) &
                    (informative_1h['rsi'] < 50)
                )
                
                dataframe = merge_informative_pair(
                    dataframe, 
                    informative_1h[['strong_uptrend', 'strong_downtrend']], 
                    self.timeframe, 
                    '1h', 
                    ffill=True, 
                    append_timeframe=False,
                    suffix='_1h'
                )
            except:
                dataframe['strong_uptrend_1h'] = 0
                dataframe['strong_downtrend_1h'] = 0
            
            # --- ENTRY TIMEFRAME INFORMATIVE ---
            entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
            if entry_timeframe != self.timeframe:
                try:
                    informative = self.dp.get_pair_dataframe(
                        pair=metadata['pair'], 
                        timeframe=entry_timeframe
                    )
                    
                    informative['rsi'] = ta.RSI(informative, timeperiod=14)
                    informative['ema_short'] = ta.EMA(informative, timeperiod=self.get_param_value(coin, 'ema_short_period'))
                    informative['ema_trend'] = ta.EMA(informative, timeperiod=self.get_param_value(coin, 'ema_trend_period'))
                    
                    macd = ta.MACD(informative, 
                                fastperiod=self.get_param_value(coin, 'macd_fast'),
                                slowperiod=self.get_param_value(coin, 'macd_slow'), 
                                signalperiod=self.get_param_value(coin, 'macd_signal'))
                    informative['macd'] = macd['macd']
                    informative['macdsignal'] = macd['macdsignal']
                    informative['macdhist'] = macd['macdhist']
                    
                    bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(informative), window=20, stds=2)
                    informative['bb_upperband'] = bollinger['upper']
                    informative['bb_middleband'] = bollinger['mid']
                    informative['bb_lowerband'] = bollinger['lower']
                    informative['bb_pct'] = (informative['close'] - bollinger['lower']) / (bollinger['upper'] - bollinger['lower'])
                    
                    informative = self.calculate_confluence_score(informative, coin)
                    
                    informative['high_last_5'] = informative['high'].rolling(5).max()
                    informative['low_last_5'] = informative['low'].rolling(5).min()
                    
                    # --- SHORT LOGIC ---
                    sell_rsi_upper = float(self.get_param_value(coin, 'sell_rsi_upper'))
                    informative['price_peak'] = (
                        (informative['high'] >= informative['high_last_5'] * 0.998) &
                        (informative['high'] > informative['high'].shift(1)) &
                        (informative['close'] > informative['ema_short']) &
                        (informative['rsi'] > sell_rsi_upper)
                    )
                    
                    informative['price_reversal'] = (
                        (informative['close'].shift(2) < informative['close'].shift(1)) &
                        (informative['close'] < informative['close'].shift(1)) &
                        (informative['close'].shift(1) > informative['close'].shift(1).rolling(5).max().shift(1)) &
                        (informative['rsi'] > sell_rsi_upper * 0.85)
                    )
                    
                    informative['macd_reversal'] = (
                        (informative['macdhist'].shift(2) < informative['macdhist'].shift(1)) &
                        (informative['macdhist'] < informative['macdhist'].shift(1)) &
                        (informative['macdhist'].shift(1) > 0) &
                        (informative['close'] > informative['ema_short'])
                    )
                    
                    informative['enhanced_short_entry'] = (
                        (informative['price_peak'] | informative['price_reversal'] | informative['macd_reversal']) &
                        informative['high_confluence'] &
                        (informative['close'] > informative['ema_short'] * (1 + self.get_param_value(coin, 'price_extension_pct')))
                    )
                    
                    # --- LONG LOGIC ---
                    buy_rsi_lower = float(self.get_param_value(coin, 'buy_rsi_lower'))
                    buy_price_extension_pct = float(self.get_param_value(coin, 'buy_price_extension_pct'))
                    
                    informative['price_dip'] = (
                        (informative['low'] <= informative['low_last_5'] * 1.002) &
                        (informative['low'] < informative['low'].shift(1)) &
                        (informative['close'] < informative['ema_short']) &
                        (informative['rsi'] < buy_rsi_lower)
                    )
                    
                    informative['price_reversal_bullish'] = (
                        (informative['close'].shift(2) > informative['close'].shift(1)) & # Prev was red
                        (informative['close'] > informative['close'].shift(1)) & # Current is green
                        (informative['close'].shift(1) < informative['close'].shift(1).rolling(5).min().shift(1)) & # Made a low
                        (informative['rsi'] < buy_rsi_lower * 1.2)
                    )
                    
                    informative['macd_reversal_bullish'] = (
                        (informative['macdhist'].shift(2) > informative['macdhist'].shift(1)) &
                        (informative['macdhist'] > informative['macdhist'].shift(1)) &
                        (informative['macdhist'].shift(1) < 0) &
                        (informative['close'] < informative['ema_short'])
                    )
                    
                    informative['enhanced_long_entry'] = (
                        (informative['price_dip'] | informative['price_reversal_bullish'] | informative['macd_reversal_bullish']) &
                        informative['long_high_confluence'] &
                        (informative['close'] < informative['ema_short'] * (1 - buy_price_extension_pct))
                    )

                    
                    for col in ['enhanced_short_entry', 'enhanced_long_entry', 'price_peak', 'price_reversal', 'macd_reversal', 'high_confluence']:
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
        
        dataframe['high_last_5'] = dataframe['high'].rolling(5).max()
        dataframe['low_last_5'] = dataframe['low'].rolling(5).min()
        
        sell_rsi_upper = float(self.get_param_value(coin, 'sell_rsi_upper'))
        buy_rsi_lower = float(self.get_param_value(coin, 'buy_rsi_lower'))
        price_extension_pct = float(self.get_param_value(coin, 'price_extension_pct'))
        buy_price_extension_pct = float(self.get_param_value(coin, 'buy_price_extension_pct'))
        
        # --- MAIN TIMEFRAME SHORT LOGIC ---
        dataframe['price_peak'] = (
            (dataframe['high'] >= dataframe['high_last_5'] * 0.998) &
            (dataframe['high'] > dataframe['high'].shift(1)) &
            (dataframe['close'] > dataframe['ema_short']) &
            (dataframe['rsi'] > sell_rsi_upper)
        )

        dataframe['price_reversal'] = (
            (dataframe['close'].shift(2) < dataframe['close'].shift(1)) &
            (dataframe['close'] < dataframe['close'].shift(1)) &
            (dataframe['close'].shift(1) > dataframe['close'].shift(1).rolling(5).max().shift(1)) &
            (dataframe['rsi'] > sell_rsi_upper * 0.85)
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
        
        # --- MAIN TIMEFRAME LONG LOGIC ---
        dataframe['price_dip'] = (
            (dataframe['low'] <= dataframe['low_last_5'] * 1.002) &
            (dataframe['low'] < dataframe['low'].shift(1)) &
            (dataframe['close'] < dataframe['ema_short']) &
            (dataframe['rsi'] < buy_rsi_lower)
        )
        
        dataframe['price_reversal_bullish'] = (
            (dataframe['close'].shift(2) > dataframe['close'].shift(1)) & # Prev was Red
            (dataframe['close'] > dataframe['close'].shift(1)) & # Current Green
            (dataframe['close'].shift(1) < dataframe['close'].shift(1).rolling(5).min().shift(1)) & # Local Bottom
            (dataframe['rsi'] < buy_rsi_lower * 1.25)
        )
        
        dataframe['macd_reversal_bullish'] = (
            (dataframe['macdhist'].shift(2) > dataframe['macdhist'].shift(1)) &
            (dataframe['macdhist'] > dataframe['macdhist'].shift(1)) &
            (dataframe['macdhist'].shift(1) < 0) &
            (dataframe['close'] < dataframe['ema_short'])
        )
        
        dataframe['enhanced_long_entry'] = (
           (dataframe['price_dip'] | dataframe['price_reversal_bullish'] | dataframe['macd_reversal_bullish']) &
           dataframe['long_high_confluence'] &
           (dataframe['close'] < dataframe['ema_short'] * (1 - buy_price_extension_pct))
        )
       
        dataframe[f'enhanced_short_entry_{self.timeframe}'] = dataframe['enhanced_short_entry'].astype(int)
        dataframe[f'enhanced_long_entry_{self.timeframe}'] = dataframe['enhanced_long_entry'].astype(int)
       
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        coin = self.get_coin_from_pair(metadata['pair'])
        trend_strength = self._trend_strength_cache.get(metadata['pair'], 0.5)
        
        entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
        
        # --- SHORT ENTRY LOGIC ---
        if 'price_position_48h' in dataframe.columns:
            not_at_bottom = dataframe['price_position_48h'] > self.price_position_48h_threshold.value
        else:
            not_at_bottom = pd.Series([True] * len(dataframe), index=dataframe.index)
        
        if 'strong_uptrend' in dataframe.columns:
            not_strong_uptrend = dataframe['strong_uptrend'] == 0
        else:
            not_strong_uptrend = pd.Series([True] * len(dataframe), index=dataframe.index)
        
        if trend_strength < self.trend_strength_threshold.value:
            not_strong_uptrend_1h = (dataframe.get('strong_uptrend_1h', 0) == 0)
                
            entry_signal_col = f'enhanced_short_entry_{entry_timeframe}'
            
            signal = dataframe[entry_signal_col] if entry_signal_col in dataframe.columns else dataframe['enhanced_short_entry']
            
            dataframe.loc[
                (signal > 0) & 
                not_strong_uptrend_1h &
                not_at_bottom &
                not_strong_uptrend,
                'enter_short'
            ] = 1
            
        # --- LONG ENTRY LOGIC ---
        # Don't long if we are at the very top of the 48h range
        if 'price_position_48h' in dataframe.columns:
            not_at_top = dataframe['price_position_48h'] < self.price_position_48h_top_threshold.value
        else:
            not_at_top = pd.Series([True] * len(dataframe), index=dataframe.index)
            
        # Don't long if there is a massive crash (strong downtrend) happening, unless it's a clear reversal
        if 'strong_downtrend' in dataframe.columns:
            not_strong_downtrend = dataframe['strong_downtrend'] == 0
        else:
            not_strong_downtrend = pd.Series([True] * len(dataframe), index=dataframe.index)
            
        not_strong_downtrend_1h = (dataframe.get('strong_downtrend_1h', 0) == 0)
        
        # Reuse entry timeframe logic
        entry_signal_col_long = f'enhanced_long_entry_{entry_timeframe}'
        signal_long = dataframe[entry_signal_col_long] if entry_signal_col_long in dataframe.columns else dataframe['enhanced_long_entry']
        
        dataframe.loc[
            (signal_long > 0) &
            not_at_top &
            not_strong_downtrend &
            not_strong_downtrend_1h,
            'enter_long'
        ] = 1
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        # --- SHORT EXIT ---
        if 'short_exit_signal_1m' in dataframe.columns:
            dataframe.loc[dataframe['short_exit_signal_1m'] > 0, 'exit_short'] = 1
        else:
            coin = self.get_coin_from_pair(metadata['pair'])
            sell_rsi_lower = float(self.get_param_value(coin, 'sell_rsi_lower'))
            
            exit_signal = (
                (dataframe['rsi'] < sell_rsi_lower * 0.8) &
                (dataframe['close'] < dataframe['bb_lowerband'] * 1.02) &
                (dataframe['close'] < dataframe['ema_short'] * 0.98)
            ) | (
                qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal']) &
                (dataframe['macd'] < 0) &
                (dataframe['macdhist'] > dataframe['macdhist'].shift(1) * 1.1) &
                (dataframe['close'] < dataframe['ema_short'])
            )
            
            dataframe.loc[exit_signal, 'exit_short'] = 1
            
        # --- LONG EXIT ---
        if 'long_exit_signal_1m' in dataframe.columns:
            dataframe.loc[dataframe['long_exit_signal_1m'] > 0, 'exit_long'] = 1
        else:
            exit_signal_long = (
                (dataframe['rsi'] > 75) & # High RSI
                (dataframe['close'] > dataframe['bb_upperband'] * 0.98) 
            ) | (
                qtpylib.crossed_below(dataframe['macd'], dataframe['macdsignal']) &
                (dataframe['macd'] > 0)
            )
            dataframe.loc[exit_signal_long, 'exit_long'] = 1
        
        return dataframe
   
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                          time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                          side: str, **kwargs) -> bool:
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        cooldown_minutes = 2 if 'bear' in self._market_regime else 3
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False

        if len(dataframe) > 0:
            # --- SHORT CONFIRMATION ---
            if side == 'short':
                trend_strength = self.calculate_trend_strength(dataframe)
                if trend_strength > self.trend_strength_threshold.value + 0.1:
                    return False
                
                if 'price_position_48h' in dataframe.columns:
                    current_position = dataframe['price_position_48h'].iloc[-1]
                    if current_position < self.price_position_48h_threshold.value:
                        return False
                
                if 'strong_uptrend' in dataframe.columns and dataframe['strong_uptrend'].iloc[-1] == 1:
                    return False
            
            # --- LONG CONFIRMATION ---
            if side == 'long':
                if 'price_position_48h' in dataframe.columns:
                    current_position = dataframe['price_position_48h'].iloc[-1]
                    # Don't long if we are already at the ceiling
                    if current_position > self.price_position_48h_top_threshold.value:
                        return False
                
                if 'strong_downtrend' in dataframe.columns and dataframe['strong_downtrend'].iloc[-1] == 1:
                    return False

        self._last_candle_seen_time[pair] = current_time
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                  current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) == 0:
            return None
            
        last_candle = dataframe.iloc[-1]
        coin = self.get_coin_from_pair(pair)
        
        if not hasattr(self, '_trade_start_reset_times'):
            self._trade_start_reset_times = {}
        
        effective_start_time = self._trade_start_reset_times.get(trade.id, trade.open_date_utc)
        trade_duration = (current_time - effective_start_time).total_seconds() / 60

        # --- SHORT CUSTOM EXIT ---
        if trade.is_short:
            try:
                if 'atr' in last_candle:
                    atr_multiplier = 2.5 if current_profit > 0.02 else 3.0
                    dynamic_exit_price = trade.open_rate - (last_candle['atr'] * atr_multiplier)
                    if current_rate <= dynamic_exit_price and current_profit > 0.01:
                        return 'atr_based_exit'
                
                entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
                entry_signal_col = f'enhanced_short_entry_{entry_timeframe}'
                
                if (entry_signal_col in last_candle and last_candle[entry_signal_col] > 0) or last_candle.get('enhanced_short_entry', 0) > 0:
                    if current_rate > trade.open_rate and current_profit < -0.01:
                        self._trade_start_reset_times[trade.id] = current_time
                        return None
                    elif current_profit > 0.005:
                        return 'new_signal_profitable_exit'
                
                # Time based ROI for shorts
                roi_thresholds = {
                    'high_vol': {"0": 0.04, "1": 0.03, "3": 0.02, "10": 0.01, "30": 0},
                    'medium_vol': {"0": 0.035, "2": 0.025, "5": 0.015, "20": 0.005, "45": 0},
                    'low_vol': {"0": 0.03, "3": 0.02, "10": 0.01, "30": 0.003, "90": 0}
                }
                
                category = self.get_coin_category(coin)
                roi_table = roi_thresholds[category]
                
                roi_threshold = None
                for time_threshold, roi_value in sorted(roi_table.items(), key=lambda x: int(x[0]) if x[0] != "0" else 0):
                    if trade_duration >= int(time_threshold):
                        roi_threshold = roi_value
                
                if roi_threshold is not None and current_profit > roi_threshold:
                    return f'{coin}_time_based_roi'
                
                sell_rsi_lower = float(self.get_param_value(coin, 'sell_rsi_lower'))
                if current_profit > 0.01 and 'rsi' in last_candle and last_candle['rsi'] < sell_rsi_lower * 0.8:
                    return 'extreme_oversold_exit'
                
                if 'trend_strength' in last_candle:
                    current_trend = self.calculate_trend_strength(dataframe)
                    if current_trend > 0.75 and current_profit > 0.005:
                        return 'strong_uptrend_detected'
                
            except Exception as e:
                pass
        
        # --- LONG CUSTOM EXIT ---
        else:
            try:
                if 'atr' in last_candle:
                    atr_multiplier = 2.5 if current_profit > 0.02 else 3.0
                    # Dynamic exit for longs is Open Rate + ATR
                    dynamic_exit_price = trade.open_rate + (last_candle['atr'] * atr_multiplier)
                    if current_rate >= dynamic_exit_price and current_profit > 0.01:
                        return 'atr_based_exit_long'
                
                # Check for new Long signal to reset timer?
                entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
                entry_signal_col = f'enhanced_long_entry_{entry_timeframe}'
                if (entry_signal_col in last_candle and last_candle[entry_signal_col] > 0) or last_candle.get('enhanced_long_entry', 0) > 0:
                     if current_rate < trade.open_rate and current_profit < -0.01:
                        self._trade_start_reset_times[trade.id] = current_time
                        return None
                
                # Time based ROI for Longs (Can use same thresholds or slightly more generous in bull market)
                roi_thresholds = {
                    'high_vol': {"0": 0.04, "1": 0.03, "3": 0.02, "10": 0.01, "30": 0},
                    'medium_vol': {"0": 0.035, "2": 0.025, "5": 0.015, "20": 0.005, "45": 0},
                    'low_vol': {"0": 0.03, "3": 0.02, "10": 0.01, "30": 0.003, "90": 0}
                }
                category = self.get_coin_category(coin)
                roi_table = roi_thresholds[category]
                
                roi_threshold = None
                for time_threshold, roi_value in sorted(roi_table.items(), key=lambda x: int(x[0]) if x[0] != "0" else 0):
                    if trade_duration >= int(time_threshold):
                        roi_threshold = roi_value
                
                if roi_threshold is not None and current_profit > roi_threshold:
                    return f'{coin}_time_based_roi_long'
                
                if current_profit > 0.01 and 'rsi' in last_candle and last_candle['rsi'] > 80:
                    return 'extreme_overbought_exit'
                    
            except Exception:
                pass
        
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
               proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
               **kwargs) -> float:
        coin = self.get_coin_from_pair(pair)
        base_leverage = float(self.get_param_value(coin, 'leverage_param'))
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            
            if side == 'short':
                if 'confluence_score' in last_candle:
                    if last_candle['confluence_score'] > 10:
                        base_leverage = min(base_leverage * 1.3, max_leverage)
                    elif last_candle['confluence_score'] < 6:
                        base_leverage = max(base_leverage * 0.7, 1)
                if 'trend_strength' in last_candle:
                    if last_candle['trend_strength'] > 0.6:
                         base_leverage = max(base_leverage * 0.5, 1)
            
            else: # Long
                if 'long_confluence_score' in last_candle:
                    if last_candle['long_confluence_score'] > 10:
                         base_leverage = min(base_leverage * 1.3, max_leverage)
                    elif last_candle['long_confluence_score'] < 6:
                         base_leverage = max(base_leverage * 0.7, 1)
        
        return min(base_leverage, max_leverage)
   
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime, 
                      current_rate: float, current_profit: float, **kwargs) -> float:
        coin = self.get_coin_from_pair(pair)
        category = self.get_coin_category(coin)
        
        if current_profit > 0.10:
            return -0.05
        elif current_profit > 0.05:
            return -0.08
        elif current_profit > 0.02:
            return -0.12
        
        stoploss_by_category = {
            'high_vol': -0.15,
            'medium_vol': -0.10,
            'low_vol': -0.06
        }
        
        base_stoploss = stoploss_by_category[category]
        
        regime_adjustments = {
            'bull_low_vol': 0.6,
            'bull_high_vol': 0.5,
            'bear_low_vol': 1.4,
            'bear_high_vol': 1.2
        }
        
        multiplier = regime_adjustments.get(self._market_regime, 1.0)
        
        # Invert logic for longs? No, stoploss is always relative to open price.
        # However, in a bull market, long stoplosses might need to be wider to handle volatility,
        # whereas short stoplosses should be tighter.
        if trade.is_short and 'bull' in self._market_regime:
             multiplier *= 0.8 # Tighten shorts in bull market
        if not trade.is_short and 'bear' in self._market_regime:
             multiplier *= 0.8 # Tighten longs in bear market
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) > 0 and 'atr' in dataframe.columns:
            last_atr = dataframe['atr'].iloc[-1]
            close_price = dataframe['close'].iloc[-1]
            atr_percentage = (last_atr / close_price)
            
            if atr_percentage > 0.02:
                multiplier *= 1.3
            elif atr_percentage < 0.01:
                multiplier *= 0.8
        
        final_stoploss = base_stoploss * multiplier
        
        return max(final_stoploss, -0.40)
   
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
    
    def get_trailing_stop_for_coin(self, coin: str) -> dict:
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

    def get_strategy_parameters(self) -> Dict[str, Any]:
        params = {
            'leverage_param_high_vol': self.leverage_param_high_vol.value,
            'leverage_param_medium_vol': self.leverage_param_medium_vol.value,
            'leverage_param_low_vol': self.leverage_param_low_vol.value,
            'buy_rsi_aggressive': self.buy_rsi_aggressive.value,
            'buy_rsi_conservative': self.buy_rsi_conservative.value,
            'buy_rsi_lower': self.buy_rsi_lower.value, # New
            'buy_price_extension_pct': self.buy_price_extension_pct.value, # New
            'trend_strength_threshold': self.trend_strength_threshold.value,
            'price_position_48h_threshold': self.price_position_48h_threshold.value,
            'strong_uptrend_threshold': self.strong_uptrend_threshold.value,
            'uptrend_period': self.uptrend_period.value,
            'sell_rsi_upper_bear': self.sell_rsi_upper_bear.value,
            'sell_rsi_upper_bull': self.sell_rsi_upper_bull.value,
            'sell_rsi_lower': self.sell_rsi_lower.value,
            'macd_fast': self.macd_fast.value,
            'macd_slow': self.macd_slow.value, 
            'macd_signal': self.macd_signal.value,
            'ema_short_period': self.ema_short_period.value,
            'ema_long_period': self.ema_long_period.value,
            'ema_trend_period': self.ema_trend_period.value,
            'price_extension_pct_conservative': self.price_extension_pct_conservative.value,
            'price_extension_pct_aggressive': self.price_extension_pct_aggressive.value,
            'confluence_threshold': self.confluence_threshold.value,
            'volume_spike_threshold': self.volume_spike_threshold.value,
            'entry_timeframe': self.entry_timeframe.value,
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
