from functools import reduce
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter
from skopt.space import Integer, Real, Categorical, Dimension

class future30(IStrategy):
    # ROI table for profit taking
    minimal_roi = {
        "0": 0.05,    # Take 5% profit immediately
        "5": 0.03,    # 3% after 5 minutes
        "15": 0.02,   # 2% after 15 minutes
        "30": 0       # Any profit after 30 minutes
    }

    # Risk parameters
    stoploss = -0.10  # Stoploss setting
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
    
    # Strategy settings
    timeframe = '1m'
    informative_timeframe = '5m'  # Added 5m timeframe for entry signals
    startup_candle_count = 100
    process_only_new_candles = True
    can_short = True
    can_long = False  # Focusing only on shorts

    # Cooldown tracking
    _last_candle_seen_time = {}

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_candle_seen_time = {}

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, self.informative_timeframe) for pair in pairs]
        return informative_pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # First, process 1m indicators for exits
        # RSI indicator on 1m for exits
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Moving averages on 1m for exit conditions
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=self.ema_short_period.value)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=self.ema_long_period.value)
        
        # Bollinger Bands on 1m for exits
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_lowerband'] = bollinger['lower']
        
        # MACD on 1m for exits
        macd = ta.MACD(dataframe, 
                      fastperiod=self.macd_fast.value,
                      slowperiod=self.macd_slow.value, 
                      signalperiod=self.macd_signal.value)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # ===== EXIT SIGNAL DETECTION ON 1m =====
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
        
        # Combined exit signal - responsive on 1m timeframe
        dataframe['short_exit_signal'] = (
            dataframe['deep_oversold'] | 
            dataframe['major_trend_reversal']
        )
        
        # Now get 5m candles for entry decisions
        if self.dp:
            informative = self.dp.get_pair_dataframe(
                pair=metadata['pair'], 
                timeframe=self.informative_timeframe
            )
            
            # ===== 5m INDICATORS FOR ENTRIES =====
            
            # RSI indicator on 5m
            informative['rsi'] = ta.RSI(informative, timeperiod=14)
            
            # Stochastic on 5m
            stoch = ta.STOCH(informative, fastk_period=14, slowk_period=3, slowd_period=3)
            informative['slowk'] = stoch['slowk']
            informative['slowd'] = stoch['slowd']
            
            # MACD with hyperoptable parameters on 5m
            macd = ta.MACD(informative, 
                          fastperiod=self.macd_fast.value,
                          slowperiod=self.macd_slow.value, 
                          signalperiod=self.macd_signal.value)
            informative['macd'] = macd['macd']
            informative['macdsignal'] = macd['macdsignal']
            informative['macdhist'] = macd['macdhist']
            
            # Store shifted values for pattern detection on 5m
            informative['macdhist_prev1'] = informative['macdhist'].shift(1)
            informative['macdhist_prev2'] = informative['macdhist'].shift(2)
            
            # Bollinger Bands on 5m
            bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(informative), window=20, stds=2)
            informative['bb_upperband'] = bollinger['upper']
            informative['bb_middleband'] = bollinger['mid']
            informative['bb_lowerband'] = bollinger['lower']
            
            # Moving averages with hyperoptable parameters on 5m
            informative['ema_short'] = ta.EMA(informative, timeperiod=self.ema_short_period.value)
            informative['ema_long'] = ta.EMA(informative, timeperiod=self.ema_long_period.value)
            
            # Store shifted prices on 5m
            for i in range(1, 4):
                informative[f'close_prev{i}'] = informative['close'].shift(i)
                informative[f'high_prev{i}'] = informative['high'].shift(i)
                informative[f'low_prev{i}'] = informative['low'].shift(i)
            
            # ===== ENTRY SIGNAL DETECTION ON 5m =====
            
            # Detect peaks - when current price is at or near local maximum
            informative['high_last_3'] = informative['high'].rolling(3).max()
            
            # Price is at a local peak - using hyperoptable parameters
            informative['price_peak'] = (
                (informative['high'] >= informative['high_last_3'] * 0.995) &  # Price near the highest point
                (informative['high'] > informative['high_prev1']) &            # Current high higher than previous
                (informative['close'] > informative['ema_short']) &            # Price above short-term average
                (informative['rsi'] > self.sell_rsi_upper.value)               # RSI elevated but not extreme (hyperopt)
            )
            
            # Price reversal after a rise - using hyperoptable parameters
            informative['price_reversal'] = (
                (informative['close_prev2'] < informative['close_prev1']) &    # Prior candle was up
                (informative['close'] < informative['close_prev1']) &           # Current candle is down
                (informative['close_prev1'] > informative['close_prev1'].rolling(3).max().shift(1)) &  # Local high
                (informative['rsi'] > self.sell_rsi_upper.value * 0.9)       # RSI elevated (hyperopt)
            )
            
            # MACD histogram reversal - using hyperoptable parameters
            informative['macd_reversal'] = (
                (informative['macdhist_prev2'] < informative['macdhist_prev1']) &  # Previous MACD hist was rising
                (informative['macdhist'] < informative['macdhist_prev1']) &         # Current MACD hist is falling
                (informative['macdhist_prev1'] > 0) &                            # Previous MACD hist was positive
                (informative['close'] > informative['ema_short'])                  # Price above short-term average
            )
            
            # Combined entry signal - using hyperoptable parameters (on 5m)
            informative['short_entry_signal'] = (
                (informative['price_peak'] | informative['price_reversal'] | informative['macd_reversal']) &
                (informative['rsi'] > self.sell_rsi_upper.value * 0.9) &   # RSI must be elevated (hyperopt)
                (informative['close'] > informative['ema_short'] * (1 + self.price_extension_pct.value))  # Price must be extended above MA (hyperopt)
            )
            
            # Merge informative timeframe data with current timeframe
            # Converting boolean values to integers for easier handling in merged dataframe
            for col in ['short_entry_signal', 'price_peak', 'price_reversal', 'macd_reversal']:
                informative[col] = informative[col].astype(int)
                
            dataframe = merge_informative_pair(dataframe, informative, self.timeframe, self.informative_timeframe, ffill=True)
            
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry signals from 5m timeframe"""
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        # Apply short entry signal from 5m timeframe
        # The column name follows the pattern: {column}_{timeframe}
        dataframe.loc[dataframe['short_entry_signal_5m'] > 0, 'enter_short'] = 1
        
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                           side: str, **kwargs) -> bool:
        """
        Simple cooldown logic - using a longer cooldown since we're using 5m signals
        """
        # Check cooldown period (5 minutes between trades of same pair - increased from 3)
        cooldown_minutes = 5
        
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
                
        # Update the last seen time for this pair
        self._last_candle_seen_time[pair] = current_time
        
        return True

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit signals - using responsive 1m timeframe"""
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        # Only mark significant exit points using 1m timeframe - for quick reactions
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
                    
                    # Exit on extreme oversold conditions (using 1m timeframe for responsiveness)
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
        """Define hyperopt space"""
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
            Real(0.003, 0.01, name='price_extension_pct')
        ]
