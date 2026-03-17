# --- Do not remove these libs ---
from freqtrade.strategy.interface import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd  # noqa
pd.options.mode.chained_assignment = None  # default='warn'
from functools import reduce
import numpy as np
from freqtrade.strategy import DecimalParameter, IntParameter, CategoricalParameter
from datetime import datetime
from typing import Dict

class future33(IStrategy):
    """
    Futures version of pulp strategy adapted for 1m timeframe with leverage
    Optimizable with hyperopt for buy, sell, ROI, trailing stop, and leverage
    """
    # Strategy parameters
    timeframe = '1m'
    startup_candle_count = 100  # Increased due to 1m timeframe
    process_only_new_candles = False
    
    # Hyperopt parameters for leverage
    leverage_param = DecimalParameter(2.0, 9.0, decimals=1, default=5.0, space="buy", optimize=True)
    
    # Buy hyperspace params - optimizable
    buy_rsi = IntParameter(30, 70, default=50, space="buy", optimize=True)
    buy_macd_threshold = DecimalParameter(-0.05, 0, default=-0.02, space="buy", optimize=True)
    buy_bb_middleband_mult = DecimalParameter(1.0, 1.5, default=1.2, space="buy", optimize=True)
    buy_price_lower_pct_mult = DecimalParameter(1.0, 1.2, default=1.1, space="buy", optimize=True)
    
    # Sell hyperspace params - optimizable
    sell_rsi = IntParameter(60, 90, default=70, space="sell", optimize=True)
    sell_bb_upperband_mult = DecimalParameter(0.8, 1.0, default=0.9, space="sell", optimize=True)
    sell_close_mult = DecimalParameter(0.97, 0.995, default=0.985, space="sell", optimize=True)
    sell_bb_upperband_high_mult = DecimalParameter(1.0, 1.2, default=1.1, space="sell", optimize=True)
    
    # Stoploss
    stoploss = DecimalParameter(-0.25, -0.05, default=-0.15, space="sell", optimize=True)
    
    # Trailing stoploss - optimizable
    trailing_stop = True
    trailing_stop_positive = DecimalParameter(0.001, 0.01, default=0.005, space="sell", optimize=True)
    trailing_stop_positive_offset = DecimalParameter(0.005, 0.02, default=0.01, space="sell", optimize=True)
    trailing_only_offset_is_reached = True
    
    # Optimizable hyperparameters for ROI
    roi_t1 = IntParameter(5, 20, default=10, space="roi", optimize=True)
    roi_t2 = IntParameter(15, 40, default=20, space="roi", optimize=True)
    roi_t3 = IntParameter(25, 60, default=30, space="roi", optimize=True)
    
    roi_p1 = DecimalParameter(0.01, 0.03, default=0.015, space="roi", optimize=True)
    roi_p2 = DecimalParameter(0.005, 0.015, default=0.01, space="roi", optimize=True)
    roi_p3 = DecimalParameter(0.001, 0.01, default=0.005, space="roi", optimize=True)
    
    # Futures specific settings
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    
    def custom_roi(self) -> Dict[str, float]:
        """
        Dynamically calculate ROI table values based on hyperopt parameters
        """
        roi_table = {
            "0": self.roi_p1.value,
            str(self.roi_t1.value): self.roi_p2.value,
            str(self.roi_t2.value): self.roi_p3.value,
            str(self.roi_t3.value): 0
        }
        return roi_table

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str, side: str, **kwargs) -> float:
        """
        Returns the leverage to use for a given pair
        """
        return self.leverage_param.value
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # MACD - adjusted for 1m timeframe
        macd = ta.MACD(dataframe, fastperiod=6, slowperiod=14, signalperiod=3)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']

        # Bollinger Bands - adjusted for 1m
        bollinger = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']

        # Moving averages - adjusted for 1m
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=5)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=12)
        dataframe['avg_price_8h'] = dataframe['close'].rolling(window=480).mean()  # 8 hours in 1m
        dataframe['price_lower_20pct'] = dataframe['avg_price_8h'] * 0.9
        dataframe['price_upper_20pct'] = dataframe['avg_price_8h'] * 1.1

        # RSI & Stochastic RSI - adjusted for 1m
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=10)
        stoch_rsi = ta.STOCHRSI(dataframe, timeperiod=10, fastk_period=3, fastd_period=3)
        dataframe['stoch_rsi_k'] = stoch_rsi['fastk']
        dataframe['stoch_rsi_d'] = stoch_rsi['fastd']

        # Volume
        dataframe['volume_ma'] = dataframe['volume'].rolling(window=20).mean()
        
        # ATR
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = []

        # MACD conditions
        conditions.append(
            (dataframe['macdhist'] > self.buy_macd_threshold.value) | 
            qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal'])
        )

        # Price conditions
        conditions.append(dataframe['close'] <= dataframe['bb_middleband'] * self.buy_bb_middleband_mult.value)
        conditions.append(dataframe['close'] <= dataframe['price_lower_20pct'] * self.buy_price_lower_pct_mult.value)

        # RSI condition
        conditions.append(dataframe['rsi'] < self.buy_rsi.value)

        # Volume condition
        conditions.append(dataframe['volume'] > dataframe['volume_ma'])

        # EMA condition
        conditions.append(dataframe['ema_short'] > dataframe['ema_long'])

        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit signals not actively used for futures - will rely on ROI and stoploss
        But keeping similar logic for manual analysis
        """
        conditions = []

        # Technical indicator exits
        conditions.append(
            (
                (dataframe['close'] >= dataframe['bb_upperband'] * self.sell_bb_upperband_mult.value) |
                (qtpylib.crossed_below(dataframe['ema_short'], dataframe['ema_long'])) |
                (dataframe['stoch_rsi_k'] > 80) |
                (dataframe['stoch_rsi_k'] < dataframe['stoch_rsi_d'])
            )
        )

        # RSI exit
        conditions.append(dataframe['rsi'] > self.sell_rsi.value)

        # Volume-based exit
        conditions.append(
            (dataframe['volume'] > dataframe['volume_ma'] * 1.5) &
            (dataframe['close'] < dataframe['close'].shift(1))
        )

        # Profit protection
        conditions.append(
            (dataframe['close'] < dataframe['close'].shift(1) * self.sell_close_mult.value) |
            (dataframe['close'] > dataframe['bb_upperband'] * self.sell_bb_upperband_high_mult.value)
        )

        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'exit_long'] = 1

        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                          time_in_force: str, current_time: datetime, **kwargs) -> bool:
        """
        Additional confirmation of trade entry with adjustments for futures
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        # Additional volume confirmation
        if last_candle['volume'] < last_candle['volume_ma'] * 0.8:
            return False

        # Prevent entry if ATR is too high (volatile) - more conservative for futures
        if last_candle['atr'] > last_candle['close'] * 0.015:
            return False

        return True
