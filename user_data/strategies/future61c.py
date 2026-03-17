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

class future61c(IStrategy):
    """
    Market Microstructure-based strategy with improved entry timing
    - Order flow analysis
    - Liquidity detection
    - Volume profile concepts
    - Price action patterns
    """
    
    # --- Strategy Configuration ---
    minimal_roi = {
        "0": 0.18,
        "10": 0.12,    
        "30": 0.08,
        "60": 0.04,
        "120": 0.02,
        "180": 0
    }
    
    stoploss = -0.05
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True
    
    use_exit_signal = True
    process_only_new_candles = True
    max_open_trades = 15
    timeframe = '5m'
    startup_candle_count = 150
    can_short = True
    can_long = True

    # --- Market Microstructure Parameters ---
    liquidity_zone_period = IntParameter(10, 30, default=20, space="both", optimize=True)
    volume_imbalance_threshold = DecimalParameter(1.5, 3.0, default=2.0, space="both", optimize=True)
    momentum_acceleration = DecimalParameter(0.002, 0.01, default=0.005, space="both", optimize=True)
    
    # Price Action Parameters
    rejection_threshold = DecimalParameter(0.001, 0.005, default=0.003, space="both", optimize=True)
    absorption_ratio = DecimalParameter(1.2, 2.5, default=1.8, space="both", optimize=True)
    
    # Trend Parameters (simplified)
    trend_ema_fast = IntParameter(8, 15, default=10, space="both", optimize=True)
    trend_ema_slow = IntParameter(20, 35, default=25, space="both", optimize=True)
    
    # Volume Profile
    vp_volume_threshold = DecimalParameter(0.7, 0.9, default=0.8, space="both", optimize=True)

    def informative_pairs(self):
        """Define additional data pairs"""
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, "15m") for pair in pairs]
        informative_pairs.append(("BTC/USDT:USDT", "5m"))
        return informative_pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Market Microstructure Indicators"""
        
        # Basic trend indicators
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.trend_ema_fast.value)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.trend_ema_slow.value)
        dataframe['trend_direction'] = np.where(dataframe['ema_fast'] > dataframe['ema_slow'], 1, -1)
        
        # === MARKET MICROSTRUCTURE INDICATORS ===
        
        # 1. Liquidity Zones (High Volume Nodes)
        dataframe = self.calculate_liquidity_zones(dataframe)
        
        # 2. Order Flow Analysis
        dataframe = self.calculate_order_flow(dataframe)
        
        # 3. Volume Profile
        dataframe = self.calculate_volume_profile(dataframe)
        
        # 4. Price Rejection Analysis
        dataframe = self.calculate_price_rejection(dataframe)
        
        # 5. Momentum and Acceleration
        dataframe = self.calculate_momentum_indicators(dataframe)
        
        # 6. Market Structure
        dataframe = self.calculate_market_structure(dataframe)
        
        # 7. Simplified Volume Analysis
        dataframe['volume_ma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_ma']
        dataframe['volume_spike'] = dataframe['volume_ratio'] > self.volume_imbalance_threshold.value
        
        # 8. Basic Oscillators (for confirmation)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['stoch_k'] = ta.STOCH(dataframe)['slowk']
        
        # 9. Support/Resistance
        dataframe['resistance'] = dataframe['high'].rolling(20).max()
        dataframe['support'] = dataframe['low'].rolling(20).min()
        
        return dataframe

    def calculate_liquidity_zones(self, dataframe: DataFrame) -> DataFrame:
        """Identify high volume price levels (liquidity zones)"""
        
        # Volume-weighted price levels
        dataframe['vwap'] = (dataframe['volume'] * (dataframe['high'] + dataframe['low'] + dataframe['close']) / 3).cumsum() / dataframe['volume'].cumsum()
        
        # High volume nodes (simplified POC)
        volume_period = self.liquidity_zone_period.value
        dataframe['high_volume_zone'] = dataframe['volume'].rolling(volume_period).mean()
        dataframe['is_liquidity_zone'] = dataframe['volume'] > dataframe['high_volume_zone'] * self.vp_volume_threshold.value
        
        # Distance from VWAP (fair value)
        dataframe['vwap_distance'] = (dataframe['close'] - dataframe['vwap']) / dataframe['vwap']
        
        return dataframe

    def calculate_order_flow(self, dataframe: DataFrame) -> DataFrame:
        """Analyze order flow and market imbalance"""
        
        # Buy/Sell pressure based on close position in candle
        dataframe['candle_range'] = dataframe['high'] - dataframe['low']
        dataframe['close_position'] = (dataframe['close'] - dataframe['low']) / dataframe['candle_range']
        
        # Strong buying pressure: close near high with high volume
        dataframe['buying_pressure'] = (
            (dataframe['close_position'] > 0.7) & 
            (dataframe['volume_ratio'] > 1.5)
        )
        
        # Strong selling pressure: close near low with high volume  
        dataframe['selling_pressure'] = (
            (dataframe['close_position'] < 0.3) & 
            (dataframe['volume_ratio'] > 1.5)
        )
        
        # Order flow imbalance
        dataframe['ofi'] = (
            (dataframe['close'] - dataframe['open']) * 
            dataframe['volume_ratio'] / dataframe['candle_range'].replace(0, 0.001)
        )
        
        return dataframe

    def calculate_volume_profile(self, dataframe: DataFrame) -> DataFrame:
        """Volume profile and absorption analysis"""
        
        # Volume delta (simplified)
        green_volume = np.where(dataframe['close'] > dataframe['open'], dataframe['volume'], 0)
        red_volume = np.where(dataframe['close'] < dataframe['open'], dataframe['volume'], 0)
        
        dataframe['volume_delta'] = (
            dataframe['volume'].rolling(5).apply(lambda x: x[green_volume].sum() - x[red_volume].sum(), raw=True)
        )
        
        # Absorption detection
        dataframe['absorption'] = (
            (dataframe['candle_range'] < dataframe['candle_range'].rolling(5).mean()) &
            (dataframe['volume'] > dataframe['volume_ma'] * self.absorption_ratio.value)
        )
        
        return dataframe

    def calculate_price_rejection(self, dataframe: DataFrame) -> DataFrame:
        """Identify price rejection at key levels"""
        
        # Pin bars (simplified)
        dataframe['upper_wick'] = dataframe['high'] - np.maximum(dataframe['open'], dataframe['close'])
        dataframe['lower_wick'] = np.minimum(dataframe['open'], dataframe['close']) - dataframe['low']
        dataframe['body'] = abs(dataframe['close'] - dataframe['open'])
        
        # Rejection candles
        dataframe['rejection_top'] = (
            (dataframe['upper_wick'] > dataframe['body'] * 2) &
            (dataframe['upper_wick'] > dataframe['candle_range'] * 0.3)
        )
        
        dataframe['rejection_bottom'] = (
            (dataframe['lower_wick'] > dataframe['body'] * 2) &
            (dataframe['lower_wick'] > dataframe['candle_range'] * 0.3)
        )
        
        # Rejection at key levels
        dataframe['rejection_resistance'] = (
            dataframe['rejection_top'] & 
            (abs(dataframe['high'] - dataframe['resistance']) / dataframe['resistance'] < self.rejection_threshold.value)
        )
        
        dataframe['rejection_support'] = (
            dataframe['rejection_bottom'] & 
            (abs(dataframe['low'] - dataframe['support']) / dataframe['support'] < self.rejection_threshold.value)
        )
        
        return dataframe

    def calculate_momentum_indicators(self, dataframe: DataFrame) -> DataFrame:
        """Momentum and acceleration analysis"""
        
        # Price acceleration (rate of change of momentum)
        dataframe['momentum_1'] = dataframe['close'].pct_change(periods=1)
        dataframe['momentum_3'] = dataframe['close'].pct_change(periods=3)
        dataframe['momentum_accel'] = dataframe['momentum_1'] - dataframe['momentum_3'].shift(1)
        
        # Strong momentum detection
        dataframe['momentum_breakout'] = (
            (dataframe['momentum_1'].abs() > self.momentum_acceleration.value) &
            (dataframe['momentum_accel'] > 0)
        )
        
        # Directional momentum
        dataframe['bull_momentum'] = (dataframe['momentum_1'] > 0) & (dataframe['momentum_accel'] > 0)
        dataframe['bear_momentum'] = (dataframe['momentum_1'] < 0) & (dataframe['momentum_accel'] < 0)
        
        return dataframe

    def calculate_market_structure(self, dataframe: DataFrame) -> DataFrame:
        """Market structure analysis (HH/HL vs LH/LL)"""
        
        # Higher Highs/Higher Lows
        dataframe['higher_high'] = dataframe['high'] > dataframe['high'].shift(1)
        dataframe['higher_low'] = dataframe['low'] > dataframe['low'].shift(1)
        dataframe['lower_high'] = dataframe['high'] < dataframe['high'].shift(1)
        dataframe['lower_low'] = dataframe['low'] < dataframe['low'].shift(1)
        
        # Market structure shifts
        dataframe['structure_bullish'] = (
            dataframe['higher_high'].rolling(3).sum() >= 2 &
            dataframe['higher_low'].rolling(3).sum() >= 2
        )
        
        dataframe['structure_bearish'] = (
            dataframe['lower_high'].rolling(3).sum() >= 2 &
            dataframe['lower_low'].rolling(3).sum() >= 2
        )
        
        # Break of structure
        dataframe['bos_bullish'] = (
            dataframe['high'] > dataframe['high'].rolling(5).max().shift(1) &
            dataframe['structure_bullish']
        )
        
        dataframe['bos_bearish'] = (
            dataframe['low'] < dataframe['low'].rolling(5).min().shift(1) &
            dataframe['structure_bearish']
        )
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry based on market microstructure signals"""
        
        # === SIMPLIFIED LONG ENTRIES ===
        
        # 1. Momentum Breakout Long
        long_breakout = [
            dataframe['trend_direction'] > 0,
            dataframe['momentum_breakout'],
            dataframe['volume_spike'],
            dataframe['bull_momentum'],
            ~dataframe['rejection_top']  # No rejection at top
        ]
        
        # 2. Liquidity Grab Long (price dips to liquidity zone then reverses)
        long_liquidity_grab = [
            dataframe['trend_direction'] > 0,
            dataframe['is_liquidity_zone'],
            dataframe['rejection_bottom'],
            dataframe['buying_pressure'],
            (dataframe['vwap_distance'] < -0.005)  # Price below VWAP
        ]
        
        # 3. Break of Structure Long
        long_bos = [
            dataframe['bos_bullish'],
            dataframe['volume_spike'],
            dataframe['bull_momentum'],
            (dataframe['rsi'] < 70)  # Not overbought
        ]
        
        # === SIMPLIFIED SHORT ENTRIES ===
        
        # 1. Momentum Breakout Short
        short_breakout = [
            dataframe['trend_direction'] < 0,
            dataframe['momentum_breakout'],
            dataframe['volume_spike'],
            dataframe['bear_momentum'],
            ~dataframe['rejection_bottom']  # No rejection at bottom
        ]
        
        # 2. Liquidity Grab Short (price rallies to liquidity zone then reverses)
        short_liquidity_grab = [
            dataframe['trend_direction'] < 0,
            dataframe['is_liquidity_zone'],
            dataframe['rejection_top'],
            dataframe['selling_pressure'],
            (dataframe['vwap_distance'] > 0.005)  # Price above VWAP
        ]
        
        # 3. Break of Structure Short
        short_bos = [
            dataframe['bos_bearish'],
            dataframe['volume_spike'],
            dataframe['bear_momentum'],
            (dataframe['rsi'] > 30)  # Not oversold
        ]
        
        # Apply conditions (require 3 out of 4 conditions for each setup)
        dataframe.loc[
            reduce(lambda x, y: x & y, long_breakout) |
            reduce(lambda x, y: x & y, long_liquidity_grab) |
            reduce(lambda x, y: x & y, long_bos), 
            'enter_long'
        ] = 1
        
        dataframe.loc[
            reduce(lambda x, y: x & y, short_breakout) |
            reduce(lambda x, y: x & y, short_liquidity_grab) |
            reduce(lambda x, y: x & y, short_bos), 
            'enter_short'
        ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit based on microstructure signals"""
        
        # Exit long positions
        exit_long_conditions = [
            dataframe['rejection_top'],  # Rejection at top
            dataframe['selling_pressure'],  # Strong selling pressure
            (dataframe['trend_direction'] < 0),  # Trend reversal
            (dataframe['rsi'] > 75),  # Overbought
            dataframe['absorption'] & (dataframe['close'] < dataframe['open'])  # Absorption at top
        ]
        
        # Exit short positions
        exit_short_conditions = [
            dataframe['rejection_bottom'],  # Rejection at bottom
            dataframe['buying_pressure'],  # Strong buying pressure
            (dataframe['trend_direction'] > 0),  # Trend reversal
            (dataframe['rsi'] < 25),  # Oversold
            dataframe['absorption'] & (dataframe['close'] > dataframe['open'])  # Absorption at bottom
        ]
        
        # Exit if any condition is met
        dataframe.loc[reduce(lambda x, y: x | y, exit_long_conditions), 'exit_long'] = 1
        dataframe.loc[reduce(lambda x, y: x | y, exit_short_conditions), 'exit_short'] = 1

        return dataframe

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """Conservative leverage for microstructure strategy"""
        return 3.0  # Fixed conservative leverage

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        """Final confirmation with market context"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty or len(dataframe) < 2:
            return False
            
        last_candle = dataframe.iloc[-1]
        prev_candle = dataframe.iloc[-2]
        
        # Avoid trading in extremely low volatility
        if last_candle['candle_range'] / last_candle['close'] < 0.002:
            return False
            
        # Avoid trading with very low volume
        if last_candle['volume_ratio'] < 0.5:
            return False
            
        # Additional momentum confirmation
        if side == 'long':
            if last_candle['momentum_1'] < -0.001:  # Don't long if recent momentum is negative
                return False
        else:
            if last_candle['momentum_1'] > 0.001:  # Don't short if recent momentum is positive
                return False
                
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, 
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """Microstructure-based early exits"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return None
            
        last_candle = dataframe.iloc[-1]
        
        # Quick profit taking on strong rejections
        if current_profit > 0.08:  # 8% profit
            if trade.is_short and last_candle['rejection_bottom']:
                return 'rejection_bottom_quick_exit'
            elif not trade.is_short and last_candle['rejection_top']:
                return 'rejection_top_quick_exit'
                
        # Exit if order flow strongly reverses
        if trade.is_short:
            if (last_candle['buying_pressure'] and 
                last_candle['volume_ratio'] > 2.0 and 
                current_profit > 0.03):
                return 'strong_buying_pressure'
        else:
            if (last_candle['selling_pressure'] and 
                last_candle['volume_ratio'] > 2.0 and 
                current_profit > 0.03):
                return 'strong_selling_pressure'
                
        return None
