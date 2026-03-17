from functools import reduce
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter
from skopt.space import Integer, Real, Categorical, Dimension

class future19(IStrategy):
    minimal_roi = {
        "0": 0.05,    # Take 5% profit immediately
        "5": 0.03,    # 3% after 5 minutes
        "15": 0.02,   # 2% after 15 minutes
        "30": 0       # Any profit after 30 minutes
    }

    stoploss = -0.09
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = False

    # Strategy settings
    timeframe = '1m'
    startup_candle_count = 100
    process_only_new_candles = True
    can_short = True
    can_long = False  # Focusing only on shorts

    # Default parameters for coins not specifically defined
    # Basic parameters
    default_leverage_param = IntParameter(1, 10, default=5, space="buy", optimize=True)
    default_buy_rsi = IntParameter(30, 50, default=40, space="buy", optimize=True)
    default_sell_rsi_upper = IntParameter(60, 85, default=70, space="sell", optimize=True)
    default_sell_rsi_lower = IntParameter(20, 40, default=30, space="sell", optimize=True)
    
    # MACD parameters
    default_macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    default_macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
    default_macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
    
    # EMA parameters
    default_ema_short_period = IntParameter(5, 15, default=8, space="both", optimize=True)
    default_ema_long_period = IntParameter(15, 30, default=21, space="both", optimize=True)
    
    # Price extension and thresholds
    default_price_extension_pct = DecimalParameter(0.003, 0.01, default=0.005, space="sell", optimize=True)
    
    # Additional parameters for signal generation
    default_peak_detection_pct = DecimalParameter(0.99, 0.999, default=0.995, space="buy", optimize=True)
    default_rsi_upper_scaling = DecimalParameter(0.85, 0.95, default=0.9, space="buy", optimize=True)
    default_bb_offset_pct = DecimalParameter(1.0, 1.03, default=1.01, space="sell", optimize=True)
    default_ema_offset_pct = DecimalParameter(0.97, 1.0, default=0.99, space="sell", optimize=True)
    default_macd_hist_increase = DecimalParameter(1.1, 1.3, default=1.2, space="sell", optimize=True)

    # Cooldown tracking
    _last_candle_seen_time = {}
    # Dictionary to store dynamically created parameters
    _coin_params = {}
    # List of supported coins (will be populated from config)
    _supported_coins = []

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_candle_seen_time = {}
        self._supported_coins = []
        
        # Extract coins from config pairs
        if config.get('exchange', {}).get('pair_whitelist'):
            for pair in config['exchange']['pair_whitelist']:
                coin = self.get_coin_from_pair(pair)
                if coin and coin not in self._supported_coins:
                    self._supported_coins.append(coin)
        
        # Initialize parameters for each coin
        self._coin_params = self._init_dynamic_coin_params()

    def _init_dynamic_coin_params(self):
        """Dynamically create parameters for each coin in whitelist"""
        params = {}
        
        for coin in self._supported_coins:
            # Basic parameters
            params[f"{coin}_leverage_param"] = IntParameter(1, 10, default=5, space="buy", optimize=True)
            params[f"{coin}_buy_rsi"] = IntParameter(30, 50, default=40, space="buy", optimize=True)
            params[f"{coin}_sell_rsi_upper"] = IntParameter(60, 85, default=70, space="sell", optimize=True)
            params[f"{coin}_sell_rsi_lower"] = IntParameter(20, 40, default=30, space="sell", optimize=True)
            
            # MACD parameters
            params[f"{coin}_macd_fast"] = IntParameter(8, 16, default=12, space="both", optimize=True)
            params[f"{coin}_macd_slow"] = IntParameter(18, 32, default=26, space="both", optimize=True)
            params[f"{coin}_macd_signal"] = IntParameter(6, 12, default=9, space="both", optimize=True)
            
            # EMA parameters
            params[f"{coin}_ema_short_period"] = IntParameter(5, 15, default=8, space="both", optimize=True)
            params[f"{coin}_ema_long_period"] = IntParameter(15, 30, default=21, space="both", optimize=True)
            
            # Price extension and thresholds
            params[f"{coin}_price_extension_pct"] = DecimalParameter(0.003, 0.01, default=0.005, space="sell", optimize=True)
            
            # Additional parameters for signal generation
            params[f"{coin}_peak_detection_pct"] = DecimalParameter(0.99, 0.999, default=0.995, space="buy", optimize=True)
            params[f"{coin}_rsi_upper_scaling"] = DecimalParameter(0.85, 0.95, default=0.9, space="buy", optimize=True)
            params[f"{coin}_bb_offset_pct"] = DecimalParameter(1.0, 1.03, default=1.01, space="sell", optimize=True)
            params[f"{coin}_ema_offset_pct"] = DecimalParameter(0.97, 1.0, default=0.99, space="sell", optimize=True)
            params[f"{coin}_macd_hist_increase"] = DecimalParameter(1.1, 1.3, default=1.2, space="sell", optimize=True)
            
            # Register the parameters with the strategy
            for param_name, param_obj in params.items():
                if param_name.startswith(f"{coin}_"):
                    setattr(self, param_name, param_obj)
        
        return params

    def get_coin_from_pair(self, pair: str) -> str:
        """Extract coin symbol from pair"""
        if '/' in pair:
            coin = pair.split('/')[0]
            return coin
        return ""

    def get_param_value(self, coin: str, param_name: str):
        """Get coin-specific parameter value or fall back to default"""
        full_param_name = f"{coin}_{param_name}"
        
        if hasattr(self, full_param_name):
            return getattr(self, full_param_name).value
        
        # Fall back to default parameter
        default_param_name = f"default_{param_name}"
        if hasattr(self, default_param_name):
            return getattr(self, default_param_name).value
            
        # Last resort fallback with default values
        default_values = {
            "leverage_param": 5,
            "buy_rsi": 40,
            "sell_rsi_upper": 70,
            "sell_rsi_lower": 30,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "ema_short_period": 8,
            "ema_long_period": 21,
            "price_extension_pct": 0.005,
            "peak_detection_pct": 0.995,
            "rsi_upper_scaling": 0.9,
            "bb_offset_pct": 1.01,
            "ema_offset_pct": 0.99,
            "macd_hist_increase": 1.2
        }
        
        return default_values.get(param_name, None)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Get coin from pair
        coin = self.get_coin_from_pair(metadata['pair'])
        
        # ===== CORE TECHNICAL INDICATORS =====
        
        # RSI indicator
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Stochastic
        stoch = ta.STOCH(dataframe, fastk_period=14, slowk_period=3, slowd_period=3)
        dataframe['slowk'] = stoch['slowk']
        dataframe['slowd'] = stoch['slowd']
        
        # MACD with coin-specific parameters
        macd_fast = self.get_param_value(coin, 'macd_fast')
        macd_slow = self.get_param_value(coin, 'macd_slow')
        macd_signal = self.get_param_value(coin, 'macd_signal')
        
        macd = ta.MACD(dataframe, 
                      fastperiod=macd_fast,
                      slowperiod=macd_slow, 
                      signalperiod=macd_signal)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Store shifted values for pattern detection
        dataframe['macdhist_prev1'] = dataframe['macdhist'].shift(1)
        dataframe['macdhist_prev2'] = dataframe['macdhist'].shift(2)
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_lowerband'] = bollinger['lower']
        
        # Moving averages with coin-specific parameters
        ema_short_period = self.get_param_value(coin, 'ema_short_period')
        ema_long_period = self.get_param_value(coin, 'ema_long_period')
        
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=ema_short_period)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=ema_long_period)
        
        # Store shifted prices
        for i in range(1, 4):
            dataframe[f'close_prev{i}'] = dataframe['close'].shift(i)
            dataframe[f'high_prev{i}'] = dataframe['high'].shift(i)
            dataframe[f'low_prev{i}'] = dataframe['low'].shift(i)
        
        # ===== ENTRY SIGNAL DETECTION =====
        
        # Get coin-specific parameters for signal generation
        sell_rsi_upper = self.get_param_value(coin, 'sell_rsi_upper')
        sell_rsi_lower = self.get_param_value(coin, 'sell_rsi_lower')
        price_extension_pct = self.get_param_value(coin, 'price_extension_pct')
        peak_detection_pct = self.get_param_value(coin, 'peak_detection_pct')
        rsi_upper_scaling = self.get_param_value(coin, 'rsi_upper_scaling')
        
        # Detect peaks - when current price is at or near local maximum
        dataframe['high_last_3'] = dataframe['high'].rolling(3).max()
        
        # Price is at a local peak - using coin-specific parameters
        dataframe['price_peak'] = (
            (dataframe['high'] >= dataframe['high_last_3'] * peak_detection_pct) &  # Price near the highest point (hyperopt)
            (dataframe['high'] > dataframe['high_prev1']) &            # Current high higher than previous
            (dataframe['close'] > dataframe['ema_short']) &            # Price above short-term average
            (dataframe['rsi'] > sell_rsi_upper)                        # RSI elevated but not extreme (hyperopt)
        )
        
        # Price reversal after a rise - using coin-specific parameters
        dataframe['price_reversal'] = (
            (dataframe['close_prev2'] < dataframe['close_prev1']) &    # Prior candle was up
            (dataframe['close'] < dataframe['close_prev1']) &           # Current candle is down
            (dataframe['close_prev1'] > dataframe['close_prev1'].rolling(3).max().shift(1)) &  # Local high
            (dataframe['rsi'] > sell_rsi_upper * rsi_upper_scaling)    # RSI elevated (hyperopt)
        )
        
        # MACD histogram reversal - using coin-specific parameters
        dataframe['macd_reversal'] = (
            (dataframe['macdhist_prev2'] < dataframe['macdhist_prev1']) &  # Previous MACD hist was rising
            (dataframe['macdhist'] < dataframe['macdhist_prev1']) &         # Current MACD hist is falling
            (dataframe['macdhist_prev1'] > 0) &                            # Previous MACD hist was positive
            (dataframe['close'] > dataframe['ema_short'])                  # Price above short-term average
        )
        
        # Combined entry signal - using coin-specific parameters
        dataframe['short_entry_signal'] = (
            (dataframe['price_peak'] | dataframe['price_reversal'] | dataframe['macd_reversal']) &
            (dataframe['rsi'] > sell_rsi_upper * rsi_upper_scaling) &   # RSI must be elevated (hyperopt)
            (dataframe['close'] > dataframe['ema_short'] * (1 + price_extension_pct))  # Price must be extended above MA (hyperopt)
        )
        
        # ===== EXIT SIGNAL DETECTION - SIGNIFICANTLY REDUCED =====
        
        # Get coin-specific parameters for exit signals
        bb_offset_pct = self.get_param_value(coin, 'bb_offset_pct')
        ema_offset_pct = self.get_param_value(coin, 'ema_offset_pct')
        macd_hist_increase = self.get_param_value(coin, 'macd_hist_increase')
        
        # Strong oversold condition for exits - only extreme cases
        dataframe['deep_oversold'] = (
            (dataframe['rsi'] < sell_rsi_lower * rsi_upper_scaling) &      # Very low RSI (hyperopt)
            (dataframe['close'] < dataframe['bb_lowerband'] * bb_offset_pct) &   # Price near or below lower BB (hyperopt)
            (dataframe['close'] < dataframe['ema_short'] * ema_offset_pct)        # Price significantly below short EMA (hyperopt)
        )
        
        # Major trend reversal - only on significant trend changes
        dataframe['major_trend_reversal'] = (
            qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal']) &  # MACD crosses above signal
            (dataframe['macd'] < 0) &                                           # MACD is negative
            (dataframe['macdhist'] > dataframe['macdhist'].shift(1) * macd_hist_increase) &  # Strong histogram increase (hyperopt)
            (dataframe['close'] < dataframe['ema_short'])                        # Price below short EMA
        )
        
        # Combined exit signal - much more selective
        dataframe['short_exit_signal'] = (
            dataframe['deep_oversold'] | 
            dataframe['major_trend_reversal']
        )
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry signals for shorts with controlled frequency"""
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        # Apply short entry signal - only where our signal is triggered
        dataframe.loc[dataframe['short_entry_signal'], 'enter_short'] = 1
        
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                           side: str, **kwargs) -> bool:
        """
        Simple cooldown logic
        """
        # Check cooldown period (3 minutes between trades of same pair)
        cooldown_minutes = 3
        
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
                
        # Update the last seen time for this pair
        self._last_candle_seen_time[pair] = current_time
        
        return True

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit signals - drastically reduced in frequency"""
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        # Only mark significant exit points - much more selective
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
                    
                    # Get coin-specific parameters
                    coin = self.get_coin_from_pair(pair)
                    sell_rsi_lower = self.get_param_value(coin, 'sell_rsi_lower')
                    
                    # Take profit at 5% to match future18 ROI
                    if current_profit > 0.05:
                        return 'short_profit_target_reached'
                    
                    # Only exit on extreme oversold conditions
                    if current_profit > 0.02 and 'rsi' in last_candle and last_candle['rsi'] < sell_rsi_lower:
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

    def hyperopt_space(self) -> List[Dimension]:
        """Define hyperopt space for all coins with additional parameters"""
        space = []
        
        # First add default parameters with expanded ranges
        space.extend([
            # Basic parameters
            Integer(1, 10, name='default_leverage_param'),
            Integer(30, 50, name='default_buy_rsi'),
            Integer(60, 85, name='default_sell_rsi_upper'),
            Integer(20, 40, name='default_sell_rsi_lower'),
            
            # MACD parameters
            Integer(8, 16, name='default_macd_fast'),
            Integer(18, 32, name='default_macd_slow'),
            Integer(6, 12, name='default_macd_signal'),
            
            # EMA parameters
            Integer(5, 15, name='default_ema_short_period'),
            Integer(15, 30, name='default_ema_long_period'),
            
            # Price extension and thresholds
            Real(0.003, 0.01, name='default_price_extension_pct'),
            
            # Additional parameters for signal generation
            Real(0.99, 0.999, name='default_peak_detection_pct'),
            Real(0.85, 0.95, name='default_rsi_upper_scaling'),
            Real(1.0, 1.03, name='default_bb_offset_pct'),
            Real(0.97, 1.0, name='default_ema_offset_pct'),
            Real(1.1, 1.3, name='default_macd_hist_increase')
        ])
        
        # Then add spaces for each coin with expanded parameters
        for coin in self._supported_coins:
            space.extend([
                # Basic parameters
                Integer(1, 10, name=f'{coin}_leverage_param'),
                Integer(30, 50, name=f'{coin}_buy_rsi'),
                Integer(60, 85, name=f'{coin}_sell_rsi_upper'),
                Integer(20, 40, name=f'{coin}_sell_rsi_lower'),
                
                # MACD parameters
                Integer(8, 16, name=f'{coin}_macd_fast'),
                Integer(18, 32, name=f'{coin}_macd_slow'),
                Integer(6, 12, name=f'{coin}_macd_signal'),
                
                # EMA parameters
                Integer(5, 15, name=f'{coin}_ema_short_period'),
                Integer(15, 30, name=f'{coin}_ema_long_period'),
                
                # Price extension and thresholds
                Real(0.003, 0.01, name=f'{coin}_price_extension_pct'),
                
                # Additional parameters for signal generation
                Real(0.99, 0.999, name=f'{coin}_peak_detection_pct'),
                Real(0.85, 0.95, name=f'{coin}_rsi_upper_scaling'),
                Real(1.0, 1.03, name=f'{coin}_bb_offset_pct'),
                Real(0.97, 1.0, name=f'{coin}_ema_offset_pct'),
                Real(1.1, 1.3, name=f'{coin}_macd_hist_increase')
            ])
        
        return space
