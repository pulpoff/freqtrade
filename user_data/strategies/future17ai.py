from functools import reduce
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter
from skopt.space import Integer, Real, Categorical, Dimension

class future17ai(IStrategy):
    # ROI table for profit taking
    minimal_roi = {
        "0": 0.05,    # Take 5% profit immediately
        "5": 0.03,    # 3% after 5 minutes
        "15": 0.02,   # 2% after 15 minutes
        "30": 0       # Any profit after 30 minutes
    }

    # Risk parameters
    stoploss = -0.10  # Stoploss setting
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = False

    # FreqAI configuration
    freqai_config = {
        "enabled": True,
        "feature_parameters": {
            "include_timeframes": ["1m", "5m", "15m"],  # Multiple timeframes for context
            "include_corr_pairlist": ["BTC/USDT:USDT", "ETH/USDT:USDT"],  # Correlated pairs
            "label_period_candles": 10,  # Predict price movement 10 candles ahead
            "include_shifted_candles": 3,  # Include 3 previous candles
            "weight_factor": 0.9,  # Weight recent data more
            "DI_threshold": 0.2,  # Data importance threshold
            "principal_component_analysis": False,
            "use_SVM_to_remove_outliers": True,
            "stratify_training_data": True,
            "indicator_periods_candles": [3, 5, 10, 20, 30]  # Multiple periods for indicators
        },
        "data_split_parameters": {
            "test_size": 0.15,
            "shuffle": False,
            "train_period_days": 30
        },
        "model_training_parameters": {
            "n_estimators": 500,
            "model_type": "LightGBMRegressor",
            "reduce_overfitting": True,
            "save_backtest_models": True,
            "lambda_l1": 0.001,
            "lambda_l2": 0.001
        },
        "prediction_parameters": {
            "live_retrain_hours": 1,  # Retrain model hourly
            "write_metrics": True,
            "pred_win_size": 10
        },
        "identifier": "future17",  # Unique identifier for this strategy's models
        "purge_old_models": True,
        "fit_live_predictions_candles": 300
    }

    # Hyperoptable parameters
    # Leverage
    leverage_param = IntParameter(1, 10, default=5, space="buy", optimize=True)
    
    # FreqAI specific parameters
    short_pred_threshold = DecimalParameter(-0.05, -0.01, default=-0.03, space="buy", optimize=True)
    short_prob_threshold = DecimalParameter(0.55, 0.95, default=0.75, space="buy", optimize=True)
    exit_short_pred_threshold = DecimalParameter(0.005, 0.02, default=0.01, space="sell", optimize=True)
    exit_short_prob_threshold = DecimalParameter(0.55, 0.9, default=0.7, space="sell", optimize=True)
    
    # RSI thresholds - keep for combined approach
    buy_rsi = IntParameter(30, 50, default=40, space="buy", optimize=True)
    sell_rsi_upper = IntParameter(60, 85, default=70, space="sell", optimize=True)
    sell_rsi_lower = IntParameter(20, 40, default=30, space="sell", optimize=True)
    
    # MACD parameters - keep for combined approach
    macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
    macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
    
    # Moving average parameters - keep for combined approach
    ema_short_period = IntParameter(5, 15, default=8, space="both", optimize=True)
    ema_long_period = IntParameter(15, 30, default=21, space="both", optimize=True)
    
    # Price extension threshold - keep for combined approach
    price_extension_pct = DecimalParameter(0.003, 0.01, default=0.005, space="sell", optimize=True)
    
    # Strategy settings
    timeframe = '1m'
    startup_candle_count = 100
    process_only_new_candles = True
    can_short = True
    can_long = False  # Focusing only on shorts

    # Cooldown tracking
    _last_candle_seen_time = {}

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_candle_seen_time = {}

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int, 
                                       metadata: dict, **kwargs) -> DataFrame:
        """
        Create additional features and add them to the dataframe
        """
        # Technical indicators at multiple timeframes
        for t in self.freqai_config["feature_parameters"]["indicator_periods_candles"]:
            dataframe[f'rsi_{t}'] = ta.RSI(dataframe, timeperiod=t)
            dataframe[f'mfi_{t}'] = ta.MFI(dataframe, timeperiod=t)
            dataframe[f'adx_{t}'] = ta.ADX(dataframe, timeperiod=t)
            
            # Bollinger Bands
            bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=t, stds=2)
            dataframe[f'bb_lowerband_{t}'] = bollinger['lower']
            dataframe[f'bb_middleband_{t}'] = bollinger['mid']
            dataframe[f'bb_upperband_{t}'] = bollinger['upper']
            dataframe[f'bb_width_{t}'] = (bollinger['upper'] - bollinger['lower']) / bollinger['mid']
            
            # MACD with different periods
            macd = ta.MACD(dataframe, fastperiod=self.macd_fast.value, 
                           slowperiod=self.macd_slow.value, signalperiod=self.macd_signal.value)
            dataframe[f'macd_{t}'] = macd['macd']
            dataframe[f'macdsignal_{t}'] = macd['macdsignal']
            dataframe[f'macdhist_{t}'] = macd['macdhist']
            
            # Stochastic
            stoch = ta.STOCH(dataframe, fastk_period=t, slowk_period=3, slowd_period=3)
            dataframe[f'slowk_{t}'] = stoch['slowk']
            dataframe[f'slowd_{t}'] = stoch['slowd']
            
            # Add EMAs for various periods
            dataframe[f'ema_{t}'] = ta.EMA(dataframe, timeperiod=t)
            
            # ATR-based features
            dataframe[f'atr_{t}'] = ta.ATR(dataframe, timeperiod=t)
            dataframe[f'atr_pct_{t}'] = dataframe[f'atr_{t}'] / dataframe['close']
            
            # Parabolic SAR
            dataframe[f'sar_{t}'] = ta.SAR(dataframe)
        
        # Price action features
        dataframe['price_change'] = (dataframe['close'] - dataframe['open']) / dataframe['open']
        dataframe['body_pct'] = abs(dataframe['close'] - dataframe['open']) / (dataframe['high'] - dataframe['low'])
        dataframe['upper_wick_pct'] = (dataframe['high'] - dataframe[['open', 'close']].max(axis=1)) / (dataframe['high'] - dataframe['low'])
        dataframe['lower_wick_pct'] = (dataframe[['open', 'close']].min(axis=1) - dataframe['low']) / (dataframe['high'] - dataframe['low'])
        
        # Volume features
        dataframe['volume_change'] = dataframe['volume'] / dataframe['volume'].shift(1)
        dataframe['volume_ma10'] = dataframe['volume'].rolling(10).mean()
        dataframe['volume_relative'] = dataframe['volume'] / dataframe['volume_ma10']
        
        # Trend features
        dataframe['close_change_1'] = dataframe['close'].pct_change(1)
        dataframe['close_change_2'] = dataframe['close'].pct_change(2)
        dataframe['close_change_5'] = dataframe['close'].pct_change(5)
        dataframe['close_change_10'] = dataframe['close'].pct_change(10)
        
        # Market regime indicators
        dataframe['volatility'] = dataframe['close'].rolling(20).std() / dataframe['close'].rolling(20).mean()
        
        # Add distance from moving averages
        for t in [7, 25, 50, 100]:
            dataframe[f'ma_{t}'] = ta.SMA(dataframe, timeperiod=t)
            dataframe[f'close_rel_ma_{t}'] = dataframe['close'] / dataframe[f'ma_{t}']
        
        # Feature interactions - these can be very powerful
        dataframe['rsi_diff'] = dataframe['rsi_10'] - dataframe['rsi_30']
        dataframe['macd_diff'] = dataframe['macd_10'] - dataframe['macd_30']
        dataframe['bb_squeeze'] = (dataframe['bb_upperband_20'] - dataframe['bb_lowerband_20']) / dataframe['bb_middleband_20']
        
        # Heikin Ashi candles
        dataframe['ha_open'] = (dataframe['open'].shift(1) + dataframe['close'].shift(1)) / 2
        dataframe['ha_close'] = (dataframe['open'] + dataframe['high'] + dataframe['low'] + dataframe['close']) / 4
        dataframe['ha_high'] = dataframe[['high', 'ha_open', 'ha_close']].max(axis=1)
        dataframe['ha_low'] = dataframe[['low', 'ha_open', 'ha_close']].min(axis=1)
        
        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        Simpler feature engineering method for creating basic features in live mode
        """
        # Just use the same function for both
        return self.feature_engineering_expand_all(dataframe, 0, metadata, **kwargs)

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        """
        Set targets for the FreqAI model
        """
        # Calculate future price movements for different periods
        for n in range(1, 11):  # Predict 1 to 10 candles ahead
            dataframe[f'future_price_{n}'] = dataframe['close'].shift(-n)
            dataframe[f'future_pct_change_{n}'] = (dataframe[f'future_price_{n}'] - dataframe['close']) / dataframe['close']
        
        # Main prediction target (10 candles ahead)
        dataframe['&s-up_or_down'] = dataframe['future_pct_change_10']
        
        # Binary classification target (will price go up or down)
        dataframe['&s-direction'] = np.where(dataframe['future_pct_change_10'] > 0, 1, 0)
        
        # Calculate the max down/up move within prediction window
        # This can help identify potential profit targets
        max_down_columns = []
        max_up_columns = []
        
        for n in range(1, 11):
            max_down_columns.append(f'future_pct_change_{n}')
            max_up_columns.append(f'future_pct_change_{n}')
        
        dataframe['&s-max_down'] = dataframe[max_down_columns].min(axis=1)
        dataframe['&s-max_up'] = dataframe[max_up_columns].max(axis=1)
        
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Create traditional strategy indicators - these will work alongside FreqAI
        These are kept from the original strategy as a backup/complementary approach
        """
        # RSI indicator
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Stochastic
        stoch = ta.STOCH(dataframe, fastk_period=14, slowk_period=3, slowd_period=3)
        dataframe['slowk'] = stoch['slowk']
        dataframe['slowd'] = stoch['slowd']
        
        # MACD with hyperoptable parameters
        macd = ta.MACD(dataframe, 
                      fastperiod=self.macd_fast.value,
                      slowperiod=self.macd_slow.value, 
                      signalperiod=self.macd_signal.value)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Store shifted values for pattern detection
        dataframe['macdhist_prev1'] = dataframe['macdhist'].shift(1)
        dataframe['macdhist_prev2'] = dataframe['macdhist'].shift(2)
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_lowerband'] = bollinger['lower']
        
        # Moving averages with hyperoptable parameters
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=self.ema_short_period.value)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=self.ema_long_period.value)
        
        # Store shifted prices
        for i in range(1, 4):
            dataframe[f'close_prev{i}'] = dataframe['close'].shift(i)
            dataframe[f'high_prev{i}'] = dataframe['high'].shift(i)
            dataframe[f'low_prev{i}'] = dataframe['low'].shift(i)
        
        # Detect peaks - when current price is at or near local maximum
        dataframe['high_last_3'] = dataframe['high'].rolling(3).max()
        
        # Price is at a local peak
        dataframe['price_peak'] = (
            (dataframe['high'] >= dataframe['high_last_3'] * 0.995) &
            (dataframe['high'] > dataframe['high_prev1']) &
            (dataframe['close'] > dataframe['ema_short']) &
            (dataframe['rsi'] > self.sell_rsi_upper.value)
        )
        
        # Price reversal after a rise
        dataframe['price_reversal'] = (
            (dataframe['close_prev2'] < dataframe['close_prev1']) &
            (dataframe['close'] < dataframe['close_prev1']) &
            (dataframe['close_prev1'] > dataframe['close_prev1'].rolling(3).max().shift(1)) &
            (dataframe['rsi'] > self.sell_rsi_upper.value * 0.9)
        )
        
        # MACD histogram reversal
        dataframe['macd_reversal'] = (
            (dataframe['macdhist_prev2'] < dataframe['macdhist_prev1']) &
            (dataframe['macdhist'] < dataframe['macdhist_prev1']) &
            (dataframe['macdhist_prev1'] > 0) &
            (dataframe['close'] > dataframe['ema_short'])
        )
        
        # Combined traditional entry signal
        dataframe['short_entry_traditional'] = (
            (dataframe['price_peak'] | dataframe['price_reversal'] | dataframe['macd_reversal']) &
            (dataframe['rsi'] > self.sell_rsi_upper.value * 0.9) &
            (dataframe['close'] > dataframe['ema_short'] * (1 + self.price_extension_pct.value))
        )
        
        # Traditional exit signals
        dataframe['deep_oversold'] = (
            (dataframe['rsi'] < self.sell_rsi_lower.value * 0.9) &
            (dataframe['close'] < dataframe['bb_lowerband'] * 1.01) &
            (dataframe['close'] < dataframe['ema_short'] * 0.99)
        )
        
        dataframe['major_trend_reversal'] = (
            qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal']) &
            (dataframe['macd'] < 0) &
            (dataframe['macdhist'] > dataframe['macdhist'].shift(1) * 1.2) &
            (dataframe['close'] < dataframe['ema_short'])
        )
        
        dataframe['short_exit_traditional'] = (
            dataframe['deep_oversold'] | 
            dataframe['major_trend_reversal']
        )
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Combined entry signals using both FreqAI and traditional approach"""
        dataframe.loc[:, 'enter_long'] = 0
        dataframe.loc[:, 'enter_short'] = 0
        
        # First check if FreqAI columns exist in the dataframe
        freqai_columns_exist = all(col in dataframe.columns for col in ['&s-up_or_down', '&s-prediction_probability', 'do_predict'])
        
        if freqai_columns_exist:
            # FreqAI-based entry signal
            freqai_short_conditions = (
                (dataframe['do_predict'] == 1) &  # FreqAI is ready
                (dataframe['&s-up_or_down'] < self.short_pred_threshold.value) &  # Predicts price drop
                (dataframe['&s-prediction_probability'] > self.short_prob_threshold.value)  # High confidence
            )
            
            # Apply FreqAI signals where available
            dataframe.loc[freqai_short_conditions, 'enter_short'] = 1
        
        # Always apply traditional signals as backup
        dataframe.loc[dataframe['short_entry_traditional'], 'enter_short'] = 1
        
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                           side: str, **kwargs) -> bool:
        """Cooldown logic between trades"""
        # Check cooldown period (3 minutes between trades of same pair)
        cooldown_minutes = 3
        
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
                
        # Update the last seen time for this pair
        self._last_candle_seen_time[pair] = current_time
        
        return True

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Combined exit signals using both FreqAI and traditional approach"""
        dataframe.loc[:, 'exit_long'] = 0
        dataframe.loc[:, 'exit_short'] = 0
        
        # First check if FreqAI columns exist in the dataframe
        freqai_columns_exist = all(col in dataframe.columns for col in ['&s-up_or_down', '&s-prediction_probability', 'do_predict'])
        
        if freqai_columns_exist:
            # FreqAI-based exit signal
            freqai_exit_conditions = (
                (dataframe['do_predict'] == 1) &  # FreqAI is ready
                (dataframe['&s-up_or_down'] > self.exit_short_pred_threshold.value) &  # Predicts price increase
                (dataframe['&s-prediction_probability'] > self.exit_short_prob_threshold.value)  # High confidence
            )
            
            # Apply FreqAI signals where available
            dataframe.loc[freqai_exit_conditions, 'exit_short'] = 1
        
        # Always apply traditional signals as backup
        dataframe.loc[dataframe['short_exit_traditional'], 'exit_short'] = 1
        
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """Custom exit logic - working alongside FreqAI signals"""
        if trade.is_short:
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if len(dataframe) > 0:
                    last_candle = dataframe.iloc[-1]
                    
                    # Take profit targets
                    if current_profit > 0.05:
                        return 'short_profit_target_reached'
                    
                    # Check FreqAI predictions if available
                    freqai_cols_exist = all(col in last_candle.index for col in 
                                           ['&s-up_or_down', '&s-prediction_probability', 'do_predict'])
                    
                    if freqai_cols_exist and last_candle['do_predict'] == 1:
                        # If FreqAI strongly predicts price increase and we have profit, exit
                        if (last_candle['&s-up_or_down'] > 0.02 and 
                            last_candle['&s-prediction_probability'] > 0.8 and
                            current_profit > 0.01):
                            return 'freqai_strong_reversal_signal'
                        
                        # If max downside prediction is reached, take profit
                        if ('&s-max_down' in last_candle.index and 
                            current_profit >= abs(last_candle['&s-max_down']) * 0.8):
                            return 'freqai_max_down_target_reached'
                    
                    # Traditional exit conditions
                    if current_profit > 0.02 and 'rsi' in last_candle and last_candle['rsi'] < 25:
                       return 'short_profit_extreme_oversold'
                    
            except Exception as e:
                pass
        
        return None

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: float, max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """Adjust position size based on prediction confidence"""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) == 0:
                return proposed_stake
                
            current_candle = dataframe.iloc[-1]
            
            # Check if FreqAI columns exist
            freqai_cols_exist = all(col in current_candle.index for col in 
                                   ['&s-up_or_down', '&s-prediction_probability', 'do_predict'])
            
            if side == 'short' and freqai_cols_exist and current_candle['do_predict'] == 1:
                confidence = current_candle['&s-prediction_probability']
                pred_magnitude = abs(current_candle['&s-up_or_down'])
                
                # Scale stake based on confidence and predicted magnitude
                if confidence > 0.9 and pred_magnitude > 0.05:
                    return min(proposed_stake * 2, max_stake)
                elif confidence > 0.8 and pred_magnitude > 0.03:
                    return min(proposed_stake * 1.5, max_stake)
                elif confidence < 0.6:
                    return min_stake  # Minimum stake for low confidence
        except Exception as e:
            pass
            
        return proposed_stake

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
                **kwargs) -> float:
        """Dynamic leverage based on prediction confidence"""
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) == 0:
                return min(self.leverage_param.value, max_leverage)
                
            current_candle = dataframe.iloc[-1]
            
            # Check if FreqAI columns exist
            freqai_cols_exist = all(col in current_candle.index for col in 
                                   ['&s-up_or_down', '&s-prediction_probability', 'do_predict'])
            
            if side == 'short' and freqai_cols_exist and current_candle['do_predict'] == 1:
                confidence = current_candle['&s-prediction_probability']
                pred_magnitude = abs(current_candle['&s-up_or_down'])
                
                # Adjust leverage based on prediction confidence and magnitude
                if confidence > 0.9 and pred_magnitude > 0.05:
                    return min(self.leverage_param.value, max_leverage)
                elif confidence > 0.8 and pred_magnitude > 0.03:
                    return min(self.leverage_param.value * 0.8, max_leverage)
                else:
                    return min(self.leverage_param.value * 0.6, max_leverage)
        except Exception as e:
            pass
            
        return min(self.leverage_param.value, max_leverage)

    def hyperopt_space(self) -> List[Dimension]:
        """Define hyperopt space including FreqAI parameters"""
        return [
            Integer(1, 10, name='leverage_param'),
            Integer(30, 50, name='buy_rsi'),
            Integer(60, 85, name='sell_rsi_upper'),
            Integer(20, 40, name='sell_rsi_lower'),
            Integer(8, 16, name='macd_fast'),
            Integer(18, 32, name='macd_slow'),
            Integer(6, 12, name='macd_signal'),
            Integer(5, 15, name='ema_short_period'),
            Integer(15, 30, name='ema_long_period'),
            Real(0.003, 0.01, name='price_extension_pct'),
            # FreqAI specific parameters
            Real(-0.05, -0.01, name='short_pred_threshold'),
            Real(0.55, 0.95, name='short_prob_threshold'),
            Real(0.005, 0.02, name='exit_short_pred_threshold'),
            Real(0.55, 0.9, name='exit_short_prob_threshold')
        ]
