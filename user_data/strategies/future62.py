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

class future62(IStrategy):
    """
    Fixed future62: Safe column access with .get() for informative merges
    - Handles empty informative dataframes and renamed columns (e.g., trend_1h_1h)
    - Base 5m indicators first, then merges, then safe conditions
    - Leading: Heikin-Ashi, Stochastic, Hull MA for early entries
    """
    
    # --- Strategy Configuration ---
    minimal_roi = {
        "0": 0.10,       # 10% immediate target
        "10": 0.05,      # 5% after 10 minutes
        "30": 0.02,      # 2% after 30 minutes
        "60": 0          # Exit after 1 hour
    }
    
    stoploss = -0.06
    
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True
    
    use_exit_signal = True
    process_only_new_candles = True
    max_open_trades = 25
    timeframe = '5m'
    startup_candle_count = 200
    can_short = True
    can_long = True

    # --- Optimizable Parameters ---
    leverage_long = IntParameter(3, 5, default=4, space="buy", optimize=True)
    leverage_short = IntParameter(3, 5, default=4, space="sell", optimize=True)
    
    ema_fast = IntParameter(6, 12, default=8, space="both", optimize=True)
    ema_medium = IntParameter(18, 30, default=21, space="both", optimize=True)
    ema_slow = IntParameter(35, 60, default=42, space="both", optimize=True)
    
    volume_ma_period = IntParameter(10, 30, default=20, space="both", optimize=True)
    volume_threshold = DecimalParameter(1.1, 2.0, default=1.3, space="both", optimize=True)
    
    adx_period = IntParameter(10, 20, default=14, space="both", optimize=True)
    adx_threshold = IntParameter(20, 35, default=25, space="both", optimize=True)
    
    rsi_period = IntParameter(10, 20, default=14, space="both", optimize=True)
    rsi_bull_threshold = IntParameter(45, 60, default=50, space="buy", optimize=True)
    rsi_bear_threshold = IntParameter(40, 55, default=50, space="sell", optimize=True)
    
    macd_fast = IntParameter(10, 15, default=12, space="both", optimize=True)
    macd_slow = IntParameter(20, 30, default=26, space="both", optimize=True)
    macd_signal = IntParameter(7, 12, default=9, space="both", optimize=True)
    
    atr_period = IntParameter(10, 20, default=14, space="both", optimize=True)
    atr_multiplier = DecimalParameter(1.5, 3.0, default=2.0, space="both", optimize=True)
    
    pullback_ema = IntParameter(4, 10, default=6, space="both", optimize=True)
    momentum_period = IntParameter(5, 15, default=8, space="both", optimize=True)
    
    stoch_k_period = IntParameter(10, 18, default=14, space="both", optimize=True)
    stoch_d_period = IntParameter(2, 5, default=3, space="both", optimize=True)
    stoch_oversold = IntParameter(15, 25, default=20, space="buy", optimize=True)
    stoch_overbought = IntParameter(75, 85, default=80, space="sell", optimize=True)
    
    hma_period = IntParameter(7, 12, default=9, space="both", optimize=True)

    def informative_pairs(self):
        """Only slower timeframes to avoid merge errors"""
        pairs = self.dp.current_whitelist()
        informative_pairs = [
            ("BTC/USDT:USDT", "5m"),
            ("BTC/USDT:USDT", "15m"),
            ("BTC/USDT:USDT", "1h")
        ]
        for pair in pairs:
            informative_pairs.append((pair, "15m"))
            informative_pairs.append((pair, "1h"))
        return informative_pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Indicators: Base first, then safe merges"""
        
        # --- Base 5m Indicators (always available) ---
        # EMAs
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe['ema_medium'] = ta.EMA(dataframe, timeperiod=self.ema_medium.value)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.ema_slow.value)
        dataframe['ema_pullback'] = ta.EMA(dataframe, timeperiod=self.pullback_ema.value)
        
        # Trends
        dataframe['uptrend'] = (
            (dataframe['ema_fast'] > dataframe['ema_medium']) & 
            (dataframe['ema_medium'] > dataframe['ema_slow'])
        )
        dataframe['downtrend'] = (
            (dataframe['ema_fast'] < dataframe['ema_medium']) & 
            (dataframe['ema_medium'] < dataframe['ema_slow'])
        )
        
        # ADX
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=self.adx_period.value)
        dataframe['strong_trend'] = dataframe['adx'] > self.adx_threshold.value
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        
        # MACD
        macd = ta.MACD(dataframe, 
                      fastperiod=self.macd_fast.value, 
                      slowperiod=self.macd_slow.value, 
                      signalperiod=self.macd_signal.value)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_hist'] = macd['macdhist']
        dataframe['macd_cross_up'] = qtpylib.crossed_above(dataframe['macd'], dataframe['macd_signal'])
        dataframe['macd_cross_down'] = qtpylib.crossed_below(dataframe['macd'], dataframe['macd_signal'])
        
        # Volume
        dataframe['volume_ma'] = ta.SMA(dataframe['volume'], timeperiod=self.volume_ma_period.value)
        dataframe['volume_spike'] = dataframe['volume'] > (dataframe['volume_ma'] * self.volume_threshold.value)
        
        # ATR
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=self.atr_period.value)
        
        # Momentum
        dataframe['momentum'] = dataframe['close'].pct_change(periods=self.momentum_period.value)
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        dataframe['bb_lower'] = bollinger['lower']
        dataframe['bb_middle'] = bollinger['mid']
        dataframe['bb_upper'] = bollinger['upper']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # Price positions
        dataframe['close_above_fast'] = dataframe['close'] > dataframe['ema_fast']
        dataframe['close_below_fast'] = dataframe['close'] < dataframe['ema_fast']
        dataframe['pullback_to_ema'] = (
            (dataframe['low'] <= dataframe['ema_pullback'] * 1.002) & 
            (dataframe['close'] > dataframe['ema_pullback'])
        )
        
        # Heikin-Ashi
        heikin_close = (dataframe['open'] + dataframe['high'] + dataframe['low'] + dataframe['close']) / 4
        heikin_open = ((dataframe['open'].shift(1) + dataframe['close'].shift(1)) / 2).fillna((dataframe['open'] + dataframe['close']) / 2)
        dataframe['ha_open'] = heikin_open
        dataframe['ha_close'] = heikin_close
        dataframe['ha_bull'] = heikin_close > heikin_open
        dataframe['ha_bear'] = heikin_close < heikin_open
        
        # Stochastic
        stoch = ta.STOCH(dataframe, fastk_period=self.stoch_k_period.value, slowk_period=self.stoch_d_period.value, slowd_period=self.stoch_d_period.value)
        dataframe['stoch_k'] = stoch['slowk']
        dataframe['stoch_d'] = stoch['slowd']
        dataframe['stoch_rising'] = dataframe['stoch_k'] > dataframe['stoch_d']
        dataframe['stoch_falling'] = dataframe['stoch_k'] < dataframe['stoch_d']
        dataframe['stoch_oversold'] = dataframe['stoch_k'] < self.stoch_oversold.value
        dataframe['stoch_overbought'] = dataframe['stoch_k'] > self.stoch_overbought.value
        
        # Hull MA
        dataframe['hma_short'] = qtpylib.hull_moving_average(dataframe['close'], window=self.hma_period.value)
        dataframe['price_above_hma'] = dataframe['close'] > dataframe['hma_short']
        dataframe['price_below_hma'] = dataframe['close'] < dataframe['hma_short']
        
        # Support/Resistance and Breakouts
        dataframe['resistance'] = dataframe['high'].rolling(window=20).max()
        dataframe['support'] = dataframe['low'].rolling(window=20).min()
        dataframe['breakout_up'] = (
            (dataframe['close'] > dataframe['resistance'].shift(1)) & 
            dataframe['volume_spike']
        )
        dataframe['breakout_down'] = (
            (dataframe['close'] < dataframe['support'].shift(1)) & 
            dataframe['volume_spike']
        )
        
        # --- Informative Merges (Safe with fallbacks) ---
        dataframe = self.add_higher_tf_confirmation(dataframe, metadata)
        dataframe = self.add_btc_trend(dataframe, metadata)
        
        # Fallbacks for any missing informative columns
        if 'trend_1h' not in dataframe.columns:
            dataframe['trend_1h'] = 0
        if 'trend_15m' not in dataframe.columns:
            dataframe['trend_15m'] = 0
        if 'btc_trend_5m' not in dataframe.columns:
            dataframe['btc_trend_5m'] = 0
        
        return dataframe

    def add_higher_tf_confirmation(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Safe higher TF merge with column checks"""
        # 15m - only if data available
        inf_15m = self.dp.get_pair_dataframe(metadata['pair'], '15m')
        if not inf_15m.empty and len(inf_15m) > 20:  # Ensure sufficient data
            inf_15m['ema_fast_15m'] = ta.EMA(inf_15m, timeperiod=12)
            inf_15m['ema_slow_15m'] = ta.EMA(inf_15m, timeperiod=26)
            inf_15m['trend_15m'] = np.where(inf_15m['ema_fast_15m'] > inf_15m['ema_slow_15m'], 1, -1)
            try:
                dataframe = merge_informative_pair(dataframe, 
                                                  inf_15m[['date', 'trend_15m']], 
                                                  self.timeframe, '15m', ffill=True)
                # Rename if needed (handle both trend_15m and trend_15m_15m)
                if 'trend_15m_15m' in dataframe.columns and 'trend_15m' not in dataframe.columns:
                    dataframe['trend_15m'] = dataframe['trend_15m_15m']
            except Exception:
                pass  # Fallback in populate_indicators
        else:
            dataframe['trend_15m'] = 0
        
        # 1h
        inf_1h = self.dp.get_pair_dataframe(metadata['pair'], '1h')
        if not inf_1h.empty and len(inf_1h) > 10:
            inf_1h['ema_fast_1h'] = ta.EMA(inf_1h, timeperiod=12)
            inf_1h['ema_slow_1h'] = ta.EMA(inf_1h, timeperiod=26)
            inf_1h['trend_1h'] = np.where(inf_1h['ema_fast_1h'] > inf_1h['ema_slow_1h'], 1, -1)
            try:
                dataframe = merge_informative_pair(dataframe, 
                                                  inf_1h[['date', 'trend_1h']], 
                                                  self.timeframe, '1h', ffill=True)
                # Handle renamed column
                if 'trend_1h_1h' in dataframe.columns and 'trend_1h' not in dataframe.columns:
                    dataframe['trend_1h'] = dataframe['trend_1h_1h']
            except Exception:
                pass
        else:
            dataframe['trend_1h'] = 0
        
        return dataframe
    
    def add_btc_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Safe BTC merge"""
        btc_5m = self.dp.get_pair_dataframe("BTC/USDT:USDT", "5m")
        if not btc_5m.empty and len(btc_5m) > 50:
            btc_5m['btc_ema_fast'] = ta.EMA(btc_5m, timeperiod=12)
            btc_5m['btc_ema_slow'] = ta.EMA(btc_5m, timeperiod=26)
            btc_5m['btc_rsi'] = ta.RSI(btc_5m, timeperiod=14)
            btc_5m['btc_trend'] = np.where(btc_5m['btc_ema_fast'] > btc_5m['btc_ema_slow'], 1, -1)
            try:
                dataframe = merge_informative_pair(dataframe, 
                                                  btc_5m[['date', 'btc_trend']], 
                                                  self.timeframe, "5m", ffill=True)
                if 'btc_trend_5m' not in dataframe.columns and 'btc_trend_5m_5m' in dataframe.columns:
                    dataframe['btc_trend_5m'] = dataframe['btc_trend_5m_5m']
            except Exception:
                pass
        else:
            dataframe['btc_trend_5m'] = 0
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Safe entry conditions with .get() fallbacks"""
        
        # Safe access helpers
        def safe_trend_1h(): return dataframe.get('trend_1h', pd.Series(0, index=dataframe.index))
        def safe_trend_15m(): return dataframe.get('trend_15m', pd.Series(0, index=dataframe.index))
        def safe_btc_trend(): return dataframe.get('btc_trend_5m', pd.Series(0, index=dataframe.index))
        
        # Long Entry
        long_early_conditions = [
            # Trend bias (use .get() with fallback)
            (safe_trend_1h() > 0) | dataframe['uptrend'],
            dataframe['ha_bull'],
            dataframe['price_above_hma'],
            dataframe['stoch_rising'] & (dataframe['stoch_k'] < 60),
            (dataframe['momentum'] > -0.005),
            (dataframe['volume'] > dataframe['volume_ma'] * 1.1) | dataframe['breakout_up'],
            (safe_btc_trend() >= 0)
        ]
        
        # Apply if sufficient conditions
        core_long = long_early_conditions[:5]  # Limit to prevent overfiltering
        if len(core_long) >= 4:
            dataframe.loc[reduce(lambda x, y: x & y, core_long), 'enter_long'] = 1
        
        # Pullback
        long_pullback_conditions = [
            dataframe['uptrend'],
            dataframe['pullback_to_ema'],
            (dataframe['rsi'] > 40) & (dataframe['rsi'] < 55),
            dataframe['close_above_fast'],
            (safe_trend_1h() > 0) & dataframe['ha_bull']
        ]
        if len(long_pullback_conditions) == 5:
            dataframe.loc[reduce(lambda x, y: x & y, long_pullback_conditions), 'enter_long'] = 1
        
        # Breakout
        long_breakout_conditions = [
            dataframe['breakout_up'],
            dataframe['strong_trend'],
            dataframe['price_above_hma'],
            dataframe['stoch_rising']
        ]
        if len(long_breakout_conditions) == 4:
            dataframe.loc[reduce(lambda x, y: x & y, long_breakout_conditions), 'enter_long'] = 1
        
        # Short Entry
        short_early_conditions = [
            (safe_trend_1h() < 0) | dataframe['downtrend'],
            dataframe['ha_bear'],
            dataframe['price_below_hma'],
            dataframe['stoch_falling'] & (dataframe['stoch_k'] > 40),
            (dataframe['momentum'] < 0.005),
            (dataframe['volume'] > dataframe['volume_ma'] * 1.1) | dataframe['breakout_down'],
            (safe_btc_trend() <= 0)
        ]
        
        core_short = short_early_conditions[:5]
        if len(core_short) >= 4:
            dataframe.loc[reduce(lambda x, y: x & y, core_short), 'enter_short'] = 1
        
        short_pullback_conditions = [
            dataframe['downtrend'],
            dataframe['pullback_to_ema'],
            (dataframe['rsi'] < 60) & (dataframe['rsi'] > 40),
            dataframe['close_below_fast'],
            (safe_trend_1h() < 0) & dataframe['ha_bear']
        ]
        if len(short_pullback_conditions) == 5:
            dataframe.loc[reduce(lambda x, y: x & y, short_pullback_conditions), 'enter_short'] = 1
        
        short_breakout_conditions = [
            dataframe['breakout_down'],
            dataframe['strong_trend'],
            dataframe['price_below_hma'],
            dataframe['stoch_falling']
        ]
        if len(short_breakout_conditions) == 4:
            dataframe.loc[reduce(lambda x, y: x & y, short_breakout_conditions), 'enter_short'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Safe exit conditions"""
        def safe_trend_1h(): return dataframe.get('trend_1h', pd.Series(0, index=dataframe.index))
        
        # Exit long
        exit_long_conditions = [
            dataframe['downtrend'],
            (dataframe['stoch_k'] < 30) & ~dataframe['ha_bull'],
            (dataframe['macd_cross_down'] & (dataframe['rsi'] < 50)),
            ((dataframe['close'] < dataframe['ema_medium']) & 
             (dataframe['stoch_overbought'] | (dataframe['momentum'] < -0.015)))
        ]
        
        # Exit short
        exit_short_conditions = [
            dataframe['uptrend'],
            (dataframe['stoch_k'] > 70) & ~dataframe['ha_bear'],
            (dataframe['macd_cross_up'] & (dataframe['rsi'] > 50)),
            ((dataframe['close'] > dataframe['ema_medium']) & 
             (dataframe['stoch_oversold'] | (dataframe['momentum'] > 0.015)))
        ]
        
        if exit_long_conditions:
            dataframe.loc[reduce(lambda x, y: x | y, exit_long_conditions), 'exit_long'] = 1
        if exit_short_conditions:
            dataframe.loc[reduce(lambda x, y: x | y, exit_short_conditions), 'exit_short'] = 1

        return dataframe
    
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        return self.leverage_long.value if side == 'long' else self.leverage_short.value

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                       current_rate: float, current_profit: float,
                       after_fill: bool, **kwargs) -> Optional[float]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        
        last_candle = dataframe.iloc[-1]
        atr = last_candle.get('atr', 0)
        bb_width = last_candle.get('bb_width', 0)
        
        if atr > 0:
            atr_stop = atr * self.atr_multiplier.value / current_rate
            multiplier = 1.5 if bb_width > 0.15 else 1.0
            adjusted_stop = max(-min(atr_stop * multiplier, 0.08), self.stoploss)
            
            if current_profit > 0.10:
                return -0.02
            elif current_profit > 0.05:
                return -0.03
            return adjusted_stop
        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return False
        
        last_candle = dataframe.iloc[-1]
        
        if last_candle.get('bb_width', 0) < 0.008:
            return False
        if last_candle.get('volume', 0) < last_candle.get('volume_ma', 1) * 0.6:
            return False
        
        if side == 'long':
            if last_candle.get('stoch_k', 50) > 75 or last_candle.get('rsi', 50) > 70:
                return False
        elif side == 'short':
            if last_candle.get('stoch_k', 50) < 25 or last_candle.get('rsi', 50) < 30:
                return False
        
        # Use 5m HMA as micro-trend proxy
        micro_trend = 1 if last_candle.get('price_above_hma', False) else -1
        if micro_trend < 0 and side == 'long':
            return False
        if micro_trend > 0 and side == 'short':
            return False
        
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, 
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        
        last_candle = dataframe.iloc[-1]
        
        if trade.is_short:
            if last_candle.get('momentum', 0) > 0.03 and last_candle.get('stoch_k', 50) > 65:
                return 'momentum_reversal'
        else:
            if last_candle.get('momentum', 0) < -0.03 and last_candle.get('stoch_k', 50) < 35:
                return 'momentum_reversal'
        
        if trade.is_short and last_candle.get('uptrend', False):
            return 'trend_change'
        elif not trade.is_short and last_candle.get('downtrend', False):
            return 'trend_change'
        
        return None
