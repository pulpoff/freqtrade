from functools import reduce
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
from scipy.signal import find_peaks

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter
from skopt.space import Integer, Real, Categorical, Dimension

class future55h(IStrategy):
    """
    Enhanced future55c strategy with multiple entry paths for 5-minute timeframes.
    
    LOOSENED VERSION - Multiple paths to entry:
    - Path 1: Composite score 4.0+ + RSI 60+ + uptrend
    - Path 2: Any divergence signal (RSI/MACD/OBV) + RSI 60+ 
    - Path 3: Peak detection + RSI 55+ (objective turning points)
    - Path 4: 2+ oscillators overbought + RSI 65+ + uptrend
    - Path 5: RSI 70+ overbought alone (simplest entry)
    
    Uses OR logic (entry if ANY path triggered) for reasonable trade frequency.
    Maintains multi-layer exhaustion detection framework from report.
    """
    
    minimal_roi = {
        "0": 0.05,
        "10": 0.04,
        "30": 0.02,
        "60": 0.01,
        "150": 0.005,
        "340": 0
    }

    stoploss = -0.30
    
    trailing_stop = True
    trailing_stop_positive = 0.08
    trailing_stop_positive_offset = 0.12
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    process_only_new_candles = True

    # ============= PHASE 1: Core Multi-Indicator Parameters =============
    # Williams %R exhaustion detection
    williams_r_period = IntParameter(8, 14, default=10, space="buy", optimize=True)
    williams_r_overbought = IntParameter(15, 30, default=20, space="buy", optimize=True)
    
    # RSI divergence detection
    rsi_period = IntParameter(7, 11, default=9, space="buy", optimize=True)
    rsi_overbought = IntParameter(60, 75, default=65, space="buy", optimize=True)
    rsi_divergence_lookback = IntParameter(10, 20, default=15, space="buy", optimize=True)
    
    # Stochastic oscillator
    stoch_fastk = IntParameter(7, 11, default=9, space="buy", optimize=True)
    stoch_slowk = IntParameter(1, 5, default=3, space="buy", optimize=True)
    stoch_slowd = IntParameter(1, 5, default=1, space="buy", optimize=True)
    stoch_overbought = IntParameter(75, 90, default=80, space="buy", optimize=True)
    
    # MACD divergence
    macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
    macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
    
    # Volume analysis
    volume_lookback = IntParameter(15, 30, default=20, space="buy", optimize=True)
    volume_ratio_threshold = DecimalParameter(1.1, 1.5, default=1.3, space="buy", optimize=True)
    obv_divergence_threshold = DecimalParameter(0.15, 0.25, default=0.20, space="buy", optimize=True)
    
    # ROC and momentum exhaustion
    roc_period = IntParameter(8, 14, default=12, space="buy", optimize=True)
    momentum_exhaustion_threshold = DecimalParameter(0.005, 0.015, default=0.01, space="buy", optimize=True)
    
    # Peak detection (scipy) - loosened to find more peaks
    peak_distance = IntParameter(10, 20, default=12, space="buy", optimize=True)
    peak_prominence_multiplier = DecimalParameter(0.2, 0.5, default=0.3, space="buy", optimize=True)
    
    # Composite scoring thresholds
    reversal_score_threshold = DecimalParameter(2.5, 5.0, default=4.0, space="buy", optimize=True)
    min_volume_ratio = DecimalParameter(0.8, 1.2, default=1.0, space="buy", optimize=True)
    
    # ============= PHASE 2: Multi-Timeframe Parameters =============
    use_multitimeframe = CategoricalParameter(['True', 'False'], default='True', space='buy', optimize=True)
    require_multitimeframe_confirmation = IntParameter(1, 3, default=2, space="buy", optimize=True)
    
    # 15m timeframe indicators
    rsi_15m_period = IntParameter(12, 16, default=14, space="buy", optimize=True)
    macd_15m_fast = IntParameter(10, 14, default=12, space="both", optimize=True)
    macd_15m_slow = IntParameter(22, 28, default=26, space="both", optimize=True)
    
    # 1h timeframe indicators  
    adx_1h_mature_threshold = IntParameter(45, 55, default=50, space="buy", optimize=True)
    rsi_1h_period = IntParameter(12, 16, default=14, space="buy", optimize=True)
    
    # ============= Original Parameters (maintained) =============
    leverage_param_high_vol = IntParameter(2, 5, default=3, space="buy", optimize=True)
    leverage_param_medium_vol = IntParameter(3, 6, default=4, space="buy", optimize=True)
    leverage_param_low_vol = IntParameter(4, 8, default=6, space="buy", optimize=True)
    
    buy_rsi_aggressive = IntParameter(25, 40, default=35, space="buy", optimize=True)
    buy_rsi_conservative = IntParameter(40, 55, default=47, space="buy", optimize=True)
    
    trend_strength_threshold = DecimalParameter(0.5, 0.8, default=0.65, space="buy", optimize=True)
    price_position_48h_threshold = DecimalParameter(0.15, 0.30, default=0.20, space="buy", optimize=True)
    
    strong_uptrend_threshold = DecimalParameter(0.025, 0.05, default=0.03, space="buy", optimize=True)
    uptrend_period = IntParameter(20, 40, default=30, space="buy", optimize=True)
    
    sell_rsi_upper_bear = IntParameter(65, 80, default=72, space="sell", optimize=True)
    sell_rsi_upper_bull = IntParameter(75, 90, default=82, space="sell", optimize=True)
    sell_rsi_lower = IntParameter(15, 35, default=25, space="sell", optimize=True)
    
    ema_short_period = IntParameter(5, 15, default=8, space="both", optimize=True)
    ema_long_period = IntParameter(15, 30, default=21, space="both", optimize=True)
    ema_trend_period = IntParameter(50, 100, default=75, space="both", optimize=True)
    
    price_extension_pct_conservative = DecimalParameter(0.004, 0.008, default=0.006, space="sell", optimize=True)
    price_extension_pct_aggressive = DecimalParameter(0.002, 0.006, default=0.004, space="sell", optimize=True)
    
    confluence_threshold = IntParameter(6, 10, default=8, space="buy", optimize=True)
    volume_spike_threshold = DecimalParameter(1.5, 3.0, default=2.0, space="buy", optimize=True)
    
    timeframe = '5m'
    entry_timeframe = CategoricalParameter(['5m', '15m'], default='15m', space='buy', optimize=True)
    
    startup_candle_count = 600
    can_short = True
    can_long = False

    _last_candle_seen_time = {}
    _coin_list = []
    _coin_parameters = {}
    _coin_roi = {}
    _coin_trailing_stop = {}
    _trade_start_reset_times = {}
    _coin_categories = {}
    _market_regime = "bear_high_vol"
    _regime_update_time = None
    _trend_strength_cache = {}

    COIN_CATEGORIES = {
        'high_vol': ['BTC', 'ETH', 'BNB', 'SOL', 'AVAX', 'MATIC', 'ATOM', 'FTM', 'NEAR'],
        'medium_vol': ['ADA', 'DOT', 'LINK', 'UNI', 'LTC', 'BCH', 'XLM', 'VET', 'ALGO'],
        'low_vol': ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDD', 'FRAX']
    }

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_candle_seen_time = {}
        self._coin_list = []
        self._coin_parameters = {}
        self._coin_roi = {}
        self._coin_trailing_stop = {}
        self._trade_start_reset_times = {}
        self._coin_categories = {}
        self._market_regime = "bear_high_vol"
        self._regime_update_time = None
        self._trend_strength_cache = {}
        
        if 'exchange' in config and 'pair_whitelist' in config['exchange']:
            for pair in config['exchange']['pair_whitelist']:
                coin = self.get_coin_from_pair(pair)
                if coin and coin not in self._coin_list:
                    self._coin_list.append(coin)
        
        self.initialize_coin_categories()
        self.initialize_coin_parameters()

    def informative_pairs(self):
        """Define additional timeframes to analyze (Phase 2)"""
        pairs = self.dp.current_whitelist()
        informative_pairs = [(pair, '15m') for pair in pairs]
        informative_pairs += [(pair, '1h') for pair in pairs]
        return informative_pairs
        
    def initialize_coin_categories(self):
        for category, coins in self.COIN_CATEGORIES.items():
            for coin in coins:
                self._coin_categories[coin] = category
        
    def initialize_coin_parameters(self):
        for coin in self._coin_list:
            self._coin_parameters[coin] = {}
            setattr(self, f"{coin}_leverage_param", IntParameter(1, 6, default=3, space="buy", optimize=True))
            self._coin_parameters[coin]['leverage_param'] = getattr(self, f"{coin}_leverage_param")
            setattr(self, f"{coin}_buy_rsi", IntParameter(35, 55, default=50, space="buy", optimize=True))
            self._coin_parameters[coin]['buy_rsi'] = getattr(self, f"{coin}_buy_rsi")
            setattr(self, f"{coin}_sell_rsi_upper", IntParameter(65, 85, default=75, space="sell", optimize=True))
            self._coin_parameters[coin]['sell_rsi_upper'] = getattr(self, f"{coin}_sell_rsi_upper")
            setattr(self, f"{coin}_sell_rsi_lower", IntParameter(15, 35, default=25, space="sell", optimize=True))
            self._coin_parameters[coin]['sell_rsi_lower'] = getattr(self, f"{coin}_sell_rsi_lower")
            setattr(self, f"{coin}_price_extension_pct", DecimalParameter(0.002, 0.006, default=0.003, space="sell", optimize=True))
            self._coin_parameters[coin]['price_extension_pct'] = getattr(self, f"{coin}_price_extension_pct")
            setattr(self, f"{coin}_macd_fast", IntParameter(8, 16, default=12, space="both", optimize=True))
            self._coin_parameters[coin]['macd_fast'] = getattr(self, f"{coin}_macd_fast")
            setattr(self, f"{coin}_macd_slow", IntParameter(18, 32, default=26, space="both", optimize=True))
            self._coin_parameters[coin]['macd_slow'] = getattr(self, f"{coin}_macd_slow")
            setattr(self, f"{coin}_macd_signal", IntParameter(6, 12, default=9, space="both", optimize=True))
            self._coin_parameters[coin]['macd_signal'] = getattr(self, f"{coin}_macd_signal")
            setattr(self, f"{coin}_ema_short_period", IntParameter(5, 15, default=8, space="both", optimize=True))
            self._coin_parameters[coin]['ema_short_period'] = getattr(self, f"{coin}_ema_short_period")
            setattr(self, f"{coin}_ema_long_period", IntParameter(15, 30, default=21, space="both", optimize=True))
            self._coin_parameters[coin]['ema_long_period'] = getattr(self, f"{coin}_ema_long_period")
            setattr(self, f"{coin}_ema_trend_period", IntParameter(50, 100, default=75, space="both", optimize=True))
            self._coin_parameters[coin]['ema_trend_period'] = getattr(self, f"{coin}_ema_trend_period")
            setattr(self, f"{coin}_entry_timeframe", CategoricalParameter(['5m', '15m'], default='5m', space='buy', optimize=True))
            self._coin_parameters[coin]['entry_timeframe'] = getattr(self, f"{coin}_entry_timeframe")
            setattr(self, f"{coin}_confluence_threshold", IntParameter(3, 6, default=4, space="buy", optimize=True))
            self._coin_parameters[coin]['confluence_threshold'] = getattr(self, f"{coin}_confluence_threshold")
            setattr(self, f"{coin}_volume_spike_threshold", DecimalParameter(1.5, 3.0, default=2.0, space="buy", optimize=True))
            self._coin_parameters[coin]['volume_spike_threshold'] = getattr(self, f"{coin}_volume_spike_threshold")
            self._coin_roi[coin] = {}

    def get_coin_from_pair(self, pair: str) -> Optional[str]:
        if pair and '/' in pair:
            parts = pair.split('/')
            return parts[0] if len(parts) > 0 else None
        return None

    def get_coin_category(self, coin: str) -> str:
        for category, coins in self.COIN_CATEGORIES.items():
            if coin in coins:
                return category
        return 'medium_vol'

    def get_param_value(self, coin: str, param_name: str):
        if coin in self._coin_parameters and param_name in self._coin_parameters[coin]:
            return self._coin_parameters[coin][param_name].value
        
        attr_name = f"{coin}_{param_name}"
        if hasattr(self, attr_name):
            return getattr(self, attr_name).value
        
        return None

    # ============= PHASE 1: PEAK DETECTION METHODS =============
    
    def detect_peaks_scipy(self, dataframe: DataFrame) -> DataFrame:
        """Peak detection using scipy for objective turning point identification"""
        prices = dataframe['close'].values
        
        if len(prices) < self.peak_distance.value:
            dataframe['peak_top'] = 0
            dataframe['peak_bottom'] = 0
            return dataframe
        
        try:
            # Detect tops
            peaks, _ = find_peaks(
                prices,
                distance=self.peak_distance.value,
                prominence=prices.std() * self.peak_prominence_multiplier.value
            )
            
            # Detect bottoms
            troughs, _ = find_peaks(
                -prices,
                distance=self.peak_distance.value,
                prominence=prices.std() * self.peak_prominence_multiplier.value
            )
            
            dataframe['peak_top'] = 0
            dataframe['peak_bottom'] = 0
            dataframe.loc[peaks, 'peak_top'] = 1
            dataframe.loc[troughs, 'peak_bottom'] = 1
        except Exception as e:
            dataframe['peak_top'] = 0
            dataframe['peak_bottom'] = 0
        
        return dataframe

    def calculate_divergence(self, dataframe: DataFrame) -> DataFrame:
        """
        Detect price-indicator divergences (Layer 2 exhaustion signal).
        Bearish divergence = price makes higher highs while indicator makes lower highs.
        This signals weakening momentum during continued advance.
        """
        lookback = self.rsi_divergence_lookback.value
        
        if len(dataframe) < lookback:
            dataframe['rsi_bearish_div'] = 0
            dataframe['macd_bearish_div'] = 0
            dataframe['obv_bearish_div'] = 0
            return dataframe
        
        # RSI divergence
        price_highs = dataframe['high'].rolling(lookback).max()
        rsi_highs = dataframe['rsi'].rolling(lookback).max()
        
        dataframe['rsi_bearish_div'] = (
            (dataframe['high'] >= price_highs * 0.995) &
            (dataframe['rsi'] < rsi_highs * 0.95)
        ).astype(int)
        
        # MACD histogram divergence
        if 'macdhist' in dataframe.columns:
            macd_highs = dataframe['macdhist'].rolling(lookback).max()
            dataframe['macd_bearish_div'] = (
                (dataframe['high'] >= price_highs * 0.995) &
                (dataframe['macdhist'] < macd_highs * 0.90)
            ).astype(int)
        else:
            dataframe['macd_bearish_div'] = 0
        
        # OBV divergence
        if 'obv' in dataframe.columns:
            obv_highs = dataframe['obv'].rolling(lookback).max()
            dataframe['obv_bearish_div'] = (
                (dataframe['high'] >= price_highs * 0.995) &
                (dataframe['obv'] < obv_highs * 0.95)
            ).astype(int)
        else:
            dataframe['obv_bearish_div'] = 0
        
        return dataframe

    def calculate_volume_analysis(self, dataframe: DataFrame) -> DataFrame:
        """
        Volume confirmation for exhaustion detection.
        Declining volume on successive rallies = distribution phase (Layer 2).
        """
        # Volume ratio vs moving average
        dataframe['volume_sma'] = ta.SMA(dataframe['volume'], timeperiod=self.volume_lookback.value)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_sma']
        
        # Detect volume decline patterns
        dataframe['volume_declining'] = (
            (dataframe['volume_ratio'].shift(1) > dataframe['volume_ratio']) &
            (dataframe['close'] > dataframe['close'].shift(1))
        ).astype(int)
        
        # Volume climax: sudden spike at extremes
        dataframe['volume_climax'] = (
            dataframe['volume_ratio'] > 3.0
        ).astype(int)
        
        return dataframe

    def calculate_momentum_exhaustion(self, dataframe: DataFrame) -> DataFrame:
        """
        ROC and momentum exhaustion detection.
        When ROC declines while price continues rising = exhaustion.
        """
        roc = ta.ROC(dataframe, timeperiod=self.roc_period.value)
        dataframe['roc'] = roc
        
        # Exhaustion: ROC below threshold while price makes new highs
        price_highs = dataframe['high'].rolling(15).max()
        dataframe['momentum_exhaustion'] = (
            (dataframe['high'] >= price_highs * 0.995) &
            (roc < self.momentum_exhaustion_threshold.value) &
            (roc > 0)
        ).astype(int)
        
        # ROC declining (momentum fade)
        dataframe['roc_declining'] = (
            (dataframe['roc'] < dataframe['roc'].shift(1)) &
            (dataframe['roc'].shift(1) < dataframe['roc'].shift(2))
        ).astype(int)
        
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all indicators including multi-timeframe data"""
        
        # ============= PHASE 1: Core Indicators =============
        
        # Momentum oscillators (Layer 1)
        dataframe['williams_r'] = ta.WILLR(dataframe, timeperiod=self.williams_r_period.value)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        
        stoch = ta.STOCH(
            dataframe,
            fastk_period=self.stoch_fastk.value,
            slowk_period=self.stoch_slowk.value,
            slowd_period=self.stoch_slowd.value
        )
        dataframe['stoch_k'] = stoch['slowk']
        dataframe['stoch_d'] = stoch['slowd']
        
        # MACD for divergence detection
        macd = ta.MACD(
            dataframe,
            fastperiod=self.macd_fast.value,
            slowperiod=self.macd_slow.value,
            signalperiod=self.macd_signal.value
        )
        dataframe['macd'] = macd['macd']
        dataframe['macdhist'] = macd['macdhist']
        
        # Volume analysis (Layer 2)
        dataframe['obv'] = ta.OBV(dataframe)
        dataframe = self.calculate_volume_analysis(dataframe)
        
        # Trend context
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.ema_short_period.value)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.ema_long_period.value)
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Peak detection (Layer 3)
        dataframe = self.detect_peaks_scipy(dataframe)
        
        # Divergence detection (Layer 2)
        dataframe = self.calculate_divergence(dataframe)
        
        # Momentum exhaustion (Layer 1)
        dataframe = self.calculate_momentum_exhaustion(dataframe)
        
        # ============= PHASE 2: Multi-Timeframe Indicators =============
        
        if self.use_multitimeframe.value == 'True':
            # Get 15m data
            try:
                informative_15m = self.dp.get_pair_dataframe(
                    pair=metadata['pair'],
                    timeframe='15m'
                )
                
                informative_15m['rsi_15m'] = ta.RSI(informative_15m, timeperiod=self.rsi_15m_period.value)
                
                macd_15m = ta.MACD(
                    informative_15m,
                    fastperiod=self.macd_15m_fast.value,
                    slowperiod=self.macd_15m_slow.value,
                    signalperiod=self.macd_signal.value
                )
                informative_15m['macd_15m'] = macd_15m['macd']
                informative_15m['macdhist_15m'] = macd_15m['macdhist']
                informative_15m['adx_15m'] = ta.ADX(informative_15m, timeperiod=14)
                
                dataframe = merge_informative_pair(
                    dataframe, informative_15m, self.timeframe, '15m', ffill=True
                )
            except Exception as e:
                pass
            
            # Get 1h data
            try:
                informative_1h = self.dp.get_pair_dataframe(
                    pair=metadata['pair'],
                    timeframe='1h'
                )
                
                informative_1h['rsi_1h'] = ta.RSI(informative_1h, timeperiod=self.rsi_1h_period.value)
                informative_1h['adx_1h'] = ta.ADX(informative_1h, timeperiod=14)
                informative_1h['ema50_1h'] = ta.EMA(informative_1h, timeperiod=50)
                
                dataframe = merge_informative_pair(
                    dataframe, informative_1h, self.timeframe, '1h', ffill=True
                )
            except Exception as e:
                pass
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry logic using composite exhaustion scoring - LOOSENED VERSION.
        Multiple paths to entry to allow reasonable trade frequency.
        """
        
        # Initialize reversal score (max ~12.5 points)
        dataframe['reversal_score'] = 0.0
        
        # ============= LAYER 1: Momentum Oscillator Signals (max 3 points) =============
        
        # Williams %R overbought
        dataframe.loc[
            dataframe['williams_r'] > -self.williams_r_overbought.value,
            'reversal_score'
        ] += 1.0
        
        # RSI overbought
        dataframe.loc[
            dataframe['rsi'] > self.rsi_overbought.value,
            'reversal_score'
        ] += 1.0
        
        # Stochastic overbought
        dataframe.loc[
            dataframe['stoch_k'] > self.stoch_overbought.value,
            'reversal_score'
        ] += 1.0
        
        # ============= LAYER 2: Divergence Signals (max 4.5 points - highest weight) =============
        
        # RSI bearish divergence (strongest signal)
        dataframe.loc[
            dataframe['rsi_bearish_div'] == 1,
            'reversal_score'
        ] += 1.5
        
        # MACD bearish divergence
        dataframe.loc[
            dataframe['macd_bearish_div'] == 1,
            'reversal_score'
        ] += 1.5
        
        # OBV bearish divergence
        dataframe.loc[
            dataframe['obv_bearish_div'] == 1,
            'reversal_score'
        ] += 1.5
        
        # ============= LAYER 3: Volume Confirmation (max 3 points) =============
        
        volume_ratio = dataframe['volume'] / dataframe['volume_sma']
        
        # High volume confirmation (loosened: any volume above SMA)
        dataframe.loc[
            volume_ratio > 1.0,
            'reversal_score'
        ] += 1.0
        
        # Declining volume on continued advance (distribution)
        dataframe.loc[
            dataframe['volume_declining'] == 1,
            'reversal_score'
        ] += 1.0
        
        # Volume climax detection (blow-off top)
        dataframe.loc[
            dataframe['volume_climax'] == 1,
            'reversal_score'
        ] += 1.0
        
        # ============= LAYER 4: Peak Detection & Momentum Exhaustion (max 3.5 points) =============
        
        # Peak detection (scipy - objective turning points)
        dataframe.loc[
            dataframe['peak_top'] == 1,
            'reversal_score'
        ] += 2.0
        
        # Momentum exhaustion (ROC declining despite higher price)
        dataframe.loc[
            dataframe['momentum_exhaustion'] == 1,
            'reversal_score'
        ] += 0.75
        
        # ROC declining (momentum fade)
        dataframe.loc[
            dataframe['roc_declining'] == 1,
            'reversal_score'
        ] += 0.75
        
        # ============= MULTI-TIMEFRAME CONFIRMATION (Phase 2) - OPTIONAL =============
        
        if self.use_multitimeframe.value == 'True':
            # Check 15m confirmation
            if 'rsi_15m' in dataframe.columns:
                mtf_15m_confirm = (
                    (dataframe['rsi_15m'] > 65) &
                    (dataframe['macdhist_15m'] < dataframe['macdhist_15m'].shift(1))
                )
                dataframe['mtf_15m_confirm'] = mtf_15m_confirm.astype(int)
            else:
                dataframe['mtf_15m_confirm'] = 0
                
            # Check 1h confirmation  
            if 'rsi_1h' in dataframe.columns:
                mtf_1h_confirm = (
                    (dataframe['rsi_1h'] > 60) &
                    (dataframe['adx_1h'] > self.adx_1h_mature_threshold.value)
                )
                dataframe['mtf_1h_confirm'] = mtf_1h_confirm.astype(int)
            else:
                dataframe['mtf_1h_confirm'] = 0
        else:
            dataframe['mtf_15m_confirm'] = 1  # Disabled = always true
            dataframe['mtf_1h_confirm'] = 1
        
        # ============= SHORT ENTRY - MULTIPLE PATHS (OR LOGIC) =============
        # This allows trades through multiple different confluence patterns
        
        # PATH 1: Moderate score + RSI overbought + in uptrend (MAIN PATH)
        path1 = (
            (dataframe['reversal_score'] >= self.reversal_score_threshold.value) &
            (dataframe['rsi'] >= 60) &
            (dataframe['close'] > dataframe['ema_fast']) &
            (dataframe['volume'] > 0)
        )
        
        # PATH 2: Strong divergence signals (divergence = highest quality indicator)
        path2 = (
            ((dataframe['rsi_bearish_div'] == 1) | 
             (dataframe['macd_bearish_div'] == 1) |
             (dataframe['obv_bearish_div'] == 1)) &
            (dataframe['rsi'] >= 60) &
            (dataframe['close'] > dataframe['ema_fast']) &
            (dataframe['volume'] > 0)
        )
        
        # PATH 3: Peak detection (strong objective signal)
        path3 = (
            (dataframe['peak_top'] == 1) &
            (dataframe['rsi'] >= 55) &
            (dataframe['volume'] > 0)
        )
        
        # PATH 4: Multiple oscillators overbought (2+ oscillators)
        path4 = (
            (dataframe['reversal_score'] >= 2.0) &
            (dataframe['rsi'] >= 65) &
            (dataframe['close'] > dataframe['ema_fast']) &
            (dataframe['volume'] > 0)
        )
        
        # PATH 5: Just strong RSI overbought + volume (simplest entry)
        path5 = (
            (dataframe['rsi'] >= 70) &
            (dataframe['close'] > dataframe['ema_fast']) &
            (volume_ratio > 1.0) &
            (dataframe['volume'] > 0)
        )
        
        # Combine all paths with OR logic (entry if ANY condition met)
        dataframe['enter_short'] = (path1 | path2 | path3 | path4 | path5).astype(int)
        dataframe['enter_tag'] = 'multi_path_entry'
        
        dataframe['enter_long'] = 0
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit logic - simplified for short positions"""
        dataframe['exit_short'] = 0
        dataframe['exit_long'] = 0
        
        return dataframe

    def get_coin_from_pair(self, pair: str) -> Optional[str]:
        if pair and '/' in pair:
            parts = pair.split('/')
            return parts[0] if len(parts) > 0 else None
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
               proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
               **kwargs) -> float:
        """Dynamic leverage based on reversal score confidence"""
        coin = self.get_coin_from_pair(pair)
        base_leverage = float(self.get_param_value(coin, 'leverage_param') or 3)
        
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            
            if len(dataframe) > 0:
                last_candle = dataframe.iloc[-1]
                
                # Scale leverage with reversal score confidence
                if 'reversal_score' in last_candle:
                    score = last_candle['reversal_score']
                    if score >= 10.0:
                        base_leverage = min(base_leverage * 1.4, max_leverage)
                    elif score >= 8.0:
                        base_leverage = min(base_leverage * 1.2, max_leverage)
                    elif score < 6.0:
                        base_leverage = max(base_leverage * 0.7, 1)
        except Exception as e:
            pass
        
        return min(base_leverage, max_leverage)

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime, 
                      current_rate: float, current_profit: float, **kwargs) -> float:
        """Custom stoploss with profit-based scaling"""
        
        if current_profit > 0.10:
            return -0.05
        elif current_profit > 0.05:
            return -0.08
        elif current_profit > 0.02:
            return -0.12
        
        coin = self.get_coin_from_pair(pair)
        category = self.get_coin_category(coin)
        
        stoploss_by_category = {
            'high_vol': -0.15,
            'medium_vol': -0.10,
            'low_vol': -0.06
        }
        
        base_stoploss = stoploss_by_category.get(category, -0.10)
        return max(base_stoploss, -0.40)

    @property
    def protections(self):
        """Protection mechanisms to prevent cascade failures"""
        return [
            {
                "method": "CooldownPeriod",
                "stop_duration_candles": 5
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 200,
                "max_allowed_drawdown": 0.20,
                "stop_duration_candles": 40
            },
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 60,
                "trade_limit": 4,
                "stop_duration_candles": 20
            }
        ]

    def get_strategy_parameters(self) -> Dict[str, Any]:
        """Return all strategy parameters for logging"""
        return {
            'williams_r_period': self.williams_r_period.value,
            'rsi_period': self.rsi_period.value,
            'stoch_fastk': self.stoch_fastk.value,
            'reversal_score_threshold': self.reversal_score_threshold.value,
            'use_multitimeframe': self.use_multitimeframe.value,
            'require_multitimeframe_confirmation': self.require_multitimeframe_confirmation.value,
            'market_regime': self._market_regime
        }
