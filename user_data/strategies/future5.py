from collections import defaultdict
from datetime import datetime, timedelta
from functools import reduce
from typing import Optional

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, CategoricalParameter, DecimalParameter, IntParameter

class future5(IStrategy):
   INTERFACE_VERSION = 3

   # Optimal ROI table from hyperopt
   minimal_roi = {
       "0": 0.086,
       "37": 0.034,
       "61": 0.011,
       "134": 0
   }
   
   # Optimized stoploss and trailing settings
   stoploss = -0.178
   trailing_stop = True
   trailing_stop_positive = 0.204
   trailing_stop_positive_offset = 0.277
   trailing_only_offset_is_reached = True

   timeframe = '5m'
   startup_candle_count = 144
   use_exit_signal = True
   ignore_roi_if_entry_signal = False
   target_leverage = 2  
   can_short = True
   position_adjustment_enable = False

   # Buy parameters from hyperopt results
   buy_rsi = IntParameter(31, 39, default=35, space='buy', optimize=True)
   buy_adx = IntParameter(22, 30, default=26, space='buy', optimize=True)
   buy_bb_mult = DecimalParameter(1.02, 1.10, decimals=2, default=1.06, space='buy', optimize=True)
   
   # Sell parameters from hyperopt results
   sell_rsi = IntParameter(72, 80, default=76, space='sell', optimize=True)
   sell_adx = IntParameter(19, 27, default=23, space='sell', optimize=True)
   sell_bb_mult = DecimalParameter(0.92, 1.00, decimals=2, default=0.96, space='sell', optimize=True)

   # Volume multiplier parameters
   long_volume_mult = DecimalParameter(1.0, 1.4, decimals=1, default=1.2, space='buy', optimize=True)
   short_volume_mult = DecimalParameter(1.3, 1.7, decimals=1, default=1.5, space='sell', optimize=True)

   # EMA trend strength parameters
   long_ema_dist = DecimalParameter(0.97, 0.99, decimals=3, default=0.982, space='buy', optimize=True)
   short_ema_dist = DecimalParameter(1.01, 1.03, decimals=3, default=1.022, space='sell', optimize=True)

   # ADX strength parameters
   long_adx_strength = IntParameter(21, 29, default=25, space='buy', optimize=True)
   short_adx_strength = IntParameter(23, 31, default=27, space='sell', optimize=True)

   # MACD/EMA combination mode with hyperopt results
   long_trend_mode = CategoricalParameter(['AND', 'OR'], default='OR', space='buy', optimize=True)
   short_trend_mode = CategoricalParameter(['AND', 'OR'], default='OR', space='sell', optimize=True)

   # Store hyperopt results
   buy_params = {
       "buy_adx": 26,
       "buy_bb_mult": 1.06,
       "buy_rsi": 35,
       "long_adx_strength": 25,
       "long_ema_dist": 0.982,
       "long_trend_mode": "OR",
       "long_volume_mult": 1.2,
   }

   sell_params = {
       "sell_adx": 23,
       "sell_bb_mult": 0.96,
       "sell_rsi": 76,
       "short_adx_strength": 27,
       "short_ema_dist": 1.022,
       "short_trend_mode": "OR",
       "short_volume_mult": 1.5,
   }

   def __init__(self, config: dict) -> None:
       super().__init__(config)
       self.last_loss_time = defaultdict(lambda: datetime.min)

   def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
       # Moving Averages
       for window in [20, 50]:
           dataframe[f'ma_{window}'] = ta.SMA(dataframe, timeperiod=window)
       
       # MACD
       macd = ta.MACD(dataframe)
       dataframe['macd'] = macd['macd']
       dataframe['macd_signal'] = macd['macdsignal']
       dataframe['macd_hist'] = macd['macdhist']
       
       # Bollinger Bands
       bollinger = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
       dataframe['bb_lowerband'] = bollinger['lower']
       dataframe['bb_middleband'] = bollinger['mid']
       dataframe['bb_upperband'] = bollinger['upper']
       
       # RSI
       dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
       
       # Volume
       dataframe['volume_ma'] = dataframe['volume'].rolling(window=20).mean()
       
       # ADX
       dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
       
       # EMAs
       dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=8)
       dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=21)
       
       return dataframe

   def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
       pair = metadata['pair']
       
       # Long conditions with hyperopt-optimizable parameters
       long_conditions = [
           (dataframe['close'] < dataframe['bb_lowerband'] * self.buy_bb_mult.value),
           (dataframe['rsi'] < self.buy_rsi.value),
           (dataframe['volume'] > dataframe['volume_ma'] * self.long_volume_mult.value),
           (dataframe['adx'] > self.long_adx_strength.value),
           (dataframe['close'] < dataframe['ema_slow'] * self.long_ema_dist.value)
       ]

       # MACD/EMA trend conditions based on mode
       long_trend_macd = (dataframe['macd_hist'] > dataframe['macd_hist'].shift(1))
       long_trend_ema = (dataframe['ema_fast'] > dataframe['ema_fast'].shift(1))
       
       if self.long_trend_mode.value == 'AND':
           long_conditions.append(long_trend_macd & long_trend_ema)
       else:  # 'OR'
           long_conditions.append(long_trend_macd | long_trend_ema)

       # Short conditions with hyperopt-optimizable parameters
       short_conditions = [
           (dataframe['close'] > dataframe['bb_upperband'] * self.sell_bb_mult.value),
           (dataframe['rsi'] > self.sell_rsi.value),
           (dataframe['volume'] > dataframe['volume_ma'] * self.short_volume_mult.value),
           (dataframe['adx'] > self.short_adx_strength.value),
           (dataframe['close'] > dataframe['ema_slow'] * self.short_ema_dist.value)
       ]

       # MACD/EMA trend conditions based on mode
       short_trend_macd = (dataframe['macd_hist'] < dataframe['macd_hist'].shift(1))
       short_trend_ema = (dataframe['ema_fast'] < dataframe['ema_fast'].shift(1))
       
       if self.short_trend_mode.value == 'AND':
           short_conditions.append(short_trend_macd & short_trend_ema)
       else:  # 'OR'
           short_conditions.append(short_trend_macd | short_trend_ema)

       # Cooldown period
       last_loss = self.last_loss_time[pair]
       if last_loss > datetime.min:
           cooldown_end = last_loss + timedelta(minutes=15)
           dataframe['cooldown_mask'] = dataframe['date'].between(last_loss, cooldown_end)
           long_conditions.append(~dataframe['cooldown_mask'])
           short_conditions.append(~dataframe['cooldown_mask'])

       dataframe.loc[reduce(lambda x, y: x & y, long_conditions), 'enter_long'] = 1
       dataframe.loc[reduce(lambda x, y: x & y, short_conditions), 'enter_short'] = 1
       
       return dataframe

   def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
       dataframe.loc[:, 'exit_long'] = 0
       dataframe.loc[:, 'exit_short'] = 0

       # Long exit conditions
       long_trend_exit = (
           (dataframe['rsi'] > 60) &
           (dataframe['close'] > dataframe['bb_middleband']) &
           (dataframe['macd_hist'] < dataframe['macd_hist'].shift(1))
       )

       long_profit_exit = (
           (dataframe['rsi'] > 70) &
           (dataframe['close'] > dataframe['bb_upperband'] * 0.995)
       )

       # Short exit conditions
       short_trend_exit = (
           (dataframe['rsi'] < 40) &
           (dataframe['close'] < dataframe['bb_middleband']) &
           (dataframe['macd_hist'] > dataframe['macd_hist'].shift(1))
       )

       short_profit_exit = (
           (dataframe['rsi'] < 30) &
           (dataframe['close'] < dataframe['bb_lowerband'] * 1.005)
       )

       dataframe.loc[long_trend_exit | long_profit_exit, 'exit_long'] = 1
       dataframe.loc[short_trend_exit | short_profit_exit, 'exit_short'] = 1
       
       return dataframe

   def custom_exit(self, pair: str, trade: Trade, current_time: datetime, 
                  current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
       # Much faster exits for both profit and loss
       if trade.entry_side == "long":
           if current_profit > 0.02:
               return 'long_profit_A'
           elif current_profit > 0.01:
               return 'long_profit_B'
           elif current_profit < -0.02:
               return 'long_stoploss_urgent'
               
       elif trade.entry_side == "short":
           if current_profit > 0.015:
               return 'short_profit_A'
           elif current_profit > 0.008:
               return 'short_profit_B'
           elif current_profit < -0.015:
               return 'short_stoploss_urgent'
       
       # Time-based exit for all trades
       minutes = (current_time - trade.open_date).total_seconds() / 60
       if minutes > 180:  # Exit after 3 hours
           return f'{trade.entry_side}_timeout_exit'
       
       return None

   def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                         rate: float, time_in_force: str, exit_reason: str,
                         current_time: datetime, **kwargs) -> bool:
       if exit_reason == 'stop_loss':
           self.last_loss_time[pair] = current_time
       return True
