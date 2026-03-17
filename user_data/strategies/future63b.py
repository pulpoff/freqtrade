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

class future63b(IStrategy):
    # --- Optimized Strategy Configuration from Hyperopt ---
    minimal_roi = {
        "0": 0.178,
        "37": 0.102,
        "97": 0.034,
        "112": 0
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
    swing_confirmation_candles = IntParameter(3, 10, default=5, space="both", optimize=True)  # New parameter for confirmation
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

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._pair_cooldowns = {}

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [("BTC/USDT:USDT", "5m")]
        for pair in pairs:
            informative_pairs.append((pair, "1h"))
        return informative_pairs

    # --- Fixed Indicator and Logic Functions (No Future Bias) ---

    def detect_swing_points(self, dataframe: DataFrame) -> DataFrame:
     lookback = self.swing_lookback.value
    
     # Use backward-looking window only (no future data)
     dataframe['swing_high'] = dataframe['high'].rolling(window=lookback).apply(
         lambda x: x.iloc[-1] if x.iloc[-1] == x.max() else np.nan, raw=False
     )
     dataframe['swing_low'] = dataframe['low'].rolling(window=lookback).apply(
         lambda x: x.iloc[-1] if x.iloc[-1] == x.min() else np.nan, raw=False
     )
    
     # Forward fill to carry last swing forward
     dataframe['last_swing_high'] = dataframe['swing_high'].ffill()
     dataframe['last_swing_low'] = dataframe['swing_low'].ffill()
    
     # Use shifted values to ensure no lookahead bias
     dataframe['prev_swing_high'] = dataframe['last_swing_high'].shift(1)
     dataframe['prev_swing_low'] = dataframe['last_swing_low'].shift(1)
    
     return dataframe

    def detect_trend_structure(self, dataframe: DataFrame) -> DataFrame:
         """
         Detect trend structure based on swing points.
         Uses both confirmed and potential swing points for faster signals.
         """
         # Primary trend structure (based on confirmed swings - more reliable but delayed)
         dataframe['uptrend_structure_confirmed'] = (
            (dataframe['last_swing_high'] > dataframe['prev_swing_high']) | 
            (dataframe['last_swing_low'] > dataframe['prev_swing_low'])
         )
         dataframe['downtrend_structure_confirmed'] = (
            (dataframe['last_swing_high'] < dataframe['prev_swing_high']) | 
            (dataframe['last_swing_low'] < dataframe['prev_swing_low'])
         )
        
         # Secondary trend structure (based on rolling highs/lows - faster but less reliable)
         dataframe['rolling_high_prev'] = dataframe['rolling_high'].shift(self.swing_lookback.value)
         dataframe['rolling_low_prev'] = dataframe['rolling_low'].shift(self.swing_lookback.value)
        
         dataframe['uptrend_structure_fast'] = (
            (dataframe['rolling_high'] > dataframe['rolling_high_prev']) | 
            (dataframe['rolling_low'] > dataframe['rolling_low_prev'])
         )
         dataframe['downtrend_structure_fast'] = (
            (dataframe['rolling_high'] < dataframe['rolling_high_prev']) | 
            (dataframe['rolling_low'] < dataframe['rolling_low_prev'])
         )
        
         # Combine both for final signal (you can adjust the logic here)
         # Using OR to be more responsive, AND would be more conservative
         dataframe['uptrend_structure'] = (
            dataframe['uptrend_structure_confirmed'] | 
            dataframe['uptrend_structure_fast']
         )
         dataframe['downtrend_structure'] = (
            dataframe['downtrend_structure_confirmed'] | 
            dataframe['downtrend_structure_fast']
         )
        
         # Fix: Replace inplace fillna with direct assignment
         dataframe['uptrend_structure'] = dataframe['uptrend_structure'].fillna(False)
         dataframe['downtrend_structure'] = dataframe['downtrend_structure'].fillna(False)
        
         return dataframe


    def detect_pullback(self, dataframe: DataFrame) -> DataFrame:
        """
        Detect pullbacks in trends - no changes needed here as it doesn't use future data.
        """
        lookback = self.pullback_lookback.value
        
        # Recent highs and lows
        dataframe['recent_high'] = dataframe['high'].rolling(lookback).max()
        dataframe['recent_low'] = dataframe['low'].rolling(lookback).min()
        
        # Calculate pullback percentages
        dataframe['pullback_from_high'] = (dataframe['recent_high'] - dataframe['close']) / dataframe['recent_high']
        dataframe['pullback_from_low'] = (dataframe['close'] - dataframe['recent_low']) / dataframe['close']
        
        # Identify valid pullbacks within the specified range
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
        Add market confirmation based on BTC trend - no changes needed.
        """
        btc_5m = self.dp.get_pair_dataframe("BTC/USDT:USDT", "5m")
        if not btc_5m.empty:
            btc_5m['btc_ma_fast'] = ta.EMA(btc_5m, timeperiod=20)
            btc_5m['btc_ma_slow'] = ta.EMA(btc_5m, timeperiod=50)
            btc_5m['btc_trend'] = np.where(btc_5m['btc_ma_fast'] > btc_5m['btc_ma_slow'], 1, -1)
            dataframe = merge_informative_pair(dataframe, btc_5m[['date', 'btc_trend']], 
                                              self.timeframe, "5m", ffill=True)
        else:
            dataframe['btc_trend_5m'] = 0
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate all indicators with proper NaN handling.
        """
        # Skip if not enough data
        if len(dataframe) < self.startup_candle_count:
            return dataframe
        
        # Core structure indicators
        dataframe = self.detect_swing_points(dataframe)
        dataframe = self.detect_trend_structure(dataframe)
        dataframe = self.detect_pullback(dataframe)
        dataframe = self.add_market_confirmation(dataframe, metadata)

        # RSI indicators
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        dataframe['rsi_reversal_up'] = qtpylib.crossed_above(
            dataframe['rsi'], 
            self.rsi_oversold_pullback.value
        )
        dataframe['rsi_reversal_down'] = qtpylib.crossed_below(
            dataframe['rsi'], 
            self.rsi_overbought_pullback.value
        )

        # MACD indicators
        macd = ta.MACD(dataframe, 
                       fastperiod=self.macd_fast.value, 
                       slowperiod=self.macd_slow.value, 
                       signalperiod=self.macd_signal.value)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macd_bullish'] = dataframe['macd'] > dataframe['macdsignal']
        dataframe['macd_bearish'] = dataframe['macd'] < dataframe['macdsignal']
        
        # Add volume confirmation (optional enhancement)
        dataframe['volume_sma'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_above_average'] = dataframe['volume'] > dataframe['volume_sma']
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate entry signals with proper data validation.
        """
        # Initialize entry columns
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        # Skip if not enough data
        if len(dataframe) < self.startup_candle_count:
            return dataframe
        
        # Long entry conditions
        long_conditions = [
            dataframe['uptrend_structure'] == True,
            dataframe['pullback_in_uptrend'] == True,
            dataframe['volume'].notna()  # Ensure we have valid data
        ]
        
        # Short entry conditions
        short_conditions = [
            dataframe['downtrend_structure'] == True,
            dataframe['pullback_in_downtrend'] == True,
            dataframe['volume'].notna()  # Ensure we have valid data
        ]

        # Add optional confirmations based on hyperparameters
        if self.use_rsi_confirmation.value:
            long_conditions.append(dataframe['rsi_reversal_up'] == True)
            short_conditions.append(dataframe['rsi_reversal_down'] == True)
        
        if self.use_macd_confirmation.value:
            long_conditions.append(dataframe['macd_bullish'] == True)
            short_conditions.append(dataframe['macd_bearish'] == True)
            
        if self.use_market_confirmation.value:
            long_conditions.append(dataframe.get('btc_trend_5m', 0) > 0)
            short_conditions.append(dataframe.get('btc_trend_5m', 0) < 0)

        # Apply entry conditions
        if long_conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, long_conditions),
                'enter_long'
            ] = 1
            
        if short_conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, short_conditions),
                'enter_short'
            ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate exit signals based on trend structure changes.
        """
        # Initialize exit columns
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        # Exit long when downtrend structure appears
        dataframe.loc[
            dataframe['downtrend_structure'] == True,
            'exit_long'
        ] = 1
        
        # Exit short when uptrend structure appears
        dataframe.loc[
            dataframe['uptrend_structure'] == True,
            'exit_short'
        ] = 1
        
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                        time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                        side: str, **kwargs) -> bool:
     """
     Confirm trade entry with cooldown period, handling backtesting mode.
     """
     # Check if in backtesting mode
     if self.config.get('runmode') in ('backtest', 'hyperopt'):
        # In backtesting mode, use only in-memory cooldown
        if pair in self._pair_cooldowns:
            if current_time - self._pair_cooldowns[pair] < timedelta(minutes=self.cooldown_minutes.value):
                return False
        self._pair_cooldowns[pair] = current_time
        return True

     # Live/dry-run mode: use database checks
     try:
        # Check recent trades from database
        recent_trades = Trade.get_trades([
            Trade.pair == pair,
            Trade.is_open == False,
            Trade.close_date > current_time - timedelta(minutes=self.cooldown_minutes.value)
        ]).all()
        
        if recent_trades:
            return False
            
        # Check open trades to avoid multiple entries
        open_trades = Trade.get_trades([
            Trade.pair == pair,
            Trade.is_open == True
        ]).all()
        
        if len(open_trades) >= 1:  # Adjust limit as needed
            return False
            
     except Exception as e:
        # Log error but don't block trade if database check fails
        self.logger.error(f"Error checking trade history: {e}")
        # Optionally, proceed with in-memory cooldown only
        if pair in self._pair_cooldowns:
            if current_time - self._pair_cooldowns[pair] < timedelta(minutes=self.cooldown_minutes.value):
                return False
                
     # Update cooldown and allow trade
     self._pair_cooldowns[pair] = current_time
     return True

    
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """
        Set leverage based on trade side.
        """
        if side == 'long':
            return min(self.leverage_long.value, max_leverage)
        else:
            return min(self.leverage_short.value, max_leverage)
    
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, **kwargs) -> float:
        """
        Optional: Implement dynamic stoploss based on swing points.
        """
        # Get current dataframe
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            
            # For long trades, use last swing low as dynamic stop
            if trade.is_short == False and 'last_swing_low' in last_candle:
                swing_low = last_candle['last_swing_low']
                if not pd.isna(swing_low) and swing_low < trade.open_rate:
                    # Calculate stoploss based on swing low
                    swing_stoploss = (swing_low - trade.open_rate) / trade.open_rate
                    # Use the tighter of swing stop or configured stop
                    return max(swing_stoploss * 0.99, self.stoploss)  # 0.99 for small buffer
            
            # For short trades, use last swing high as dynamic stop
            elif trade.is_short == True and 'last_swing_high' in last_candle:
                swing_high = last_candle['last_swing_high']
                if not pd.isna(swing_high) and swing_high > trade.open_rate:
                    # Calculate stoploss based on swing high
                    swing_stoploss = (trade.open_rate - swing_high) / trade.open_rate
                    # Use the tighter of swing stop or configured stop
                    return max(swing_stoploss * 0.99, self.stoploss)
        
        return self.stoploss
