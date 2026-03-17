from collections import defaultdict
from datetime import datetime, timedelta
from functools import reduce
from typing import Optional, List, Tuple, Dict
from skopt.space import Dimension, Real

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter

class future6(IStrategy):
    # Updated ROI table from hyperopt results
    minimal_roi = {
        "0": 0.012,
        "5": 0.009,
        "15": 0.005,
        "29": 0
    }

    # Risk management parameters from hyperopt
    stoploss = -0.252
    trailing_stop = True
    trailing_stop_positive = 0.235
    trailing_stop_positive_offset = 0.291
    trailing_only_offset_is_reached = False

    # Leverage parameters - updated based on results
    max_leverage_param = IntParameter(2, 3, default=2, space="sell", optimize=True)
    min_leverage_param = IntParameter(1, 1, default=1, space="sell", optimize=False)
    
    # Updated parameter ranges based on hyperopt results
    bb_multiplier = DecimalParameter(0.94, 0.98, default=0.955, space="sell", optimize=True)
    sell_rsi_threshold = IntParameter(40, 50, default=43, space="sell", optimize=True)
    volume_ma_multiplier = DecimalParameter(1.5, 2.0, default=1.715, space="sell", optimize=True)
    
    # Cooldown parameter - narrowed around optimal
    cooldown_lookback = IntParameter(1, 3, default=2, space="sell", optimize=True)

    # Other strategy parameters
    timeframe = '1m'
    startup_candle_count = 100
    process_only_new_candles = True
    use_exit_signal = True
    can_short = True  # Enable short trading
    can_long = False  # Disable long trading

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_trade_time = {}
        self.dynamic_leverage = {}

    def leverage(self, pair: str, current_time: datetime, **kwargs) -> float:
        """Return the leverage to use - dynamically calculated based on price position"""
        if pair in self.dynamic_leverage:
            return float(self.dynamic_leverage[pair])
        else:
            # Default to minimum leverage if we can't determine
            return float(self.min_leverage_param.value)

    def hyperopt_space(self) -> List[Dimension]:
        """Define hyperopt space for optimizing trailing stop parameters"""
        return [
            Real(-0.3, -0.1, name='stoploss'),
            Real(0.15, 0.3, name='trailing_stop_positive'),
            Real(0.2, 0.35, name='trailing_stop_positive_offset'),
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Basic indicators
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        
        # Volume
        dataframe['volume_ma'] = dataframe['volume'].rolling(window=20).mean()
        
        # Simple price movements
        dataframe['price_change'] = dataframe['close'].pct_change()
        dataframe['price_rise'] = dataframe['price_change'] > 0.001  # Looking for rises now instead of dips
        
        # 48-hour average price
        dataframe['avg_price_48h'] = dataframe['close'].rolling(window=2880).mean()
        
        # Calculate 48h high and low for leverage calculation
        dataframe['48h_high'] = dataframe['high'].rolling(window=2880).max()
        dataframe['48h_low'] = dataframe['low'].rolling(window=2880).min()
        dataframe['price_48h_position'] = (dataframe['close'] - dataframe['48h_low']) / (dataframe['48h_high'] - dataframe['48h_low']).replace(0, float('nan'))
        
        # Store dynamic leverage calculation - inverse logic for shorts
        pair = metadata['pair']
        if not dataframe.empty and 'price_48h_position' in dataframe:
            if not np.isnan(dataframe['price_48h_position'].iloc[-1]):
                price_position = dataframe['price_48h_position'].iloc[-1]
                
                # Ensure reasonable range
                price_position = max(0.01, min(0.99, price_position))
                
                # Calculate leverage: max at TOP of range for shorts, min at bottom
                # This is the inverse of the long strategy
                max_lev = self.max_leverage_param.value
                min_lev = self.min_leverage_param.value
                
                # Direct relationship for shorts - higher in range = higher leverage
                leverage = min_lev + ((max_lev - min_lev) * price_position)
                
                # Store the calculated leverage
                self.dynamic_leverage[pair] = round(leverage)
            else:
                # Default to minimum if we can't calculate
                self.dynamic_leverage[pair] = self.min_leverage_param.value
                
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry conditions for shorts - inverse of long logic
        """
        pair = metadata['pair']
        
        # No long entries
        dataframe['enter_long'] = 0
        
        # Cooldown check with optimized lookback
        cooldown_ok = True
        if pair in self._last_trade_time:
            last_trade = self._last_trade_time[pair]
            cooldown_minutes = self.cooldown_lookback.value
            cooldown_end = last_trade + timedelta(minutes=cooldown_minutes)
            now = datetime.now()
            if now < cooldown_end:
                cooldown_ok = False
        
        # Simple entry conditions for shorts - only need ONE of these to be true
        if cooldown_ok:
            short_conditions = [
                # Condition 1: Price above Bollinger upper band with optimized multiplier
                (dataframe['close'] > dataframe['bb_upperband'] * self.bb_multiplier.value),
                
                # Condition 2: RSI overbought with optimized threshold
                (dataframe['rsi'] > self.sell_rsi_threshold.value) & (dataframe['rsi'] < 80),
                
                # Condition 3: Volume spike with optimized multiplier
                (dataframe['volume'] > dataframe['volume_ma'] * self.volume_ma_multiplier.value),
                
                # Condition 4: Price rise (opposite of dip for longs)
                (dataframe['price_rise'])
            ]
            
            # Generate short entry signals - need just ONE of any_conditions to be true
            dataframe.loc[reduce(lambda x, y: x | y, short_conditions), 'enter_short'] = 1
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit conditions for shorts - inverse of long exit conditions
        """
        # Initialize both exit columns to 0
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        # Basic exit conditions for shorts - only need ONE to be true
        short_exit_conditions = [
            # Condition 1: Price below Bollinger lower band
            (dataframe['close'] < dataframe['bb_lowerband'] * 1.02),
            
            # Condition 2: RSI oversold
            (dataframe['rsi'] < 30),
            
            # Condition 3: Volume spike with price decrease
            (dataframe['volume'] > dataframe['volume_ma'] * 2.0) & 
            (dataframe['price_change'] < -0.002)
        ]
        
        dataframe.loc[reduce(lambda x, y: x | y, short_exit_conditions), 'exit_short'] = 1
            
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """
        Profit taking and emergency exit logic for shorts
        """
        # Track trades for cooldown
        self._last_trade_time[pair] = current_time
        
        # Take profit based on leverage - using hyperopt optimal values
        leverage = trade.leverage if trade.leverage else 1
        base_profit = 0.012  # Aligned with ROI table's first threshold
        target_profit = base_profit * leverage
        
        # Profit taking (for shorts, profit is still positive)
        if current_profit >= target_profit:
            return 'take_profit'
            
        # Emergency exit - still keeping this for safety but adjusted
        if current_profit <= -0.15 and current_profit > self.stoploss:
            # Only exit if we've been in the trade for a while
            if (current_time - trade.open_date_utc).total_seconds() > 60:
                return 'emergency_exit'
                
        return None

    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                          rate: float, time_in_force: str, exit_reason: str,
                          current_time: datetime, **kwargs) -> bool:
        """
        Record trade time for cooldown
        """
        self._last_trade_time[pair] = current_time
        return True
