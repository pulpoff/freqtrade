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
from freqtrade.strategy.parameters import IntParameter, DecimalParameter

class future64(IStrategy):
    """
    Stable simplification: future61 core + mild Hull MA leading
    - Entries: 3 core conditions (EMA + volume + RSI)
    - No exit_signal (ROI/trailing only); custom for strong reversals
    - Wider stops, max_open_trades=4, blacklist volatiles
    """
    
    # Conservative ROI (hold winners longer)
    minimal_roi = {
        "0": 0.04,        
        "30": 0.03,       
        "60": 0.02,       
        "120": 0.01,      
        "180": 0,
        "320": -0.05
    }
    
    stoploss = -0.08  # Wider for 5m noise
    
    trailing_stop = True
    trailing_stop_positive = 0.025  # Looser trail
    trailing_stop_positive_offset = 0.05
    trailing_only_offset_is_reached = True
    
    # Key: No signal exits
    use_exit_signal = False
    exit_profit_only = True
    ignore_roi_if_entry_signal = False
    
    position_adjustment_enable = True
    max_entry_position_adjustment = 1
    
    process_only_new_candles = True
    max_open_trades = 4
    timeframe = '5m'
    startup_candle_count = 250  # More for stability
    can_short = True
    can_long = True

    # Blacklist volatiles from backtests
    def whitelist_for_active_trades(self, whitelists: dict[str, list[str]]) -> dict[str, list[str]]:
        whitelist = whitelists.copy()
        if 'pairlist' in whitelist:
            # Exclude poor performers
            whitelist['pairlist'] = [p for p in whitelist['pairlist'] 
                                   if 'APT' not in p and 'BNB' not in p]
        return whitelist

    # --- Conservative Parameters ---
    leverage_long = IntParameter(2, 4, default=3, space="buy", optimize=True)
    leverage_short = IntParameter(2, 4, default=3, space="sell", optimize=True)
    
    # Like future61
    ema_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    ema_medium = IntParameter(20, 40, default=26, space="both", optimize=True)
    ema_slow = IntParameter(40, 80, default=50, space="both", optimize=True)
    
    volume_ma_period = IntParameter(15, 25, default=20, space="both", optimize=True)
    volume_threshold = DecimalParameter(1.3, 2.0, default=1.5, space="both", optimize=True)  # Quality volume
    
    adx_period = IntParameter(12, 18, default=14, space="both", optimize=True)
    adx_threshold = IntParameter(22, 35, default=28, space="both", optimize=True)  # Strong only
    
    rsi_period = IntParameter(12, 18, default=14, space="both", optimize=True)
    rsi_bull_threshold = IntParameter(50, 65, default=55, space="buy", optimize=True)
    rsi_bear_threshold = IntParameter(35, 50, default=45, space="sell", optimize=True)
    
    macd_fast = IntParameter(10, 15, default=12, space="both", optimize=True)
    macd_slow = IntParameter(20, 30, default=26, space="both", optimize=True)
    macd_signal = IntParameter(7, 12, default=9, space="both", optimize=True)
    
    atr_period = IntParameter(12, 20, default=14, space="both", optimize=True)
    atr_multiplier = DecimalParameter(2.5, 4.0, default=3.0, space="both", optimize=True)  # Wider
    
    # Mild leading only
    hma_period = IntParameter(8, 14, default=9, space="both", optimize=True)

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [("BTC/USDT:USDT", "15m"), ("BTC/USDT:USDT", "1h")]
        for pair in pairs:
            if 'APT' not in pair and 'BNB' not in pair:
                informative_pairs.extend([(pair, "15m"), (pair, "1h")])
        return informative_pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Core future61 indicators
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe['ema_medium'] = ta.EMA(dataframe, timeperiod=self.ema_medium.value)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.ema_slow.value)
        
        dataframe['uptrend'] = (
            (dataframe['ema_fast'] > dataframe['ema_medium']) & 
            (dataframe['ema_medium'] > dataframe['ema_slow'])
        )
        dataframe['downtrend'] = (
            (dataframe['ema_fast'] < dataframe['ema_medium']) & 
            (dataframe['ema_medium'] < dataframe['ema_slow'])
        )
        
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=self.adx_period.value)
        dataframe['strong_trend'] = dataframe['adx'] > self.adx_threshold.value
        
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        
        macd = ta.MACD(dataframe, fastperiod=self.macd_fast.value, slowperiod=self.macd_slow.value, signalperiod=self.macd_signal.value)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_cross_up'] = qtpylib.crossed_above(dataframe['macd'], dataframe['macd_signal'])
        dataframe['macd_cross_down'] = qtpylib.crossed_below(dataframe['macd'], dataframe['macd_signal'])
        
        dataframe['volume_ma'] = ta.SMA(dataframe['volume'], timeperiod=self.volume_ma_period.value)
        dataframe['volume_spike'] = dataframe['volume'] > (dataframe['volume_ma'] * self.volume_threshold.value)
        
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=self.atr_period.value)
        dataframe['momentum'] = dataframe['close'].pct_change(periods=10)
        
        # Mild Hull MA leading
        dataframe['hma_short'] = qtpylib.hull_moving_average(dataframe['close'], window=self.hma_period.value)
        dataframe['price_above_hma'] = dataframe['close'] > dataframe['hma_short']
        dataframe['price_below_hma'] = dataframe['close'] < dataframe['hma_short']
        
        # Safe merges (15m/1h only)
        dataframe = self.add_higher_tf_confirmation(dataframe, metadata)
        
        # Fallbacks
        dataframe['trend_1h'] = dataframe.get('trend_1h', pd.Series(0, index=dataframe.index))
        dataframe['trend_15m'] = dataframe.get('trend_15m', pd.Series(0, index=dataframe.index))
        
        return dataframe

    def add_higher_tf_confirmation(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 15m
        inf_15m = self.dp.get_pair_dataframe(metadata['pair'], '15m')
        if not inf_15m.empty and len(inf_15m) > 30:
            inf_15m['ema_fast_15m'] = ta.EMA(inf_15m, timeperiod=self.ema_fast.value)
            inf_15m['ema_slow_15m'] = ta.EMA(inf_15m, timeperiod=self.ema_slow.value)
            inf_15m['trend_15m'] = np.where(inf_15m['ema_fast_15m'] > inf_15m['ema_slow_15m'], 1, -1)
            try:
                dataframe = merge_informative_pair(dataframe, inf_15m[['date', 'trend_15m']], self.timeframe, '15m', ffill=True)
                if 'trend_15m_15m' in dataframe.columns:
                    dataframe['trend_15m'] = dataframe['trend_15m_15m']
            except Exception:
                pass
        else:
            dataframe['trend_15m'] = 0
        
        # 1h
        inf_1h = self.dp.get_pair_dataframe(metadata['pair'], '1h')
        if not inf_1h.empty and len(inf_1h) > 15:
            inf_1h['ema_fast_1h'] = ta.EMA(inf_1h, timeperiod=self.ema_fast.value)
            inf_1h['ema_slow_1h'] = ta.EMA(inf_1h, timeperiod=self.ema_slow.value)
            inf_1h['trend_1h'] = np.where(inf_1h['ema_fast_1h'] > inf_1h['ema_slow_1h'], 1, -1)
            try:
                dataframe = merge_informative_pair(dataframe, inf_1h[['date', 'trend_1h']], self.timeframe, '1h', ffill=True)
                if 'trend_1h_1h' in dataframe.columns:
                    dataframe['trend_1h'] = dataframe['trend_1h_1h']
            except Exception:
                pass
        else:
            dataframe['trend_1h'] = 0
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Safe access
        def safe_trend_1h(): return dataframe.get('trend_1h', pd.Series(0, index=dataframe.index))
        
        # Long: 3 core conditions
        long_core = [
            dataframe['uptrend'] & (safe_trend_1h() >= 0),  # EMA trend + 1h bias
            dataframe['volume_spike'],  # Quality volume
            dataframe['rsi'] > self.rsi_bull_threshold.value  # Momentum
        ]
        
        # Optional leading (mild)
        long_optional = [
            dataframe['price_above_hma'],  # Hull MA
            dataframe['macd'] > dataframe['macd_signal']  # MACD
        ]
        
        # Base entry (3 core)
        base_long = reduce(lambda x, y: x & y, long_core)
        dataframe.loc[base_long, 'enter_long'] = 1
        
        # Enhanced (3 core + 1 optional)
        if len(long_optional) > 0:
            enhanced_long = base_long & long_optional[0]
            dataframe.loc[enhanced_long, 'enter_long'] = 1
        
        # Pullback: Conservative 4 conditions
        long_pullback = [
            dataframe['uptrend'],
            (dataframe['rsi'] > 45) & (dataframe['rsi'] < 65),  # Neutral pullback
            dataframe['volume'] > dataframe['volume_ma'] * 1.1,  # Above avg
            safe_trend_1h() > 0
        ]
        if len(long_pullback) == 4:
            dataframe.loc[reduce(lambda x, y: x & y, long_pullback), 'enter_long'] = 1
        
        # Short: Symmetric
        short_core = [
            dataframe['downtrend'] & (safe_trend_1h() <= 0),
            dataframe['volume_spike'],
            dataframe['rsi'] < self.rsi_bear_threshold.value
        ]
        
        base_short = reduce(lambda x, y: x & y, short_core)
        dataframe.loc[base_short, 'enter_short'] = 1
        
        short_optional = [
            dataframe['price_below_hma'],
            dataframe['macd'] < dataframe['macd_signal']
        ]
        
        if len(short_optional) > 0:
            enhanced_short = base_short & short_optional[0]
            dataframe.loc[enhanced_short, 'enter_short'] = 1
        
        short_pullback = [
            dataframe['downtrend'],
            (dataframe['rsi'] < 55) & (dataframe['rsi'] > 35),
            dataframe['volume'] > dataframe['volume_ma'] * 1.1,
            safe_trend_1h() < 0
        ]
        if len(short_pullback) == 4:
            dataframe.loc[reduce(lambda x, y: x & y, short_pullback), 'enter_short'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Empty: No signal exits
        return dataframe
    
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        # Fixed conservative
        return self.leverage_long.value if side == 'long' else self.leverage_short.value

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                       current_rate: float, current_profit: float,
                       after_fill: bool, **kwargs) -> Optional[float]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty or current_profit > 0.04:  # Trail after 4%
            return None
        
        last = dataframe.iloc[-1].squeeze()
        atr = last.get('atr', 0)
        if atr > 0:
            stop = - (atr * self.atr_multiplier.value / current_rate)
            return max(stop, self.stoploss)
        return None

    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: Optional[float], max_stake: float, **kwargs) -> Optional[float]:
        # Conservative: Add only on strong trend
        if current_profit < 0.04 or trade.nr_of_successful_entries >= 1:
            return None
        
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if dataframe.empty:
            return None
        last = dataframe.iloc[-1].squeeze()
        
        if ((trade.is_short and last.get('downtrend', False) and last.get('strong_trend', False)) or
            (not trade.is_short and last.get('uptrend', False) and last.get('strong_trend', False))):
            return max_stake * 0.2  # Small add
        
        # Partial only at higher profit
        if current_profit > 0.10:
            return -(trade.stake_amount * 0.25)
        
        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return False
        last = dataframe.iloc[-1].squeeze()
        
        # Basic quality filters
        if last.get('volume', 0) < last.get('volume_ma', 1):
            return False
        
        # Avoid extremes
        if side == 'long':
            if last.get('rsi', 50) > 75:
                return False
        else:
            if last.get('rsi', 50) < 25:
                return False
        
        # Mild leading
        if side == 'long' and not last.get('price_above_hma', False):
            return False
        if side == 'short' and not last.get('price_below_hma', False):
            return False
        
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, 
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        last = dataframe.iloc[-1].squeeze()
        
        # Only strong reversals (2%+ move)
        momentum_threshold = 0.02
        if trade.is_short:
            if last.get('momentum', 0) > momentum_threshold and not last.get('downtrend', False):
                return 'strong_reversal'
        else:
            if last.get('momentum', 0) < -momentum_threshold and not last.get('uptrend', False):
                return 'strong_reversal'
        
        return None
