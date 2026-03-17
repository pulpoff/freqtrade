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

class future24(IStrategy):
    # Improved ROI table - take profits faster and more aggressively
    minimal_roi = {
        "0": 0.02,    # Take 2% profit immediately
        "5": 0.015,   # 1.5% after 5 minutes
        "10": 0.01,   # 1% after 10 minutes
        "15": 0.005,  # 0.5% after 15 minutes
        "20": 0       # Any profit after 20 minutes
    }

    # Better risk parameters based on analysis
    stoploss = -0.03  # Tighter stoploss
    trailing_stop = True
    trailing_stop_positive = 0.01  # Start trailing at 1%
    trailing_stop_positive_offset = 0.015  # Offset by 1.5%
    trailing_only_offset_is_reached = True  # Only trail after reaching the offset

    # Strategy settings
    timeframe = '1m'
    startup_candle_count = 100
    process_only_new_candles = True
    can_short = True
    can_long = False  # Focusing only on shorts

    # Parameters - optimized based on the results
    leverage_param = IntParameter(1, 5, default=2, space="buy", optimize=True)  # Lower default leverage
    buy_rsi = IntParameter(30, 50, default=40, space="buy", optimize=True)
    sell_rsi_upper = IntParameter(55, 75, default=65, space="sell", optimize=True)  # Higher default
    sell_rsi_lower = IntParameter(20, 40, default=30, space="sell", optimize=True)
    
    # MACD parameters
    macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
    macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
    
    # EMA parameters
    ema_short_period = IntParameter(5, 15, default=8, space="both", optimize=True)
    ema_long_period = IntParameter(15, 30, default=21, space="both", optimize=True)
    tema_period = IntParameter(7, 21, default=9, space="both", optimize=True)
    
    # Price extension - less aggressive
    price_extension_pct = DecimalParameter(0.002, 0.008, default=0.003, space="sell", optimize=True)
    
    # Signal combination parameters
    use_price_peak = CategoricalParameter([True, False], default=True, space="buy", optimize=True)
    use_price_reversal = CategoricalParameter([True, False], default=True, space="buy", optimize=True)
    use_macd_reversal = CategoricalParameter([True, False], default=True, space="buy", optimize=True)
    use_tema_trend = CategoricalParameter([True, False], default=True, space="buy", optimize=True)  # Enable by default
    
    # Exit signal parameters - adjusted based on results
    use_deep_oversold = CategoricalParameter([True, False], default=False, space="sell", optimize=True)  # Disable by default
    use_trend_reversal = CategoricalParameter([True, False], default=True, space="sell", optimize=True)

    # Cooldown tracking
    _last_candle_seen_time = {}
    
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_candle_seen_time = {}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ===== CORE TECHNICAL INDICATORS =====
        
        # RSI indicator
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Stochastic
        stoch = ta.STOCH(dataframe, fastk_period=14, slowk_period=3, slowd_period=3)
        dataframe['slowk'] = stoch['slowk']
        dataframe['slowd'] = stoch['slowd']
        
        # MACD
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
        
        # Moving averages
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=self.ema_short_period.value)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=self.ema_long_period.value)
        dataframe['tema'] = ta.TEMA(dataframe, timeperiod=self.tema_period.value)
        
        # Store shifted prices
        for i in range(1, 4):
            dataframe[f'close_prev{i}'] = dataframe['close'].shift(i)
            dataframe[f'high_prev{i}'] = dataframe['high'].shift(i)
            dataframe[f'low_prev{i}'] = dataframe['low'].shift(i)
        
        # ===== IMPROVED TREND DETECTION =====
        
        # Better trend detection - more strict to avoid bad entries
        dataframe['downtrend'] = (
            (dataframe['ema_short'] < dataframe['ema_long']) &  # Short EMA below long EMA
            (dataframe['ema_short'].shift(3) > dataframe['ema_short']) &  # Short EMA has been decreasing
            (dataframe['ema_long'].shift(3) > dataframe['ema_long'])      # Long EMA has been decreasing too
        )
        
        dataframe['tema_downtrend'] = (
            (dataframe['tema'] < dataframe['ema_short']) &
            (dataframe['tema'].shift(2) > dataframe['tema'])  # TEMA decreasing
        )
        
        # ===== ENTRY SIGNAL DETECTION =====
        
        # Set up basic conditions
        dataframe['high_last_3'] = dataframe['high'].rolling(3).max()
        
        # Price is at a local peak - more selective
        dataframe['price_peak'] = (
            (dataframe['high'] >= dataframe['high_last_3'] * 0.995) &  # Price near the highest point (more strict)
            (dataframe['high'] > dataframe['high_prev1']) &           # Current high higher than previous
            (dataframe['close'] > dataframe['ema_short']) &           # Price above short-term average
            (dataframe['rsi'] > self.sell_rsi_upper.value)            # RSI elevated (more strict)
        )
        
        # Price reversal after a rise - more selective
        dataframe['price_reversal'] = (
            (dataframe['close_prev1'] > dataframe['close_prev2']) &     # Prior candle was up
            (dataframe['close'] < dataframe['close_prev1'] * 0.997) &   # Current candle is down significantly
            (dataframe['close_prev1'] > dataframe['close_prev1'].rolling(3).max().shift(1)) &  # Local high
            (dataframe['rsi'] > self.sell_rsi_upper.value * 0.95)       # RSI elevated
        )
        
        # MACD histogram reversal - more selective
        dataframe['macd_reversal'] = (
            (dataframe['macdhist_prev2'] < dataframe['macdhist_prev1']) &  # Previous MACD hist was rising
            (dataframe['macdhist'] < dataframe['macdhist_prev1'] * 0.8) &  # Current MACD hist is falling significantly
            (dataframe['macdhist_prev1'] > 0) &                           # Previous MACD hist was positive
            (dataframe['close'] > dataframe['ema_short'])                 # Price above short EMA
        )
        
        # Determine primary entry conditions - require stronger signals
        entry_condition = False
        
        # Add selected signal types
        if self.use_price_peak.value:
            entry_condition = entry_condition | dataframe['price_peak']
            
        if self.use_price_reversal.value:
            entry_condition = entry_condition | dataframe['price_reversal']
            
        if self.use_macd_reversal.value:
            entry_condition = entry_condition | dataframe['macd_reversal']
        
        # If no signals were selected, use all of them
        if not self.use_price_peak.value and not self.use_price_reversal.value and not self.use_macd_reversal.value:
            entry_condition = (
                dataframe['price_peak'] | 
                dataframe['price_reversal'] | 
                dataframe['macd_reversal']
            )
            
        # Apply TEMA trend filter only if enabled
        if self.use_tema_trend.value:
            trend_condition = dataframe['downtrend'] & dataframe['tema_downtrend']
        else:
            trend_condition = dataframe['downtrend']  # Only require basic downtrend
            
        # IMPROVED SHORT ENTRY SIGNAL - more selective to reduce losing trades
        dataframe['short_entry_signal'] = (
            entry_condition &
            trend_condition &
            (dataframe['rsi'] > self.sell_rsi_upper.value * 0.95) &  # RSI must be elevated
            (dataframe['close'] > dataframe['ema_short'] * (1 + self.price_extension_pct.value))  # Price extended above EMA
        )
        
        # Additional quality filter - don't enter when price is already near lower BB
        dataframe.loc[
            (dataframe['close'] < dataframe['bb_middleband']) |
            (dataframe['rsi'] < self.buy_rsi.value),            # RSI not too low already
            'short_entry_signal'
        ] = False
        
        # ===== EXIT SIGNAL DETECTION =====
        
        # Improved exit conditions - focusing on early profit-taking
        dataframe['deep_oversold'] = (
            (dataframe['rsi'] < self.sell_rsi_lower.value) &                  # Very low RSI (stricter)
            ((dataframe['close'] < dataframe['bb_lowerband'] * 1.01) |        # Price near lower BB
             (dataframe['close'] < dataframe['ema_short'] * 0.99))            # Price below short EMA
        )
        
        # Improved trend reversal exit - more selective
        dataframe['major_trend_reversal'] = (
            qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal']) &  # MACD crosses above signal
            (dataframe['macd'] < 0) &                                           # MACD is negative
            (dataframe['rsi'] < 45)                                             # RSI not too high
        )
        
        # Combined exit signal - favor quick profit-taking
        exit_condition = False
        
        if self.use_deep_oversold.value:
            exit_condition = exit_condition | dataframe['deep_oversold']
            
        if self.use_trend_reversal.value:
            exit_condition = exit_condition | dataframe['major_trend_reversal']
            
        # If no signals selected, use trend reversal by default
        if not self.use_deep_oversold.value and not self.use_trend_reversal.value:
            exit_condition = dataframe['major_trend_reversal']
            
        dataframe['short_exit_signal'] = exit_condition
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry signals for shorts with controlled frequency"""
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        # Apply short entry signal
        dataframe.loc[dataframe['short_entry_signal'], 'enter_short'] = 1
        
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                           side: str, **kwargs) -> bool:
        """
        Improved cooldown logic - longer cooldown to avoid frequent trades
        """
        # Check cooldown period (increased to 5 minutes between trades)
        cooldown_minutes = 5
        
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
                
        # Update the last seen time for this pair
        self._last_candle_seen_time[pair] = current_time
        
        return True

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit signals"""
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        # Mark exit points
        dataframe.loc[dataframe['short_exit_signal'], 'exit_short'] = 1
        
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """
        Improved exit logic - focus on quick profits and early loss-cutting
        """
        if trade.is_short:
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if len(dataframe) > 0:
                    last_candle = dataframe.iloc[-1]
                    
                    # Take profit at 2% - quick profit-taking
                    if current_profit > 0.02:
                        return 'short_profit_target_reached'
                    
                    # Exit on profit and oversold
                    if current_profit > 0.01 and 'rsi' in last_candle and last_candle['rsi'] < 30:
                        return 'short_profit_with_oversold'
                    
                    # Cut losses early
                    if current_profit < -0.01 and trade.open_date_utc + timedelta(minutes=10) < current_time:
                        return 'short_early_loss_exit'
                    
            except Exception as e:
                pass
        
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
                **kwargs) -> float:
        """Return leverage value - reduced to lower risk"""
        return float(self.leverage_param.value)

    def hyperopt_space(self) -> List[Dimension]:
        """Define hyperopt space - focused on key parameters"""
        return [
            Integer(1, 5, name='leverage_param'),  # Lower leverage range
            Integer(30, 50, name='buy_rsi'),
            Integer(55, 75, name='sell_rsi_upper'),
            Integer(20, 40, name='sell_rsi_lower'),
            Integer(8, 16, name='macd_fast'),
            Integer(18, 32, name='macd_slow'),
            Integer(6, 12, name='macd_signal'),
            Integer(5, 15, name='ema_short_period'),
            Integer(15, 30, name='ema_long_period'),
            Integer(7, 21, name='tema_period'),
            Real(0.002, 0.008, name='price_extension_pct'),
            Categorical([True, False], name='use_price_peak'),
            Categorical([True, False], name='use_price_reversal'),
            Categorical([True, False], name='use_macd_reversal'),
            Categorical([True, False], name='use_tema_trend'),
            Categorical([True, False], name='use_deep_oversold'),
            Categorical([True, False], name='use_trend_reversal')
        ]
