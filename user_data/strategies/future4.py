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

class future4(IStrategy):
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
    max_leverage_param = IntParameter(2, 10, default=3, space="buy", optimize=True)
    min_leverage_param = IntParameter(1, 2, default=1, space="buy", optimize=True)
    
    # Updated parameter ranges based on hyperopt results
    bb_multiplier = DecimalParameter(1.02, 1.06, default=1.045, space="buy", optimize=True)
    buy_rsi_threshold = IntParameter(50, 60, default=57, space="buy", optimize=True)
    volume_ma_multiplier = DecimalParameter(1.5, 2.0, default=1.715, space="buy", optimize=True)
    
    # Cooldown parameter - narrowed around optimal
    cooldown_lookback = IntParameter(1, 3, default=2, space="buy", optimize=True)

    # Other strategy parameters
    timeframe = '1m'
    startup_candle_count = 100
    process_only_new_candles = True
    use_exit_signal = True
    can_short = False

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
        
        # Simple price dips
        dataframe['price_change'] = dataframe['close'].pct_change()
        dataframe['price_dip'] = dataframe['price_change'] < -0.001
        
        # 48-hour average price
        dataframe['avg_price_48h'] = dataframe['close'].rolling(window=2880).mean()
        
        # Calculate 48h high and low for leverage calculation
        dataframe['48h_high'] = dataframe['high'].rolling(window=2880).max()
        dataframe['48h_low'] = dataframe['low'].rolling(window=2880).min()
        dataframe['price_48h_position'] = (dataframe['close'] - dataframe['48h_low']) / (dataframe['48h_high'] - dataframe['48h_low']).replace(0, float('nan'))
        
        # Store dynamic leverage calculation
        pair = metadata['pair']
        if not dataframe.empty and 'price_48h_position' in dataframe:
            if not np.isnan(dataframe['price_48h_position'].iloc[-1]):
                price_position = dataframe['price_48h_position'].iloc[-1]
                
                # Ensure reasonable range
                price_position = max(0.01, min(0.99, price_position))
                
                # Calculate leverage: max at bottom of range, min at top
                max_lev = self.max_leverage_param.value
                min_lev = self.min_leverage_param.value
                
                # Inverse relationship - lower position = higher leverage
                leverage = max_lev - ((max_lev - min_lev) * price_position)
                
                # Store the calculated leverage
                self.dynamic_leverage[pair] = round(leverage)
            else:
                # Default to minimum if we can't calculate
                self.dynamic_leverage[pair] = self.min_leverage_param.value
                
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry conditions with parameters optimized from hyperopt
        """
        pair = metadata['pair']
        
        # Simple entry conditions - only need ONE of these to be true
        any_conditions = [
            # Condition 1: Price below Bollinger lower band with optimized multiplier
            (dataframe['close'] < dataframe['bb_lowerband'] * self.bb_multiplier.value),
            
            # Condition 2: RSI oversold with optimized threshold
            (dataframe['rsi'] < self.buy_rsi_threshold.value) & (dataframe['rsi'] > 20),
            
            # Condition 3: Volume spike with optimized multiplier
            (dataframe['volume'] > dataframe['volume_ma'] * self.volume_ma_multiplier.value),
            
            # Condition 4: Price dip
            (dataframe['price_dip'])
        ]
        
        # Cooldown check with optimized lookback
        cooldown_ok = True
        if pair in self._last_trade_time:
            last_trade = self._last_trade_time[pair]
            cooldown_minutes = self.cooldown_lookback.value
            cooldown_end = last_trade + timedelta(minutes=cooldown_minutes)
            now = datetime.now()
            if now < cooldown_end:
                cooldown_ok = False
        
        # Generate entry signals - need just ONE of any_conditions to be true
        if cooldown_ok:
            dataframe.loc[reduce(lambda x, y: x | y, any_conditions), 'enter_long'] = 1
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit conditions - optimized based on good ROI results
        """
        # Basic exit conditions - only need ONE to be true
        exit_conditions = [
            # Condition 1: Price above Bollinger upper band
            (dataframe['close'] > dataframe['bb_upperband'] * 0.98),
            
            # Condition 2: RSI overbought
            (dataframe['rsi'] > 70),
            
            # Condition 3: Volume spike with price increase
            (dataframe['volume'] > dataframe['volume_ma'] * 2.0) & 
            (dataframe['price_change'] > 0.002)
        ]
        
        dataframe.loc[reduce(lambda x, y: x | y, exit_conditions), 'exit_long'] = 1
            
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """
        Profit taking and emergency exit logic
        """
        # Track trades for cooldown
        self._last_trade_time[pair] = current_time
        
        # Take profit based on leverage - using hyperopt optimal values
        leverage = trade.leverage if trade.leverage else 1
        base_profit = 0.012  # Aligned with ROI table's first threshold
        target_profit = base_profit * leverage
        
        # Profit taking
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
