from datetime import datetime, timedelta
from typing import Optional, List

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter
from skopt.space import Integer, Real, Categorical, Dimension

class future25(IStrategy):
    # Faster profit-taking ROI
    minimal_roi = {
        "0": 0.02,    # Take 2% profit immediately
        "5": 0.015,   # 1.5% after 5 minutes
        "10": 0.01,   # 1% after 10 minutes
        "15": 0.005,  # 0.5% after 15 minutes
    }

    # Tighter risk parameters
    stoploss = -0.13  # Smaller stoploss
    trailing_stop = True
    trailing_stop_positive = 0.01  # Start trailing at 1%
    trailing_stop_positive_offset = 0.015  # Offset by 1.5%
    trailing_only_offset_is_reached = True  # Only trail after reaching the offset

    # Strategy settings
    timeframe = '1m'
    startup_candle_count = 30
    process_only_new_candles = True
    can_short = True
    can_long = False  # Focusing only on shorts

    # Basic parameters
    leverage_param = IntParameter(1, 3, default=2, space="buy", optimize=True)  # Lower leverage
    rsi_period = IntParameter(10, 20, default=14, space="buy", optimize=True)
    rsi_upper = IntParameter(65, 85, default=70, space="sell", optimize=True)
    rsi_lower = IntParameter(20, 35, default=30, space="sell", optimize=True)
    ema_period = IntParameter(5, 20, default=10, space="both", optimize=True)
    use_profit_only = CategoricalParameter([True, False], default=True, space="sell", optimize=True)
    
    # Cooldown tracking
    _last_candle_seen_time = {}
    
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_candle_seen_time = {}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Basic indicators
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        dataframe['ema'] = ta.EMA(dataframe, timeperiod=self.ema_period.value)
        
        # Calculate price changes for volatility assessment
        dataframe['price_change'] = (dataframe['close'] - dataframe['close'].shift(1)) / dataframe['close'].shift(1)
        dataframe['volatility'] = dataframe['price_change'].rolling(5).std()
        
        # Entry condition: Price above EMA + RSI overbought 
        dataframe['short_entry'] = (
            (dataframe['close'] > dataframe['ema']) &
            (dataframe['rsi'] > self.rsi_upper.value)
        )
        
        # IMPROVED EXIT CONDITION: Only exit on profit or strong signal
        # Regular exit: Price below EMA AND RSI below midpoint (not waiting for oversold)
        dataframe['regular_exit'] = (
            (dataframe['close'] < dataframe['ema']) &
            (dataframe['rsi'] < 45)  # Use a more aggressive RSI threshold
        )
        
        # Profit-taking exit: If we have profit and conditions favor exit
        dataframe['short_exit'] = dataframe['regular_exit']
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        # Apply short entry signal
        dataframe.loc[dataframe['short_entry'], 'enter_short'] = 1
        
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                           side: str, **kwargs) -> bool:
        # Cooldown period of 3 minutes
        cooldown_minutes = 3
        
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
                
        # Update the last seen time for this pair
        self._last_candle_seen_time[pair] = current_time
        
        return True

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        # Only apply exit signals if we're not using profit-only exits
        if self.use_profit_only.value == False:  # Using explicit comparison
            dataframe.loc[dataframe['short_exit'], 'exit_short'] = 1
        
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        if trade.is_short:
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if len(dataframe) > 0:
                    last_candle = dataframe.iloc[-1]
                    
                    # Only exit on profit
                    if self.use_profit_only.value == True and current_profit <= 0:  # Using explicit comparison
                        return None
                    
                    # Take profit at 2%
                    if current_profit >= 0.02:
                        return 'short_profit_hit'
                    
                    # Take profit at 1% if held more than 5 minutes
                    if current_profit >= 0.01 and (current_time - trade.open_date_utc) > timedelta(minutes=5):
                        return 'short_profit_timeout'
                    
                    # Exit on RSI below 40 if we have profit
                    if current_profit > 0 and 'rsi' in last_candle and last_candle['rsi'] < 40:
                        return 'short_profit_rsi_exit'
                    
                    # Cut losses after 10 minutes
                    if current_profit < 0 and (current_time - trade.open_date_utc) > timedelta(minutes=10):
                        return 'short_loss_timeout'
                    
            except Exception as e:
                pass
        
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
                **kwargs) -> float:
        """Return leverage value"""
        return float(self.leverage_param.value)

    def hyperopt_space(self) -> List[Dimension]:
        """Define hyperopt space - basic parameters only"""
        return [
            Integer(1, 3, name='leverage_param'),
            Integer(10, 20, name='rsi_period'),
            Integer(65, 85, name='rsi_upper'),
            Integer(20, 35, name='rsi_lower'),
            Integer(5, 20, name='ema_period'),
            Categorical([True, False], name='use_profit_only'),
        ]
