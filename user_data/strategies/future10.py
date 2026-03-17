from functools import reduce
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict
from skopt.space import Dimension, Real, Integer

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter

class future10(IStrategy):
    # Optimized ROI table from hyperopt results
    minimal_roi = {
        "0": 0.089,
        "8": 0.036,
        "20": 0.014,
        "38": 0
    }

    # Risk parameters - from hyperopt
    stoploss = -0.322
    trailing_stop = True
    trailing_stop_positive = 0.14
    trailing_stop_positive_offset = 0.174
    trailing_only_offset_is_reached = False

    # Leverage parameters - optimized
    leverage_param = IntParameter(1, 10, default=5, space="buy", optimize=True)
    
    # Entry parameters - optimized values with adjusted ranges
    rsi_buy = IntParameter(40, 50, default=45, space="buy", optimize=True)
    rsi_sell = IntParameter(77, 87, default=82, space="sell", optimize=True)
    
    # Entry filters - optimized
    min_price_change = DecimalParameter(0.002, 0.006, default=0.004, space="buy", optimize=True)
    volume_filter = DecimalParameter(0.7, 0.9, default=0.76, space="buy", optimize=True)

    # Short entry parameters (from new14 strategy)
    exit_rsi_threshold = IntParameter(55, 75, default=65, space="sell", optimize=True)
    exit_volume_multiplier = DecimalParameter(1.0, 2.0, default=1.2, space="sell", optimize=True)
    
    # Exit settings
    use_exit_signal = False  # Rely on ROI and stoploss
    
    # Strategy settings
    timeframe = '1m'
    startup_candle_count = 100
    process_only_new_candles = True
    can_short = True
    can_long = True

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.last_trade_time = {}

    def leverage(self, pair: str, current_time: datetime, **kwargs) -> float:
        """Return the leverage to use"""
        return float(self.leverage_param.value)

    def hyperopt_space(self) -> List[Dimension]:
        """Define hyperopt space with tighter ranges around optimized values"""
        return [
            Real(-0.35, -0.25, name='stoploss'),
            Real(0.1, 0.2, name='trailing_stop_positive'),
            Real(0.15, 0.2, name='trailing_stop_positive_offset'),
            # Add the leverage parameter to the hyperopt space
            Integer(3, 7, name='leverage_param'),
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # RSI indicator
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Volume indicators
        dataframe['volume_ma'] = dataframe['volume'].rolling(window=20).mean()
        
        # Price movement
        dataframe['price_change'] = dataframe['close'].pct_change().abs()
        
        # Trend indicators
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=21)
        dataframe['uptrend'] = dataframe['ema_short'] > dataframe['ema_long']
        dataframe['downtrend'] = dataframe['ema_short'] < dataframe['ema_long']
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        
        # MACD indicators (from new14 strategy)
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_hist'] = macd['macdhist']
        
        dataframe['hist_trend'] = dataframe['macd_hist'] > dataframe['macd_hist'].shift(1)
        dataframe['hist_peak'] = (
            (dataframe['macd_hist'] > dataframe['macd_hist'].shift(1)) & 
            (dataframe['macd_hist'] > dataframe['macd_hist'].shift(2))
        )
        
        # Local peak detection for short entries (from new14 strategy)
        dataframe['local_peak'] = (
            (dataframe['close'] > dataframe['close'].shift(2)) &
            (dataframe['close'] > dataframe['close'].shift(1)) &
            (dataframe['close'] > dataframe['close'].shift(-1)) &
            (dataframe['close'] > dataframe['close'].shift(-2))
        )
        
        # Sequential price drops (from new14 strategy)
        dataframe['price_dropped'] = dataframe['close'] < dataframe['close'].shift(1)
        dataframe['sequential_drops'] = (
            dataframe['price_dropped'] & 
            dataframe['price_dropped'].shift(1) & 
            dataframe['price_dropped'].shift(2)
        )
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry conditions with optimized parameters"""
        # Initialize entry columns
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        # Wait at least 1 minute between trades of the same pair
        pair = metadata['pair']
        cooldown_ok = True
        if pair in self.last_trade_time:
            last_trade = self.last_trade_time[pair]
            if datetime.now() - last_trade < timedelta(minutes=1):
                cooldown_ok = False
                
        if cooldown_ok:
            # Long entries - using optimized parameters
            long_conditions = [
                # RSI oversold - optimized value
                (dataframe['rsi'] < self.rsi_buy.value),
                # Significant price movement - optimized value
                (dataframe['price_change'] > self.min_price_change.value),
                # Volume confirmation - optimized value
                (dataframe['volume'] > dataframe['volume_ma'] * self.volume_filter.value),
                # In uptrend
                (dataframe['uptrend']),
                # Near lower BB
                (dataframe['close'] < dataframe['bb_lowerband'] * 1.01)
            ]
            
            # Short entries - using exit conditions from new14 strategy
            short_conditions = [
                # Local peak detected
                dataframe['local_peak'],
                # RSI overbought threshold from new14
                dataframe['rsi'] > self.exit_rsi_threshold.value,
                # MACD histogram trending up (from new14)
                dataframe['macd_hist'] > dataframe['macd_hist'].shift(2),
                # Volume confirmation (from new14)
                dataframe['volume'] > dataframe['volume_ma'] * self.exit_volume_multiplier.value
            ]
            
            # Generate entry signals
            dataframe.loc[reduce(lambda x, y: x & y, long_conditions), 'enter_long'] = 1
            dataframe.loc[reduce(lambda x, y: x & y, short_conditions), 'enter_short'] = 1
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit signals disabled - relying entirely on ROI"""
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """Record trades for cooldown"""
        self.last_trade_time[pair] = current_time
        
        # Additional exit logic for shorts based on sequential drops (inspired by new14)
        if trade.is_short:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            last_candle = dataframe.iloc[-1]
            
            if last_candle['sequential_drops']:
                return 'short_exit_sequential_drops'
        
        return None  # Rely on ROI and stoploss for other exits
