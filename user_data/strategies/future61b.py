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

class future61b(IStrategy):
    """
    Improved trend-following strategy for futures trading with leverage
    - Better trend detection using multiple timeframes
    - Improved entry timing with momentum confirmation
    - Dynamic stop loss based on volatility
    - Better risk management
    """
    
    # --- Strategy Configuration ---
    minimal_roi = {
        "0": 0.25,      # 25% at start (with leverage)
        "20": 0.15,     # 15% after 20 minutes
        "60": 0.08,     # 8% after 1 hour
        "120": 0.04,    # 4% after 2 hours
        "180": 0.02,    # 2% after 3 hours
        "240": 0        # Exit after 4 hours
    }
    
    # Wider stop loss for leveraged trading
    stoploss = -0.08  # 8% stop loss (more room for volatility)
    
    # Enable trailing stop for profit protection
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.04
    trailing_only_offset_is_reached = True
    
    use_exit_signal = True
    process_only_new_candles = True
    max_open_trades = 25
    timeframe = '5m'
    startup_candle_count = 200
    can_short = True
    can_long = True

    # --- Optimizable Parameters ---
    # Leverage
    leverage_long = IntParameter(6, 12, default=9, space="buy", optimize=True)
    leverage_short = IntParameter(6, 12, default=9, space="sell", optimize=True)
    
    # Trend Detection
    ema_fast = IntParameter(8, 20, default=12, space="both", optimize=True)
    ema_medium = IntParameter(20, 40, default=26, space="both", optimize=True)
    ema_slow = IntParameter(40, 80, default=50, space="both", optimize=True)
    
    # Volume confirmation
    volume_ma_period = IntParameter(10, 30, default=20, space="both", optimize=True)
    volume_threshold = DecimalParameter(1.2, 2.5, default=1.5, space="both", optimize=True)
    
    # ADX for trend strength
    adx_period = IntParameter(10, 20, default=14, space="both", optimize=True)
    adx_threshold = IntParameter(20, 35, default=25, space="both", optimize=True)
    
    # RSI for momentum
    rsi_period = IntParameter(10, 20, default=14, space="both", optimize=True)
    rsi_bull_threshold = IntParameter(50, 65, default=55, space="buy", optimize=True)
    rsi_bear_threshold = IntParameter(35, 50, default=45, space="sell", optimize=True)
    
    # MACD for momentum confirmation
    macd_fast = IntParameter(10, 15, default=12, space="both", optimize=True)
    macd_slow = IntParameter(20, 30, default=26, space="both", optimize=True)
    macd_signal = IntParameter(7, 12, default=9, space="both", optimize=True)
    
    # ATR for volatility-based decisions
    atr_period = IntParameter(10, 20, default=14, space="both", optimize=True)
    atr_multiplier = DecimalParameter(1.5, 3.0, default=2.0, space="both", optimize=True)
    
    # Entry timing
    pullback_ema = IntParameter(5, 15, default=9, space="both", optimize=True)
    momentum_period = IntParameter(5, 15, default=10, space="both", optimize=True)

    def informative_pairs(self):
        """Define additional data pairs for market context"""
        pairs = self.dp.current_whitelist()
        informative_pairs = [
            ("BTC/USDT:USDT", "5m"),
            ("BTC/USDT:USDT", "15m"),
            ("BTC/USDT:USDT", "1h")
        ]
        # Add higher timeframe for each pair
        for pair in pairs:
            informative_pairs.append((pair, "15m"))
            informative_pairs.append((pair, "1h"))
        return informative_pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all technical indicators"""
        
        # EMAs for trend detection
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe['ema_medium'] = ta.EMA(dataframe, timeperiod=self.ema_medium.value)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.ema_slow.value)
        
        # Pullback EMA for entry timing
        dataframe['ema_pullback'] = ta.EMA(dataframe, timeperiod=self.pullback_ema.value)
        
        # Trend direction based on EMA alignment
        dataframe['uptrend'] = (
            (dataframe['ema_fast'] > dataframe['ema_medium']) & 
            (dataframe['ema_medium'] > dataframe['ema_slow'])
        )
        dataframe['downtrend'] = (
            (dataframe['ema_fast'] < dataframe['ema_medium']) & 
            (dataframe['ema_medium'] < dataframe['ema_slow'])
        )
        
        # ADX for trend strength
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=self.adx_period.value)
        dataframe['strong_trend'] = dataframe['adx'] > self.adx_threshold.value
        
        # RSI for momentum
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        
        # MACD for momentum confirmation
        macd = ta.MACD(dataframe, 
                      fastperiod=self.macd_fast.value, 
                      slowperiod=self.macd_slow.value, 
                      signalperiod=self.macd_signal.value)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_hist'] = macd['macdhist']
        
        # MACD crossovers
        dataframe['macd_cross_up'] = qtpylib.crossed_above(dataframe['macd'], dataframe['macd_signal'])
        dataframe['macd_cross_down'] = qtpylib.crossed_below(dataframe['macd'], dataframe['macd_signal'])
        
        # Volume analysis
        dataframe['volume_ma'] = ta.SMA(dataframe['volume'], timeperiod=self.volume_ma_period.value)
        dataframe['volume_spike'] = dataframe['volume'] > (dataframe['volume_ma'] * self.volume_threshold.value)
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=self.atr_period.value)
        
        # Momentum indicator
        dataframe['momentum'] = dataframe['close'].pct_change(periods=self.momentum_period.value)
        
        # Bollinger Bands for volatility context
        bollinger = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        dataframe['bb_lower'] = bollinger['lower']
        dataframe['bb_middle'] = bollinger['mid']
        dataframe['bb_upper'] = bollinger['upper']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # Price position relative to EMAs
        dataframe['close_above_fast'] = dataframe['close'] > dataframe['ema_fast']
        dataframe['close_below_fast'] = dataframe['close'] < dataframe['ema_fast']
        
        # Pullback detection for better entries
        dataframe['pullback_to_ema'] = (
            (dataframe['low'] <= dataframe['ema_pullback'] * 1.002) & 
            (dataframe['close'] > dataframe['ema_pullback'])
        )
        
        # Higher timeframe trend confirmation
        dataframe = self.add_higher_tf_confirmation(dataframe, metadata)
        
        # BTC market trend
        dataframe = self.add_btc_trend(dataframe, metadata)
        
        # Support and Resistance levels (simplified, no future bias)
        dataframe['resistance'] = dataframe['high'].rolling(window=20).max()
        dataframe['support'] = dataframe['low'].rolling(window=20).min()
        
        # Breakout detection
        dataframe['breakout_up'] = (
            (dataframe['close'] > dataframe['resistance'].shift(1)) & 
            dataframe['volume_spike']
        )
        dataframe['breakout_down'] = (
            (dataframe['close'] < dataframe['support'].shift(1)) & 
            dataframe['volume_spike']
        )
        
        return dataframe

    def add_higher_tf_confirmation(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add higher timeframe trend confirmation"""
        # Get 15m data
        inf_15m = self.dp.get_pair_dataframe(metadata['pair'], '15m')
        if not inf_15m.empty:
            inf_15m['ema_fast_15m'] = ta.EMA(inf_15m, timeperiod=12)
            inf_15m['ema_slow_15m'] = ta.EMA(inf_15m, timeperiod=26)
            inf_15m['trend_15m'] = np.where(inf_15m['ema_fast_15m'] > inf_15m['ema_slow_15m'], 1, -1)
            dataframe = merge_informative_pair(dataframe, 
                                              inf_15m[['date', 'trend_15m']], 
                                              self.timeframe, '15m', ffill=True)
        else:
            dataframe['trend_15m'] = 0
            
        # Get 1h data
        inf_1h = self.dp.get_pair_dataframe(metadata['pair'], '1h')
        if not inf_1h.empty:
            inf_1h['ema_fast_1h'] = ta.EMA(inf_1h, timeperiod=12)
            inf_1h['ema_slow_1h'] = ta.EMA(inf_1h, timeperiod=26)
            inf_1h['trend_1h'] = np.where(inf_1h['ema_fast_1h'] > inf_1h['ema_slow_1h'], 1, -1)
            dataframe = merge_informative_pair(dataframe, 
                                              inf_1h[['date', 'trend_1h']], 
                                              self.timeframe, '1h', ffill=True)
        else:
            dataframe['trend_1h'] = 0
            
        return dataframe
    
    def add_btc_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add BTC market trend for overall market context"""
        btc_5m = self.dp.get_pair_dataframe("BTC/USDT:USDT", "5m")
        if not btc_5m.empty:
            btc_5m['btc_ema_fast'] = ta.EMA(btc_5m, timeperiod=12)
            btc_5m['btc_ema_slow'] = ta.EMA(btc_5m, timeperiod=26)
            btc_5m['btc_rsi'] = ta.RSI(btc_5m, timeperiod=14)
            btc_5m['btc_trend'] = np.where(btc_5m['btc_ema_fast'] > btc_5m['btc_ema_slow'], 1, -1)
            btc_5m['btc_strong'] = np.where(btc_5m['btc_rsi'] > 50, 1, -1)
            dataframe = merge_informative_pair(dataframe, 
                                              btc_5m[['date', 'btc_trend', 'btc_strong']], 
                                              self.timeframe, "5m", ffill=True)
        else:
            dataframe['btc_trend_5m'] = 0
            dataframe['btc_strong_5m'] = 0
            
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Define entry conditions for long and short positions"""
        
        # Long Entry Conditions
        long_conditions = [
            # Trend alignment
            dataframe['uptrend'],
            dataframe['strong_trend'],
            
            # Price action
            (dataframe['close'] > dataframe['ema_fast']),
            
            # Momentum confirmation
            (dataframe['rsi'] > self.rsi_bull_threshold.value),
            (dataframe['macd'] > dataframe['macd_signal']),
            (dataframe['momentum'] > 0),
            
            # Higher timeframe confirmation (at least one agrees)
            ((dataframe.get('trend_15m', 0) > 0) | (dataframe.get('trend_1h', 0) > 0)),
            
            # Volume confirmation
            dataframe['volume_spike'],
            
            # Optional: BTC not in strong downtrend
            (dataframe.get('btc_trend_5m', 0) >= 0)
        ]
        
        # Alternative long entry on pullback
        long_pullback_conditions = [
            dataframe['uptrend'],
            dataframe['pullback_to_ema'],
            (dataframe['rsi'] > 40),
            (dataframe['rsi'] < 60),
            dataframe['close_above_fast'],
            (dataframe.get('trend_1h', 0) > 0)
        ]
        
        # Alternative long entry on breakout
        long_breakout_conditions = [
            dataframe['breakout_up'],
            dataframe['strong_trend'],
            (dataframe['rsi'] > 50),
            (dataframe['macd'] > dataframe['macd_signal'])
        ]
        
        # Short Entry Conditions
        short_conditions = [
            # Trend alignment
            dataframe['downtrend'],
            dataframe['strong_trend'],
            
            # Price action
            (dataframe['close'] < dataframe['ema_fast']),
            
            # Momentum confirmation
            (dataframe['rsi'] < self.rsi_bear_threshold.value),
            (dataframe['macd'] < dataframe['macd_signal']),
            (dataframe['momentum'] < 0),
            
            # Higher timeframe confirmation
            ((dataframe.get('trend_15m', 0) < 0) | (dataframe.get('trend_1h', 0) < 0)),
            
            # Volume confirmation
            dataframe['volume_spike'],
            
            # Optional: BTC not in strong uptrend
            (dataframe.get('btc_trend_5m', 0) <= 0)
        ]
        
        # Alternative short entry on pullback
        short_pullback_conditions = [
            dataframe['downtrend'],
            dataframe['pullback_to_ema'],
            (dataframe['rsi'] < 60),
            (dataframe['rsi'] > 40),
            dataframe['close_below_fast'],
            (dataframe.get('trend_1h', 0) < 0)
        ]
        
        # Alternative short entry on breakdown
        short_breakout_conditions = [
            dataframe['breakout_down'],
            dataframe['strong_trend'],
            (dataframe['rsi'] < 50),
            (dataframe['macd'] < dataframe['macd_signal'])
        ]
        
        # Apply long conditions
        if long_conditions:
            dataframe.loc[reduce(lambda x, y: x & y, long_conditions), 'enter_long'] = 1
        if long_pullback_conditions:
            dataframe.loc[reduce(lambda x, y: x & y, long_pullback_conditions), 'enter_long'] = 1
        if long_breakout_conditions:
            dataframe.loc[reduce(lambda x, y: x & y, long_breakout_conditions), 'enter_long'] = 1
            
        # Apply short conditions
        if short_conditions:
            dataframe.loc[reduce(lambda x, y: x & y, short_conditions), 'enter_short'] = 1
        if short_pullback_conditions:
            dataframe.loc[reduce(lambda x, y: x & y, short_pullback_conditions), 'enter_short'] = 1
        if short_breakout_conditions:
            dataframe.loc[reduce(lambda x, y: x & y, short_breakout_conditions), 'enter_short'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Define exit conditions"""
        
        # Exit long conditions
        exit_long_conditions = [
            # Trend reversal
            dataframe['downtrend'] |
            
            # Momentum reversal
            (dataframe['macd_cross_down'] & (dataframe['rsi'] < 45)) |
            
            # Strong bearish signal
            ((dataframe['close'] < dataframe['ema_medium']) & 
             (dataframe['rsi'] < 40) & 
             (dataframe['momentum'] < -0.02))
        ]
        
        # Exit short conditions
        exit_short_conditions = [
            # Trend reversal
            dataframe['uptrend'] |
            
            # Momentum reversal
            (dataframe['macd_cross_up'] & (dataframe['rsi'] > 55)) |
            
            # Strong bullish signal
            ((dataframe['close'] > dataframe['ema_medium']) & 
             (dataframe['rsi'] > 60) & 
             (dataframe['momentum'] > 0.02))
        ]
        
        if exit_long_conditions:
            dataframe.loc[reduce(lambda x, y: x | y, exit_long_conditions), 'exit_long'] = 1
            
        if exit_short_conditions:
            dataframe.loc[reduce(lambda x, y: x | y, exit_short_conditions), 'exit_short'] = 1

        return dataframe
    
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """Return leverage based on position side"""
        return self.leverage_long.value if side == 'long' else self.leverage_short.value

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                       current_rate: float, current_profit: float,
                       after_fill: bool, **kwargs) -> Optional[float]:
        """
        Dynamic stop loss based on ATR and profit
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return None
            
        last_candle = dataframe.iloc[-1]
        atr = last_candle.get('atr', 0)
        
        if atr > 0:
            # Base stop loss adjusted by ATR
            atr_stop = atr * self.atr_multiplier.value / current_rate
            
            # Tighten stop loss as profit increases
            if current_profit > 0.15:
                return -0.02  # 2% stop when in 15%+ profit
            elif current_profit > 0.10:
                return -0.03  # 3% stop when in 10%+ profit
            elif current_profit > 0.05:
                return -0.04  # 4% stop when in 5%+ profit
            else:
                # Use ATR-based stop, but cap it
                return max(-min(atr_stop, 0.12), self.stoploss)
        
        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        """
        Additional confirmation before entering a trade
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return False
            
        last_candle = dataframe.iloc[-1]
        
        # Don't enter if volatility is too low (ranging market)
        if last_candle.get('bb_width', 0) < 0.01:
            return False
            
        # Don't enter if volume is too low
        if last_candle.get('volume', 0) < last_candle.get('volume_ma', 1) * 0.5:
            return False
        
        # Additional check for long positions
        if side == 'long':
            # Don't long if RSI is overbought
            if last_candle.get('rsi', 50) > 75:
                return False
        
        # Additional check for short positions
        elif side == 'short':
            # Don't short if RSI is oversold
            if last_candle.get('rsi', 50) < 25:
                return False
        
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, 
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """
        Custom exit logic for special conditions
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return None
            
        last_candle = dataframe.iloc[-1]
        
        # Quick exit if momentum strongly reverses
        if trade.is_short:
            if last_candle.get('momentum', 0) > 0.03 and last_candle.get('rsi', 50) > 65:
                return 'momentum_reversal'
        else:  # Long position
            if last_candle.get('momentum', 0) < -0.03 and last_candle.get('rsi', 50) < 35:
                return 'momentum_reversal'
        
        # Exit if trend structure breaks down completely
        if trade.is_short and last_candle.get('uptrend', False):
            return 'trend_change'
        elif not trade.is_short and last_candle.get('downtrend', False):
            return 'trend_change'
        
        return None
