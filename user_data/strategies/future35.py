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

class future35(IStrategy):
    # ROI table from hyperopt results
    minimal_roi = {
        "0": 0.02,
        "30": 0.016,
        "150": 0.007,
        "340": 0
    }

    # Risk parameters from hyperopt results
    stoploss = -0.05
    trailing_stop = True
    trailing_stop_positive = 0.16
    trailing_stop_positive_offset = 0.213
    trailing_only_offset_is_reached = True

    # Default hyperoptable parameters with updated defaults from JSON
    # Leverage
    leverage_param = IntParameter(6, 10, default=4, space="buy", optimize=True)
    
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
    timeframe = '1m'  # Base timeframe for all signals - always use 1m for exits
    
    # Allow hyperopt to choose between 1m, 5m, and 15m for each coin's entry signals
    # Default to 1m as requested
    entry_timeframe = CategoricalParameter(['1m', '5m', '15m'], default='1m', space='buy', optimize=True)
    
    # Other settings
    startup_candle_count = 100
    process_only_new_candles = True
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
            
            # Add timeframe selection parameter for each coin - default to 1m as requested
            setattr(self, f"{coin}_entry_timeframe", CategoricalParameter(['1m', '5m', '15m'], default='1m', space='buy', optimize=True))
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
            'entry_timeframe': '1m'  # Default to 1m as requested
        }
        return defaults.get(param_name, 1.0)

    def informative_pairs(self):
        """Define informative pairs to load"""
        pairs = self.dp.current_whitelist()
        informative_pairs = []
        
        # Add all pairs with their respective timeframes
        for pair in pairs:
            # Add coin-specific entry timeframe
            coin = self.get_coin_from_pair(pair)
            if coin in self._coin_parameters and 'entry_timeframe' in self._coin_parameters[coin]:
                entry_tf = self._coin_parameters[coin]['entry_timeframe'].value
                # Only add if different from base timeframe
                if entry_tf != self.timeframe:
                    informative_pairs.append((pair, entry_tf))
        
        return informative_pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Get coin for this pair
        coin = self.get_coin_from_pair(metadata['pair'])
        
        # Get coin-specific parameters
        ema_short_period = int(self.get_param_value(coin, 'ema_short_period'))
        ema_long_period = int(self.get_param_value(coin, 'ema_long_period'))
        macd_fast = int(self.get_param_value(coin, 'macd_fast'))
        macd_slow = int(self.get_param_value(coin, 'macd_slow'))
        macd_signal = int(self.get_param_value(coin, 'macd_signal'))
        sell_rsi_upper = float(self.get_param_value(coin, 'sell_rsi_upper'))
        sell_rsi_lower = float(self.get_param_value(coin, 'sell_rsi_lower'))
        price_extension_pct = float(self.get_param_value(coin, 'price_extension_pct'))
        
        # Get coin-specific entry timeframe (default to 1m as requested)
        entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
        
        # === POPULATE BASE TIMEFRAME INDICATORS ===
        # These are ALWAYS calculated on 1m timeframe for responsive exits
        
        # RSI indicator 
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Moving averages
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=ema_short_period)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=ema_long_period)
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_lowerband'] = bollinger['lower']
        
        # MACD
        macd = ta.MACD(dataframe, 
                      fastperiod=macd_fast,
                      slowperiod=macd_slow, 
                      signalperiod=macd_signal)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # ===== EXIT SIGNAL DETECTION ON BASE TIMEFRAME (1m) =====
        # Strong oversold condition for exits - only extreme cases
        dataframe['deep_oversold'] = (
            (dataframe['rsi'] < sell_rsi_lower * 0.9) &      # Very low RSI
            (dataframe['close'] < dataframe['bb_lowerband'] * 1.01) &   # Price near or below lower BB
            (dataframe['close'] < dataframe['ema_short'] * 0.99)         # Price significantly below short EMA
        )
        
        # Major trend reversal - only on significant trend changes
        dataframe['major_trend_reversal'] = (
            qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal']) &  # MACD crosses above signal
            (dataframe['macd'] < 0) &                                           # MACD is negative
            (dataframe['macdhist'] > dataframe['macdhist'].shift(1) * 1.2) &     # Strong histogram increase
            (dataframe['close'] < dataframe['ema_short'])                        # Price below short EMA
        )
        
        # Combined exit signal - always uses 1m for responsiveness
        dataframe['short_exit_signal'] = (
            dataframe['deep_oversold'] | 
            dataframe['major_trend_reversal']
        )
        
        # === PROCESS ENTRY SIGNALS ===
        
        # If using 1m for both entry and exit
        if entry_timeframe == '1m':
            # Detect peaks - when current price is at or near local maximum
            dataframe['high_last_3'] = dataframe['high'].rolling(3).max()
            
            # Price is at a local peak
            dataframe['price_peak'] = (
                (dataframe['high'] >= dataframe['high_last_3'] * 0.995) &  # Price near the highest point
                (dataframe['high'] > dataframe['high'].shift(1)) &         # Current high higher than previous
                (dataframe['close'] > dataframe['ema_short']) &            # Price above short-term average
                (dataframe['rsi'] > sell_rsi_upper)                        # RSI elevated
            )
            
            # Price reversal after a rise
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
            
            # Add a column with the current timeframe suffix to maintain consistent column naming
            dataframe[f'short_entry_signal_{entry_timeframe}'] = dataframe['short_entry_signal'].astype(int)
        
        # If using a different timeframe for entry signals
        elif self.dp:
            # Get the entry timeframe dataframe
            informative = self.dp.get_pair_dataframe(
                pair=metadata['pair'], 
                timeframe=entry_timeframe
            )
            
            # ===== INDICATORS FOR ENTRIES ON INFORMATIVE TIMEFRAME =====
            
            # RSI indicator
            informative['rsi'] = ta.RSI(informative, timeperiod=14)
            
            # Stochastic
            stoch = ta.STOCH(informative, fastk_period=14, slowk_period=3, slowd_period=3)
            informative['slowk'] = stoch['slowk']
            informative['slowd'] = stoch['slowd']
            
            # MACD with parameters
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
            
            # Moving averages with parameters
            informative['ema_short'] = ta.EMA(informative, timeperiod=ema_short_period)
            informative['ema_long'] = ta.EMA(informative, timeperiod=ema_long_period)
            
            # Store shifted prices
            for i in range(1, 4):
                informative[f'close_prev{i}'] = informative['close'].shift(i)
                informative[f'high_prev{i}'] = informative['high'].shift(i)
                informative[f'low_prev{i}'] = informative['low'].shift(i)
            
            # ===== ENTRY SIGNAL DETECTION =====
            
            # Detect peaks - when current price is at or near local maximum
            informative['high_last_3'] = informative['high'].rolling(3).max()
            
            # Price is at a local peak - using parameters
            informative['price_peak'] = (
                (informative['high'] >= informative['high_last_3'] * 0.995) &  # Price near the highest point
                (informative['high'] > informative['high_prev1']) &            # Current high higher than previous
                (informative['close'] > informative['ema_short']) &            # Price above short-term average
                (informative['rsi'] > sell_rsi_upper)                          # RSI elevated
            )
            
            # Price reversal after a rise - using parameters
            informative['price_reversal'] = (
                (informative['close_prev2'] < informative['close_prev1']) &    # Prior candle was up
                (informative['close'] < informative['close_prev1']) &           # Current candle is down
                (informative['close_prev1'] > informative['close_prev1'].rolling(3).max().shift(1)) &  # Local high
                (informative['rsi'] > sell_rsi_upper * 0.9)       # RSI elevated
            )
            
            # MACD histogram reversal - using parameters
            informative['macd_reversal'] = (
                (informative['macdhist_prev2'] < informative['macdhist_prev1']) &  # Previous MACD hist was rising
                (informative['macdhist'] < informative['macdhist_prev1']) &         # Current MACD hist is falling
                (informative['macdhist_prev1'] > 0) &                            # Previous MACD hist was positive
                (informative['close'] > informative['ema_short'])                  # Price above short-term average
            )
            
            # Combined entry signal - using parameters
            informative['short_entry_signal'] = (
                (informative['price_peak'] | informative['price_reversal'] | informative['macd_reversal']) &
                (informative['rsi'] > sell_rsi_upper * 0.9) &   # RSI must be elevated
                (informative['close'] > informative['ema_short'] * (1 + price_extension_pct))  # Price must be extended above MA
            )
            
            # Merge informative timeframe data with current timeframe
            # Converting boolean values to integers for easier handling in merged dataframe
            for col in ['short_entry_signal', 'price_peak', 'price_reversal', 'macd_reversal']:
                informative[col] = informative[col].astype(int)
            
            # Make sure to set append_timeframe to False when using a custom suffix
            dataframe = merge_informative_pair(
                dataframe, 
                informative, 
                self.timeframe, 
                entry_timeframe, 
                ffill=True, 
                append_timeframe=False,  # Set to False when using custom suffix
                suffix=f"_{entry_timeframe}"
            )
            
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry signals from dynamic timeframe"""
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        # Get coin for this pair
        coin = self.get_coin_from_pair(metadata['pair'])
        
        # Get coin-specific entry timeframe
        entry_timeframe = self.get_param_value(coin, 'entry_timeframe')
        
        # The entry signal column name will have the dynamic timeframe suffix
        entry_signal_col = f'short_entry_signal_{entry_timeframe}'
        
        # Apply short entry signal from selected timeframe
        if entry_signal_col in dataframe.columns:
            dataframe.loc[dataframe[entry_signal_col] > 0, 'enter_short'] = 1
        
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                           side: str, **kwargs) -> bool:
        """
        Simple cooldown logic - using a longer cooldown since we may be using different timeframes
        """
        # Only apply to shorts
        if side != 'short':
            return True
            
        # Check cooldown period (5 minutes between trades of same pair)
        cooldown_minutes = 5
        
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
                
        # Update the last seen time for this pair
        self._last_candle_seen_time[pair] = current_time
        
        return True

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit signals - always using base timeframe (1m) for quick reactions"""
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        # Only mark significant exit points using 1m timeframe for quick reactions
        dataframe.loc[dataframe['short_exit_signal'], 'exit_short'] = 1
        
        return dataframe

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
                    
            except Exception as e:
                pass
        
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
                **kwargs) -> float:
        """Return leverage based on coin-specific parameter"""
        coin = self.get_coin_from_pair(pair)
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
