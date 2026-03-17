from functools import reduce
from datetime import datetime, timedelta
from typing import Optional, Dict
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class future66b(IStrategy):
    """
    SCALPING STRATEGY with Per-Coin FreqAI Parameters
    
    Features:
    - Per-coin optimizable parameters (leverage, thresholds, etc.)
    - Swing high/low detection for precise entries
    - 24h price position filter
    - FreqAI integration for ML-based filtering
    - Loss cooldown per pair
    """
    
    # FreqAI enabled
    process_only_new_candles = True
    use_exit_signal = False  # Disabled - let ROI and trailing stops work
    startup_candle_count = 300
    can_short = True
    can_long = True
    
    timeframe = '5m'
    
    # Default ROI
    minimal_roi = {
        "0": 0.06,
        "20": 0.05,
        "50": 0.03,
        "80": 0.02,
        "100": 0.01,
        "150": 0.005,
        "240": -0.01,
    }
    
    stoploss = -0.025
    
    trailing_stop = True
    trailing_stop_positive = 0.012
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True
    
    max_open_trades = 10
    
    # ==========================================
    # DEFAULT PARAMETERS (used when coin-specific not available)
    # ==========================================
    
    # Leverage
    leverage_long_default = IntParameter(3, 8, default=4, space="buy", optimize=True)
    leverage_short_default = IntParameter(3, 8, default=5, space="sell", optimize=True)
    
    # Swing detection - larger values = fewer, bigger swings
    swing_period_default = IntParameter(4, 10, default=6, space="both", optimize=True)
    
    # RSI thresholds
    rsi_ob_default = IntParameter(60, 80, default=68, space="sell", optimize=True)
    rsi_os_default = IntParameter(20, 40, default=32, space="buy", optimize=True)
    
    # 24h position thresholds
    position_high_default = IntParameter(75, 95, default=85, space="buy", optimize=True)
    position_low_default = IntParameter(5, 25, default=15, space="sell", optimize=True)
    
    # ML confidence
    ml_long_conf_default = DecimalParameter(0.5, 0.8, default=0.6, space="buy", optimize=True)
    ml_short_conf_default = DecimalParameter(0.5, 0.8, default=0.6, space="sell", optimize=True)
    
    # Stoploss
    stoploss_default = DecimalParameter(0.05, 0.15, default=0.08, space="sell", optimize=True)
    
    # Trailing stop
    ts_positive_default = DecimalParameter(0.008, 0.02, default=0.012, space="sell", optimize=True)
    ts_offset_default = DecimalParameter(0.015, 0.04, default=0.02, space="sell", optimize=True)
    
    # ROI parameters
    roi_t1_default = IntParameter(10, 30, default=15, space="roi", optimize=True)
    roi_t2_default = IntParameter(30, 60, default=45, space="roi", optimize=True)
    roi_t3_default = IntParameter(60, 120, default=90, space="roi", optimize=True)
    roi_p1_default = DecimalParameter(0.03, 0.10, default=0.08, space="roi", optimize=True)
    roi_p2_default = DecimalParameter(0.02, 0.06, default=0.05, space="roi", optimize=True)
    roi_p3_default = DecimalParameter(0.01, 0.03, default=0.02, space="roi", optimize=True)

    def __init__(self, config: dict) -> None:
        """Initialize strategy with per-coin parameters"""
        super().__init__(config)
        self.dp = None
        
        # Track loss times for cooldown
        self.last_loss_time = defaultdict(lambda: datetime.min)
        
        # Get coins from whitelist
        self.coins = []
        if 'exchange' in config and 'pair_whitelist' in config['exchange']:
            for pair in config['exchange']['pair_whitelist']:
                coin = pair.split('/')[0]
                if coin not in self.coins:
                    self.coins.append(coin)
        
        # Create per-coin parameters
        for coin in self.coins:
            self._create_coin_parameters(coin)
    
    def _create_coin_parameters(self, coin: str):
        """Create all parameters for a specific coin"""
        
        # Leverage
        setattr(self, f"{coin}_leverage_long",
                IntParameter(3, 8, default=4, space="buy", optimize=True))
        setattr(self, f"{coin}_leverage_short",
                IntParameter(3, 8, default=5, space="sell", optimize=True))
        
        # Swing period - larger = fewer signals
        setattr(self, f"{coin}_swing_period",
                IntParameter(4, 10, default=6, space="both", optimize=True))
        
        # RSI thresholds
        setattr(self, f"{coin}_rsi_ob",
                IntParameter(60, 80, default=68, space="sell", optimize=True))
        setattr(self, f"{coin}_rsi_os",
                IntParameter(20, 40, default=32, space="buy", optimize=True))
        
        # 24h position thresholds
        setattr(self, f"{coin}_position_high",
                IntParameter(75, 95, default=85, space="buy", optimize=True))
        setattr(self, f"{coin}_position_low",
                IntParameter(5, 25, default=15, space="sell", optimize=True))
        
        # ML confidence
        setattr(self, f"{coin}_ml_long_conf",
                DecimalParameter(0.5, 0.8, default=0.6, space="buy", optimize=True))
        setattr(self, f"{coin}_ml_short_conf",
                DecimalParameter(0.5, 0.8, default=0.6, space="sell", optimize=True))
        
        # Stoploss
        setattr(self, f"{coin}_stoploss",
                DecimalParameter(0.05, 0.15, default=0.08, space="sell", optimize=True))
        
        # Trailing stop
        setattr(self, f"{coin}_ts_positive",
                DecimalParameter(0.008, 0.02, default=0.012, space="sell", optimize=True))
        setattr(self, f"{coin}_ts_offset",
                DecimalParameter(0.015, 0.04, default=0.02, space="sell", optimize=True))
        
        # ROI
        setattr(self, f"{coin}_roi_t1",
                IntParameter(10, 30, default=15, space="roi", optimize=True))
        setattr(self, f"{coin}_roi_t2",
                IntParameter(30, 60, default=45, space="roi", optimize=True))
        setattr(self, f"{coin}_roi_t3",
                IntParameter(60, 120, default=90, space="roi", optimize=True))
        setattr(self, f"{coin}_roi_p1",
                DecimalParameter(0.03, 0.10, default=0.08, space="roi", optimize=True))
        setattr(self, f"{coin}_roi_p2",
                DecimalParameter(0.02, 0.06, default=0.05, space="roi", optimize=True))
        setattr(self, f"{coin}_roi_p3",
                DecimalParameter(0.01, 0.03, default=0.02, space="roi", optimize=True))

    def get_coin_param(self, coin: str, param_name: str, default_value=None):
        """Get coin-specific parameter or fall back to default"""
        coin_param = f"{coin}_{param_name}"
        if hasattr(self, coin_param):
            param = getattr(self, coin_param)
            return param.value if hasattr(param, 'value') else param
        
        # Fallback to default
        default_param = f"{param_name}_default"
        if hasattr(self, default_param):
            param = getattr(self, default_param)
            return param.value if hasattr(param, 'value') else param
        
        return default_value

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
        
        dataframe[f'%-roc_{period}'] = (
            (dataframe['close'] - dataframe['close'].shift(period)) / 
            dataframe['close'].shift(period) * 100
        )
        
        dataframe[f'%-rsi_{period}'] = ta.RSI(dataframe, timeperiod=period)
        
        dataframe[f'%-ema_{period}'] = ta.EMA(dataframe, timeperiod=period)
        dataframe[f'%-dist_ema_{period}'] = (
            (dataframe['close'] - dataframe[f'%-ema_{period}']) / 
            dataframe['close'] * 100
        )
        
        dataframe[f'%-atr_{period}'] = ta.ATR(dataframe, timeperiod=period)
        dataframe[f'%-atr_pct_{period}'] = dataframe[f'%-atr_{period}'] / dataframe['close'] * 100
        
        bb = ta.BBANDS(dataframe, timeperiod=period, nbdevup=2.0, nbdevdn=2.0)
        dataframe[f'%-bb_pos_{period}'] = (
            (dataframe['close'] - bb['lowerband']) / 
            (bb['upperband'] - bb['lowerband']) * 100
        )
        
        dataframe[f'%-vol_ratio_{period}'] = (
            dataframe['volume'] / dataframe['volume'].rolling(period).mean()
        )
        
        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """Basic ML features"""
        
        dataframe['%-hour'] = dataframe['date'].dt.hour
        dataframe['%-dayofweek'] = dataframe['date'].dt.dayofweek
        
        dataframe['%-body_pct'] = abs(dataframe['close'] - dataframe['open']) / dataframe['close'] * 100
        dataframe['%-upper_wick'] = (dataframe['high'] - dataframe[['open', 'close']].max(axis=1)) / dataframe['close'] * 100
        dataframe['%-lower_wick'] = (dataframe[['open', 'close']].min(axis=1) - dataframe['low']) / dataframe['close'] * 100
        
        dataframe['%-consec_green'] = (dataframe['close'] > dataframe['open']).rolling(5).sum()
        dataframe['%-consec_red'] = (dataframe['close'] < dataframe['open']).rolling(5).sum()
        
        # 24h price position
        candles_24h = 288
        high_24h = dataframe['high'].rolling(window=candles_24h).max()
        low_24h = dataframe['low'].rolling(window=candles_24h).min()
        range_24h = high_24h - low_24h
        dataframe['%-position_24h'] = (dataframe['close'] - low_24h) / range_24h * 100
        
        # 12h momentum
        dataframe['%-momentum_12h'] = (
            (dataframe['close'] - dataframe['close'].shift(144)) / 
            dataframe['close'].shift(144) * 100
        )
        
        return dataframe

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """Standard indicators"""
        dataframe = self.populate_core_indicators(dataframe, metadata)
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """Define ML prediction targets"""
        
        dataframe['future_5'] = (dataframe['close'].shift(-5) - dataframe['close']) / dataframe['close'] * 100
        dataframe['future_10'] = (dataframe['close'].shift(-10) - dataframe['close']) / dataframe['close'] * 100
        dataframe['future_20'] = (dataframe['close'].shift(-20) - dataframe['close']) / dataframe['close'] * 100
        
        dataframe['&-long_target'] = (
            (dataframe['future_5'] > 1.0) |
            (dataframe['future_10'] > 1.5) |
            (dataframe['future_20'] > 2.0)
        ).astype(int)
        
        dataframe['&-short_target'] = (
            (dataframe['future_5'] < -1.0) |
            (dataframe['future_10'] < -1.5) |
            (dataframe['future_20'] < -2.0)
        ).astype(int)
        
        dataframe.drop(columns=['future_5', 'future_10', 'future_20'], inplace=True, errors='ignore')
        
        return dataframe

    # ==========================================
    # Core Indicators
    # ==========================================
    
    def populate_core_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all indicators"""
        
        coin = metadata['pair'].split('/')[0]
        period = self.get_coin_param(coin, 'swing_period', 5)
        
        # ============================================
        # SWING DETECTION - More Strict
        # ============================================
        
        # Use larger window for more significant swings
        dataframe['local_high'] = dataframe['high'].rolling(window=period*2+1, center=True).max()
        dataframe['is_swing_high'] = dataframe['high'] == dataframe['local_high']
        
        dataframe['local_low'] = dataframe['low'].rolling(window=period*2+1, center=True).min()
        dataframe['is_swing_low'] = dataframe['low'] == dataframe['local_low']
        
        # Require significant price movement from swing point (at least 0.5% move)
        dataframe['swing_high_passed'] = (
            dataframe['is_swing_high'].shift(period) &
            (dataframe['high'] < dataframe['high'].shift(period)) &
            (dataframe['high'].shift(1) < dataframe['high'].shift(period)) &
            (dataframe['high'].shift(2) < dataframe['high'].shift(period)) &  # 3 lower highs
            ((dataframe['high'].shift(period) - dataframe['close']) / dataframe['close'] > 0.003)  # Dropped at least 0.3%
        )
        
        dataframe['swing_low_passed'] = (
            dataframe['is_swing_low'].shift(period) &
            (dataframe['low'] > dataframe['low'].shift(period)) &
            (dataframe['low'].shift(1) > dataframe['low'].shift(period)) &
            (dataframe['low'].shift(2) > dataframe['low'].shift(period)) &  # 3 higher lows
            ((dataframe['close'] - dataframe['low'].shift(period)) / dataframe['close'] > 0.003)  # Rose at least 0.3%
        )
        
        # ============================================
        # REVERSAL PATTERNS - Stricter
        # ============================================
        
        # Bearish reversal: After clear upward move, strong red candle
        dataframe['up_move'] = (
            (dataframe['close'].shift(1) > dataframe['close'].shift(3)) &
            (dataframe['close'].shift(2) > dataframe['close'].shift(4)) &
            (dataframe['close'].shift(1) > dataframe['close'].shift(2))  # Consecutive up
        )
        dataframe['strong_red'] = (
            (dataframe['close'] < dataframe['open']) &
            ((dataframe['open'] - dataframe['close']) > (dataframe['high'] - dataframe['low']) * 0.65) &  # 65% body
            (dataframe['close'] < dataframe['low'].shift(1))  # Closes below previous low
        )
        dataframe['bearish_reversal'] = dataframe['up_move'] & dataframe['strong_red']
        
        # Bullish reversal: After clear downward move, strong green candle
        dataframe['down_move'] = (
            (dataframe['close'].shift(1) < dataframe['close'].shift(3)) &
            (dataframe['close'].shift(2) < dataframe['close'].shift(4)) &
            (dataframe['close'].shift(1) < dataframe['close'].shift(2))  # Consecutive down
        )
        dataframe['strong_green'] = (
            (dataframe['close'] > dataframe['open']) &
            ((dataframe['close'] - dataframe['open']) > (dataframe['high'] - dataframe['low']) * 0.65) &  # 65% body
            (dataframe['close'] > dataframe['high'].shift(1))  # Closes above previous high
        )
        dataframe['bullish_reversal'] = dataframe['down_move'] & dataframe['strong_green']
        
        # Engulfing patterns - must be significant
        dataframe['bearish_engulf'] = (
            (dataframe['close'].shift(1) > dataframe['open'].shift(1)) &  # Prev green
            (dataframe['close'] < dataframe['open']) &  # Current red
            (dataframe['open'] >= dataframe['close'].shift(1)) &
            (dataframe['close'] <= dataframe['open'].shift(1)) &
            ((dataframe['open'] - dataframe['close']) > (dataframe['close'].shift(1) - dataframe['open'].shift(1)) * 1.2)  # Bigger than prev
        )
        
        dataframe['bullish_engulf'] = (
            (dataframe['close'].shift(1) < dataframe['open'].shift(1)) &  # Prev red
            (dataframe['close'] > dataframe['open']) &  # Current green
            (dataframe['open'] <= dataframe['close'].shift(1)) &
            (dataframe['close'] >= dataframe['open'].shift(1)) &
            ((dataframe['close'] - dataframe['open']) > (dataframe['open'].shift(1) - dataframe['close'].shift(1)) * 1.2)  # Bigger than prev
        )
        
        # ============================================
        # RSI
        # ============================================
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
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
        
        dataframe['touch_upper'] = dataframe['high'] >= dataframe['bb_upper']
        dataframe['touch_lower'] = dataframe['low'] <= dataframe['bb_lower']
        
        # ============================================
        # VOLUME
        # ============================================
        dataframe['volume_ma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_ma']
        
        # ============================================
        # ATR
        # ============================================
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # ============================================
        # 24H PRICE POSITION
        # ============================================
        candles_24h = 288
        
        dataframe['high_24h'] = dataframe['high'].rolling(window=candles_24h).max()
        dataframe['low_24h'] = dataframe['low'].rolling(window=candles_24h).min()
        dataframe['range_24h'] = dataframe['high_24h'] - dataframe['low_24h']
        
        dataframe['position_24h'] = (
            (dataframe['close'] - dataframe['low_24h']) / 
            dataframe['range_24h'] * 100
        )
        
        # 12h momentum
        dataframe['pump_12h'] = (
            (dataframe['close'] - dataframe['close'].shift(144)) / 
            dataframe['close'].shift(144) * 100
        )
        dataframe['recent_pump'] = dataframe['pump_12h'] > 8
        dataframe['recent_dump'] = dataframe['pump_12h'] < -8
        
        # ============================================
        # HIGHER TIMEFRAMES
        # ============================================
        dataframe = self._add_htf_data(dataframe, metadata)
        
        return dataframe

    def _add_htf_data(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add higher timeframe data"""
        
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
        """Entry logic with per-coin parameters"""
        
        coin = metadata['pair'].split('/')[0]
        pair = metadata['pair']
        
        # Get coin-specific parameters
        rsi_ob = self.get_coin_param(coin, 'rsi_ob', 68)
        rsi_os = self.get_coin_param(coin, 'rsi_os', 32)
        position_high = self.get_coin_param(coin, 'position_high', 85)
        position_low = self.get_coin_param(coin, 'position_low', 15)
        ml_long_conf = self.get_coin_param(coin, 'ml_long_conf', 0.6)
        ml_short_conf = self.get_coin_param(coin, 'ml_short_conf', 0.6)
        
        # Check for FreqAI predictions
        has_ml = '&-pred_long_target' in dataframe.columns
        
        # Check cooldown
        last_loss = self.last_loss_time[pair]
        in_cooldown = False
        if last_loss > datetime.min:
            cooldown_end = last_loss + timedelta(hours=1)
            # We can't easily filter by date here, but we track it
        
        # ============================================
        # SHORT ENTRIES - Much Stricter
        # ============================================
        
        # Primary: Swing high with bearish confirmation
        short_swing_confirmed = (
            dataframe['swing_high_passed'] &
            (
                dataframe['bearish_reversal'] |
                dataframe['bearish_engulf'] |
                (dataframe['rsi'] > rsi_ob)
            )
        )
        
        # Alternative: Very strong bearish signal at resistance
        short_strong_pattern = (
            dataframe['bearish_engulf'] &
            dataframe['touch_upper'] &
            (dataframe['rsi'] > rsi_ob - 5) &
            dataframe['extended_up']
        )
        
        # Position and momentum filters
        short_filters = (
            (dataframe['position_24h'] > position_low + 10) &  # Not near 24h low (with buffer)
            (~dataframe['recent_dump']) &
            (dataframe['bb_width'] > 0.015) &
            (dataframe['volume_ratio'] > 0.5)
        )
        
        short_signal = (short_swing_confirmed | short_strong_pattern) & short_filters
        
        # ML filter
        if has_ml:
            short_signal = short_signal & (
                (dataframe['&-pred_short_target'] > ml_short_conf) |
                (dataframe['&-pred_long_target'] < 0.3)
            )
        
        dataframe.loc[short_signal, 'enter_short'] = 1
        
        # ============================================
        # LONG ENTRIES - Much Stricter
        # ============================================
        
        # Primary: Swing low with bullish confirmation
        long_swing_confirmed = (
            dataframe['swing_low_passed'] &
            (
                dataframe['bullish_reversal'] |
                dataframe['bullish_engulf'] |
                (dataframe['rsi'] < rsi_os)
            )
        )
        
        # Alternative: Very strong bullish signal at support
        long_strong_pattern = (
            dataframe['bullish_engulf'] &
            dataframe['touch_lower'] &
            (dataframe['rsi'] < rsi_os + 5) &
            dataframe['extended_down']
        )
        
        # Position and momentum filters
        long_filters = (
            (dataframe['position_24h'] < position_high - 10) &  # Not near 24h high (with buffer)
            (~dataframe['recent_pump']) &
            (dataframe['bb_width'] > 0.015) &
            (dataframe['volume_ratio'] > 0.5)
        )
        
        long_signal = (long_swing_confirmed | long_strong_pattern) & long_filters
        
        # ML filter
        if has_ml:
            long_signal = long_signal & (
                (dataframe['&-pred_long_target'] > ml_long_conf) |
                (dataframe['&-pred_short_target'] < 0.3)
            )
        
        dataframe.loc[long_signal, 'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit signals DISABLED - let ROI and trailing stops handle exits
        Too many exit signals kill profitability
        """
        # Don't set any exit signals - rely on ROI, trailing stop, and custom_exit
        return dataframe

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """Coin-specific leverage"""
        coin = pair.split('/')[0]
        
        if side == 'long':
            lev = self.get_coin_param(coin, 'leverage_long', 4)
        else:
            lev = self.get_coin_param(coin, 'leverage_short', 5)
        
        return min(float(lev), max_leverage)

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                       current_rate: float, current_profit: float,
                       after_fill: bool, **kwargs) -> Optional[float]:
        """Coin-specific stoploss with ATR adjustment"""
        
        coin = pair.split('/')[0]
        base_stoploss = self.get_coin_param(coin, 'stoploss', 0.08)
        ts_positive = self.get_coin_param(coin, 'ts_positive', 0.012)
        ts_offset = self.get_coin_param(coin, 'ts_offset', 0.02)
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return -base_stoploss
            
        last_candle = dataframe.iloc[-1]
        atr = last_candle.get('atr', 0)
        
        if atr > 0:
            atr_stop = (atr * 2.5) / current_rate
            
            # Dynamic trailing
            if current_profit > ts_offset * 2:
                return -ts_positive * 0.5
            elif current_profit > ts_offset:
                return -ts_positive
            elif current_profit > ts_offset * 0.5:
                return -ts_positive * 1.5
            else:
                return max(-min(atr_stop, base_stoploss), -base_stoploss)
        
        return -base_stoploss

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        """Entry confirmation with cooldown check"""
        
        coin = pair.split('/')[0]
        
        # Check cooldown
        last_loss = self.last_loss_time[pair]
        if last_loss > datetime.min:
            cooldown_end = last_loss + timedelta(hours=1)
            if current_time < cooldown_end:
                return False
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return False
            
        last_candle = dataframe.iloc[-1]
        
        # Basic filters
        if last_candle.get('bb_width', 0) < 0.01:
            return False
        
        if last_candle.get('volume_ratio', 0) < 0.3:
            return False
        
        # RSI sanity
        rsi = last_candle.get('rsi', 50)
        if side == 'short' and rsi < 25:
            return False
        if side == 'long' and rsi > 75:
            return False
        
        # 24h position check
        position_24h = last_candle.get('position_24h', 50)
        position_high = self.get_coin_param(coin, 'position_high', 85)
        position_low = self.get_coin_param(coin, 'position_low', 15)
        
        if side == 'long' and position_24h > position_high:
            return False
        if side == 'short' and position_24h < position_low:
            return False
        
        # HTF alignment
        trend_15m = last_candle.get('trend_15m', 0)
        if side == 'short' and trend_15m > 0 and rsi < 60:
            return False
        if side == 'long' and trend_15m < 0 and rsi > 40:
            return False
        
        return True

    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                          rate: float, time_in_force: str, exit_reason: str,
                          current_time: datetime, **kwargs) -> bool:
        """Track losses for cooldown"""
        if exit_reason == 'stop_loss' or (exit_reason == 'force_exit' and trade.calc_profit_ratio(rate) < 0):
            self.last_loss_time[pair] = current_time
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, 
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """Custom exit logic - only on strong reversal signals"""
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return None
            
        last_candle = dataframe.iloc[-1]
        
        # Only consider exits when in meaningful profit
        if current_profit < 0.015:  # Need at least 1.5% profit
            return None
        
        # Exit shorts only on confirmed swing low with strong bullish pattern
        if trade.is_short:
            if (last_candle.get('swing_low_passed', False) and 
                last_candle.get('bullish_engulf', False) and
                current_profit > 0.02):
                return 'swing_reversal'
        
        # Exit longs only on confirmed swing high with strong bearish pattern
        else:
            if (last_candle.get('swing_high_passed', False) and 
                last_candle.get('bearish_engulf', False) and
                current_profit > 0.02):
                return 'swing_reversal'
        
        # ML reversal signal with high confidence
        if '&-pred_long_target' in last_candle:
            if trade.is_short and last_candle['&-pred_long_target'] > 0.8 and current_profit > 0.02:
                return 'ml_reversal'
            elif not trade.is_short and last_candle.get('&-pred_short_target', 0) > 0.8 and current_profit > 0.02:
                return 'ml_reversal'
        
        return None
