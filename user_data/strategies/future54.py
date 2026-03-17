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
from skopt.space import Integer, Real, Categorical, Dimension

class future54(IStrategy):
    # IMPROVEMENT 1: More aggressive ROI for capturing bigger moves
    minimal_roi = {
        "0": 0.15,    # Increased from 0.05 to capture larger moves
        "10": 0.10,   # Quicker scaling
        "30": 0.07,
        "60": 0.04,
        "150": 0.02,
        "340": 0
    }

    # IMPROVEMENT 2: Increased stoploss for more room
    stoploss = -0.40  # Increased from -0.25 to -0.40 for more breathing room
    
    # IMPROVEMENT 3: More aggressive trailing stop
    trailing_stop = True
    trailing_stop_positive = 0.08  # Reduced from 0.16 for tighter trailing
    trailing_stop_positive_offset = 0.12  # Reduced from 0.213
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    process_only_new_candles = True

    # IMPROVEMENT 4: Higher leverage parameters for more aggressive positioning
    leverage_param_high_vol = IntParameter(2, 5, default=3, space="buy", optimize=True)
    leverage_param_medium_vol = IntParameter(3, 6, default=4, space="buy", optimize=True)
    leverage_param_low_vol = IntParameter(4, 8, default=6, space="buy", optimize=True)
    
    # IMPROVEMENT 5: More sophisticated entry parameters
    buy_rsi_aggressive = IntParameter(25, 40, default=35, space="buy", optimize=True)
    buy_rsi_conservative = IntParameter(40, 55, default=47, space="buy", optimize=True)
    
    # NEW: Trend strength filter to avoid shorting in strong uptrends
    trend_strength_threshold = DecimalParameter(0.5, 0.8, default=0.65, space="buy", optimize=True)
    
    sell_rsi_upper_bear = IntParameter(65, 80, default=72, space="sell", optimize=True)
    sell_rsi_upper_bull = IntParameter(75, 90, default=82, space="sell", optimize=True)
    sell_rsi_lower = IntParameter(15, 35, default=25, space="sell", optimize=True)
    
    macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
    macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
    
    ema_short_period = IntParameter(5, 15, default=8, space="both", optimize=True)
    ema_long_period = IntParameter(15, 30, default=21, space="both", optimize=True)
    
    # NEW: Additional EMA for better trend detection
    ema_trend_period = IntParameter(50, 100, default=75, space="both", optimize=True)
    
    price_extension_pct_conservative = DecimalParameter(0.004, 0.008, default=0.006, space="sell", optimize=True)
    price_extension_pct_aggressive = DecimalParameter(0.002, 0.006, default=0.004, space="sell", optimize=True)
    
    # IMPROVEMENT 6: Higher confluence threshold for better quality shorts
    confluence_threshold = IntParameter(6, 10, default=8, space="buy", optimize=True)
    
    # NEW: Volume spike detection
    volume_spike_threshold = DecimalParameter(1.5, 3.0, default=2.0, space="buy", optimize=True)
    
    timeframe = '5m'
    entry_timeframe = CategoricalParameter(['5m', '15m'], default='15m', space='buy', optimize=True)
    
    startup_candle_count = 200
    can_short = True
    can_long = False

    _last_candle_seen_time = {}
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
        self._coin_categories = {}
        self._market_regime = "bear_high_vol"
        self._regime_update_time = None
        self._trend_strength_cache = {}
        self.initialize_coin_categories()
        
    def initialize_coin_categories(self):
        for category, coins in self.COIN_CATEGORIES.items():
            for coin in coins:
                self._coin_categories[coin] = category
    
    def get_coin_from_pair(self, pair: str) -> str:
        if '/' in pair:
            return pair.split('/')[0]
        return "UNKNOWN"
    
    def get_coin_category(self, coin: str) -> str:
        return self._coin_categories.get(coin, 'medium_vol')
    
    # NEW: Enhanced trend strength calculation
    def calculate_trend_strength(self, dataframe: DataFrame) -> float:
        """Calculate overall trend strength to avoid shorting in strong uptrends"""
        if len(dataframe) < 100:
            return 0.5
            
        # Multiple timeframe EMAs
        ema_20 = dataframe['ema_short'].iloc[-1]
        ema_50 = dataframe['ema_long'].iloc[-1]
        ema_trend = dataframe['ema_trend'].iloc[-1] if 'ema_trend' in dataframe else ema_50
        
        close = dataframe['close'].iloc[-1]
        
        # Calculate trend components
        short_trend = 1 if close > ema_20 else 0
        medium_trend = 1 if close > ema_50 else 0
        long_trend = 1 if close > ema_trend else 0
        
        # Price momentum
        returns_5 = (close / dataframe['close'].iloc[-5] - 1) if len(dataframe) > 5 else 0
        returns_20 = (close / dataframe['close'].iloc[-20] - 1) if len(dataframe) > 20 else 0
        
        momentum_score = 0
        if returns_5 > 0.02:
            momentum_score += 0.5
        if returns_20 > 0.05:
            momentum_score += 0.5
            
        # MACD trend
        macd_trend = 1 if dataframe['macd'].iloc[-1] > dataframe['macdsignal'].iloc[-1] else 0
        
        # Volume trend
        volume_trend = 1 if dataframe['volume'].iloc[-1] > dataframe['volume'].rolling(20).mean().iloc[-1] else 0
        
        # Weighted trend strength (0 to 1)
        trend_strength = (
            short_trend * 0.25 +
            medium_trend * 0.25 +
            long_trend * 0.2 +
            momentum_score * 0.15 +
            macd_trend * 0.1 +
            volume_trend * 0.05
        )
        
        return trend_strength
    
    def detect_market_regime(self, dataframe: DataFrame) -> str:
        if len(dataframe) < 200:
            return self._market_regime
            
        ema_50 = ta.EMA(dataframe, timeperiod=50)
        ema_200 = ta.EMA(dataframe, timeperiod=200)
        
        volatility = dataframe['close'].rolling(20).std()
        avg_volatility = volatility.rolling(100).mean()
        
        current_trend = ema_50.iloc[-1] > ema_200.iloc[-1]
        current_volatility = volatility.iloc[-1] / avg_volatility.iloc[-1]
        
        # NEW: Consider recent price action for regime detection
        recent_high = dataframe['high'].rolling(50).max().iloc[-1]
        recent_low = dataframe['low'].rolling(50).min().iloc[-1]
        price_position = (dataframe['close'].iloc[-1] - recent_low) / (recent_high - recent_low)
        
        if current_trend and current_volatility < 1.2 and price_position > 0.7:
            return 'bull_low_vol'
        elif current_trend and current_volatility >= 1.2:
            return 'bull_high_vol'
        elif not current_trend and current_volatility < 1.2:
            return 'bear_low_vol'
        else:
            return 'bear_high_vol'
    
    def get_regime_adjusted_params(self, coin: str) -> dict:
        category = self.get_coin_category(coin)
        
        base_params = {
            'high_vol': {
                'leverage_param': self.leverage_param_high_vol.value,
                'buy_rsi': self.buy_rsi_aggressive.value,
                'price_extension_pct': self.price_extension_pct_aggressive.value
            },
            'medium_vol': {
                'leverage_param': self.leverage_param_medium_vol.value,
                'buy_rsi': self.buy_rsi_conservative.value,
                'price_extension_pct': self.price_extension_pct_conservative.value
            },
            'low_vol': {
                'leverage_param': self.leverage_param_low_vol.value,
                'buy_rsi': self.buy_rsi_conservative.value,
                'price_extension_pct': self.price_extension_pct_conservative.value
            }
        }
        
        params = base_params[category].copy()
        
        # IMPROVEMENT: More aggressive adjustments for different regimes
        regime_adjustments = {
            'bull_low_vol': {'leverage_mult': 0.5, 'rsi_adj': +15, 'ext_mult': 1.5},  # Very conservative in bull markets
            'bull_high_vol': {'leverage_mult': 0.4, 'rsi_adj': +20, 'ext_mult': 2.0},  # Even more conservative
            'bear_low_vol': {'leverage_mult': 1.5, 'rsi_adj': -5, 'ext_mult': 0.7},   # More aggressive in bear
            'bear_high_vol': {'leverage_mult': 1.2, 'rsi_adj': -2, 'ext_mult': 0.9}   # Moderately aggressive
        }
        
        adj = regime_adjustments.get(self._market_regime, regime_adjustments['bear_high_vol'])
        
        params['leverage_param'] = max(1, int(params['leverage_param'] * adj['leverage_mult']))
        params['sell_rsi_upper'] = self.sell_rsi_upper_bear.value if 'bear' in self._market_regime else self.sell_rsi_upper_bull.value
        params['sell_rsi_upper'] += adj['rsi_adj']
        params['sell_rsi_lower'] = self.sell_rsi_lower.value
        params['price_extension_pct'] *= adj['ext_mult']
        
        return params

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = []
        
        for pair in pairs:
            informative_pairs.append((pair, '1m'))
            informative_pairs.append((pair, '1h'))  # NEW: Add 1h for better trend detection
            if self.entry_timeframe.value != self.timeframe:
                informative_pairs.append((pair, self.entry_timeframe.value))
        
        return informative_pairs

    def calculate_confluence_score(self, dataframe: DataFrame, coin: str) -> DataFrame:
        params = self.get_regime_adjusted_params(coin)
        
        dataframe['volume_avg'] = dataframe['volume'].rolling(20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_avg']
        
        # NEW: Enhanced signals with more weight on reversal patterns
        signals = {}
        
        # RSI divergence detection
        rsi_divergence = (
            (dataframe['high'] > dataframe['high'].shift(1)) &
            (dataframe['rsi'] < dataframe['rsi'].shift(1)) &
            (dataframe['rsi'] > params['sell_rsi_upper'] - 5)
        )
        
        signals['rsi_signal'] = (dataframe['rsi'] > params['sell_rsi_upper']).astype(int) * 3
        signals['rsi_divergence'] = rsi_divergence.astype(int) * 4  # NEW: High weight for divergence
        signals['bb_signal'] = (dataframe['bb_pct'] > 0.90).astype(int) * 3  # Increased threshold
        signals['macd_signal'] = (
            (dataframe['macdhist'] < dataframe['macdhist'].shift(1)) &
            (dataframe['macdhist'].shift(1) > 0) &
            (dataframe['macdhist'].shift(1) > dataframe['macdhist'].shift(2))  # Peak detection
        ).astype(int) * 3
        signals['volume_spike'] = (dataframe['volume_ratio'] > self.volume_spike_threshold.value).astype(int) * 2
        signals['trend_signal'] = (dataframe['close'] > dataframe['ema_short']).astype(int) * 1
        signals['extension_signal'] = (
            dataframe['close'] > dataframe['ema_short'] * (1 + params['price_extension_pct'])
        ).astype(int) * 3
        
        # NEW: Candle pattern detection
        signals['shooting_star'] = (
            ((dataframe['high'] - dataframe['close']) > 2 * abs(dataframe['close'] - dataframe['open'])) &
            ((dataframe['close'] - dataframe['low']) < 0.3 * (dataframe['high'] - dataframe['low']))
        ).astype(int) * 2
        
        dataframe['confluence_score'] = sum(signals.values())
        dataframe['high_confluence'] = dataframe['confluence_score'] >= self.confluence_threshold.value
        
        return dataframe

    def clean_up_old_trades(self):
        """Clean up tracking data for closed trades"""
        try:
            from freqtrade.persistence import Trade
            current_open_trade_ids = set(trade.id for trade in Trade.get_open_trades())
            if hasattr(self, '_trade_start_reset_times'):
                closed_trade_ids = set(self._trade_start_reset_times.keys()) - current_open_trade_ids
                for trade_id in closed_trade_ids:
                    if trade_id in self._trade_start_reset_times:
                        del self._trade_start_reset_times[trade_id]
        except ImportError:
            # Trade module not available during backtesting
            pass

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        self.clean_up_old_trades()
        
        # Update regime less frequently but more accurately
        if (self._regime_update_time is None or 
            datetime.now() - self._regime_update_time > timedelta(hours=2)):
            self._market_regime = self.detect_market_regime(dataframe)
            self._regime_update_time = datetime.now()
        
        coin = self.get_coin_from_pair(metadata['pair'])
        params = self.get_regime_adjusted_params(coin)
        
        # Standard indicators
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=self.ema_short_period.value)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=self.ema_long_period.value)
        dataframe['ema_trend'] = ta.EMA(dataframe, timeperiod=self.ema_trend_period.value)
        
        # NEW: ATR for dynamic stop loss
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        macd = ta.MACD(dataframe, 
                     fastperiod=self.macd_fast.value,
                     slowperiod=self.macd_slow.value, 
                     signalperiod=self.macd_signal.value)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_pct'] = (dataframe['close'] - bollinger['lower']) / (bollinger['upper'] - bollinger['lower'])
        
        # Calculate trend strength
        trend_strength = self.calculate_trend_strength(dataframe)
        self._trend_strength_cache[metadata['pair']] = trend_strength
        dataframe['trend_strength'] = trend_strength
        
        # Enhanced 1m timeframe analysis
        if self.dp:
            try:
                informative_1m = self.dp.get_pair_dataframe(
                    pair=metadata['pair'], 
                    timeframe='1m'
                )
                
                informative_1m['rsi'] = ta.RSI(informative_1m, timeperiod=14)
                informative_1m['ema_short'] = ta.EMA(informative_1m, timeperiod=self.ema_short_period.value)
                
                bollinger_1m = qtpylib.bollinger_bands(qtpylib.typical_price(informative_1m), window=20, stds=2)
                informative_1m['bb_lowerband'] = bollinger_1m['lower']
                
                macd_1m = ta.MACD(informative_1m, 
                                fastperiod=self.macd_fast.value,
                                slowperiod=self.macd_slow.value, 
                                signalperiod=self.macd_signal.value)
                informative_1m['macd'] = macd_1m['macd']
                informative_1m['macdsignal'] = macd_1m['macdsignal']
                informative_1m['macdhist'] = macd_1m['macdhist']
                
                # More aggressive exit conditions
                informative_1m['deep_oversold'] = (
                    (informative_1m['rsi'] < params['sell_rsi_lower'] * 0.8) &  # More aggressive
                    (informative_1m['close'] < informative_1m['bb_lowerband'] * 1.02) &
                    (informative_1m['close'] < informative_1m['ema_short'] * 0.98)
                )
                
                informative_1m['major_trend_reversal'] = (
                    qtpylib.crossed_above(informative_1m['macd'], informative_1m['macdsignal']) &
                    (informative_1m['macd'] < 0) &
                    (informative_1m['macdhist'] > informative_1m['macdhist'].shift(1) * 1.1) &  # Less strict
                    (informative_1m['close'] < informative_1m['ema_short'])
                )
                
                informative_1m['short_exit_signal'] = (
                    informative_1m['deep_oversold'] | 
                    informative_1m['major_trend_reversal']
                )
                
                informative_1m['short_exit_signal'] = informative_1m['short_exit_signal'].astype(int)
                
                dataframe = merge_informative_pair(
                    dataframe, 
                    informative_1m[['short_exit_signal']], 
                    self.timeframe, 
                    '1m', 
                    ffill=True, 
                    append_timeframe=False,
                    suffix='_1m'
                )
                
            except Exception as e:
                dataframe['short_exit_signal_1m'] = 0
            
            # NEW: 1h timeframe for trend confirmation
            try:
                informative_1h = self.dp.get_pair_dataframe(
                    pair=metadata['pair'], 
                    timeframe='1h'
                )
                
                informative_1h['rsi'] = ta.RSI(informative_1h, timeperiod=14)
                informative_1h['ema_50'] = ta.EMA(informative_1h, timeperiod=50)
                informative_1h['ema_200'] = ta.EMA(informative_1h, timeperiod=200)
                
                # Strong uptrend detection on 1h
                informative_1h['strong_uptrend'] = (
                    (informative_1h['close'] > informative_1h['ema_50']) &
                    (informative_1h['ema_50'] > informative_1h['ema_200']) &
                    (informative_1h['rsi'] > 50) &
                    (informative_1h['rsi'] < 70)
                )
                
                dataframe = merge_informative_pair(
                    dataframe, 
                    informative_1h[['strong_uptrend']], 
                    self.timeframe, 
                    '1h', 
                    ffill=True, 
                    append_timeframe=False,
                    suffix='_1h'
                )
            except:
                dataframe['strong_uptrend_1h'] = 0
            
            if self.entry_timeframe.value != self.timeframe:
                try:
                    informative = self.dp.get_pair_dataframe(
                        pair=metadata['pair'], 
                        timeframe=self.entry_timeframe.value
                    )
                    
                    informative['rsi'] = ta.RSI(informative, timeperiod=14)
                    informative['ema_short'] = ta.EMA(informative, timeperiod=self.ema_short_period.value)
                    informative['ema_trend'] = ta.EMA(informative, timeperiod=self.ema_trend_period.value)
                    
                    macd = ta.MACD(informative, 
                                fastperiod=self.macd_fast.value,
                                slowperiod=self.macd_slow.value, 
                                signalperiod=self.macd_signal.value)
                    informative['macd'] = macd['macd']
                    informative['macdsignal'] = macd['macdsignal']
                    informative['macdhist'] = macd['macdhist']
                    
                    bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(informative), window=20, stds=2)
                    informative['bb_upperband'] = bollinger['upper']
                    informative['bb_middleband'] = bollinger['mid']
                    informative['bb_lowerband'] = bollinger['lower']
                    informative['bb_pct'] = (informative['close'] - bollinger['lower']) / (bollinger['upper'] - bollinger['lower'])
                    
                    informative = self.calculate_confluence_score(informative, coin)
                    
                    informative['high_last_5'] = informative['high'].rolling(5).max()  # Changed from 3 to 5
                    
                    informative['price_peak'] = (
                        (informative['high'] >= informative['high_last_5'] * 0.998) &
                        (informative['high'] > informative['high'].shift(1)) &
                        (informative['close'] > informative['ema_short']) &
                        (informative['rsi'] > params['sell_rsi_upper'])
                    )
                    
                    informative['price_reversal'] = (
                        (informative['close'].shift(2) < informative['close'].shift(1)) &
                        (informative['close'] < informative['close'].shift(1)) &
                        (informative['close'].shift(1) > informative['close'].shift(1).rolling(5).max().shift(1)) &
                        (informative['rsi'] > params['sell_rsi_upper'] * 0.85)
                    )
                    
                    informative['macd_reversal'] = (
                        (informative['macdhist'].shift(2) < informative['macdhist'].shift(1)) &
                        (informative['macdhist'] < informative['macdhist'].shift(1)) &
                        (informative['macdhist'].shift(1) > 0) &
                        (informative['close'] > informative['ema_short'])
                    )
                    
                    informative['enhanced_short_entry'] = (
                        (informative['price_peak'] | informative['price_reversal'] | informative['macd_reversal']) &
                        informative['high_confluence'] &
                        (informative['close'] > informative['ema_short'] * (1 + params['price_extension_pct']))
                    )
                    
                    for col in ['enhanced_short_entry', 'price_peak', 'price_reversal', 'macd_reversal', 'high_confluence']:
                        informative[col] = informative[col].astype(int)
                    
                    dataframe = merge_informative_pair(
                        dataframe, 
                        informative, 
                        self.timeframe, 
                        self.entry_timeframe.value, 
                        ffill=True, 
                        append_timeframe=False,
                        suffix=f'_{self.entry_timeframe.value}'
                    )
                except Exception as e:
                    pass
        
        dataframe = self.calculate_confluence_score(dataframe, coin)
        
        dataframe['high_last_5'] = dataframe['high'].rolling(5).max()
        
        dataframe['price_peak'] = (
            (dataframe['high'] >= dataframe['high_last_5'] * 0.998) &
            (dataframe['high'] > dataframe['high'].shift(1)) &
            (dataframe['close'] > dataframe['ema_short']) &
            (dataframe['rsi'] > params['sell_rsi_upper'])
        )

        dataframe['price_reversal'] = (
            (dataframe['close'].shift(2) < dataframe['close'].shift(1)) &
            (dataframe['close'] < dataframe['close'].shift(1)) &
            (dataframe['close'].shift(1) > dataframe['close'].shift(1).rolling(5).max().shift(1)) &
            (dataframe['rsi'] > params['sell_rsi_upper'] * 0.85)
        )
        
        dataframe['macd_reversal'] = (
            (dataframe['macdhist'].shift(2) < dataframe['macdhist'].shift(1)) &
            (dataframe['macdhist'] < dataframe['macdhist'].shift(1)) &
            (dataframe['macdhist'].shift(1) > 0) &
            (dataframe['close'] > dataframe['ema_short'])
        )
       
        dataframe['enhanced_short_entry'] = (
           (dataframe['price_peak'] | dataframe['price_reversal'] | dataframe['macd_reversal']) &
           dataframe['high_confluence'] &
           (dataframe['close'] > dataframe['ema_short'] * (1 + params['price_extension_pct']))
        )
       
        dataframe[f'enhanced_short_entry_{self.timeframe}'] = dataframe['enhanced_short_entry'].astype(int)
       
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        coin = self.get_coin_from_pair(metadata['pair'])
        
        # NEW: Check trend strength before entering
        trend_strength = self._trend_strength_cache.get(metadata['pair'], 0.5)
        
        # Only short if trend is not too strong
        if trend_strength < self.trend_strength_threshold.value:
            # Also check 1h timeframe if available
            if 'strong_uptrend_1h' in dataframe.columns:
                # Avoid shorting in strong 1h uptrends
                not_strong_uptrend = (dataframe['strong_uptrend_1h'] == 0)
            else:
                not_strong_uptrend = pd.Series([True] * len(dataframe), index=dataframe.index)
                
            if hasattr(self, 'freqai') and self.freqai and 'prediction' in dataframe.columns:
                last_candle = dataframe.iloc[-1].squeeze() if len(dataframe) > 0 else None
                
                if last_candle is not None:
                    prediction_value = last_candle['prediction']
                    
                    threshold = 0.7
                    if 'market_trend' in dataframe.columns:
                        market_trend = last_candle['market_trend']
                        if market_trend > 0.7:
                            threshold = 0.8
                        elif market_trend < 0.3:
                            threshold = 0.6
                    
                    dataframe.loc[
                        (dataframe['prediction'] > threshold) & 
                        (dataframe['volume'] > 0) &
                        not_strong_uptrend,
                        'enter_short'
                    ] = 1
            else:
                entry_signal_col = f'enhanced_short_entry_{self.entry_timeframe.value}'
                
                if entry_signal_col in dataframe.columns:
                    dataframe.loc[
                        (dataframe[entry_signal_col] > 0) & 
                        not_strong_uptrend,
                        'enter_short'
                    ] = 1
                else:
                    dataframe.loc[
                        (dataframe['enhanced_short_entry'] > 0) &
                        not_strong_uptrend,
                        'enter_short'
                    ] = 1
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        if 'short_exit_signal_1m' in dataframe.columns:
            dataframe.loc[dataframe['short_exit_signal_1m'] > 0, 'exit_short'] = 1
        else:
            coin = self.get_coin_from_pair(metadata['pair'])
            params = self.get_regime_adjusted_params(coin)
            
            exit_signal = (
                (dataframe['rsi'] < params['sell_rsi_lower'] * 0.8) &  # More aggressive exit
                (dataframe['close'] < dataframe['bb_lowerband'] * 1.02) &
                (dataframe['close'] < dataframe['ema_short'] * 0.98)
            ) | (
                qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal']) &
                (dataframe['macd'] < 0) &
                (dataframe['macdhist'] > dataframe['macdhist'].shift(1) * 1.1) &
                (dataframe['close'] < dataframe['ema_short'])
            )
            
            dataframe.loc[exit_signal, 'exit_short'] = 1
        
        return dataframe
   
    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                          time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                          side: str, **kwargs) -> bool:
        if side != 'short':
            return True
            
        # Shorter cooldown for more opportunities
        cooldown_minutes = 2 if 'bear' in self._market_regime else 3
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        # Final trend check
        if len(dataframe) > 0:
            trend_strength = self.calculate_trend_strength(dataframe)
            if trend_strength > self.trend_strength_threshold.value + 0.1:  # Extra safety margin
                return False
        
            if 'prediction_probability' in dataframe.columns:
                latest_prob = dataframe['prediction_probability'].iloc[-1]
                if latest_prob < 0.25:  # Lowered from 0.3
                    return False
        
        self._last_candle_seen_time[pair] = current_time
        
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                  current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        if trade.is_short:
            try:
                coin = self.get_coin_from_pair(pair)
                params = self.get_regime_adjusted_params(coin)
                
                if not hasattr(self, '_trade_start_reset_times'):
                    self._trade_start_reset_times = {}
                
                effective_start_time = self._trade_start_reset_times.get(trade.id, trade.open_date_utc)
                
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if len(dataframe) > 0:
                    last_candle = dataframe.iloc[-1]
                    
                    # NEW: Dynamic exit based on ATR
                    if 'atr' in last_candle:
                        atr_multiplier = 2.5 if current_profit > 0.02 else 3.0
                        dynamic_exit_price = trade.open_rate - (last_candle['atr'] * atr_multiplier)
                        if current_rate <= dynamic_exit_price and current_profit > 0.01:
                            return 'atr_based_exit'
                    
                    # Check for new entry signal to reset or exit
                    entry_signal_col = f'enhanced_short_entry_{self.entry_timeframe.value}'
                    
                    if (entry_signal_col in last_candle and last_candle[entry_signal_col] > 0) or last_candle.get('enhanced_short_entry', 0) > 0:
                        if current_rate > trade.open_rate and current_profit < -0.01:
                            # Reset timer if getting new signal at worse price
                            self._trade_start_reset_times[trade.id] = current_time
                            return None
                        elif current_profit > 0.005:
                            # Exit if profitable and new signal appears
                            return 'new_signal_profitable_exit'
                
                trade_duration = (current_time - effective_start_time).total_seconds() / 60
                
                # IMPROVEMENT: More aggressive time-based exits
                roi_thresholds = {
                    'high_vol': {"0": 0.04, "1": 0.03, "3": 0.02, "10": 0.01, "30": 0},
                    'medium_vol': {"0": 0.035, "2": 0.025, "5": 0.015, "20": 0.005, "45": 0},
                    'low_vol': {"0": 0.03, "3": 0.02, "10": 0.01, "30": 0.003, "90": 0}
                }
                
                category = self.get_coin_category(coin)
                roi_table = roi_thresholds[category]
                
                roi_threshold = None
                for time_threshold, roi_value in sorted(roi_table.items(), key=lambda x: int(x[0]) if x[0] != "0" else 0):
                    if trade_duration >= int(time_threshold):
                        roi_threshold = roi_value
                
                if roi_threshold is not None and current_profit > roi_threshold:
                    return f'{coin}_time_based_roi'
                
                # Quick exit on extreme oversold
                if current_profit > 0.01 and 'rsi' in last_candle and last_candle['rsi'] < params['sell_rsi_lower'] * 0.8:
                    return 'extreme_oversold_exit'
                
                # NEW: Trend reversal exit
                if 'trend_strength' in last_candle:
                    current_trend = self.calculate_trend_strength(dataframe)
                    if current_trend > 0.75 and current_profit > 0.005:
                        return 'strong_uptrend_detected'
                
                if hasattr(self, 'freqai') and self.freqai and 'prediction' in dataframe.columns:
                    if 'prediction' in last_candle and last_candle['prediction'] < 0.25:
                        if current_profit > 0.005:
                            return 'ai_reversal_predicted'
                
            except Exception as e:
                pass
        
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
               proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
               **kwargs) -> float:
        coin = self.get_coin_from_pair(pair)
        params = self.get_regime_adjusted_params(coin)
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        # Dynamic leverage based on confidence
        base_leverage = float(params['leverage_param'])
        
        if len(dataframe) > 0:
            last_candle = dataframe.iloc[-1]
            
            # Adjust leverage based on confluence score
            if 'confluence_score' in last_candle:
                if last_candle['confluence_score'] > 10:
                    base_leverage = min(base_leverage * 1.3, max_leverage)
                elif last_candle['confluence_score'] < 6:
                    base_leverage = max(base_leverage * 0.7, 1)
            
            # Reduce leverage in strong uptrends
            if 'trend_strength' in last_candle:
                if last_candle['trend_strength'] > 0.6:
                    base_leverage = max(base_leverage * 0.5, 1)
        
        return min(base_leverage, max_leverage)
   
    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime, 
                      current_rate: float, current_profit: float, **kwargs) -> float:
        coin = self.get_coin_from_pair(pair)
        category = self.get_coin_category(coin)
        
        # IMPROVEMENT: Wider initial stops, tighter as profit grows
        if current_profit > 0.10:
            return -0.05  # Very tight stop at high profit
        elif current_profit > 0.05:
            return -0.08  # Tighter stop
        elif current_profit > 0.02:
            return -0.12  # Moderate stop
        
        # Base stoploss by category with more room
        stoploss_by_category = {
            'high_vol': -0.15,  # Increased from -0.08
            'medium_vol': -0.10,  # Increased from -0.05
            'low_vol': -0.06    # Increased from -0.03
        }
        
        base_stoploss = stoploss_by_category[category]
        
        # Regime adjustments
        regime_adjustments = {
            'bull_low_vol': 0.6,   # Tighter in bull markets
            'bull_high_vol': 0.5,
            'bear_low_vol': 1.4,   # Wider in bear markets
            'bear_high_vol': 1.2
        }
        
        multiplier = regime_adjustments.get(self._market_regime, 1.0)
        
        # Dynamic adjustment based on ATR if available
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) > 0 and 'atr' in dataframe.columns:
            last_atr = dataframe['atr'].iloc[-1]
            close_price = dataframe['close'].iloc[-1]
            atr_percentage = (last_atr / close_price)
            
            # Adjust stoploss based on volatility
            if atr_percentage > 0.02:  # High volatility
                multiplier *= 1.3
            elif atr_percentage < 0.01:  # Low volatility
                multiplier *= 0.8
        
        final_stoploss = base_stoploss * multiplier
        
        # Never exceed maximum stoploss
        return max(final_stoploss, -0.40)
