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

class future2(IStrategy):
    INTERFACE_VERSION = 3

    minimal_roi = {
        "0": 0.05,    
        "30": 0.03,   
        "40": 0.02,   
        "60": 0.01    
    }
    
    stoploss = -0.065  
    trailing_stop = True
    trailing_stop_positive = 0.01  
    trailing_stop_positive_offset = 0.02  
    trailing_only_offset_is_reached = True

    timeframe = '5m'
    startup_candle_count = 144
    use_exit_signal = True
    ignore_roi_if_entry_signal = False
    target_leverage = 2  
    can_short = True
    position_adjustment_enable = False

    # Buy params - slightly tighter ranges
    buy_rsi = IntParameter(32, 36, default=34, space='buy', optimize=True)
    buy_adx = IntParameter(19, 23, default=21, space='buy', optimize=True)
    buy_bb_mult = DecimalParameter(1.02, 1.06, decimals=2, default=1.04, space='buy', optimize=True)
    
    # Sell params - improved for shorts
    sell_rsi = IntParameter(75, 81, default=78, space='sell', optimize=True)
    sell_adx = IntParameter(23, 27, default=25, space='sell', optimize=True)
    sell_bb_mult = DecimalParameter(0.98, 1.02, decimals=2, default=1.0, space='sell', optimize=True)

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
        
        # ATR
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
     pair = metadata['pair']
    
     # Long conditions - reduced and simplified
     long_conditions = [
        (dataframe['close'] < dataframe['bb_lowerband'] * self.buy_bb_mult.value),
        (dataframe['rsi'] < self.buy_rsi.value),
        (dataframe['volume'] > dataframe['volume_ma']),  # Reduced volume requirement
        (
            (dataframe['macd_hist'] > dataframe['macd_hist'].shift(1)) |  # MACD improving OR
            (dataframe['ema_fast'] > dataframe['ema_fast'].shift(1))      # Fast EMA rising
        )
     ]

     # Short conditions - reduced and simplified
     short_conditions = [
        (dataframe['close'] > dataframe['bb_upperband'] * self.sell_bb_mult.value),
        (dataframe['rsi'] > self.sell_rsi.value),
        (dataframe['volume'] > dataframe['volume_ma']),  # Reduced volume requirement
        (
            (dataframe['macd_hist'] < dataframe['macd_hist'].shift(1)) |  # MACD declining OR
            (dataframe['ema_fast'] < dataframe['ema_fast'].shift(1))      # Fast EMA falling
        )
     ]

     # Cooldown period
     last_loss = self.last_loss_time[pair]
     if last_loss > datetime.min:
        cooldown_end = last_loss + timedelta(minutes=30)
        dataframe['cooldown_mask'] = dataframe['date'].between(last_loss, cooldown_end)
        long_conditions.append(~dataframe['cooldown_mask'])
        short_conditions.append(~dataframe['cooldown_mask'])

     dataframe.loc[reduce(lambda x, y: x & y, long_conditions), 'enter_long'] = 1
     dataframe.loc[reduce(lambda x, y: x & y, short_conditions), 'enter_short'] = 1
    
     return dataframe


    def populate_entry_trend1(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata['pair']
        
        # Long conditions with trend confirmation
        long_conditions = [
            (dataframe['close'] < dataframe['bb_lowerband'] * self.buy_bb_mult.value),
            (dataframe['rsi'] < self.buy_rsi.value),
            (dataframe['volume'] > dataframe['volume_ma'] * 1.5),
            (dataframe['adx'] > self.buy_adx.value),
            (dataframe['macd_hist'] > dataframe['macd_hist'].shift(1)),
            (dataframe['close'] < dataframe['ma_50']),
            (dataframe['ema_fast'] > dataframe['ema_fast'].shift(1))
        ]

        # Short conditions with improved filters
        short_conditions = [
            (dataframe['close'] > dataframe['bb_upperband'] * self.sell_bb_mult.value),
            (dataframe['rsi'] > self.sell_rsi.value),
            (dataframe['volume'] > dataframe['volume_ma'] * 2),
            (dataframe['adx'] > self.sell_adx.value),
            (dataframe['macd_hist'] < dataframe['macd_hist'].shift(1)),
            (dataframe['close'] > dataframe['ma_50']),
            (dataframe['ema_fast'] < dataframe['ema_fast'].shift(1))
        ]

        # Cooldown period
        last_loss = self.last_loss_time[pair]
        if last_loss > datetime.min:
            cooldown_end = last_loss + timedelta(minutes=30)
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
            (dataframe['rsi'] > 65) &
            (dataframe['close'] > dataframe['bb_middleband']) &
            (dataframe['macd_hist'] < dataframe['macd_hist'].shift(1)) &
            (dataframe['ema_fast'] < dataframe['ema_slow'])
        )

        long_profit_exit = (
            (dataframe['rsi'] > 75) &
            (dataframe['close'] > dataframe['bb_upperband'] * 0.995) &
            (dataframe['macd_hist'] < 0)
        )

        # Short exit conditions
        short_trend_exit = (
            (dataframe['rsi'] < 35) &
            (dataframe['close'] < dataframe['bb_middleband']) &
            (dataframe['macd_hist'] > dataframe['macd_hist'].shift(1)) &
            (dataframe['ema_fast'] > dataframe['ema_slow'])
        )

        short_profit_exit = (
            (dataframe['rsi'] < 25) &
            (dataframe['close'] < dataframe['bb_lowerband'] * 1.005) &
            (dataframe['macd_hist'] > 0)
        )

        dataframe.loc[long_trend_exit | long_profit_exit, 'exit_long'] = 1
        dataframe.loc[short_trend_exit | short_profit_exit, 'exit_short'] = 1
        
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, 
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        if trade.entry_side == "long":
            if current_profit > 0.03:
                return 'long_profit_A'
            elif current_profit > 0.02:
                return 'long_profit_B'
            elif current_profit < -0.01 and trade.duration_min > 60:
                return 'long_stoploss_time'
            elif current_profit < -0.02 and trade.duration_min > 30:
                return 'long_stoploss_urgent'
                
        elif trade.entry_side == "short":
            if current_profit > 0.02:
                return 'short_profit_A'
            elif current_profit > 0.015:
                return 'short_profit_B'
            elif current_profit < -0.01 and trade.duration_min > 45:
                return 'short_stoploss_time'
            elif current_profit < -0.015 and trade.duration_min > 20:
                return 'short_stoploss_urgent'
        
        return None

    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                          rate: float, time_in_force: str, exit_reason: str,
                          current_time: datetime, **kwargs) -> bool:
        if exit_reason == 'stop_loss':
            self.last_loss_time[pair] = current_time
        return True
