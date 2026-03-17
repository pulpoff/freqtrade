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

class future67(IStrategy):
    """
    Advanced FreqAI Strategy with FULL Dynamic Parameters
    
    ML Predicts EVERYTHING:
    1. Entry signals (long/short probability)
    2. Optimal leverage (3-10x per trade)  
    3. Dynamic ROI targets (profit-taking)
    4. Optimal hold time
    5. Position sizing
    
    Everything adapts to market conditions!
    """
    
    process_only_new_candles = True
    use_exit_signal = False 
    startup_candle_count = 200
    can_short = True
    can_long = True
    
    # Fallback ROI (if ML unavailable)
    minimal_roi = {
        "0": 0.20,
        "15": 0.12,
        "45": 0.06,
        "90": 0.03,
        "150": 0.01,
    }
    
    stoploss = -0.10
    
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True
    
    max_open_trades = 25
    timeframe = '5m'
    
    # Plot ML predictions
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
                '&-pred_roi': {'color': 'orange'},
            }
        }
    }
    
    # Parameters
    leverage_fallback = IntParameter(3, 8, default=4, space="both", optimize=False)
    ml_confidence_long = DecimalParameter(0.5, 0.85, default=0.65, space="buy", optimize=True)
    ml_confidence_short = DecimalParameter(0.5, 0.85, default=0.65, space="sell", optimize=True)
    min_leverage = IntParameter(2, 5, default=3, space="both", optimize=False)
    max_leverage = IntParameter(6, 10, default=8, space="both", optimize=False)
    min_roi = DecimalParameter(0.01, 0.05, default=0.02, space="both", optimize=False)
    max_roi = DecimalParameter(0.15, 0.35, default=0.25, space="both", optimize=False)

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

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int,
                                       metadata: dict, **kwargs) -> DataFrame:
        # Price momentum
        dataframe[f'%-roc_{period}'] = dataframe['close'].pct_change(period) * 100
        dataframe[f'%-price_velocity_{period}'] = dataframe['close'].pct_change(period) * 100
        
        # RSI
        dataframe[f'%-rsi_{period}'] = ta.RSI(dataframe, timeperiod=period)
        dataframe[f'%-rsi_change_{period}'] = dataframe[f'%-rsi_{period}'].diff()
        
        # EMAs
        dataframe[f'%-ema_fast_{period}'] = ta.EMA(dataframe, timeperiod=int(period * 0.5))
        dataframe[f'%-ema_slow_{period}'] = ta.EMA(dataframe, timeperiod=period)
        dataframe[f'%-ema_diff_{period}'] = (
            (dataframe[f'%-ema_fast_{period}'] - dataframe[f'%-ema_slow_{period}']) / 
            dataframe['close'] * 100
        )
        
        # Volatility
        dataframe[f'%-atr_{period}'] = ta.ATR(dataframe, timeperiod=period)
        dataframe[f'%-atr_pct_{period}'] = (dataframe[f'%-atr_{period}'] / dataframe['close']) * 100
        
        # Bollinger Bands
        bb = ta.BBANDS(dataframe, timeperiod=period, nbdevup=2.0, nbdevdn=2.0)
        dataframe[f'%-bb_width_{period}'] = (bb['upperband'] - bb['lowerband']) / bb['middleband'] * 100
        dataframe[f'%-bb_position_{period}'] = (
            (dataframe['close'] - bb['lowerband']) / (bb['upperband'] - bb['lowerband']) * 100
        )
        
        # Volume
        dataframe[f'%-volume_ratio_{period}'] = (
            dataframe['volume'] / dataframe['volume'].rolling(period).mean()
        )
        
        # MACD
        macd = ta.MACD(dataframe, fastperiod=int(period*0.5), slowperiod=period, signalperiod=int(period*0.35))
        dataframe[f'%-macd_{period}'] = macd['macd']
        dataframe[f'%-macd_hist_{period}'] = macd['macdhist']
        
        # Price patterns
        dataframe[f'%-higher_high_{period}'] = (
            dataframe['high'] > dataframe['high'].shift(1).rolling(period).max()
        ).astype(int)
        dataframe[f'%-lower_low_{period}'] = (
            dataframe['low'] < dataframe['low'].shift(1).rolling(period).min()
        ).astype(int)
        
        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        dataframe['%-current_hour'] = dataframe['date'].dt.hour
        dataframe['%-day_of_week'] = dataframe['date'].dt.dayofweek
        dataframe['%-high_low_range'] = (dataframe['high'] - dataframe['low']) / dataframe['close'] * 100
        dataframe['%-consecutive_green'] = (dataframe['close'] > dataframe['open']).rolling(5).sum()
        dataframe['%-consecutive_red'] = (dataframe['close'] < dataframe['open']).rolling(5).sum()
        return dataframe

    def feature_engineering_standard(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=10)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=26)
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['volume_ma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_ma']
        
        bb = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_width'] = (bb['upperband'] - bb['lowerband']) / bb['middleband']
        
        dataframe = self.add_higher_tf_data(dataframe, metadata)
        return dataframe

    def add_higher_tf_data(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        for tf, tf_name in [('15m', '15m'), ('1h', '1h')]:
            inf_df = self.dp.get_pair_dataframe(metadata['pair'], tf)
            if not inf_df.empty:
                inf_df[f'ema_fast_{tf_name}'] = ta.EMA(inf_df, timeperiod=10)
                inf_df[f'ema_slow_{tf_name}'] = ta.EMA(inf_df, timeperiod=26)
                inf_df[f'trend_{tf_name}'] = np.where(
                    inf_df[f'ema_fast_{tf_name}'] > inf_df[f'ema_slow_{tf_name}'], 1, -1
                )
                dataframe = merge_informative_pair(
                    dataframe, inf_df[['date', f'trend_{tf_name}']], 
                    self.timeframe, tf, ffill=True
                )
            else:
                dataframe[f'trend_{tf_name}'] = 0
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """Define all ML targets"""
        
        # Calculate future returns
        horizons = [5, 10, 20, 40]
        for shift in horizons:
            dataframe[f'future_return_{shift}'] = (
                (dataframe['close'].shift(-shift) - dataframe['close']) / dataframe['close'] * 100
            )
            dataframe[f'future_high_{shift}'] = (
                (dataframe['high'].rolling(shift).max().shift(-shift) - dataframe['close']) / 
                dataframe['close'] * 100
            )
            dataframe[f'future_low_{shift}'] = (
                (dataframe['low'].rolling(shift).min().shift(-shift) - dataframe['close']) / 
                dataframe['close'] * 100
            )
        
        # TARGET 1 & 2: Entry signals
        dataframe['&-long_target'] = (
            (dataframe['future_high_20'] > 2.0) | (dataframe['future_high_40'] > 2.5)
        ).astype(int)
        
        dataframe['&-short_target'] = (
            (dataframe['future_low_20'] < -2.0) | (dataframe['future_low_40'] < -2.5)
        ).astype(int)
        
        # TARGET 3: Optimal Leverage
        dataframe['recent_volatility'] = dataframe['atr'].rolling(20).mean() / dataframe['close'] * 100
        dataframe['max_expected_return'] = dataframe[[f'future_high_{h}' for h in horizons]].max(axis=1).abs()
        
        dataframe['&-leverage_target'] = np.clip(
            6 - (dataframe['recent_volatility'] - 2.5) * 1.5 + (dataframe['max_expected_return'] / 5.0),
            3, 10
        )
        
        # TARGET 4: Dynamic ROI
        dataframe['trend_strength'] = abs(
            (dataframe['ema_fast'] - dataframe['ema_slow']) / dataframe['close'] * 100
        )
        
        dataframe['&-roi_target'] = np.clip(
            0.05 + (dataframe['recent_volatility'] * 2.0) + (dataframe['trend_strength'] * 1.5),
            0.02, 0.30
        )
        
        # TARGET 5: Optimal hold time
        max_profit_indices = []
        for idx in range(len(dataframe)):
            if idx < len(dataframe) - 40:
                future_returns = [dataframe[f'future_return_{h}'].iloc[idx] for h in horizons]
                max_profit_indices.append(horizons[np.argmax(np.abs(future_returns))])
            else:
                max_profit_indices.append(20)
        
        dataframe['&-optimal_hold_time'] = max_profit_indices
        
        # Cleanup
        drop_cols = (
            [f'future_return_{h}' for h in horizons] + 
            [f'future_high_{h}' for h in horizons] + 
            [f'future_low_{h}' for h in horizons] +
            ['recent_volatility', 'max_expected_return', 'trend_strength']
        )
        dataframe.drop(columns=drop_cols, inplace=True, errors='ignore')
        
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.feature_engineering_standard(dataframe, metadata)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        has_predictions = (
            '&-pred_long_target' in dataframe.columns and
            '&-pred_short_target' in dataframe.columns
        )
        
        if has_predictions:
            logger.info(f"Using FreqAI predictions for {metadata['pair']}")
            
            # LONG
            long_conditions = [
                (dataframe['&-pred_long_target'] > self.ml_confidence_long.value),
                (dataframe['rsi'] > 35),
                (dataframe['rsi'] < 80),
                (dataframe['bb_width'] > 0.015),
                (dataframe['volume_ratio'] > 0.7),
            ]
            if 'trend_15m' in dataframe.columns:
                long_conditions.append(dataframe['trend_15m'] >= 0)
            
            dataframe.loc[reduce(lambda x, y: x & y, long_conditions), 'enter_long'] = 1
            
            # SHORT
            short_conditions = [
                (dataframe['&-pred_short_target'] > self.ml_confidence_short.value),
                (dataframe['rsi'] > 20),
                (dataframe['rsi'] < 65),
                (dataframe['bb_width'] > 0.015),
                (dataframe['volume_ratio'] > 0.7),
            ]
            if 'trend_15m' in dataframe.columns:
                short_conditions.append(dataframe['trend_15m'] <= 0)
            
            dataframe.loc[reduce(lambda x, y: x & y, short_conditions), 'enter_short'] = 1
        else:
            logger.warning(f"FreqAI predictions not available, using fallback")
            dataframe = self.populate_entry_fallback(dataframe, metadata)
        
        return dataframe

    def populate_entry_fallback(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['long_score'] = 0
        dataframe['short_score'] = 0
        dataframe['trend_up'] = dataframe['ema_fast'] > dataframe['ema_slow']
        dataframe['trend_down'] = dataframe['ema_fast'] < dataframe['ema_slow']
        dataframe['roc_3'] = dataframe['close'].pct_change(3) * 100
        
        dataframe.loc[dataframe['trend_up'], 'long_score'] += 2
        dataframe.loc[dataframe['roc_3'] > 0.3, 'long_score'] += 1
        dataframe.loc[dataframe['rsi'] > 50, 'long_score'] += 1
        dataframe.loc[dataframe['volume_ratio'] > 1.2, 'long_score'] += 1
        
        dataframe.loc[dataframe['trend_down'], 'short_score'] += 2
        dataframe.loc[dataframe['roc_3'] < -0.3, 'short_score'] += 1
        dataframe.loc[dataframe['rsi'] < 50, 'short_score'] += 1
        dataframe.loc[dataframe['volume_ratio'] > 1.2, 'short_score'] += 1
        
        dataframe.loc[dataframe['long_score'] >= 4, 'enter_long'] = 1
        dataframe.loc[dataframe['short_score'] >= 4, 'enter_short'] = 1
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """ML-predicted dynamic leverage"""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if dataframe.empty:
                return self.leverage_fallback.value
            
            last_candle = dataframe.iloc[-1]
            if '&-pred_leverage_target' in last_candle:
                ml_leverage = last_candle['&-pred_leverage_target']
                safe_leverage = np.clip(ml_leverage, self.min_leverage.value, 
                                       min(self.max_leverage.value, max_leverage))
                logger.info(f"{pair} {side}: ML leverage={ml_leverage:.1f}, using={safe_leverage:.1f}")
                return float(safe_leverage)
        except Exception as e:
            logger.error(f"Error getting leverage: {e}")
        return self.leverage_fallback.value

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, 
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """ML-driven dynamic exits"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        
        last_candle = dataframe.iloc[-1]
        
        # Exit at ML-predicted ROI
        if '&-pred_roi_target' in last_candle:
            predicted_roi = last_candle['&-pred_roi_target']
            if current_profit >= (predicted_roi * 0.9):
                logger.info(f"{pair}: Hit ML ROI {predicted_roi:.2%}, profit={current_profit:.2%}")
                return 'ml_roi_target_reached'
        
        # Exit at optimal hold time
        if '&-pred_optimal_hold_time' in last_candle:
            optimal_hold = last_candle['&-pred_optimal_hold_time']
            trade_duration = (current_time - trade.open_date_utc).total_seconds() / 60
            candles_held = trade_duration / 5
            if candles_held > (optimal_hold * 1.5):
                logger.info(f"{pair}: Exceeded optimal hold time")
                return 'ml_optimal_time_exceeded'
        
        # ML reversal
        if '&-pred_long_target' in last_candle and '&-pred_short_target' in last_candle:
            if trade.is_short and last_candle['&-pred_long_target'] > 0.8:
                return 'ml_reversal_signal'
            elif not trade.is_short and last_candle['&-pred_short_target'] > 0.8:
                return 'ml_reversal_signal'
        
        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                           side: str, **kwargs) -> bool:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return False
        
        last_candle = dataframe.iloc[-1]
        
        if last_candle.get('bb_width', 0) < 0.01:
            return False
        if last_candle.get('volume_ratio', 0) < 0.5:
            return False
        
        rsi = last_candle.get('rsi', 50)
        if side == 'long' and (rsi > 80 or rsi < 30):
            return False
        if side == 'short' and (rsi < 20 or rsi > 70):
            return False
        
        # Don't enter if ML predicts low ROI
        if '&-pred_roi_target' in last_candle:
            if last_candle['&-pred_roi_target'] < 0.015:
                return False
        
        return True

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                       current_rate: float, current_profit: float,
                       after_fill: bool, **kwargs) -> Optional[float]:
        """Dynamic stop adapting to ML-predicted ROI"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        
        last_candle = dataframe.iloc[-1]
        atr = last_candle.get('atr', 0)
        
        if atr > 0:
            atr_stop = (atr * 2.5) / current_rate
            
            # Adapt based on ML ROI prediction
            roi_multiplier = 1.0
            if '&-pred_roi_target' in last_candle:
                predicted_roi = last_candle['&-pred_roi_target']
                if predicted_roi > 0.15:
                    roi_multiplier = 1.3  # Wider stop for high ROI
                elif predicted_roi < 0.05:
                    roi_multiplier = 0.7  # Tighter for low ROI
            
            if current_profit > 0.12:
                return -0.02 * roi_multiplier
            elif current_profit > 0.08:
                return -0.03 * roi_multiplier
            elif current_profit > 0.04:
                return -0.045 * roi_multiplier
            else:
                return max(-min(atr_stop * roi_multiplier, 0.12), self.stoploss)
        
        return None
