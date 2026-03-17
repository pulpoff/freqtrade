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

class future12(IStrategy):
    # Optimized ROI table from hyperopt results
    minimal_roi = {
        "0": 0.04,
        "2": 0.007,
        "5": 0.003,
        "18": 0
    }

    # Risk parameters - from hyperopt
    stoploss = -0.103
    trailing_stop = True
    trailing_stop_positive = 0.241
    trailing_stop_positive_offset = 0.323
    trailing_only_offset_is_reached = True

    # Leverage parameters - optimized
    leverage_param = IntParameter(10, 15, default=12, space="buy", optimize=True)
    
    # Long entry parameters (from pulp2h strategy) - all set to optimize
    buy_bb_width_threshold = DecimalParameter(0.05, 0.2, default=0.155, space="buy", optimize=True)
    buy_rsi_lower = IntParameter(10, 40, default=33, space="buy", optimize=True)
    buy_rsi_upper = IntParameter(30, 50, default=32, space="buy", optimize=True)
    buy_macd_hist_threshold = DecimalParameter(-0.05, 0.0, default=-0.028, space="buy", optimize=True)
    buy_volume_multiplier_min = DecimalParameter(1.0, 3.0, default=2.766, space="buy", optimize=True)
    buy_volume_multiplier_max = DecimalParameter(3.0, 10.0, default=7.521, space="buy", optimize=True)
    
    # Added for long optimization
    use_bb_condition = CategoricalParameter([True, False], default=True, space="buy", optimize=True)
    use_macd_condition = CategoricalParameter([True, False], default=True, space="buy", optimize=True)
    use_rsi_condition = CategoricalParameter([True, False], default=True, space="buy", optimize=True)
    use_volume_condition = CategoricalParameter([True, False], default=True, space="buy", optimize=True)
    
    # Short entry parameters
    rsi_buy = IntParameter(38, 48, default=43, space="buy", optimize=True)
    rsi_sell = IntParameter(77, 87, default=82, space="sell", optimize=True)
    min_price_change = DecimalParameter(0.002, 0.006, default=0.004, space="buy", optimize=True)
    volume_filter = DecimalParameter(0.78, 0.9, default=0.839, space="buy", optimize=True)
    
    # Short entry parameters (from new14 strategy)
    exit_rsi_threshold = IntParameter(60, 70, default=65, space="sell", optimize=True)
    exit_volume_multiplier = DecimalParameter(1.0, 1.4, default=1.2, space="sell", optimize=True)
    
    # Strategy settings
    timeframe = '1m'
    startup_candle_count = 880
    process_only_new_candles = True
    can_short = True
    can_long = True

    # Cooldown settings
    _last_stoploss_time: Dict[str, datetime] = {}
    cooldown_period = timedelta(hours=1)

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.last_trade_time = {}

    def leverage(self, pair: str, current_time: datetime, **kwargs) -> float:
        """Return the leverage to use"""
        return float(self.leverage_param.value)

    def hyperopt_space(self) -> List[Dimension]:
        """Define hyperopt space with tighter ranges around optimized values"""
        return [
            Real(-0.12, -0.08, name='stoploss'),
            Real(0.22, 0.27, name='trailing_stop_positive'),
            Real(0.3, 0.35, name='trailing_stop_positive_offset'),
            # Add the leverage parameter to the hyperopt space
            Integer(10, 15, name='leverage_param'),
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
        dataframe['bb_width'] = (dataframe['bb_upperband'] - dataframe['bb_lowerband']) / dataframe['bb_middleband']
        
        # MACD indicators (from new14/pulp2h strategy)
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        dataframe['hist_trend'] = dataframe['macdhist'] > dataframe['macdhist'].shift(1)
        dataframe['hist_peak'] = (
            (dataframe['macdhist'] > dataframe['macdhist'].shift(1)) & 
            (dataframe['macdhist'] > dataframe['macdhist'].shift(2))
        )
        
        # 48-hour average price (from pulp2h)
        dataframe['avg_price_48h'] = dataframe['close'].rolling(window=880).mean()
        dataframe['price_lower_20pct'] = dataframe['avg_price_48h'] * 0.9
        dataframe['price_upper_20pct'] = dataframe['avg_price_48h'] * 1.1
        
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
        
        current_candle_time = dataframe.iloc[-1]['date']  # Get current candle's time

        # Wait at least 1 minute between trades of the same pair
        pair = metadata['pair']
        cooldown_ok = True
        if pair in self.last_trade_time:
            last_trade = self.last_trade_time[pair]
            #if datetime.now() - last_trade < timedelta(minutes=1):
            #    cooldown_ok = False
            if (current_candle_time - last_trade) < timedelta(minutes=1):
              cooldown_ok = False

                
        # Check for cooldown after stoploss
        if pair in self._last_stoploss_time:
            if datetime.now() - self._last_stoploss_time[pair] < self.cooldown_period:
                cooldown_ok = False
                
        if cooldown_ok:
            # Long entries - using indicators from pulp2h strategy with optimization flags
            long_conditions = []
            
            # Bollinger Band condition - can be enabled/disabled by hyperopt
            bb_condition = (
                (dataframe['close'] <= dataframe['bb_lowerband'] * 1.01) &
                (dataframe['close'] > dataframe['bb_lowerband'] * 0.995) &
                (dataframe['bb_width'] < self.buy_bb_width_threshold.value)
            )
            
            # MACD check - can be enabled/disabled by hyperopt
            macd_condition = (
                (dataframe['macdhist'] > self.buy_macd_hist_threshold.value) | 
                qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal'])
            )
            
            # RSI checks - can be enabled/disabled by hyperopt
            rsi_condition = (
                (dataframe['rsi'] < self.buy_rsi_upper.value) &
                (dataframe['rsi'] > self.buy_rsi_lower.value)
            )
            
            # Volume confirmation - can be enabled/disabled by hyperopt
            volume_condition = (
                (dataframe['volume'] > dataframe['volume_ma'] * self.buy_volume_multiplier_min.value) &
                (dataframe['volume'] < dataframe['volume_ma'] * self.buy_volume_multiplier_max.value)
            )
            
            # Build long conditions based on hyperopt flags
            if self.use_bb_condition.value:
                long_conditions.append(bb_condition)
            
            if self.use_macd_condition.value:
                long_conditions.append(macd_condition)
                
            if self.use_rsi_condition.value:
                long_conditions.append(rsi_condition)
                
            if self.use_volume_condition.value:
                long_conditions.append(volume_condition)
            
            # Short entries - using exit conditions from new14 strategy
            short_conditions = [
                # Local peak detected
                dataframe['local_peak'],
                # RSI overbought threshold from new14
                dataframe['rsi'] > self.exit_rsi_threshold.value,
                # MACD histogram trending up (from new14)
                dataframe['macdhist'] > dataframe['macdhist'].shift(2),
                # Volume confirmation (from new14)
                dataframe['volume'] > dataframe['volume_ma'] * self.exit_volume_multiplier.value
            ]
            
            # Generate entry signals
            if long_conditions:  # Only proceed if we have at least one condition
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
        
    def stop_loss_reached(self, trade_now: 'Trade', current_rate: float, current_profit: float, **kwargs) -> tuple:
        self._last_stoploss_time[trade_now.pair] = datetime.now()
        return super().stop_loss_reached(trade_now, current_rate, current_profit, **kwargs)
