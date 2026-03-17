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

class future63(IStrategy):
    """
    Stable future63: Conservative like future61 + mild leading signals
    - Entries: 3-4 core conditions (EMA trend + volume/RSI)
    - Exits: No exit_signal (ROI/trailing only); custom for strong reversals
    - Reduced filters; max_open_trades=3; blacklist volatile pairs
    """
    
    # Conservative config
    minimal_roi = {
        "0": 0.05,        # Higher initial to hold winners
        "30": 0.03,       
        "60": 0.02,       
        "100": 0          
    }
    
    stoploss = -0.08  # Wider for 5m volatility
    
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True
    
    # Disable signal exits
    use_exit_signal = False  # Key fix: Rely on ROI/trailing/custom only
    exit_profit_only = True  # Exit only on profit
    ignore_roi_if_entry_signal = False
    
    position_adjustment_enable = True
    max_entry_position_adjustment = 1  # Conservative adds
    
    process_only_new_candles = True
    max_open_trades = 3  # Balanced
    timeframe = '5m'
    startup_candle_count = 200
    can_short = True
    can_long = True
    
    # Blacklist poor performers from backtest
    def whitelist_for_active_trades(self, whitelists: dict[str, list[str]]) -> dict[str, list[str]]:
        whitelist = whitelists.copy()
        # Remove volatile losers
        if 'pairlist' in whitelist:
            whitelist['pairlist'] = [p for p in whitelist['pairlist'] if 'APT' not in p and 'BNB' not in p]
        return whitelist

    # --- Conservative Parameters ---
    leverage_long = IntParameter(2, 4, default=3, space="buy", optimize=True)  # Capped
    leverage_short = IntParameter(2, 4, default=3, space="sell", optimize=True)
    
    ema_fast = IntParameter(8, 15, default=12, space="both", optimize=True)  # Like future61
    ema_medium = IntParameter(20, 35, default=26, space="both", optimize=True)
    ema_slow = IntParameter(40, 70, default=50, space="both", optimize=True)
    
    volume_ma_period = IntParameter(15, 25, default=20, space="both", optimize=True)
    volume_threshold = DecimalParameter(1.2, 1.8, default=1.4, space="both", optimize=True)  # Higher for quality
    
    adx_period = IntParameter(12, 18, default=14, space="both", optimize=True)
    adx_threshold = IntParameter(22, 32, default=25, space="both", optimize=True)  # Strong trends only
    
    rsi_period = IntParameter(12, 18, default=14, space="both", optimize=True)
    rsi_bull_threshold = IntParameter(50, 60, default=55, space="buy", optimize=True)  # Mild bull
    rsi_bear_threshold = IntParameter(40, 50, default=45, space="sell", optimize=True)  # Mild bear
    
    macd_fast = IntParameter(10, 15, default=12, space="both", optimize=True)
    macd_slow = IntParameter(20, 30, default=26, space="both", optimize=True)
    macd_signal = IntParameter(7, 12, default=9, space="both", optimize=True)
    
    atr_period = IntParameter(12, 18, default=14, space="both", optimize=True)
    atr_multiplier = DecimalParameter(2.0, 3.5, default=2.5, space="both", optimize=True)  # Wider
    
    # Mild leading
    hma_period = IntParameter(8, 14, default=9, space="both", optimize=True)
    stoch_k_period = IntParameter(12, 16, default=14, space="both", optimize=True)
    stoch_d_period = IntParameter(3, 5, default=3, space="both", optimize=True)

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = [
            ("BTC/USDT:USDT", "15m"),
            ("BTC/USDT:USDT", "1h")
        ]
        for pair in pairs:
            if 'APT' not in pair and 'BNB' not in pair:  # Filter in informative
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
        
        # Mild leading: Hull MA + simple Stochastic (no extremes)
        dataframe['hma_short'] = qtpylib.hull_moving_average(dataframe['close'], window=self.hma_period.value)
        dataframe['price_above_hma'] = dataframe['close'] > dataframe['hma_short']
        dataframe['price_below_hma'] = dataframe['close'] < dataframe['hma_short']
        
        stoch = ta.STOCH(dataframe, fastk_period=self.stoch_k_period.value, slowk_period=self.stoch_d_period.value, slowd_period=self.stoch_d_period.value)
        dataframe['stoch_k'] = stoch['slowk']
        dataframe['stoch_d'] = stoch['slowd']
        dataframe['stoch_rising'] = dataframe['stoch_k'] > dataframe['stoch_d']
        dataframe['stoch_falling'] = dataframe['stoch_k'] < dataframe['stoch_d']
        
        # Safe merges (reduced BTC to 15m/1h only)
        dataframe = self.add_higher_tf_confirmation(dataframe, metadata)
        
        # Fallbacks
        if 'trend_1h' not in dataframe.columns:
            dataframe['trend_1h'] = 0
        if 'trend_15m' not in dataframe.columns:
            dataframe['trend_15m'] = 0
        
        return dataframe

    def add_higher_tf_confirmation(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Simplified: 15m/1h only, no BTC 5m (causes noise)
        inf_15m = self.dp.get_pair_dataframe(metadata['pair'], '15m')
        if not inf_15m.empty and len(inf_15m) > 20:
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
        
        inf_1h = self.dp.get_pair_dataframe(metadata['pair'], '1h')
        if not inf_1h.empty and len(inf_1h) > 10:
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
        def safe_trend_1h(): return dataframe.get('trend_1h', pd.Series(0, index=dataframe.index))
        def safe_trend_15m(): return dataframe.get('trend_15m', pd.Series(0, index=dataframe.index))
        
        # Long: 3 core conditions (EMA + volume + mild momentum)
        long_conditions = [
            dataframe['uptrend'] & (safe_trend_1h() >= 0),  # Strict trend alignment
            dataframe['rsi'] > self.rsi_bull_threshold.value,
            dataframe['volume_spike'],
            dataframe['macd'] > dataframe['macd_signal'],  # Momentum
            dataframe['price_above_hma']  # Mild leading
        ]
        
        # Core 3 + optional 2
        core_long = long_conditions[:3]
        optional_long = long_conditions[3:]
        base_signal = reduce(lambda x, y: x & y, core_long)
        if len(optional_long) >= 2:
            enhanced_signal = base_signal & reduce(lambda x, y: x & y, optional_long[:2])
            dataframe.loc[enhanced_signal, 'enter_long'] = 1
        else:
            dataframe.loc[base_signal, 'enter_long'] = 1
        
        # Pullback: Conservative
        long_pullback = [
            dataframe['uptrend'],
            (dataframe['close'] > dataframe['ema_fast']) & (dataframe['rsi'] < 65),  # Pullback without extremes
            dataframe['volume'] > dataframe['volume_ma'],
            safe_trend_15m() > 0
        ]
        if len(long_pullback) == 4:
            dataframe.loc[reduce(lambda x, y: x & y, long_pullback), 'enter_long'] = 1
        
        # Short: Symmetric
        short_conditions = [
            dataframe['downtrend'] & (safe_trend_1h() <= 0),
            dataframe['rsi'] < self.rsi_bear_threshold.value,
            dataframe['volume_spike'],
            dataframe['macd'] < dataframe['macd_signal'],
            dataframe['price_below_hma']
        ]
        
        core_short = short_conditions[:3]
        optional_short = short_conditions[3:]
        base_short = reduce(lambda x, y: x & y, core_short)
        if len(optional_short) >= 2:
            enhanced_short = base_short & reduce(lambda x, y: x & y, optional_short[:2])
            dataframe.loc[enhanced_short, 'enter_short'] = 1
        else:
            dataframe.loc[base_short, 'enter_short'] = 1
        
        short_pullback = [
            dataframe['downtrend'],
            (dataframe['close'] < dataframe['ema_fast']) & (dataframe['rsi'] > 35),
            dataframe['volume'] > dataframe['volume_ma'],
            safe_trend_15m() < 0
        ]
        if len(short_pullback) == 4:
            dataframe.loc[reduce(lambda x, y: x & y, short_pullback), 'enter_short'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Empty: No signal exits (use_exit_signal=False)
        # All exits via ROI/trailing/custom_stoploss
        return dataframe
    
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        # Conservative: Base only, no dynamic boost
        return self.leverage_long.value if side == 'long' else self.leverage_short.value

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                       current_rate: float, current_profit: float,
                       after_fill: bool, **kwargs) -> Optional[float]:
        # Simple ATR-based, no complex vol
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty or current_profit > 0.05:  # Trail after 5%
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
        # Minimal: Add only on strong confirmation
        if current_profit < 0.03 or trade.nr_of_successful_entries >= 1:
            return None
        
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if dataframe.empty:
            return None
        last = dataframe.iloc[-1].squeeze()
        
        # Add only if trend accelerating
        if (trade.is_short and last.get('downtrend', False) and last.get('strong_trend', False)) or \
           (not trade.is_short and last.get('uptrend', False) and last.get('strong_trend', False)):
            return max_stake * 0.25  # Small add
        
        # Partial exit conservative
        if current_profit > 0.08:
            return -(trade.stake_amount * 0.25)
        
        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return False
        last = dataframe.iloc[-1].squeeze()
        
        # Basic filters only
        if last.get('volume', 0) < last.get('volume_ma', 1) * 1.0:  # Above avg
            return False
        
        if side == 'long':
            if last.get('rsi', 50) > 75 or not last.get('price_above_hma', False):
                return False
        else:
            if last.get('rsi', 50) < 25 or not last.get('price_below_hma', False):
                return False
        
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, 
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        # Only strong reversals (>2% momentum shift)
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        last = dataframe.iloc[-1].squeeze()
        
        # Strong momentum reversal only
        if trade.is_short:
            if last.get('momentum', 0) > 0.02 and last.get('stoch_falling', False) == False:  # Clear bull shift
                return 'strong_reversal'
        else:
            if last.get('momentum', 0) < -0.02 and last.get('stoch_rising', False) == False:
                return 'strong_reversal'
        
        # Trend break only if opposite EMA alignment
        if trade.is_short and last.get('uptrend', False) and current_profit > 0.01:
            return 'trend_break_profit'
        elif not trade.is_short and last.get('downtrend', False) and current_profit > 0.01:
            return 'trend_break_profit'
        
        return None
