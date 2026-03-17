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

class future68(IStrategy):
    """
    FreqAI-Enabled Strategy
    
    Features:
    - ML predicts entry signals (long/short probability)
    - ML predicts optimal leverage (dynamic per trade)
    - ML learns from market conditions
    - Combines traditional indicators with ML predictions
    - Adaptive to changing market regimes
    """
    
    # Enable FreqAI
    process_only_new_candles = True
    use_exit_signal = False  # Let ROI and trailing stops work
    startup_candle_count = 200
    can_short = True
    can_long = True
    
    # Strategy configuration
    minimal_roi = {
        "0": 0.03,
        "15": 0.02,
        "45": 0.01,
        "90": 0.006,
        "150": 0.001,
        "240": -0.01,
        "320": -0.03,
    }
    
    stoploss = -0.015
    
    trailing_stop = True
    trailing_stop_positive = 0.005
    trailing_stop_positive_offset = 0.01
    trailing_only_offset_is_reached = True
    
    max_open_trades = 4
    timeframe = '5m'
    
    # FreqAI-specific settings
    plot_config = {
        'main_plot': {
            'ema_fast': {'color': 'blue'},
            'ema_slow': {'color': 'red'},
        },
        'subplots': {
            "RSI": {
                'rsi': {'color': 'red'},
            },
            "FreqAI": {
                '&-pred_long_prob': {'color': 'green'},
                '&-pred_short_prob': {'color': 'red'},
                '&-pred_leverage': {'color': 'blue'},
            }
        }
    }
    
    # Fallback parameters when ML not available
    leverage_long_fallback = IntParameter(3, 10, default=4, space="buy", optimize=False)
    leverage_short_fallback = IntParameter(3, 10, default=5, space="sell", optimize=False)
    
    # ML confidence thresholds
    ml_confidence_long = DecimalParameter(0.5, 0.85, default=0.65, space="buy", optimize=True)
    ml_confidence_short = DecimalParameter(0.5, 0.85, default=0.65, space="sell", optimize=True)
    
    # Minimum leverage bounds (safety)
    min_leverage = IntParameter(2, 5, default=3, space="both", optimize=False)
    max_leverage = IntParameter(5, 10, default=8, space="both", optimize=False)

    def informative_pairs(self):
        """Define pairs for higher timeframes"""
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

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int,
                                       metadata: dict, **kwargs) -> DataFrame:
        """
        Create features for ML model
        All features should start with '%' to be used by FreqAI
        """
        
        # Price-based features
        dataframe[f'%-roc_{period}'] = (
            (dataframe['close'] - dataframe['close'].shift(period)) / 
            dataframe['close'].shift(period) * 100
        )
        dataframe[f'%-price_pct_change_{period}'] = dataframe['close'].pct_change(period) * 100
        
        # Momentum features
        dataframe[f'%-rsi_{period}'] = ta.RSI(dataframe, timeperiod=period)
        dataframe[f'%-rsi_change_{period}'] = dataframe[f'%-rsi_{period}'].diff()
        
        # Trend features
        dataframe[f'%-ema_fast_{period}'] = ta.EMA(dataframe, timeperiod=int(period * 0.5))
        dataframe[f'%-ema_slow_{period}'] = ta.EMA(dataframe, timeperiod=period)
        dataframe[f'%-ema_diff_{period}'] = (
            (dataframe[f'%-ema_fast_{period}'] - dataframe[f'%-ema_slow_{period}']) / 
            dataframe['close'] * 100
        )
        
        # Volatility features
        dataframe[f'%-atr_{period}'] = ta.ATR(dataframe, timeperiod=period)
        dataframe[f'%-atr_pct_{period}'] = (dataframe[f'%-atr_{period}'] / dataframe['close']) * 100
        
        bb = ta.BBANDS(dataframe, timeperiod=period, nbdevup=2.0, nbdevdn=2.0)
        dataframe[f'%-bb_width_{period}'] = (
            (bb['upperband'] - bb['lowerband']) / bb['middleband'] * 100
        )
        dataframe[f'%-bb_position_{period}'] = (
            (dataframe['close'] - bb['lowerband']) / 
            (bb['upperband'] - bb['lowerband']) * 100
        )
        
        # Volume features
        dataframe[f'%-volume_ratio_{period}'] = (
            dataframe['volume'] / dataframe['volume'].rolling(period).mean()
        )
        
        # MACD features
        macd = ta.MACD(dataframe, fastperiod=int(period*0.5), 
                       slowperiod=period, signalperiod=int(period*0.35))
        dataframe[f'%-macd_{period}'] = macd['macd']
        dataframe[f'%-macd_signal_{period}'] = macd['macdsignal']
        dataframe[f'%-macd_hist_{period}'] = macd['macdhist']
        
        # Price action patterns
        dataframe[f'%-higher_high_{period}'] = (
            dataframe['high'] > dataframe['high'].shift(1).rolling(period).max()
        ).astype(int)
        dataframe[f'%-lower_low_{period}'] = (
            dataframe['low'] < dataframe['low'].shift(1).rolling(period).min()
        ).astype(int)
        
        # Candle patterns
        dataframe[f'%-body_size_{period}'] = (
            abs(dataframe['close'] - dataframe['open']) / dataframe['close'] * 100
        )
        dataframe[f'%-candle_direction_{period}'] = (
            (dataframe['close'] > dataframe['open']).astype(int)
        )
        
        # Distance from moving averages
        dataframe[f'%-dist_ema_fast_{period}'] = (
            (dataframe['close'] - dataframe[f'%-ema_fast_{period}']) / 
            dataframe['close'] * 100
        )
        dataframe[f'%-dist_ema_slow_{period}'] = (
            (dataframe['close'] - dataframe[f'%-ema_slow_{period}']) / 
            dataframe['close'] * 100
        )
        
        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        Basic features that don't depend on period
        """
        
        # Add current indicators (non-period dependent)
        dataframe['%-current_hour'] = dataframe['date'].dt.hour
        dataframe['%-day_of_week'] = dataframe['date'].dt.dayofweek
        
        # Price position
        dataframe['%-high_low_range'] = (
            (dataframe['high'] - dataframe['low']) / dataframe['close'] * 100
        )
        
        # Consecutive candles
        dataframe['%-consecutive_green'] = (
            (dataframe['close'] > dataframe['open']).rolling(5).sum()
        )
        dataframe['%-consecutive_red'] = (
            (dataframe['close'] < dataframe['open']).rolling(5).sum()
        )
        
        return dataframe

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        Standard indicators that will also be used for traditional logic
        """
        
        # EMAs
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=10)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=26)
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # ATR
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # Volume
        dataframe['volume_ma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_ma']
        
        # Bollinger Bands
        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_width'] = (bb['upperband'] - bb['lowerband']) / bb['middleband']
        
        # Higher timeframe trend
        dataframe = self.add_higher_tf_data(dataframe, metadata)
        
        return dataframe

    def add_higher_tf_data(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add higher timeframe data"""
        # 15m trend
        inf_15m = self.dp.get_pair_dataframe(metadata['pair'], '15m')
        if not inf_15m.empty:
            inf_15m['ema_fast_15m'] = ta.EMA(inf_15m, timeperiod=10)
            inf_15m['ema_slow_15m'] = ta.EMA(inf_15m, timeperiod=26)
            inf_15m['trend_15m'] = np.where(
                inf_15m['ema_fast_15m'] > inf_15m['ema_slow_15m'], 1, -1
            )
            dataframe = merge_informative_pair(
                dataframe, inf_15m[['date', 'trend_15m']], 
                self.timeframe, '15m', ffill=True
            )
        else:
            dataframe['trend_15m'] = 0
        
        # 1h trend
        inf_1h = self.dp.get_pair_dataframe(metadata['pair'], '1h')
        if not inf_1h.empty:
            inf_1h['ema_fast_1h'] = ta.EMA(inf_1h, timeperiod=10)
            inf_1h['ema_slow_1h'] = ta.EMA(inf_1h, timeperiod=26)
            inf_1h['trend_1h'] = np.where(
                inf_1h['ema_fast_1h'] > inf_1h['ema_slow_1h'], 1, -1
            )
            dataframe = merge_informative_pair(
                dataframe, inf_1h[['date', 'trend_1h']], 
                self.timeframe, '1h', ffill=True
            )
        else:
            dataframe['trend_1h'] = 0
            
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        Define what the ML model should predict
        
        Targets:
        1. Long probability (0-1)
        2. Short probability (0-1)
        3. Optimal leverage (2-10)
        """
        
        # Calculate future returns at different horizons
        for shift in [5, 10, 20]:  # 5, 10, 20 candles ahead
            dataframe[f'future_return_{shift}'] = (
                (dataframe['close'].shift(-shift) - dataframe['close']) / 
                dataframe['close'] * 100
            )
        
        # Target 1: Long entry signal (1 if profitable long in next 20 candles)
        # Profitable defined as > 2% gain within 20 candles
        dataframe['&-long_target'] = (
            (dataframe['future_return_5'] > 1.5) |
            (dataframe['future_return_10'] > 2.0) |
            (dataframe['future_return_20'] > 2.5)
        ).astype(int)
        
        # Target 2: Short entry signal (1 if profitable short in next 20 candles)
        dataframe['&-short_target'] = (
            (dataframe['future_return_5'] < -1.5) |
            (dataframe['future_return_10'] < -2.0) |
            (dataframe['future_return_20'] < -2.5)
        ).astype(int)
        
        # Target 3: Optimal leverage based on volatility and expected return
        # Higher volatility = lower leverage, Higher expected return = higher leverage
        dataframe['recent_volatility'] = dataframe['atr'].rolling(20).mean() / dataframe['close'] * 100
        dataframe['expected_return'] = dataframe[['future_return_5', 'future_return_10', 'future_return_20']].mean(axis=1).abs()
        
        # Calculate optimal leverage (3-8x)
        # High volatility (>5%) = 3x, Low volatility (<2%) = 8x
        # Adjusted by expected return
        dataframe['&-leverage_target'] = np.clip(
            8 - (dataframe['recent_volatility'] * 1.0) + (dataframe['expected_return'] * 0.3),
            3, 8
        )
        
        # Clean up temporary columns
        dataframe.drop(columns=[f'future_return_{s}' for s in [5, 10, 20]] + 
                      ['recent_volatility', 'expected_return'], 
                      inplace=True, errors='ignore')
        
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate indicators
        This is called by FreqAI for feature engineering
        """
        
        # Standard indicators
        dataframe = self.feature_engineering_standard(dataframe, metadata)
        
        # Let FreqAI handle the rest via feature_engineering functions
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Entry logic using ML predictions
        """
        
        # Check if FreqAI predictions exist
        has_predictions = (
            '&-pred_long_target' in dataframe.columns and
            '&-pred_short_target' in dataframe.columns and
            '&-pred_leverage_target' in dataframe.columns
        )
        
        if has_predictions:
            # Use ML predictions
            logger.info(f"Using FreqAI predictions for {metadata['pair']}")
            
            # LONG ENTRIES
            # Enter long if:
            # 1. ML predicts long with high confidence
            # 2. Basic sanity checks pass
            long_conditions = [
                (dataframe['&-pred_long_target'] > self.ml_confidence_long.value),  # ML confident
                (dataframe['rsi'] > 35),  # Not oversold
                (dataframe['rsi'] < 80),  # Not overbought
                (dataframe['bb_width'] > 0.015),  # Not ranging
                (dataframe['volume_ratio'] > 0.7),  # Decent volume
            ]
            
            # Add higher timeframe confirmation for extra safety
            if 'trend_15m' in dataframe.columns:
                long_conditions.append(dataframe['trend_15m'] >= 0)
            
            dataframe.loc[
                reduce(lambda x, y: x & y, long_conditions),
                'enter_long'
            ] = 1
            
            # SHORT ENTRIES
            short_conditions = [
                (dataframe['&-pred_short_target'] > self.ml_confidence_short.value),  # ML confident
                (dataframe['rsi'] > 20),  # Not oversold
                (dataframe['rsi'] < 65),  # Not overbought
                (dataframe['bb_width'] > 0.015),  # Not ranging
                (dataframe['volume_ratio'] > 0.7),  # Decent volume
            ]
            
            if 'trend_15m' in dataframe.columns:
                short_conditions.append(dataframe['trend_15m'] <= 0)
            
            dataframe.loc[
                reduce(lambda x, y: x & y, short_conditions),
                'enter_short'
            ] = 1
            
        else:
            # Fallback: Use traditional score-based system
            logger.warning(f"FreqAI predictions not available for {metadata['pair']}, using fallback logic")
            dataframe = self.populate_entry_fallback(dataframe, metadata)
        
        return dataframe

    def populate_entry_fallback(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Fallback entry logic when ML predictions unavailable
        Uses the proven score-based system
        """
        
        dataframe['long_score'] = 0
        dataframe['short_score'] = 0
        
        # Calculate additional indicators for fallback
        dataframe['trend_up'] = dataframe['ema_fast'] > dataframe['ema_slow']
        dataframe['trend_down'] = dataframe['ema_fast'] < dataframe['ema_slow']
        dataframe['roc_3'] = dataframe['close'].pct_change(3) * 100
        
        # LONG SCORING
        dataframe.loc[dataframe['trend_up'], 'long_score'] += 2
        dataframe.loc[dataframe['roc_3'] > 0.3, 'long_score'] += 1
        dataframe.loc[dataframe['rsi'] > 50, 'long_score'] += 1
        dataframe.loc[dataframe['volume_ratio'] > 1.2, 'long_score'] += 1
        if 'trend_15m' in dataframe.columns:
            dataframe.loc[dataframe['trend_15m'] > 0, 'long_score'] += 1
        
        # SHORT SCORING
        dataframe.loc[dataframe['trend_down'], 'short_score'] += 2
        dataframe.loc[dataframe['roc_3'] < -0.3, 'short_score'] += 1
        dataframe.loc[dataframe['rsi'] < 50, 'short_score'] += 1
        dataframe.loc[dataframe['volume_ratio'] > 1.2, 'short_score'] += 1
        if 'trend_15m' in dataframe.columns:
            dataframe.loc[dataframe['trend_15m'] < 0, 'short_score'] += 1
        
        # APPLY ENTRIES
        dataframe.loc[dataframe['long_score'] >= 4, 'enter_long'] = 1
        dataframe.loc[dataframe['short_score'] >= 4, 'enter_short'] = 1
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit signals disabled - let ROI and trailing stops work
        """
        return dataframe

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """
        Dynamic leverage using ML predictions
        """
        
        try:
            # Get the analyzed dataframe
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            
            if dataframe.empty:
                logger.warning(f"Empty dataframe for {pair}, using fallback leverage")
                return self.leverage_long_fallback.value if side == 'long' else self.leverage_short_fallback.value
            
            last_candle = dataframe.iloc[-1]
            
            # Check if ML prediction exists
            if '&-pred_leverage_target' in last_candle:
                # Use ML-predicted optimal leverage
                ml_leverage = last_candle['&-pred_leverage_target']
                
                # Apply safety bounds
                safe_leverage = np.clip(
                    ml_leverage,
                    self.min_leverage.value,
                    min(self.max_leverage.value, max_leverage)
                )
                
                logger.info(f"{pair} {side}: ML predicted leverage={ml_leverage:.1f}, using={safe_leverage:.1f}")
                return float(safe_leverage)
            
            else:
                # Fallback: Use fixed leverage
                fallback_lev = self.leverage_long_fallback.value if side == 'long' else self.leverage_short_fallback.value
                logger.info(f"{pair} {side}: Using fallback leverage={fallback_lev}")
                return float(fallback_lev)
                
        except Exception as e:
            logger.error(f"Error getting leverage for {pair}: {e}")
            return self.leverage_long_fallback.value if side == 'long' else self.leverage_short_fallback.value

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                       current_rate: float, current_profit: float,
                       after_fill: bool, **kwargs) -> Optional[float]:
        """
        Dynamic stop loss
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return None
            
        last_candle = dataframe.iloc[-1]
        atr = last_candle.get('atr', 0)
        
        if atr > 0:
            atr_stop = (atr * 2.5) / current_rate
            
            # Tighter stops in profit
            if current_profit > 0.12:
                return -0.02
            elif current_profit > 0.08:
                return -0.03
            elif current_profit > 0.04:
                return -0.045
            else:
                return max(-min(atr_stop, 0.12), self.stoploss)
        
        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        """
        Final entry confirmation
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return False
            
        last_candle = dataframe.iloc[-1]
        
        # Basic sanity checks
        if last_candle.get('bb_width', 0) < 0.01:
            return False
        
        if last_candle.get('volume_ratio', 0) < 0.5:
            return False
        
        rsi = last_candle.get('rsi', 50)
        if side == 'long' and (rsi > 80 or rsi < 30):
            return False
        if side == 'short' and (rsi < 20 or rsi > 70):
            return False
        
        return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, 
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """
        Minimal custom exits
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return None
            
        last_candle = dataframe.iloc[-1]
        
        # Check if ML predicts strong reversal
        if '&-pred_long_target' in last_candle and '&-pred_short_target' in last_candle:
            if trade.is_short and last_candle['&-pred_long_target'] > 0.8:
                return 'ml_reversal_signal'
            elif not trade.is_short and last_candle['&-pred_short_target'] > 0.8:
                return 'ml_reversal_signal'
        
        # Extreme price movement
        roc = (current_rate - dataframe['close'].iloc[-6]) / dataframe['close'].iloc[-6] * 100
        if trade.is_short and roc > 4.0:
            return 'extreme_reversal'
        elif not trade.is_short and roc < -4.0:
            return 'extreme_reversal'
        
        return None
