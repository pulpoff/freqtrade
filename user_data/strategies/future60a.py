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

class future60a(IStrategy):
    # --- Optimized Strategy Configuration ---
    minimal_roi = {
        "0": 0.178, "37": 0.102, "97": 0.034, "112": 0
    }
    stoploss = -0.026
    
    trailing_stop = False
    use_exit_signal = True
    process_only_new_candles = True
    max_open_trades = 25
    timeframe = '5m'
    startup_candle_count = 250
    can_short = True
    can_long = True

    # --- Optimized Hyperparameters ---
    use_macd_confirmation = CategoricalParameter([True, False], default=False, space="buy", optimize=True)
    use_rsi_confirmation = CategoricalParameter([True, False], default=False, space="buy", optimize=True)
    use_market_confirmation = CategoricalParameter([True, False], default=False, space="buy", optimize=True)
    
    leverage_long = IntParameter(4, 12, default=12, space="buy", optimize=True)
    leverage_short = IntParameter(4, 12, default=12, space="sell", optimize=True)
    
    swing_lookback = IntParameter(10, 30, default=20, space="both", optimize=True)
    pullback_min_percent = DecimalParameter(0.002, 0.008, default=0.004, space="both", optimize=True)
    pullback_max_percent = DecimalParameter(0.010, 0.025, default=0.015, space="both", optimize=True)
    pullback_lookback = IntParameter(3, 10, default=7, space="both", optimize=True)
    cooldown_minutes = IntParameter(1, 5, default=2, space="both", optimize=True)
    
    rsi_period = IntParameter(10, 20, default=14, space="both", optimize=True)
    rsi_oversold_pullback = IntParameter(25, 40, default=28, space="buy", optimize=True)
    rsi_overbought_pullback = IntParameter(60, 75, default=71, space="sell", optimize=True)
    
    macd_fast = IntParameter(10, 15, default=12, space="both", optimize=True)
    macd_slow = IntParameter(20, 30, default=26, space="both", optimize=True)
    macd_signal = IntParameter(7, 12, default=9, space="both", optimize=True)

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [("BTC/USDT:USDT", "5m")]
        for pair in pairs:
            informative_pairs.append((pair, "1h"))
        return informative_pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.detect_swing_points_no_bias(dataframe)
        dataframe = self.detect_trend_structure(dataframe)
        dataframe = self.detect_pullback(dataframe)
        dataframe = self.add_market_confirmation(dataframe, metadata)

        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        dataframe['rsi_reversal_up'] = qtpylib.crossed_above(dataframe['rsi'], self.rsi_oversold_pullback.value)
        dataframe['rsi_reversal_down'] = qtpylib.crossed_below(dataframe['rsi'], self.rsi_overbought_pullback.value)

        macd = ta.MACD(dataframe, fastperiod=self.macd_fast.value, slowperiod=self.macd_slow.value, signalperiod=self.macd_signal.value)
        dataframe['macd_bullish'] = (macd['macd'] > macd['macdsignal'])
        dataframe['macd_bearish'] = (macd['macd'] < macd['macdsignal'])
        
        # Simplified cooldown without accessing Trade history during backtesting
        dataframe['cooldown_active'] = False  # Will be handled in custom_entry_price if needed
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        long_conditions = [
            dataframe['uptrend_structure'],
            dataframe['pullback_in_uptrend'],
            ~dataframe['cooldown_active']
        ]
        short_conditions = [
            dataframe['downtrend_structure'],
            dataframe['pullback_in_downtrend'],
            ~dataframe['cooldown_active']
        ]

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
        dataframe.loc[dataframe['downtrend_structure'], 'exit_long'] = 1
        dataframe.loc[dataframe['uptrend_structure'], 'exit_short'] = 1
        return dataframe
    
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        return self.leverage_long.value if side == 'long' else self.leverage_short.value

    def detect_swing_points_no_bias(self, dataframe: DataFrame) -> DataFrame:
        """
        Detect swing points without future bias - only looking at past data
        """
        lookback = self.swing_lookback.value
        
        # Initialize columns
        dataframe['swing_high'] = np.nan
        dataframe['swing_low'] = np.nan
        
        # Only look at past data to detect swing points
        for i in range(lookback * 2, len(dataframe)):
            # Check if the point at i-lookback is a swing high
            # by comparing it to lookback periods before and after
            center_idx = i - lookback
            
            # Get the window of data (only past data up to current point i)
            high_window = dataframe['high'].iloc[center_idx-lookback:center_idx+lookback+1]
            low_window = dataframe['low'].iloc[center_idx-lookback:center_idx+lookback+1]
            
            # Check if center point is highest in the window
            if len(high_window) == 2 * lookback + 1:
                if high_window.iloc[lookback] == high_window.max():
                    dataframe.loc[dataframe.index[i], 'swing_high'] = high_window.iloc[lookback]
                
                # Check if center point is lowest in the window
                if low_window.iloc[lookback] == low_window.min():
                    dataframe.loc[dataframe.index[i], 'swing_low'] = low_window.iloc[lookback]
        
        # Forward fill the last known swing points
        dataframe['last_swing_high'] = dataframe['swing_high'].ffill()
        dataframe['last_swing_low'] = dataframe['swing_low'].ffill()
        
        # Get previous swing points for comparison
        dataframe['prev_swing_high'] = dataframe['last_swing_high'].shift(1)
        dataframe['prev_swing_low'] = dataframe['last_swing_low'].shift(1)
        
        return dataframe

    def detect_trend_structure(self, dataframe: DataFrame) -> DataFrame:
        """
        Detect trend structure based on swing points
        """
        # Higher highs or higher lows indicate uptrend
        dataframe['uptrend_structure'] = (
            (dataframe['last_swing_high'] > dataframe['prev_swing_high']) | 
            (dataframe['last_swing_low'] > dataframe['prev_swing_low'])
        )
        
        # Lower highs or lower lows indicate downtrend
        dataframe['downtrend_structure'] = (
            (dataframe['last_swing_high'] < dataframe['prev_swing_high']) | 
            (dataframe['last_swing_low'] < dataframe['prev_swing_low'])
        )
        
        # Fill NaN values with False
        dataframe['uptrend_structure'] = dataframe['uptrend_structure'].fillna(False)
        dataframe['downtrend_structure'] = dataframe['downtrend_structure'].fillna(False)
        
        return dataframe

    def detect_pullback(self, dataframe: DataFrame) -> DataFrame:
        """
        Detect pullbacks in trends
        """
        lookback = self.pullback_lookback.value
        
        # Calculate recent highs and lows
        dataframe['recent_high'] = dataframe['high'].rolling(lookback).max()
        dataframe['recent_low'] = dataframe['low'].rolling(lookback).min()
        
        # Calculate pullback percentages
        dataframe['pullback_from_high'] = (dataframe['recent_high'] - dataframe['close']) / dataframe['recent_high']
        dataframe['pullback_from_low'] = (dataframe['close'] - dataframe['recent_low']) / dataframe['close']
        
        # Identify pullbacks within the specified range
        dataframe['pullback_in_uptrend'] = dataframe['pullback_from_high'].between(
            self.pullback_min_percent.value, 
            self.pullback_max_percent.value
        )
        dataframe['pullback_in_downtrend'] = dataframe['pullback_from_low'].between(
            self.pullback_min_percent.value, 
            self.pullback_max_percent.value
        )
        
        return dataframe
    
    def add_market_confirmation(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Add BTC market trend confirmation
        """
        btc_5m = self.dp.get_pair_dataframe("BTC/USDT:USDT", "5m")
        if not btc_5m.empty:
            btc_5m['btc_ma_fast'] = ta.EMA(btc_5m, timeperiod=20)
            btc_5m['btc_ma_slow'] = ta.EMA(btc_5m, timeperiod=50)
            btc_5m['btc_trend'] = np.where(btc_5m['btc_ma_fast'] > btc_5m['btc_ma_slow'], 1, -1)
            dataframe = merge_informative_pair(dataframe, btc_5m[['date', 'btc_trend']], self.timeframe, "5m", ffill=True)
        else:
            dataframe['btc_trend_5m'] = 0
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        """
        Additional trade entry confirmation with cooldown logic
        """
        # Implement cooldown at trade entry instead of in indicators
        if self.cooldown_minutes.value > 0:
            trades = Trade.get_trades_proxy(pair=pair, is_open=False)
            if trades and len(trades) > 0:
                last_trade = trades[-1]
                if last_trade.close_date_utc:
                    time_since_last = current_time - last_trade.close_date_utc
                    if time_since_last < timedelta(minutes=self.cooldown_minutes.value):
                        return False
        
        return True
