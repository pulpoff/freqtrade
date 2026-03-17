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
import logging

logger = logging.getLogger(__name__)


class future65(IStrategy):
    """
    SCALPING STRATEGY with FreqAI Support
    
    Core Logic:
    - SHORT ONLY at swing highs (peaks) - price reversing DOWN
    - LONG ONLY at swing lows (bottoms) - price reversing UP
    - FreqAI filters out bad market conditions
    
    Key principle: We want FEWER, BETTER entries at actual turning points.
    """
    
    # FreqAI enabled
    process_only_new_candles = True
    use_exit_signal = False
    startup_candle_count = 200
    can_short = True
    can_long = True
    
    minimal_roi = {
        "0": 0.08,
        "15": 0.05,
        "45": 0.03,
        "90": 0.02,
        "150": 0.01,
        "240": -0.01,
    }
    
    stoploss = -0.08
    
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.025
    trailing_only_offset_is_reached = True
    
    max_open_trades = 8
    timeframe = '5m'
    
    # Parameters
    leverage_long = IntParameter(3, 8, default=4, space="buy", optimize=True)
    leverage_short = IntParameter(3, 8, default=5, space="sell", optimize=True)
    
    # Swing detection sensitivity
    swing_period = IntParameter(3, 8, default=5, space="both", optimize=True)
    
    # RSI thresholds for confirmation
    rsi_ob = IntParameter(60, 75, default=65, space="sell", optimize=True)
    rsi_os = IntParameter(25, 40, default=35, space="buy", optimize=True)
    
    # ML confidence (when FreqAI active)
    ml_confidence_long = DecimalParameter(0.5, 0.8, default=0.6, space="buy", optimize=True)
    ml_confidence_short = DecimalParameter(0.5, 0.8, default=0.6, space="sell", optimize=True)

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [
            ("BTC/USDT:USDT", "5m"),
            ("BTC/USDT:USDT", "15m"),
            ("BTC/USDT:USDT", "1h"),
        ]
        for pair in pairs:
            informative_pairs.append((pair, "15m"))
            informative_pairs.append((pair, "1h"))
        return informative_pairs

    # ==========================================
    # FreqAI Feature Engineering
    # ==========================================
    
    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int,
                                       metadata: dict, **kwargs) -> DataFrame:
        """ML features that expand with period"""
        
        # Price momentum
        dataframe[f'%-roc_{period}'] = (
            (dataframe['close'] - dataframe['close'].shift(period)) / 
            dataframe['close'].shift(period) * 100
        )
        
        # RSI
        dataframe[f'%-rsi_{period}'] = ta.RSI(dataframe, timeperiod=period)
        
        # EMA relationship
        dataframe[f'%-ema_{period}'] = ta.EMA(dataframe, timeperiod=period)
        dataframe[f'%-dist_ema_{period}'] = (
            (dataframe['close'] - dataframe[f'%-ema_{period}']) / 
            dataframe['close'] * 100
        )
        
        # Volatility
        dataframe[f'%-atr_{period}'] = ta.ATR(dataframe, timeperiod=period)
        dataframe[f'%-atr_pct_{period}'] = dataframe[f'%-atr_{period}'] / dataframe['close'] * 100
        
        # BB position
        bb = ta.BBANDS(dataframe, timeperiod=period, nbdevup=2.0, nbdevdn=2.0)
        dataframe[f'%-bb_pos_{period}'] = (
            (dataframe['close'] - bb['lowerband']) / 
            (bb['upperband'] - bb['lowerband']) * 100
        )
        
        # Volume ratio
        dataframe[f'%-vol_ratio_{period}'] = (
            dataframe['volume'] / dataframe['volume'].rolling(period).mean()
        )
        
        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """Basic ML features"""
        
        dataframe['%-hour'] = dataframe['date'].dt.hour
        dataframe['%-dayofweek'] = dataframe['date'].dt.dayofweek
        
        # Candle patterns
        dataframe['%-body_pct'] = abs(dataframe['close'] - dataframe['open']) / dataframe['close'] * 100
        dataframe['%-upper_wick'] = (dataframe['high'] - dataframe[['open', 'close']].max(axis=1)) / dataframe['close'] * 100
        dataframe['%-lower_wick'] = (dataframe[['open', 'close']].min(axis=1) - dataframe['low']) / dataframe['close'] * 100
        
        # Consecutive direction
        dataframe['%-consec_green'] = (dataframe['close'] > dataframe['open']).rolling(5).sum()
        dataframe['%-consec_red'] = (dataframe['close'] < dataframe['open']).rolling(5).sum()
        
        return dataframe

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """Standard indicators"""
        dataframe = self.populate_core_indicators(dataframe, metadata)
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """Define ML prediction targets"""
        
        # Future returns
        dataframe['future_5'] = (dataframe['close'].shift(-5) - dataframe['close']) / dataframe['close'] * 100
        dataframe['future_10'] = (dataframe['close'].shift(-10) - dataframe['close']) / dataframe['close'] * 100
        dataframe['future_20'] = (dataframe['close'].shift(-20) - dataframe['close']) / dataframe['close'] * 100
        
        # Long target: profitable long trade
        dataframe['&-long_target'] = (
            (dataframe['future_5'] > 1.0) |
            (dataframe['future_10'] > 1.5) |
            (dataframe['future_20'] > 2.0)
        ).astype(int)
        
        # Short target: profitable short trade
        dataframe['&-short_target'] = (
            (dataframe['future_5'] < -1.0) |
            (dataframe['future_10'] < -1.5) |
            (dataframe['future_20'] < -2.0)
        ).astype(int)
        
        # Cleanup
        dataframe.drop(columns=['future_5', 'future_10', 'future_20'], inplace=True, errors='ignore')
        
        return dataframe

    # ==========================================
    # Core Indicator Logic
    # ==========================================
    
    def populate_core_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all indicators for entry logic"""
        
        period = self.swing_period.value
        
        # ============================================
        # SWING HIGH/LOW DETECTION - The Core Logic
        # ============================================
        
        # Find local highs: Current high is the max of surrounding candles
        dataframe['local_high'] = dataframe['high'].rolling(window=period, center=True).max()
        dataframe['is_swing_high'] = dataframe['high'] == dataframe['local_high']
        
        # Find local lows: Current low is the min of surrounding candles
        dataframe['local_low'] = dataframe['low'].rolling(window=period, center=True).min()
        dataframe['is_swing_low'] = dataframe['low'] == dataframe['local_low']
        
        # Detect when we've PASSED a swing point (can't look into future)
        # Swing high passed: We see lower highs for N candles after a peak
        dataframe['swing_high_passed'] = (
            dataframe['is_swing_high'].shift(period) &  # There was a swing high N candles ago
            (dataframe['high'] < dataframe['high'].shift(period)) &  # Current high is lower
            (dataframe['high'].shift(1) < dataframe['high'].shift(period))  # Previous high also lower
        )
        
        # Swing low passed: We see higher lows for N candles after a bottom
        dataframe['swing_low_passed'] = (
            dataframe['is_swing_low'].shift(period) &  # There was a swing low N candles ago
            (dataframe['low'] > dataframe['low'].shift(period)) &  # Current low is higher
            (dataframe['low'].shift(1) > dataframe['low'].shift(period))  # Previous low also higher
        )
        
        # ============================================
        # REVERSAL CANDLE PATTERNS
        # ============================================
        
        # Bearish reversal: After upward move, strong red candle
        dataframe['up_move'] = dataframe['close'].shift(1) > dataframe['close'].shift(4)
        dataframe['strong_red'] = (
            (dataframe['close'] < dataframe['open']) &
            ((dataframe['open'] - dataframe['close']) > (dataframe['high'] - dataframe['low']) * 0.6)
        )
        dataframe['bearish_reversal'] = dataframe['up_move'] & dataframe['strong_red']
        
        # Bullish reversal: After downward move, strong green candle
        dataframe['down_move'] = dataframe['close'].shift(1) < dataframe['close'].shift(4)
        dataframe['strong_green'] = (
            (dataframe['close'] > dataframe['open']) &
            ((dataframe['close'] - dataframe['open']) > (dataframe['high'] - dataframe['low']) * 0.6)
        )
        dataframe['bullish_reversal'] = dataframe['down_move'] & dataframe['strong_green']
        
        # Engulfing patterns
        dataframe['bearish_engulf'] = (
            (dataframe['close'].shift(1) > dataframe['open'].shift(1)) &  # Prev green
            (dataframe['close'] < dataframe['open']) &  # Current red
            (dataframe['open'] >= dataframe['close'].shift(1)) &
            (dataframe['close'] <= dataframe['open'].shift(1))
        )
        
        dataframe['bullish_engulf'] = (
            (dataframe['close'].shift(1) < dataframe['open'].shift(1)) &  # Prev red
            (dataframe['close'] > dataframe['open']) &  # Current green
            (dataframe['open'] <= dataframe['close'].shift(1)) &
            (dataframe['close'] >= dataframe['open'].shift(1))
        )
        
        # ============================================
        # RSI
        # ============================================
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_overbought'] = dataframe['rsi'] > self.rsi_ob.value
        dataframe['rsi_oversold'] = dataframe['rsi'] < self.rsi_os.value
        
        # RSI turning points
        dataframe['rsi_turning_down'] = (
            (dataframe['rsi'].shift(1) > dataframe['rsi']) &
            (dataframe['rsi'].shift(2) < dataframe['rsi'].shift(1))
        )
        dataframe['rsi_turning_up'] = (
            (dataframe['rsi'].shift(1) < dataframe['rsi']) &
            (dataframe['rsi'].shift(2) > dataframe['rsi'].shift(1))
        )
        
        # ============================================
        # TREND
        # ============================================
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=10)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=26)
        dataframe['uptrend'] = dataframe['ema_fast'] > dataframe['ema_slow']
        dataframe['downtrend'] = dataframe['ema_fast'] < dataframe['ema_slow']
        
        # Price extended from EMA (good for mean reversion)
        dataframe['dist_from_ema'] = (dataframe['close'] - dataframe['ema_fast']) / dataframe['close'] * 100
        dataframe['extended_up'] = dataframe['dist_from_ema'] > 1.0
        dataframe['extended_down'] = dataframe['dist_from_ema'] < -1.0
        
        # ============================================
        # BOLLINGER BANDS
        # ============================================
        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_upper'] = bb['upperband']
        dataframe['bb_lower'] = bb['lowerband']
        dataframe['bb_mid'] = bb['middleband']
        dataframe['bb_width'] = (bb['upperband'] - bb['lowerband']) / bb['middleband']
        
        # Touch/breach of bands
        dataframe['touch_upper'] = dataframe['high'] >= dataframe['bb_upper']
        dataframe['touch_lower'] = dataframe['low'] <= dataframe['bb_lower']
        
        # ============================================
        # VOLUME
        # ============================================
        dataframe['volume_ma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_ma']
        dataframe['volume_spike'] = dataframe['volume_ratio'] > 1.5
        
        # ============================================
        # ATR
        # ============================================
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # ============================================
        # HIGHER TIMEFRAMES
        # ============================================
        dataframe = self._add_htf_data(dataframe, metadata)
        
        return dataframe

    def _add_htf_data(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add higher timeframe confirmation"""
        
        # 15m trend
        inf_15m = self.dp.get_pair_dataframe(metadata['pair'], '15m')
        if not inf_15m.empty:
            inf_15m['ema_f'] = ta.EMA(inf_15m, timeperiod=10)
            inf_15m['ema_s'] = ta.EMA(inf_15m, timeperiod=26)
            inf_15m['trend_15m'] = np.where(inf_15m['ema_f'] > inf_15m['ema_s'], 1, -1)
            inf_15m['rsi_15m'] = ta.RSI(inf_15m, timeperiod=14)
            dataframe = merge_informative_pair(
                dataframe, inf_15m[['date', 'trend_15m', 'rsi_15m']], 
                self.timeframe, '15m', ffill=True
            )
        else:
            dataframe['trend_15m'] = 0
            dataframe['rsi_15m'] = 50
            
        # 1h trend
        inf_1h = self.dp.get_pair_dataframe(metadata['pair'], '1h')
        if not inf_1h.empty:
            inf_1h['ema_f'] = ta.EMA(inf_1h, timeperiod=10)
            inf_1h['ema_s'] = ta.EMA(inf_1h, timeperiod=26)
            inf_1h['trend_1h'] = np.where(inf_1h['ema_f'] > inf_1h['ema_s'], 1, -1)
            dataframe = merge_informative_pair(
                dataframe, inf_1h[['date', 'trend_1h']], 
                self.timeframe, '1h', ffill=True
            )
        else:
            dataframe['trend_1h'] = 0
            
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Main indicator function"""
        dataframe = self.populate_core_indicators(dataframe, metadata)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        ENTRY LOGIC
        
        Core principle: Trade the reversal at swing points
        - SHORT when price shows reversal at a HIGH
        - LONG when price shows reversal at a LOW
        """
        
        # Check for FreqAI predictions
        has_ml = '&-pred_long_target' in dataframe.columns
        
        # ============================================
        # SHORT ENTRIES - At Swing Highs Only
        # ============================================
        
        # Primary condition: We've passed a swing high (reversal confirmed)
        short_swing = dataframe['swing_high_passed']
        
        # Alternative: Bearish patterns at extended price
        short_pattern = (
            (dataframe['bearish_reversal'] | dataframe['bearish_engulf']) &
            (dataframe['extended_up'] | dataframe['touch_upper'])
        )
        
        # Confirmation: RSI supports the short
        short_rsi_confirm = (
            dataframe['rsi_overbought'] |
            dataframe['rsi_turning_down']
        )
        
        # Combine: Need swing/pattern AND rsi confirmation
        short_signal = (
            (short_swing | short_pattern) &
            short_rsi_confirm &
            (dataframe['bb_width'] > 0.015) &  # Not ranging
            (dataframe['volume_ratio'] > 0.5)  # Some volume
        )
        
        # Apply ML filter if available
        if has_ml:
            short_signal = short_signal & (
                (dataframe['&-pred_short_target'] > self.ml_confidence_short.value) |
                (dataframe['&-pred_long_target'] < 0.3)  # ML says don't go long
            )
        
        dataframe.loc[short_signal, 'enter_short'] = 1
        
        # ============================================
        # LONG ENTRIES - At Swing Lows Only
        # ============================================
        
        # Primary condition: We've passed a swing low (reversal confirmed)
        long_swing = dataframe['swing_low_passed']
        
        # Alternative: Bullish patterns at extended price
        long_pattern = (
            (dataframe['bullish_reversal'] | dataframe['bullish_engulf']) &
            (dataframe['extended_down'] | dataframe['touch_lower'])
        )
        
        # Confirmation: RSI supports the long
        long_rsi_confirm = (
            dataframe['rsi_oversold'] |
            dataframe['rsi_turning_up']
        )
        
        # Combine: Need swing/pattern AND rsi confirmation
        long_signal = (
            (long_swing | long_pattern) &
            long_rsi_confirm &
            (dataframe['bb_width'] > 0.015) &
            (dataframe['volume_ratio'] > 0.5)
        )
        
        # Apply ML filter if available
        if has_ml:
            long_signal = long_signal & (
                (dataframe['&-pred_long_target'] > self.ml_confidence_long.value) |
                (dataframe['&-pred_short_target'] < 0.3)  # ML says don't go short
            )
        
        dataframe.loc[long_signal, 'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exits via ROI and trailing stops"""
        return dataframe

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """Dynamic leverage"""
        return self.leverage_long.value if side == 'long' else self.leverage_short.value

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                       current_rate: float, current_profit: float,
                       after_fill: bool, **kwargs) -> Optional[float]:
        """ATR-based stop loss"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return None
            
        last_candle = dataframe.iloc[-1]
        atr = last_candle.get('atr', 0)
        
        if atr > 0:
            atr_stop = (atr * 2.5) / current_rate
            
            if current_profit > 0.10:
                return -0.015
            elif current_profit > 0.06:
                return -0.025
            elif current_profit > 0.03:
                return -0.035
            else:
                return max(-min(atr_stop, 0.10), self.stoploss)
        
        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        """Final entry confirmation"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return False
            
        last_candle = dataframe.iloc[-1]
        
        # Don't enter in tight range
        if last_candle.get('bb_width', 0) < 0.01:
            return False
        
        # Need some volume
        if last_candle.get('volume_ratio', 0) < 0.3:
            return False
        
        # RSI sanity checks
        rsi = last_candle.get('rsi', 50)
        if side == 'short' and rsi < 30:  # Don't short when already oversold
            return False
        if side == 'long' and rsi > 70:  # Don't long when already overbought
            return False
        
        # HTF alignment check (optional but helps)
        trend_15m = last_candle.get('trend_15m', 0)
        if side == 'short' and trend_15m > 0:
            # Shorting against 15m uptrend - need strong signal
            if rsi < 60:
                return False
        if side == 'long' and trend_15m < 0:
            # Longing against 15m downtrend - need strong signal
            if rsi > 40:
                return False
        
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, 
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """Exit on reversal signals"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return None
            
        last_candle = dataframe.iloc[-1]
        
        # Exit shorts at swing lows
        if trade.is_short:
            if last_candle.get('swing_low_passed', False) and current_profit > 0.005:
                return 'swing_reversal'
            if last_candle.get('bullish_engulf', False) and current_profit > 0.01:
                return 'bullish_reversal'
        
        # Exit longs at swing highs
        else:
            if last_candle.get('swing_high_passed', False) and current_profit > 0.005:
                return 'swing_reversal'
            if last_candle.get('bearish_engulf', False) and current_profit > 0.01:
                return 'bearish_reversal'
        
        # Check ML signal for exit
        if '&-pred_long_target' in last_candle:
            if trade.is_short and last_candle['&-pred_long_target'] > 0.75:
                return 'ml_reversal'
            elif not trade.is_short and last_candle.get('&-pred_short_target', 0) > 0.75:
                return 'ml_reversal'
        
        return None
