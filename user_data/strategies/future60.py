from functools import reduce
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter

class future60(IStrategy):
    # --- Strategy Configuration ---
    minimal_roi = {"0": 0.025, "15": 0.015, "30": 0.010, "45": 0.005, "60": 0}
    stoploss = -0.015
    trailing_stop = False
    use_exit_signal = True
    process_only_new_candles = True
    max_open_trades = 8
    timeframe = '5m'
    startup_candle_count = 250
    can_short = True
    can_long = True

    # --- Hyperparameters for Optimization ---
    use_macd_confirmation = CategoricalParameter([True, False], default=True, space="buy", optimize=True)
    use_rsi_confirmation = CategoricalParameter([True, False], default=True, space="buy", optimize=True)
    use_market_confirmation = CategoricalParameter([True, False], default=True, space="buy", optimize=True)
    
    swing_lookback = IntParameter(10, 30, default=20, space="both", optimize=True)
    pullback_min_percent = DecimalParameter(0.002, 0.008, default=0.004, space="both", optimize=True)
    pullback_max_percent = DecimalParameter(0.010, 0.025, default=0.015, space="both", optimize=True)
    pullback_lookback = IntParameter(3, 10, default=7, space="both", optimize=True)
    
    rsi_period = IntParameter(10, 20, default=14, space="both", optimize=True)
    rsi_oversold_pullback = IntParameter(25, 40, default=35, space="buy", optimize=True)
    rsi_overbought_pullback = IntParameter(60, 75, default=65, space="sell", optimize=True)
    
    macd_fast = IntParameter(10, 15, default=12, space="both", optimize=True)
    macd_slow = IntParameter(20, 30, default=26, space="both", optimize=True)
    macd_signal = IntParameter(7, 12, default=9, space="both", optimize=True)
    
    cooldown_minutes = IntParameter(1, 5, default=2, space="both", optimize=True)

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._pair_cooldowns = {}

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [("BTC/USDT:USDT", "5m")]
        for pair in pairs:
            informative_pairs.append((pair, "1h"))
        return informative_pairs

    # --- Indicator and Logic Functions ---

    def detect_swing_points(self, dataframe: DataFrame) -> DataFrame:
        lookback = self.swing_lookback.value
        dataframe['swing_high'] = dataframe['high'].rolling(window=2 * lookback + 1, center=True).apply(
            lambda x: x[lookback] if x[lookback] == max(x) else np.nan, raw=True
        )
        dataframe['swing_low'] = dataframe['low'].rolling(window=2 * lookback + 1, center=True).apply(
            lambda x: x[lookback] if x[lookback] == min(x) else np.nan, raw=True
        )
        dataframe['last_swing_high'] = dataframe['swing_high'].ffill()
        dataframe['last_swing_low'] = dataframe['swing_low'].ffill()
        dataframe['prev_swing_high'] = dataframe['last_swing_high'].shift(1)
        dataframe['prev_swing_low'] = dataframe['last_swing_low'].shift(1)
        return dataframe

    def detect_trend_structure(self, dataframe: DataFrame) -> DataFrame:
        dataframe['uptrend_structure'] = (dataframe['last_swing_high'] > dataframe['prev_swing_high']) | (dataframe['last_swing_low'] > dataframe['prev_swing_low'])
        dataframe['downtrend_structure'] = (dataframe['last_swing_high'] < dataframe['prev_swing_high']) | (dataframe['last_swing_low'] < dataframe['prev_swing_low'])
        return dataframe

    def detect_pullback(self, dataframe: DataFrame) -> DataFrame:
        lookback = self.pullback_lookback.value
        dataframe['recent_high'] = dataframe['high'].rolling(lookback).max()
        dataframe['recent_low'] = dataframe['low'].rolling(lookback).min()
        dataframe['pullback_from_high'] = (dataframe['recent_high'] - dataframe['close']) / dataframe['recent_high']
        dataframe['pullback_from_low'] = (dataframe['close'] - dataframe['recent_low']) / dataframe['close']
        dataframe['pullback_in_uptrend'] = dataframe['pullback_from_high'].between(self.pullback_min_percent.value, self.pullback_max_percent.value)
        dataframe['pullback_in_downtrend'] = dataframe['pullback_from_low'].between(self.pullback_min_percent.value, self.pullback_max_percent.value)
        return dataframe
    
    def add_market_confirmation(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        btc_5m = self.dp.get_pair_dataframe("BTC/USDT:USDT", "5m")
        if not btc_5m.empty:
            btc_5m['btc_ma_fast'] = ta.EMA(btc_5m, timeperiod=20)
            btc_5m['btc_ma_slow'] = ta.EMA(btc_5m, timeperiod=50)
            btc_5m['btc_trend'] = np.where(btc_5m['btc_ma_fast'] > btc_5m['btc_ma_slow'], 1, -1)
            dataframe = merge_informative_pair(dataframe, btc_5m[['date', 'btc_trend']], self.timeframe, "5m", ffill=True)
        else:
            dataframe['btc_trend_5m'] = 0
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.detect_swing_points(dataframe)
        dataframe = self.detect_trend_structure(dataframe)
        dataframe = self.detect_pullback(dataframe)
        dataframe = self.add_market_confirmation(dataframe, metadata)

        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        dataframe['rsi_reversal_up'] = qtpylib.crossed_above(dataframe['rsi'], self.rsi_oversold_pullback.value)
        dataframe['rsi_reversal_down'] = qtpylib.crossed_below(dataframe['rsi'], self.rsi_overbought_pullback.value)

        # MACD
        macd = ta.MACD(dataframe, fastperiod=self.macd_fast.value, slowperiod=self.macd_slow.value, signalperiod=self.macd_signal.value)
        dataframe['macd_bullish'] = (macd['macd'] > macd['macdsignal'])
        dataframe['macd_bearish'] = (macd['macd'] < macd['macdsignal'])
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        long_conditions = [
            dataframe['uptrend_structure'],
            dataframe['pullback_in_uptrend']
        ]
        short_conditions = [
            dataframe['downtrend_structure'],
            dataframe['pullback_in_downtrend']
        ]

        # Add optional confirmations based on hyperopt parameters
        if self.use_rsi_confirmation.value:
            long_conditions.append(dataframe['rsi_reversal_up'])
            short_conditions.append(dataframe['rsi_reversal_down'])
        
        if self.use_macd_confirmation.value:
            long_conditions.append(dataframe['macd_bullish'])
            short_conditions.append(dataframe['macd_bearish'])
            
        if self.use_market_confirmation.value:
            long_conditions.append(dataframe.get('btc_trend_5m', 0) > 0)
            short_conditions.append(dataframe.get('btc_trend_5m', 0) < 0)

        if long_conditions:
            dataframe.loc[reduce(lambda x, y: x & y, long_conditions), 'enter_long'] = 1
            
        if short_conditions:
            dataframe.loc[reduce(lambda x, y: x & y, short_conditions), 'enter_short'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Exit if the trend structure breaks
        dataframe.loc[dataframe['downtrend_structure'], 'exit_long'] = 1
        dataframe.loc[dataframe['uptrend_structure'], 'exit_short'] = 1
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, time_in_force: str, current_time: datetime, entry_tag: Optional[str], side: str, **kwargs) -> bool:
        if pair in self._pair_cooldowns:
            if current_time - self._pair_cooldowns[pair] < timedelta(minutes=self.cooldown_minutes.value):
                return False
        self._pair_cooldowns[pair] = current_time
        return True
