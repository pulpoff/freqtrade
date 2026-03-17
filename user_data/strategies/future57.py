from functools import reduce
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter

class future57(IStrategy):
    minimal_roi = {
        "0": 0.03,
        "10": 0.02,
        "30": 0.015,
        "60": 0.01,
        "90": 0.001
    }

    stoploss = -0.15
    trailing_stop = False
    trailing_stop_positive = 0.16
    trailing_stop_positive_offset = 0.213
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    process_only_new_candles = True

    # Core parameters
    leverage_param = IntParameter(4, 10, default=8, space="buy", optimize=True)
    
    buy_rsi = IntParameter(30, 50, default=42, space="buy", optimize=True)
    sell_rsi_upper = IntParameter(60, 85, default=72, space="sell", optimize=True)
    sell_rsi_lower = IntParameter(20, 40, default=28, space="sell", optimize=True)
    
    macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
    macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
    
    ema_short_period = IntParameter(5, 15, default=8, space="both", optimize=True)
    ema_long_period = IntParameter(15, 30, default=21, space="both", optimize=True)
    
    price_extension_pct = DecimalParameter(0.003, 0.01, default=0.004, space="sell", optimize=True)
    confluence_threshold = IntParameter(5, 9, default=5, space="buy", optimize=True)
    
    # Bollinger Band Exit Parameters
    bb_exit_period = IntParameter(15, 25, default=20, space="sell", optimize=True)
    bb_exit_std = DecimalParameter(1.5, 2.5, default=2.0, space="sell", optimize=True)
    bb_penetration_threshold = DecimalParameter(0.001, 0.005, default=0.002, space="sell", optimize=True)
    bb_exit_confirmation_candles = IntParameter(1, 3, default=2, space="sell", optimize=True)
    
    # Minimum profit and holding time
    min_profit_for_bb_exit = DecimalParameter(0.005, 0.02, default=0.008, space="sell", optimize=True)
    min_holding_minutes = IntParameter(30, 120, default=60, space="sell", optimize=True)
    max_holding_hours = IntParameter(8, 48, default=24, space="sell", optimize=True)
    
    # Emergency exit parameters
    emergency_rsi_threshold = IntParameter(25, 35, default=30, space="sell", optimize=True)
    emergency_loss_threshold = DecimalParameter(-0.03, -0.01, default=-0.02, space="sell", optimize=True)
    
    # Volume confirmation
    volume_exit_multiplier = DecimalParameter(0.8, 1.5, default=1.1, space="sell", optimize=True)
    
    timeframe = '5m'
    startup_candle_count = 200
    can_short = True
    can_long = False

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_candle_seen_time = {}
        self._trade_start_times = {}
        self._market_regime = "bear_high_vol"
        self._regime_update_time = None

    def detect_market_regime(self, dataframe: DataFrame) -> str:
        """Detect current market regime based on EMAs and volatility"""
        if len(dataframe) < 200:
            return self._market_regime
            
        ema_50 = ta.EMA(dataframe, timeperiod=50)
        ema_200 = ta.EMA(dataframe, timeperiod=200)
        
        volatility = dataframe['close'].rolling(20).std()
        avg_volatility = volatility.rolling(100).mean()
        
        current_trend = ema_50.iloc[-1] > ema_200.iloc[-1]
        current_volatility = volatility.iloc[-1] / avg_volatility.iloc[-1]
        
        if current_trend and current_volatility < 1.2:
            return 'bull_low_vol'
        elif current_trend and current_volatility >= 1.2:
            return 'bull_high_vol'
        elif not current_trend and current_volatility < 1.2:
            return 'bear_low_vol'
        else:
            return 'bear_high_vol'

    def get_coin_from_pair(self, pair: str) -> str:
        """Extract coin symbol from trading pair"""
        if '/' in pair:
            return pair.split('/')[0]
        return "UNKNOWN"

    def informative_pairs(self):
        """Define informative pairs for additional timeframes"""
        pairs = self.dp.current_whitelist()
        informative_pairs = []
        
        for pair in pairs:
            informative_pairs.append((pair, '1m'))  # For fine-grained exit signals
            
        return informative_pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all technical indicators"""
        
        # Update market regime every 4 hours
        if (self._regime_update_time is None or 
            datetime.now() - self._regime_update_time > timedelta(hours=4)):
            self._market_regime = self.detect_market_regime(dataframe)
            self._regime_update_time = datetime.now()
        
        # Basic indicators
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=self.ema_short_period.value)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=self.ema_long_period.value)
        
        # MACD
        macd = ta.MACD(dataframe, 
                     fastperiod=self.macd_fast.value,
                     slowperiod=self.macd_slow.value, 
                     signalperiod=self.macd_signal.value)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Bollinger Bands for entry
        bollinger = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), 
            window=20, 
            stds=2
        )
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_pct'] = (dataframe['close'] - bollinger['lower']) / (bollinger['upper'] - bollinger['lower'])
        
        # Bollinger Bands for exit (customizable period and std)
        bb_exit = qtpylib.bollinger_bands(
            qtpylib.typical_price(dataframe), 
            window=self.bb_exit_period.value, 
            stds=self.bb_exit_std.value
        )
        dataframe['bb_exit_upper'] = bb_exit['upper']
        dataframe['bb_exit_middle'] = bb_exit['mid']
        dataframe['bb_exit_lower'] = bb_exit['lower']
        
        # Volume indicators
        dataframe['volume_avg'] = dataframe['volume'].rolling(20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_avg']
        
        # Calculate confluence score for entry
        dataframe = self.calculate_confluence_score(dataframe)
        
        # Calculate Bollinger Band exit signals
        dataframe = self.calculate_bb_exit_signals(dataframe)
        
        return dataframe

    def calculate_confluence_score(self, dataframe: DataFrame) -> DataFrame:
        """Calculate confluence score for entry signals"""
        
        signals = {}
        signals['rsi_signal'] = (dataframe['rsi'] > self.sell_rsi_upper.value).astype(int) * 3
        signals['bb_signal'] = (dataframe['bb_pct'] > 0.85).astype(int) * 2
        signals['macd_signal'] = (
            (dataframe['macdhist'] < dataframe['macdhist'].shift(1)) &
            (dataframe['macdhist'].shift(1) > 0)
        ).astype(int) * 2
        signals['volume_signal'] = (dataframe['volume_ratio'] > 1.3).astype(int) * 1
        signals['trend_signal'] = (dataframe['close'] > dataframe['ema_short']).astype(int) * 1
        signals['extension_signal'] = (
            dataframe['close'] > dataframe['ema_short'] * (1 + self.price_extension_pct.value)
        ).astype(int) * 2
        signals['momentum_signal'] = (
            (dataframe['close'] > dataframe['close'].shift(1)) &
            (dataframe['close'].shift(1) > dataframe['close'].shift(2))
        ).astype(int) * 1
        
        dataframe['confluence_score'] = sum(signals.values())
        dataframe['high_confluence'] = dataframe['confluence_score'] >= self.confluence_threshold.value
        
        return dataframe

    def calculate_bb_exit_signals(self, dataframe: DataFrame) -> DataFrame:
        """Calculate Bollinger Band-based exit signals for short positions"""
        
        # Price penetration below lower BB (indicating potential downtrend exhaustion)
        dataframe['bb_price_below'] = dataframe['close'] < dataframe['bb_exit_lower']
        dataframe['bb_penetration'] = (dataframe['bb_exit_lower'] - dataframe['close']) / dataframe['close']
        
        # Significant penetration below lower BB
        dataframe['bb_deep_penetration'] = (
            dataframe['bb_penetration'] > self.bb_penetration_threshold.value
        )
        
        # Price touching or going below lower BB with volume confirmation
        dataframe['bb_touch_with_volume'] = (
            dataframe['bb_price_below'] &
            (dataframe['volume'] > dataframe['volume_avg'] * self.volume_exit_multiplier.value)
        )
        
        # Consecutive candles below BB (stronger signal)
        bb_candles = self.bb_exit_confirmation_candles.value
        dataframe['bb_consecutive_below'] = (
            dataframe['bb_price_below'].rolling(bb_candles).sum() >= bb_candles
        )
        
        # Price starting to recover from BB lower band
        dataframe['bb_recovery_start'] = (
            (dataframe['close'].shift(1) < dataframe['bb_exit_lower'].shift(1)) &
            (dataframe['close'] >= dataframe['bb_exit_lower']) &
            (dataframe['close'] > dataframe['close'].shift(1))
        )
        
        # Strong BB recovery signal (price moves back above lower band with momentum)
        dataframe['bb_strong_recovery'] = (
            dataframe['bb_recovery_start'] &
            (dataframe['close'] > dataframe['close'].shift(1)) &
            (dataframe['rsi'] > dataframe['rsi'].shift(1)) &
            (dataframe['volume'] > dataframe['volume_avg'])
        )
        
        # Main exit signal: price has been below BB and is starting to recover
        dataframe['bb_exit_signal'] = (
            (dataframe['bb_deep_penetration'] | dataframe['bb_consecutive_below']) &
            (dataframe['bb_recovery_start'] | dataframe['bb_strong_recovery'])
        )
        
        # Emergency exit: price has been way below BB for too long (failed trade)
        dataframe['bb_emergency_exit'] = (
            (dataframe['bb_penetration'] > self.bb_penetration_threshold.value * 2) &
            (dataframe['bb_consecutive_below']) &
            (dataframe['rsi'] < self.emergency_rsi_threshold.value)
        )
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Define entry conditions for short positions"""
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        # Peak detection
        peak_lookback = 8
        dataframe['high_last_n'] = dataframe['high'].rolling(peak_lookback).max()
        
        # MACD momentum weakness
        dataframe['macd_momentum_weak'] = (
            (dataframe['macdhist'] < dataframe['macdhist'].shift(1)) &
            (dataframe['macdhist'].shift(1) >= dataframe['macdhist'].shift(2)) &
            (dataframe['macd'] > dataframe['macdsignal'])
        )
        
        # MACD approaching bearish cross
        dataframe['macd_approaching_bear_cross'] = (
            (dataframe['macd'] > dataframe['macdsignal']) &
            (dataframe['macd'] - dataframe['macdsignal'] < 
             (dataframe['macd'].shift(1) - dataframe['macdsignal'].shift(1))) &
            (dataframe['macdhist'] < dataframe['macdhist'].shift(1))
        )
        
        # True peak detection
        dataframe['true_peak'] = (
            (dataframe['high'] >= dataframe['high_last_n']) &
            (dataframe['high'] > dataframe['high'].shift(1)) &
            (dataframe['high'].shift(1) > dataframe['high'].shift(2)) &
            (dataframe['close'] < dataframe['high']) &
            (dataframe['rsi'] > self.sell_rsi_upper.value) &
            (dataframe['close'] > dataframe['ema_short'] * (1 + self.price_extension_pct.value)) &
            (dataframe['macd_momentum_weak'] | dataframe['macd_approaching_bear_cross'])
        )
        
        # Momentum failure
        dataframe['momentum_failure'] = (
            (dataframe['close'] < dataframe['close'].shift(1)) &
            (dataframe['close'].shift(1) > dataframe['close'].shift(2)) &
            (dataframe['high'] <= dataframe['high'].shift(1)) &
            (dataframe['rsi'] > self.sell_rsi_upper.value * 0.9) &
            (dataframe['macdhist'] < dataframe['macdhist'].shift(1)) &
            (dataframe['volume'] > dataframe['volume_avg'] * 1.1)
        )
        
        # RSI divergence
        dataframe['rsi_divergence'] = (
            (dataframe['close'] > dataframe['close'].shift(4)) &
            (dataframe['rsi'] < dataframe['rsi'].shift(4)) &
            (dataframe['rsi'] > self.sell_rsi_upper.value * 0.85)
        )
        
        # Enhanced short entry signal
        dataframe.loc[
            (dataframe['true_peak'] | dataframe['momentum_failure'] | dataframe['rsi_divergence']) &
            dataframe['high_confluence'] &
            (dataframe['volume'] > dataframe['volume_avg'] * 0.7),
            'enter_short'
        ] = 1
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Define exit conditions based on Bollinger Band signals"""
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        # Main exit signal: Bollinger Band indicates downtrend exhaustion
        dataframe.loc[
            dataframe['bb_exit_signal'] | dataframe['bb_emergency_exit'],
            'exit_short'
        ] = 1
        
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """Custom exit logic with strict Bollinger Band conditions"""
        
        if not trade.is_short:
            return None
            
        try:
            # Track trade start time
            if trade.id not in self._trade_start_times:
                self._trade_start_times[trade.id] = trade.open_date_utc
            
            trade_start = self._trade_start_times[trade.id]
            trade_duration_minutes = (current_time - trade_start).total_seconds() / 60
            trade_duration_hours = trade_duration_minutes / 60
            
            # Get current dataframe
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) == 0:
                return None
                
            last_candle = dataframe.iloc[-1]
            
            # Minimum holding time check
            if trade_duration_minutes < self.min_holding_minutes.value:
                return None
            
            # Maximum holding time - force exit regardless of conditions
            if trade_duration_hours > self.max_holding_hours.value:
                return 'max_holding_time_reached'
            
            # Emergency exit for significant losses
            if current_profit < self.emergency_loss_threshold.value:
                if last_candle['rsi'] < self.emergency_rsi_threshold.value:
                    return 'emergency_loss_cut'
            
            # Only exit if we have minimum profit AND BB signal
            if current_profit >= self.min_profit_for_bb_exit.value:
                
                # Primary exit: Bollinger Band exit signal
                if last_candle['bb_exit_signal']:
                    return 'bb_downtrend_exhaustion'
                
                # Strong recovery signal
                if last_candle['bb_strong_recovery']:
                    return 'bb_strong_recovery'
                
                # Check for multiple consecutive candles below BB followed by recovery
                if len(dataframe) >= 3:
                    recent_candles = dataframe.tail(3)
                    
                    # Look for pattern: below BB -> below BB -> recovery
                    below_bb_pattern = (
                        recent_candles.iloc[-3]['bb_price_below'] and
                        recent_candles.iloc[-2]['bb_price_below'] and
                        recent_candles.iloc[-1]['bb_recovery_start']
                    )
                    
                    if below_bb_pattern and current_profit > self.min_profit_for_bb_exit.value * 1.5:
                        return 'bb_pattern_recovery'
            
            # Emergency exit if price has been below BB for too long
            if last_candle['bb_emergency_exit'] and current_profit > 0:
                return 'bb_emergency_recovery'
                
        except Exception as e:
            # Log error but don't exit on exceptions
            print(f"Error in custom_exit for {pair}: {e}")
            
        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        """Confirm trade entry with additional checks"""
        
        if side != 'short':
            return True
        
        # Cooldown between trades
        cooldown_minutes = 5 if 'bear' in self._market_regime else 3
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
        
        self._last_candle_seen_time[pair] = current_time
        return True

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], 
                side: str, **kwargs) -> float:
        """Dynamic leverage based on market conditions"""
        
        base_leverage = self.leverage_param.value
        
        # Reduce leverage in high volatility markets
        if 'high_vol' in self._market_regime:
            return max(1.0, float(base_leverage * 0.7))
        elif 'bull' in self._market_regime:
            return max(1.0, float(base_leverage * 0.8))
        
        return float(base_leverage)

    def custom_stoploss(self, pair: str, current_time: datetime, current_rate: float, 
                       current_profit: float, **kwargs) -> float:
        """Dynamic stoploss"""
        return self.stoploss

    def cleanup_trade_data(self):
        """Clean up tracking data for closed trades"""
        try:
            current_trade_ids = {trade.id for trade in Trade.get_open_trades()}
            
            # Clean up start times for closed trades
            closed_ids = set(self._trade_start_times.keys()) - current_trade_ids
            for trade_id in closed_ids:
                if trade_id in self._trade_start_times:
                    del self._trade_start_times[trade_id]
                    
        except Exception:
            pass

    def get_strategy_name(self) -> str:
        """Return strategy name for identification"""
        return "future57"
