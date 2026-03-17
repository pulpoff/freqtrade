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

class future18(IStrategy):
    # ROI table for profit taking
    minimal_roi = {
        "0": 0.05,    # Take 5% profit immediately
        "5": 0.03,    # 3% after 5 minutes
        "15": 0.02,   # 2% after 15 minutes
        "30": 0       # Any profit after 30 minutes
    }

    # Risk parameters
    stoploss = -0.08  # Stoploss setting
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = False

    # Hyperoptable parameters
    # Leverage
    leverage_param = IntParameter(1, 10, default=5, space="buy", optimize=True)
    
    # RSI thresholds
    buy_rsi = IntParameter(30, 50, default=40, space="buy", optimize=True)
    sell_rsi_upper = IntParameter(60, 85, default=70, space="sell", optimize=True)
    sell_rsi_lower = IntParameter(20, 40, default=30, space="sell", optimize=True)
    
    # MACD parameters
    macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
    macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
    
    # Moving average parameters
    ema_short_period = IntParameter(5, 15, default=8, space="both", optimize=True)
    ema_long_period = IntParameter(15, 30, default=21, space="both", optimize=True)
    
    # Price extension threshold
    price_extension_pct = DecimalParameter(0.003, 0.01, default=0.005, space="sell", optimize=True)
    
    # New parameter: Wait time before entry confirmation
    entry_wait_time = IntParameter(1, 15, default=5, space="buy", optimize=True)
    
    # Strategy settings
    timeframe = '1m'
    startup_candle_count = 100
    process_only_new_candles = True
    can_short = True
    can_long = False  # Focusing only on shorts

    # Cooldown tracking
    _last_candle_seen_time = {}
    
    # Entry signal tracking
    _entry_signals = {}

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_candle_seen_time = {}
        self._entry_signals = {}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ===== CORE TECHNICAL INDICATORS =====
        
        # RSI indicator
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Stochastic
        stoch = ta.STOCH(dataframe, fastk_period=14, slowk_period=3, slowd_period=3)
        dataframe['slowk'] = stoch['slowk']
        dataframe['slowd'] = stoch['slowd']
        
        # MACD with hyperoptable parameters
        macd = ta.MACD(dataframe, 
                      fastperiod=self.macd_fast.value,
                      slowperiod=self.macd_slow.value, 
                      signalperiod=self.macd_signal.value)
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
        
        # Moving averages with hyperoptable parameters
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=self.ema_short_period.value)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=self.ema_long_period.value)
        
        # Store shifted prices
        for i in range(1, 4):
            dataframe[f'close_prev{i}'] = dataframe['close'].shift(i)
            dataframe[f'high_prev{i}'] = dataframe['high'].shift(i)
            dataframe[f'low_prev{i}'] = dataframe['low'].shift(i)
        
        # ===== ENTRY SIGNAL DETECTION =====
        
        # Detect peaks - when current price is at or near local maximum
        dataframe['high_last_3'] = dataframe['high'].rolling(3).max()
        
        # Price is at a local peak - using hyperoptable parameters
        dataframe['price_peak'] = (
            (dataframe['high'] >= dataframe['high_last_3'] * 0.995) &  # Price near the highest point
            (dataframe['high'] > dataframe['high_prev1']) &            # Current high higher than previous
            (dataframe['close'] > dataframe['ema_short']) &            # Price above short-term average
            (dataframe['rsi'] > self.sell_rsi_upper.value)             # RSI elevated but not extreme (hyperopt)
        )
        
        # Price reversal after a rise - using hyperoptable parameters
        dataframe['price_reversal'] = (
            (dataframe['close_prev2'] < dataframe['close_prev1']) &    # Prior candle was up
            (dataframe['close'] < dataframe['close_prev1']) &           # Current candle is down
            (dataframe['close_prev1'] > dataframe['close_prev1'].rolling(3).max().shift(1)) &  # Local high
            (dataframe['rsi'] > self.sell_rsi_upper.value * 0.9)       # RSI elevated (hyperopt)
        )
        
        # MACD histogram reversal - using hyperoptable parameters
        dataframe['macd_reversal'] = (
            (dataframe['macdhist_prev2'] < dataframe['macdhist_prev1']) &  # Previous MACD hist was rising
            (dataframe['macdhist'] < dataframe['macdhist_prev1']) &         # Current MACD hist is falling
            (dataframe['macdhist_prev1'] > 0) &                            # Previous MACD hist was positive
            (dataframe['close'] > dataframe['ema_short'])                  # Price above short-term average
        )
        
        # Combined entry signal - using hyperoptable parameters
        dataframe['short_entry_signal'] = (
            (dataframe['price_peak'] | dataframe['price_reversal'] | dataframe['macd_reversal']) &
            (dataframe['rsi'] > self.sell_rsi_upper.value * 0.9) &   # RSI must be elevated (hyperopt)
            (dataframe['close'] > dataframe['ema_short'] * (1 + self.price_extension_pct.value))  # Price must be extended above MA (hyperopt)
        )
        
        # ===== EXIT SIGNAL DETECTION - SIGNIFICANTLY REDUCED =====
        
        # Strong oversold condition for exits - only extreme cases
        dataframe['deep_oversold'] = (
            (dataframe['rsi'] < self.sell_rsi_lower.value * 0.9) &      # Very low RSI (hyperopt)
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
        # We will not actually enter here, this is just a signal 
        # The actual entry decision will be in confirm_trade_entry
        dataframe.loc[dataframe['short_entry_signal'], 'enter_short'] = 1
        
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                           side: str, **kwargs) -> bool:
        """
        Enhanced confirmation logic:
        1. Record the entry signal with timestamp and price
        2. Check if we've waited long enough
        3. Compare current price with recorded price
        4. Enter only if price has stayed the same or increased (for shorts)
        """
        # If this is the first time we see this signal, record it and reject (need to wait)
        if pair not in self._entry_signals:
            self._entry_signals[pair] = {
                'timestamp': current_time,
                'price': rate
            }
            return False
        
        entry_signal = self._entry_signals[pair]
        elapsed_minutes = (current_time - entry_signal['timestamp']).total_seconds() / 60
        
        # If we haven't waited long enough, reject
        if elapsed_minutes < self.entry_wait_time.value:
            return False
        
        # If we've waited enough, check price action
        original_price = entry_signal['price']
        
        # For shorts, we want price to have held or gone up
        if side == 'short':
            # If price went down, reject the trade
            if rate < original_price:
                # Clear the signal since it didn't work out
                del self._entry_signals[pair]
                return False
        else:  # For longs (if implemented in future)
            # If price went up, reject the trade
            if rate > original_price:
                # Clear the signal since it didn't work out
                del self._entry_signals[pair]
                return False
        
        # Check cooldown period (3 minutes between trades of same pair)
        cooldown_minutes = 3
        
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
                
        # Update the last seen time for this pair
        self._last_candle_seen_time[pair] = current_time
        
        # Clear the entry signal since we're entering the trade
        del self._entry_signals[pair]
        
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
                    
                    # Take profit at 5%
                    if current_profit > 0.05:
                        return 'short_profit_target_reached'
                    
                    # Only exit on extreme oversold conditions
                    if current_profit > 0.02 and 'rsi' in last_candle and last_candle['rsi'] < 25:
                        return 'short_profit_extreme_oversold'
                    
            except Exception as e:
                pass
        
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
                **kwargs) -> float:
        """Return leverage based on hyperopt parameter"""
        return float(self.leverage_param.value)

    def hyperopt_space(self) -> List[Dimension]:
        """Define hyperopt space with the new wait time parameter"""
        return [
            Integer(1, 10, name='leverage_param'),
            Integer(30, 50, name='buy_rsi'),
            Integer(60, 85, name='sell_rsi_upper'),
            Integer(20, 40, name='sell_rsi_lower'),
            Integer(8, 16, name='macd_fast'),
            Integer(18, 32, name='macd_slow'),
            Integer(6, 12, name='macd_signal'),
            Integer(5, 15, name='ema_short_period'),
            Integer(15, 30, name='ema_long_period'),
            Real(0.003, 0.01, name='price_extension_pct'),
            Integer(1, 15, name='entry_wait_time')  # New hyperopt parameter
        ]
