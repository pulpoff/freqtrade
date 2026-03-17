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

class future36(IStrategy):
    # ROI table from hyperopt results
    minimal_roi = {
        "0": 0.02,
        "3": 0.015,
        "15": 0.007,
        "34": 0
    }

    # Risk parameters from hyperopt results
    stoploss = -0.05
    trailing_stop = True
    trailing_stop_positive = 0.16
    trailing_stop_positive_offset = 0.213
    trailing_only_offset_is_reached = True

    # FreqAI settings
    use_exit_signal = True
    process_only_new_candles = True

    # Default hyperoptable parameters with updated defaults from JSON
    # Leverage
    leverage_param = IntParameter(1, 10, default=5, space="buy", optimize=True)
    
    # RSI thresholds
    buy_rsi = IntParameter(30, 50, default=47, space="buy", optimize=True)
    sell_rsi_upper = IntParameter(60, 85, default=79, space="sell", optimize=True)
    sell_rsi_lower = IntParameter(20, 40, default=21, space="sell", optimize=True)
    
    # MACD parameters
    macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
    macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
    
    # Moving average parameters
    ema_short_period = IntParameter(5, 15, default=8, space="both", optimize=True)
    ema_long_period = IntParameter(15, 30, default=21, space="both", optimize=True)
    
    # Price extension threshold
    price_extension_pct = DecimalParameter(0.003, 0.01, default=0.006, space="sell", optimize=True)
    
    # Base strategy settings
    timeframe = '5m'  # Changed to 5m to comply with FreqAI
    
    # Allow hyperopt to choose between 5m and 15m for each coin's entry signals
    # Default to 5m
    entry_timeframe = CategoricalParameter(['5m', '15m'], default='5m', space='buy', optimize=True)
    
    # Other settings
    startup_candle_count = 100
    can_short = True
    can_long = False  # Focusing only on shorts

    # Cooldown tracking
    _last_candle_seen_time = {}
    _coin_list = []  # Dynamic coin list
    _coin_parameters = {}  # Dictionary to hold coin-specific parameters

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_candle_seen_time = {}
        self._coin_list = []
        self._coin_parameters = {}
        
        # Dynamically populate the coin list from pairs in config
        if 'exchange' in config and 'pair_whitelist' in config['exchange']:
            for pair in config['exchange']['pair_whitelist']:
                coin = self.get_coin_from_pair(pair)
                if coin and coin not in self._coin_list:
                    self._coin_list.append(coin)
        
        # Initialize coin-specific parameters
        self.initialize_coin_parameters()
        
    def initialize_coin_parameters(self):
        """Create parameter objects for each coin"""
        for coin in self._coin_list:
            self._coin_parameters[coin] = {}
            
            # Create coin-specific parameters - use the same defaults as your JSON initially
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
            
            # Add timeframe selection parameter for each coin
            setattr(self, f"{coin}_entry_timeframe", CategoricalParameter(['5m', '15m'], default='5m', space='buy', optimize=True))
            self._coin_parameters[coin]['entry_timeframe'] = getattr(self, f"{coin}_entry_timeframe")
    
    def get_coin_from_pair(self, pair: str) -> str:
        """Extract coin name from pair (e.g. 'BTC/USDT' -> 'BTC')"""
        if '/' in pair:
            return pair.split('/')[0]
        return "UNKNOWN"
    
    def get_param_value(self, coin: str, param_name: str):
        """Get parameter value for a specific coin, falling back to default if not available"""
        # First try to get coin-specific parameter
        if coin in self._coin_parameters and param_name in self._coin_parameters[coin]:
            return self._coin_parameters[coin][param_name].value
        
        # Fall back to default parameter
        if hasattr(self, param_name):
            return getattr(self, param_name).value
        
        # Return appropriate default values if parameter not found - use the values from your JSON
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
            'entry_timeframe': '5m'
        }
        return defaults.get(param_name, 1.0)

    def informative_pairs(self):
        """Define informative pairs to load"""
        pairs = self.dp.current_whitelist()
        informative_pairs = []
        
        # Always include 1m for exit signals
        for pair in pairs:
            informative_pairs.append((pair, '1m'))
            
            # Add coin-specific entry timeframe
            coin = self.get_coin_from_pair(pair)
            if coin in self._coin_parameters and 'entry_timeframe' in self._coin_parameters[coin]:
                entry_tf = self._coin_parameters[coin]['entry_timeframe'].value
                # Only add if different from base timeframe
                if entry_tf != self.timeframe:
                    informative_pairs.append((pair, entry_tf))
        
        return informative_pairs

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int, 
                                     metadata: dict) -> DataFrame:
        """
        Create additional features for FreqAI
        """
        # Get coin for this pair
        coin = self.get_coin_from_pair(metadata['pair'])
        
        # Get coin-specific parameters as starting points
        ema_short_period = int(self.get_param_value(coin, 'ema_short_period'))
        ema_long_period = int(self.get_param_value(coin, 'ema_long_period'))
        macd_fast = int(self.get_param_value(coin, 'macd_fast'))
        macd_slow = int(self.get_param_value(coin, 'macd_slow'))
        macd_signal = int(self.get_param_value(coin, 'macd_signal'))
        
        # Add your standard indicators as features
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=ema_short_period)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=ema_long_period)
        
        # MACD
        macd = ta.MACD(dataframe, 
                     fastperiod=macd_fast,
                     slowperiod=macd_slow, 
                     signalperiod=macd_signal)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Add market phase and trend indicators
        dataframe['price_change'] = dataframe['close'].pct_change()
        dataframe['volatility'] = dataframe['close'].rolling(14).std()
        
        # Add distance from moving averages (normalized)
        dataframe['dist_from_ema_short'] = (dataframe['close'] / dataframe['ema_short']) - 1
        dataframe['dist_from_ema_long'] = (dataframe['close'] / dataframe['ema_long']) - 1
        
        # Volume-based features
        dataframe['volume_change'] = dataframe['volume'].pct_change()
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_width'] = (bollinger['upper'] - bollinger['lower']) / bollinger['mid']
        dataframe['bb_pct'] = (dataframe['close'] - bollinger['lower']) / (bollinger['upper'] - bollinger['lower'])
        
        return dataframe
        
    def feature_engineering_expand_basic(self, dataframe: DataFrame, period: int,
                                      metadata: dict) -> DataFrame:
        """
        Simple feature engineering for time-series data
        """
        # Time-based features
        dataframe['hour'] = dataframe['date'].dt.hour
        dataframe['day_of_week'] = dataframe['date'].dt.dayofweek
        
        # Statistical features
        for window in [5, 10, 20]:
            dataframe[f'return_{window}'] = dataframe['close'].pct_change(window)
            dataframe[f'volatility_{window}'] = dataframe['close'].rolling(window).std()
            
        # Shift features to create lagged values
        for n in range(1, 5):
            dataframe[f'close_shift_{n}'] = dataframe['close'].shift(n)
            dataframe[f'volume_shift_{n}'] = dataframe['volume'].shift(n)
            dataframe[f'rsi_shift_{n}'] = dataframe['rsi'].shift(n)
            
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        Define targets for FreqAI to predict
        """
        # Get coin for this pair
        coin = self.get_coin_from_pair(metadata['pair'])
        
        # Get coin-specific parameters
        sell_rsi_upper = float(self.get_param_value(coin, 'sell_rsi_upper'))
        price_extension_pct = float(self.get_param_value(coin, 'price_extension_pct'))
        
        # Create features similar to your entry conditions
        dataframe['high_last_3'] = dataframe['high'].rolling(3).max()
        
        # Create simplified versions of your entry signals
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
        
        # Combined entry signal (historical)
        entry_signal = (
            (price_peak | price_reversal | macd_reversal) &
            (dataframe['rsi'] > sell_rsi_upper * 0.9) &
            (dataframe['close'] > dataframe['ema_short'] * (1 + price_extension_pct))
        )
        
        # Target: Did price drop by X% within N candles (for shorts)
        # This creates the prediction target based on future price movement
        dataframe['future_price'] = dataframe['close'].shift(-20)  # 20 candles into the future
        dataframe['price_drop'] = (dataframe['future_price'] / dataframe['close']) - 1.0
        
        # Normalize the drop to a range of 0-1, where 0 is no drop and 1 is max drop
        # For shorts, a negative drop is good, so we invert
        dataframe['target'] = -1 * dataframe['price_drop']
        
        # Cap it between 0 and 1
        dataframe['target'] = dataframe['target'].clip(0, 1)
        
        # Add historical signals as features
        dataframe['historical_signal'] = entry_signal.astype(int)
        
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Get coin for this pair
        coin = self.get_coin_from_pair(metadata['pair'])
        
        # Get coin-specific parameters for this pair
        ema_short_period = int(self.get_param_value(coin, 'ema_short_period'))
        ema_long_period = int(self.get_param_value(coin, 'ema_long_period'))
        macd_fast = int(self.get_param_value(coin, 'macd_fast'))
        macd_slow = int(self.get_param_value(coin, 'macd_slow'))
        macd_signal = int(self.get_param_value(coin, 'macd_signal'))
        sell_rsi_upper = float(self.get_param_value(coin, 'sell_rsi_upper'))
        sell_rsi_lower = float(self.get_param_value(coin, 'sell_rsi_lower'))
        price_extension_pct = float(self.get_param_value(coin, 'price_extension_pct'))
        
        # Get coin-specific entry timeframe
        entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
        
        # First process indicators for the base timeframe (5m)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=ema_short_period)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=ema_long_period)
        
        # MACD
        macd = ta.MACD(dataframe, 
                     fastperiod=macd_fast,
                     slowperiod=macd_slow, 
                     signalperiod=macd_signal)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_lowerband'] = bollinger['lower']
        
        # Get 1m data for exit signals
        if self.dp:
            try:
                # Load 1m dataframe for responsive exit signals
                informative_1m = self.dp.get_pair_dataframe(
                    pair=metadata['pair'], 
                    timeframe='1m'
                )
                
                # Calculate indicators for 1m data
                informative_1m['rsi'] = ta.RSI(informative_1m, timeperiod=14)
                informative_1m['ema_short'] = ta.EMA(informative_1m, timeperiod=ema_short_period)
                informative_1m['ema_long'] = ta.EMA(informative_1m, timeperiod=ema_long_period)
                
                # Bollinger Bands on 1m
                bollinger_1m = qtpylib.bollinger_bands(qtpylib.typical_price(informative_1m), window=20, stds=2)
                informative_1m['bb_upperband'] = bollinger_1m['upper']
                informative_1m['bb_middleband'] = bollinger_1m['mid']
                informative_1m['bb_lowerband'] = bollinger_1m['lower']
                
                # MACD on 1m
                macd_1m = ta.MACD(informative_1m, 
                                fastperiod=macd_fast,
                                slowperiod=macd_slow, 
                                signalperiod=macd_signal)
                informative_1m['macd'] = macd_1m['macd']
                informative_1m['macdsignal'] = macd_1m['macdsignal']
                informative_1m['macdhist'] = macd_1m['macdhist']
                
                # Exit signals for 1m
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
                
                informative_1m['short_exit_signal'] = (
                    informative_1m['deep_oversold'] | 
                    informative_1m['major_trend_reversal']
                )
                
                # Convert to integers for merging
                informative_1m['short_exit_signal'] = informative_1m['short_exit_signal'].astype(int)
                
                # Merge 1m exit signals with base timeframe
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
                print(f"Error processing 1m data: {e}")
                # Fallback - calculate exit signals on 5m if 1m fails
                dataframe['short_exit_signal_1m'] = (
                    (dataframe['rsi'] < sell_rsi_lower * 0.9) &
                    (dataframe['close'] < dataframe['bb_lowerband'] * 1.01) &
                    (dataframe['close'] < dataframe['ema_short'] * 0.99)
                ) | (
                    qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal']) &
                    (dataframe['macd'] < 0) &
                    (dataframe['macdhist'] > dataframe['macdhist'].shift(1) * 1.2) &
                    (dataframe['close'] < dataframe['ema_short'])
                )
                dataframe['short_exit_signal_1m'] = dataframe['short_exit_signal_1m'].astype(int)
            
            # Load informative higher timeframe if different from base
            if entry_timeframe != self.timeframe:
                try:
                    # Get the entry timeframe dataframe
                    informative = self.dp.get_pair_dataframe(
                        pair=metadata['pair'], 
                        timeframe=entry_timeframe
                    )
                    
                    # Calculate entry indicators on the higher timeframe
                    informative['rsi'] = ta.RSI(informative, timeperiod=14)
                    
                    # Stochastic
                    stoch = ta.STOCH(informative, fastk_period=14, slowk_period=3, slowd_period=3)
                    informative['slowk'] = stoch['slowk']
                    informative['slowd'] = stoch['slowd']
                    
                    # MACD
                    macd = ta.MACD(informative, 
                                fastperiod=macd_fast,
                                slowperiod=macd_slow, 
                                signalperiod=macd_signal)
                    informative['macd'] = macd['macd']
                    informative['macdsignal'] = macd['macdsignal']
                    informative['macdhist'] = macd['macdhist']
                    
                    # Store shifted values for pattern detection
                    informative['macdhist_prev1'] = informative['macdhist'].shift(1)
                    informative['macdhist_prev2'] = informative['macdhist'].shift(2)
                    
                    # Bollinger Bands
                    bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(informative), window=20, stds=2)
                    informative['bb_upperband'] = bollinger['upper']
                    informative['bb_middleband'] = bollinger['mid']
                    informative['bb_lowerband'] = bollinger['lower']
                    
                    # Moving averages
                    informative['ema_short'] = ta.EMA(informative, timeperiod=ema_short_period)
                    informative['ema_long'] = ta.EMA(informative, timeperiod=ema_long_period)
                    
                    # Store shifted prices
                    for i in range(1, 4):
                        informative[f'close_prev{i}'] = informative['close'].shift(i)
                        informative[f'high_prev{i}'] = informative['high'].shift(i)
                        informative[f'low_prev{i}'] = informative['low'].shift(i)
                    
                    # Entry signal detection
                    informative['high_last_3'] = informative['high'].rolling(3).max()
                    
                    # Price peak
                    informative['price_peak'] = (
                        (informative['high'] >= informative['high_last_3'] * 0.995) &
                        (informative['high'] > informative['high_prev1']) &
                        (informative['close'] > informative['ema_short']) &
                        (informative['rsi'] > sell_rsi_upper)
                    )
                    
                    # Price reversal
                    informative['price_reversal'] = (
                        (informative['close_prev2'] < informative['close_prev1']) &
                        (informative['close'] < informative['close_prev1']) &
                        (informative['close_prev1'] > informative['close_prev1'].rolling(3).max().shift(1)) &
                        (informative['rsi'] > sell_rsi_upper * 0.9)
                    )
                    
                    # MACD histogram reversal
                    informative['macd_reversal'] = (
                        (informative['macdhist_prev2'] < informative['macdhist_prev1']) &
                        (informative['macdhist'] < informative['macdhist_prev1']) &
                        (informative['macdhist_prev1'] > 0) &
                        (informative['close'] > informative['ema_short'])
                    )
                    
                    # Combined entry signal
                    informative['short_entry_signal'] = (
                        (informative['price_peak'] | informative['price_reversal'] | informative['macd_reversal']) &
                        (informative['rsi'] > sell_rsi_upper * 0.9) &
                        (informative['close'] > informative['ema_short'] * (1 + price_extension_pct))
                    )
                    
                    # Convert boolean values to integers
                    for col in ['short_entry_signal', 'price_peak', 'price_reversal', 'macd_reversal']:
                        informative[col] = informative[col].astype(int)
                    
                    # Merge informative timeframe with base timeframe
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
                    print(f"Error processing {entry_timeframe} data: {e}")
        
        # Entry signals for base timeframe
        # Detect peaks - when current price is at or near local maximum
        dataframe['high_last_3'] = dataframe['high'].rolling(3).max()
        
        # Price peak
        dataframe['price_peak'] = (
            (dataframe['high'] >= dataframe['high_last_3'] * 0.995) &  # Price near the highest point
            (dataframe['high'] > dataframe['high'].shift(1)) &         # Current high higher than previous
            (dataframe['close'] > dataframe['ema_short']) &            # Price above short-term average
            (dataframe['rsi'] > sell_rsi_upper)                        # RSI elevated
        )
        
        # Price reversal
        dataframe['price_reversal'] = (
            (dataframe['close'].shift(2) < dataframe['close'].shift(1)) &    # Prior candle was up
            (dataframe['close'] < dataframe['close'].shift(1)) &             # Current candle is down
            (dataframe['close'].shift(1) > dataframe['close'].shift(1).rolling(3).max().shift(1)) &  # Local high
            (dataframe['rsi'] > sell_rsi_upper * 0.9)                       # RSI elevated
        )
        
        # MACD histogram reversal
        dataframe['macd_reversal'] = (
            (dataframe['macdhist'].shift(2) < dataframe['macdhist'].shift(1)) &  # Previous MACD hist was rising
            (dataframe['macdhist'] < dataframe['macdhist'].shift(1)) &           # Current MACD hist is falling
            (dataframe['macdhist'].shift(1) > 0) &                              # Previous MACD hist was positive
            (dataframe['close'] > dataframe['ema_short'])                       # Price above short-term average
        )
        
        # Combined entry signal
        dataframe['short_entry_signal'] = (
            (dataframe['price_peak'] | dataframe['price_reversal'] | dataframe['macd_reversal']) &
            (dataframe['rsi'] > sell_rsi_upper * 0.9) &   # RSI must be elevated
            (dataframe['close'] > dataframe['ema_short'] * (1 + price_extension_pct))  # Price must be extended above MA
        )
        
        # Add a column with the current timeframe suffix for consistency
        dataframe[f'short_entry_signal_{self.timeframe}'] = dataframe['short_entry_signal'].astype(int)
        
        return dataframe

    def adjust_parameters_from_model(self, dataframe: DataFrame, metadata: dict) -> Dict:
        """
        Use FreqAI model outputs to dynamically adjust strategy parameters
        """
        coin = self.get_coin_from_pair(metadata['pair'])
        
        # Default parameters
        adjusted_params = {
            'leverage_param': self.get_param_value(coin, 'leverage_param'),
            'buy_rsi': self.get_param_value(coin, 'buy_rsi'),
            'sell_rsi_upper': self.get_param_value(coin, 'sell_rsi_upper'),
            'sell_rsi_lower': self.get_param_value(coin, 'sell_rsi_lower'),
            'price_extension_pct': self.get_param_value(coin, 'price_extension_pct')
        }
        
        # If we have model prediction data
        if 'prediction_probability' in dataframe.columns and len(dataframe) > 0:
            # Get the latest probability
            prob = dataframe['prediction_probability'].iloc[-1]
            
            # Adjust parameters based on model confidence
            if prob > 0.8:  # High confidence
                # More aggressive settings
                adjusted_params['leverage_param'] = min(adjusted_params['leverage_param'] * 1.2, 5)
                adjusted_params['price_extension_pct'] = max(adjusted_params['price_extension_pct'] * 0.9, 0.004)
            elif prob < 0.4:  # Low confidence
                # More conservative settings
                adjusted_params['leverage_param'] = max(adjusted_params['leverage_param'] * 0.8, 1)
                adjusted_params['price_extension_pct'] = min(adjusted_params['price_extension_pct'] * 1.2, 0.008)
                
            # Adjust RSI based on recent market conditions
            if 'market_trend' in dataframe.columns:
                trend = dataframe['market_trend'].iloc[-1]
                if trend > 0.5:  # Strong uptrend
                    adjusted_params['sell_rsi_upper'] = min(adjusted_params['sell_rsi_upper'] + 5, 85)
                else:  # Weaker trend
                    adjusted_params['sell_rsi_upper'] = max(adjusted_params['sell_rsi_upper'] - 5, 70)
        
        return adjusted_params

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry signals using FreqAI predictions when available"""
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        # Get coin for this pair
        coin = self.get_coin_from_pair(metadata['pair'])
        
        # If FreqAI is enabled and prediction is available, use its predictions for entry
        if hasattr(self, 'freqai') and self.freqai and 'prediction' in dataframe.columns:
            # Get latest dataframe row
            last_candle = dataframe.iloc[-1].squeeze() if len(dataframe) > 0 else None
            
            if last_candle is not None:
                # High prediction values indicate entry opportunities
                prediction_value = last_candle['prediction']
                
                # Adjust threshold based on market conditions
                threshold = 0.7
                if 'market_trend' in dataframe.columns:
                    market_trend = last_candle['market_trend']
                    # Raise threshold in strong trends
                    if market_trend > 0.7:
                        threshold = 0.8
                    # Lower threshold in weaker trends
                    elif market_trend < 0.3:
                        threshold = 0.6
                
                # Apply prediction-based entry logic
                dataframe.loc[
                    (dataframe['prediction'] > threshold) & 
                    (dataframe['volume'] > 0),  # Make sure there's volume
                    'enter_short'
                ] = 1
        else:
            # Fall back to traditional signal detection
            # Get coin-specific entry timeframe
            entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
            
            # The entry signal column name will have the dynamic timeframe suffix
            entry_signal_col = f'short_entry_signal_{entry_timeframe}'
            
            # Apply short entry signal from selected timeframe
            if entry_signal_col in dataframe.columns:
                dataframe.loc[dataframe[entry_signal_col] > 0, 'enter_short'] = 1
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit signals - using responsive 1m timeframe"""
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        # Use 1m exit signals when available
        if 'short_exit_signal_1m' in dataframe.columns:
            dataframe.loc[dataframe['short_exit_signal_1m'] > 0, 'exit_short'] = 1
        else:
            # Fallback to base timeframe exit signals
            dataframe.loc[dataframe['short_exit_signal'] > 0, 'exit_short'] = 1
        
        return dataframe
    
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                           side: str, **kwargs) -> bool:
        """
        Adjust parameters based on FreqAI predictions and apply cooldown logic
        """
        # Only apply to shorts
        if side != 'short':
            return True
            
        # Get coin for this pair
        coin = self.get_coin_from_pair(pair)
        
        # Apply cooldown logic
        cooldown_minutes = 5
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
        
        # Get the latest dataframe
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        # If we have FreqAI enabled and data available
        if hasattr(self, 'freqai') and self.freqai and len(dataframe) > 0:
            # Get dynamically adjusted parameters
            adjusted_params = self.adjust_parameters_from_model(dataframe, {'pair': pair})
            
            # Use adjusted leverage
            if 'leverage_param' in adjusted_params:
                self._coin_parameters[coin]['leverage_param'].value = adjusted_params['leverage_param']
            
            # Check if prediction confidence is too low
            if 'prediction_probability' in dataframe.columns:
                latest_prob = dataframe['prediction_probability'].iloc[-1]
                if latest_prob < 0.3:  # Very low confidence
                    return False  # Skip this trade
        
        # Update the last seen time for this pair
        self._last_candle_seen_time[pair] = current_time
        
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """Custom exit logic for shorts - mostly rely on ROI instead of signals"""
        if trade.is_short:
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if len(dataframe) > 0:
                    last_candle = dataframe.iloc[-1]
                    
                    # Take profit at 3% (based on updated ROI settings)
                    if current_profit > 0.03:
                        return 'short_profit_target_reached'
                    
                    # Exit on extreme oversold conditions (using 1m timeframe for responsiveness)
                    coin = self.get_coin_from_pair(pair)
                    sell_rsi_lower = float(self.get_param_value(coin, 'sell_rsi_lower'))
                    
                    if current_profit > 0.016 and 'rsi' in last_candle and last_candle['rsi'] < sell_rsi_lower:
                        return 'short_profit_extreme_oversold'
                    
                    # FreqAI-based exit
                    if hasattr(self, 'freqai') and self.freqai and 'prediction' in dataframe.columns:
                        # If the model suddenly predicts much lower success probability
                        if 'prediction' in last_candle and last_candle['prediction'] < 0.3:
                            if current_profit > 0.01:  # Only exit if we have some profit
                                return 'freqai_predicted_reversal'
                    
            except Exception as e:
                pass
        
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
                **kwargs) -> float:
        """Return leverage based on dynamically adjusted parameters"""
        coin = self.get_coin_from_pair(pair)
        
        # Get the latest dataframe
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        # If we have FreqAI enabled and data available
        if hasattr(self, 'freqai') and self.freqai and len(dataframe) > 0:
            # Get dynamically adjusted parameters
            adjusted_params = self.adjust_parameters_from_model(dataframe, {'pair': pair})
            
            # Use adjusted leverage from model
            if 'leverage_param' in adjusted_params:
                return float(adjusted_params['leverage_param'])
        
        # Fall back to static parameter
        return float(self.get_param_value(coin, 'leverage_param'))

    # Ensure coin-specific parameters are saved to the JSON output
    def get_strategy_parameters(self) -> Dict[str, Any]:
        """Export strategy parameters including coin-specific ones"""
        params = {}
        
        # Add global parameters
        params.update({
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
            'entry_timeframe': self.entry_timeframe.value
        })
        
        # Add coin-specific parameters
        for coin in self._coin_list:
            if coin in self._coin_parameters:
                for param_name, param_obj in self._coin_parameters[coin].items():
                    params[f"{coin}_{param_name}"] = param_obj.value
        
        return params
