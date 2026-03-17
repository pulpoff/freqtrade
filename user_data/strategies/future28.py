from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter
from skopt.space import Integer, Real, Categorical, Dimension

from freqtrade.freqai.prediction_models.XGBoostRegressor import XGBoostRegressor
from freqtrade.freqai.base_models.BaseRegressionModel import BaseRegressionModel
from freqtrade.freqai.data_kitchen import FreqaiDataKitchen

class future28(IStrategy):
    # Faster profit-taking ROI
    minimal_roi = {
        "0": 0.06,    # Take 2% profit immediately
        "5": 0.045,   # 1.5% after 5 minutes
        "10": 0.03,   # 1% after 10 minutes
        "15": 0.005,  # 0.5% after 15 minutes
    }

    # Tighter risk parameters
    stoploss = -0.09  # Smaller stoploss
    trailing_stop = True
    trailing_stop_positive = 0.02  # Start trailing at 1%
    trailing_stop_positive_offset = 0.025  # Offset by 1.5%
    trailing_only_offset_is_reached = True  # Only trail after reaching the offset

    # Strategy settings
    timeframe = '1m'
    startup_candle_count = 30
    process_only_new_candles = True
    can_short = True
    can_long = False  # Focusing only on shorts

    # Default parameters
    default_leverage_param = IntParameter(1, 3, default=2, space="buy", optimize=True)
    default_rsi_period = IntParameter(10, 20, default=14, space="buy", optimize=True)
    default_rsi_upper = IntParameter(65, 85, default=70, space="sell", optimize=True)
    default_rsi_lower = IntParameter(20, 35, default=30, space="sell", optimize=True)
    default_ema_period = IntParameter(5, 20, default=10, space="both", optimize=True)
    default_macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    default_macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
    default_macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
    default_use_profit_only = CategoricalParameter([True, False], default=True, space="sell", optimize=True)
    
    # FreqAI settings
    freqai_conf = {
        "enabled": True,
        "purge_old_models": True,
        "train_period_days": 7,
        "backtest_period_days": 2,
        "identifier": "future28",
        "feature_parameters": {
            "include_timeframes": ["1m"],
            "include_corr_pairlist": [
                "BTC/USDT:USDT",
                "ETH/USDT:USDT"
            ],
            "label_period_candles": 20,
            "include_shifted_candles": 0,
            "DI_threshold": 0.0,
            "weight_factor": 0.9,
            "principal_component_analysis": False,
            "use_SVM_to_remove_outliers": False,
            "stratify_training_data": 0,
            "indicator_max_period_candles": 20,
            "indicator_periods_candles": [10, 15, 20]
        },
        "data_split_parameters": {
            "test_size": 0.15,
            "random_state": 42,
            "shuffle": False
        },
        "model_training_parameters": {
            "n_estimators": 100,
            "learning_rate": 0.05,
            "max_depth": 5,
            "gamma": 0.05,
            "subsample": 0.7,
            "colsample_bytree": 0.7,
            "tree_method": "gpu_hist",
            "predictor": "gpu_predictor",
            "objective": "reg:squarederror",
            "verbosity": 0,
            "random_state": 42
        }
    }
    
    # Cooldown tracking
    _last_candle_seen_time = {}
    # Dictionary to store coin-specific parameters
    _coin_params = {}
    # List of supported coins (will be populated from config)
    _supported_coins = []
    
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_candle_seen_time = {}
        self._supported_coins = []
        # Initialize freqai_info attribute
        self.freqai_info = None
        
        # Extract coins from config pairs
        if config.get('exchange', {}).get('pair_whitelist'):
            for pair in config['exchange']['pair_whitelist']:
                coin = self.get_coin_from_pair(pair)
                if coin and coin not in self._supported_coins:
                    self._supported_coins.append(coin)
        
        # Initialize parameters for each coin
        self._coin_params = self._init_dynamic_coin_params()

    def _init_dynamic_coin_params(self):
        """Dynamically create parameters for each coin in whitelist"""
        params = {}
        
        for coin in self._supported_coins:
            # Basic parameters
            params[f"{coin}_leverage_param"] = IntParameter(1, 3, default=2, space="buy", optimize=True)
            params[f"{coin}_rsi_period"] = IntParameter(10, 20, default=14, space="buy", optimize=True)
            params[f"{coin}_rsi_upper"] = IntParameter(65, 85, default=70, space="sell", optimize=True)
            params[f"{coin}_rsi_lower"] = IntParameter(20, 35, default=30, space="sell", optimize=True)
            params[f"{coin}_ema_period"] = IntParameter(5, 20, default=10, space="both", optimize=True)
            
            # MACD parameters
            params[f"{coin}_macd_fast"] = IntParameter(8, 16, default=12, space="both", optimize=True)
            params[f"{coin}_macd_slow"] = IntParameter(18, 32, default=26, space="both", optimize=True)
            params[f"{coin}_macd_signal"] = IntParameter(6, 12, default=9, space="both", optimize=True)
            
            # Profit-only parameter
            params[f"{coin}_use_profit_only"] = CategoricalParameter([True, False], default=True, space="sell", optimize=True)
            
            # Register the parameters with the strategy
            for param_name, param_obj in params.items():
                if param_name.startswith(f"{coin}_"):
                    setattr(self, param_name, param_obj)
        
        return params

    def get_coin_from_pair(self, pair: str) -> str:
        """Extract coin symbol from pair"""
        if '/' in pair:
            coin = pair.split('/')[0]
            return coin
        return ""

    def get_param_value(self, coin: str, param_name: str):
        """Get coin-specific parameter value or fall back to default"""
        full_param_name = f"{coin}_{param_name}"
        
        if hasattr(self, full_param_name):
            return getattr(self, full_param_name).value
        
        # Fall back to default parameter
        default_param_name = f"default_{param_name}"
        if hasattr(self, default_param_name):
            return getattr(self, default_param_name).value
            
        # Last resort fallback with default values
        default_values = {
            "leverage_param": 2,
            "rsi_period": 14,
            "rsi_upper": 70,
            "rsi_lower": 30,
            "ema_period": 10,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "use_profit_only": True
        }
        
        return default_values.get(param_name, None)

    def feature_engineering_expand_all(self, dataframe: DataFrame, period: int, metadata: Dict, **kwargs) -> DataFrame:
        """
        Create features for FreqAI using technical indicators
        """
        coin = self.get_coin_from_pair(metadata["pair"])
        
        # Add basic indicators
        dataframe[f'rsi_{period}'] = ta.RSI(dataframe, timeperiod=period)
        dataframe[f'ema_{period}'] = ta.EMA(dataframe, timeperiod=period)
        
        # MACD
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe[f'macd_{period}'] = macd['macd']
        dataframe[f'macdsignal_{period}'] = macd['macdsignal']
        dataframe[f'macdhist_{period}'] = macd['macdhist']
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe[f'bb_lowerband_{period}'] = bollinger['lower']
        dataframe[f'bb_middleband_{period}'] = bollinger['mid']
        dataframe[f'bb_upperband_{period}'] = bollinger['upper']
        
        # Price relationship to BB
        dataframe[f'bb_width_{period}'] = (bollinger['upper'] - bollinger['lower']) / bollinger['mid']
        dataframe[f'close_to_bb_lower_{period}'] = (dataframe['close'] - bollinger['lower']) / (bollinger['upper'] - bollinger['lower'])
        
        # Volatility
        dataframe[f'volatility_{period}'] = dataframe['close'].rolling(period).std()
        
        # Momentum
        dataframe[f'mom_{period}'] = ta.MOM(dataframe, timeperiod=period)
        
        # ADX
        dataframe[f'adx_{period}'] = ta.ADX(dataframe)
        
        # Ichimoku
        dataframe[f'ichimoku_a_{period}'] = (
            (dataframe['high'].rolling(9).max() + dataframe['low'].rolling(9).min()) / 2
        ).shift(period)
        
        dataframe[f'ichimoku_b_{period}'] = (
            (dataframe['high'].rolling(26).max() + dataframe['low'].rolling(26).min()) / 2
        ).shift(period)
        
        # Close distance from ATH over period
        dataframe[f'close_to_ath_{period}'] = dataframe['close'] / dataframe['high'].rolling(period).max()
        
        # Close distance from ATL over period
        dataframe[f'close_to_atl_{period}'] = dataframe['close'] / dataframe['low'].rolling(period).min()
        
        # Volume indicators
        dataframe[f'volume_mean_{period}'] = dataframe['volume'].rolling(period).mean()
        dataframe[f'volume_std_{period}'] = dataframe['volume'].rolling(period).std()
        
        # Price change
        dataframe[f'change_{period}'] = (dataframe['close'] - dataframe['close'].shift(period)) / dataframe['close'].shift(period)
        
        # Label - Future price change as target for regression
        dataframe[f'&s-future_price_change_{period}'] = dataframe['close'].pct_change(periods=period).shift(-period)
        
        return dataframe

    def feature_engineering_expand_basic(self, dataframe: DataFrame, metadata: Dict, **kwargs) -> DataFrame:
        """
        Create more basic features for FreqAI
        """
        dataframe['%-day_of_week'] = dataframe['date'].dt.dayofweek
        dataframe['%-hour'] = dataframe['date'].dt.hour
        
        # Price levels
        dataframe['%-close_to_high'] = dataframe['close'] / dataframe['high']
        dataframe['%-close_to_low'] = dataframe['close'] / dataframe['low']
        
        # Price relationship with MA
        dataframe['%-close_over_ema_10'] = dataframe['close'] / ta.EMA(dataframe, timeperiod=10)
        dataframe['%-close_over_ema_50'] = dataframe['close'] / ta.EMA(dataframe, timeperiod=50)
        
        # Set target
        dataframe['&s-target'] = dataframe['close'].pct_change(periods=20).shift(-20)
        
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: Dict, **kwargs) -> DataFrame:
        """
        Set targets for FreqAI
        """
        coin = self.get_coin_from_pair(metadata["pair"])
        
        # Set target thresholds based on coin volatility
        target_col = "&s-target"
        if target_col in dataframe.columns:
            # Get target values and calculate thresholds
            targets = dataframe[target_col]
            
            # Entry and exit thresholds
            entry_threshold = targets.quantile(0.7)  # Top 30% price drops for short entries
            exit_threshold = targets.quantile(0.4)   # Top 60% price rises for short exits
            
            # Set binary classification targets
            dataframe['&s-entry_signal'] = (targets < -entry_threshold).astype('int')
            dataframe['&s-exit_signal'] = (targets > exit_threshold).astype('int')
            
            # Set regression targets for parameter optimization
            dataframe['&s-rsi_upper'] = 70 + 15 * targets  # Higher targets -> higher RSI threshold
            dataframe['&s-rsi_lower'] = 30 + 10 * targets  # Higher targets -> higher RSI exit threshold
            dataframe['&s-leverage'] = 1 + targets.abs() * 2  # Higher absolute targets -> higher leverage
            
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Get coin from pair
        coin = self.get_coin_from_pair(metadata['pair'])
        
        # Get coin-specific parameters
        rsi_period = self.get_param_value(coin, 'rsi_period')
        rsi_upper = self.get_param_value(coin, 'rsi_upper')
        rsi_lower = self.get_param_value(coin, 'rsi_lower')
        ema_period = self.get_param_value(coin, 'ema_period')
        macd_fast = self.get_param_value(coin, 'macd_fast')
        macd_slow = self.get_param_value(coin, 'macd_slow')
        macd_signal = self.get_param_value(coin, 'macd_signal')
        
        # Basic indicators with coin-specific parameters
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=rsi_period)
        dataframe['ema'] = ta.EMA(dataframe, timeperiod=ema_period)
        
        # Calculate price changes for volatility assessment
        dataframe['price_change'] = (dataframe['close'] - dataframe['close'].shift(1)) / dataframe['close'].shift(1)
        dataframe['volatility'] = dataframe['price_change'].rolling(5).std()
        
        # Detect peaks - when current price is at or near local maximum (original peak detection)
        dataframe['high_last_3'] = dataframe['high'].rolling(3).max()
        
        # Check if FreqAI predictions are available and override parameters if so
        if hasattr(self, 'freqai_info') and self.freqai_info is not None and "prediction" in dataframe.columns:
            # Use FreqAI predictions to adjust parameters
            if "&s-rsi_upper" in self.freqai_info['feature_names']:
                idx = self.freqai_info['feature_names'].index('&s-rsi_upper')
                dataframe['freqai_rsi_upper'] = dataframe['prediction'].apply(lambda x: x[idx])
                # Apply limits to the prediction
                dataframe['freqai_rsi_upper'] = dataframe['freqai_rsi_upper'].clip(65, 85)
                rsi_upper_adjusted = dataframe['freqai_rsi_upper']
            else:
                rsi_upper_adjusted = pd.Series([rsi_upper] * len(dataframe))
            
            if "&s-rsi_lower" in self.freqai_info['feature_names']:
                idx = self.freqai_info['feature_names'].index('&s-rsi_lower')
                dataframe['freqai_rsi_lower'] = dataframe['prediction'].apply(lambda x: x[idx])
                # Apply limits to the prediction
                dataframe['freqai_rsi_lower'] = dataframe['freqai_rsi_lower'].clip(20, 40)
                rsi_lower_adjusted = dataframe['freqai_rsi_lower']
            else:
                rsi_lower_adjusted = pd.Series([rsi_lower] * len(dataframe))
            
            # Use entry signal for trade decisions if available
            if "&s-entry_signal" in self.freqai_info['feature_names']:
                idx = self.freqai_info['feature_names'].index('&s-entry_signal')
                dataframe['freqai_entry'] = dataframe['prediction'].apply(lambda x: x[idx] > 0.7)
        else:
            # Use static parameters if FreqAI is not available
            rsi_upper_adjusted = pd.Series([rsi_upper] * len(dataframe))
            rsi_lower_adjusted = pd.Series([rsi_lower] * len(dataframe))
        
        # ORIGINAL PEAK DETECTION - bringing back the more selective peak detection
        dataframe['price_peak'] = (
            (dataframe['high'] >= dataframe['high_last_3'] * 0.995) &  # Price near the highest point
            (dataframe['high'] > dataframe['high'].shift(1)) &         # Current high higher than previous
            (dataframe['close'] > dataframe['ema']) &                  # Price above EMA
            (dataframe['rsi'] > rsi_upper_adjusted)                    # RSI overbought - adjusted by FreqAI if available
        )
        
        # Price reversal after a rise - more selective
        dataframe['price_reversal'] = (
            (dataframe['close'].shift(1) > dataframe['close'].shift(2)) &  # Prior candle was up
            (dataframe['close'] < dataframe['close'].shift(1) * 0.997) &    # Current candle is down significantly
            (dataframe['close'].shift(1) > dataframe['close'].shift(1).rolling(3).max().shift(1)) &  # Local high
            (dataframe['rsi'] > rsi_upper_adjusted * 0.95)                 # RSI elevated - adjusted by FreqAI if available
        )
        
        # MACD with coin-specific parameters
        macd = ta.MACD(dataframe, 
                      fastperiod=macd_fast,
                      slowperiod=macd_slow, 
                      signalperiod=macd_signal)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        dataframe['macdhist_prev1'] = dataframe['macdhist'].shift(1)
        
        # MACD histogram reversal - additional confirmation
        dataframe['macd_reversal'] = (
            (dataframe['macdhist'] < dataframe['macdhist_prev1']) &    # Current MACD hist is falling
            (dataframe['macdhist_prev1'] > 0) &                       # Previous MACD hist was positive
            (dataframe['close'] > dataframe['ema'])                    # Price above EMA
        )
        
        # COMBINED ENTRY SIGNAL - using original peak detection with improved logic
        # If FreqAI entry signal is available, use it to enhance decision
        if 'freqai_entry' in dataframe.columns:
            dataframe['short_entry'] = (
                ((dataframe['price_peak'] | dataframe['price_reversal'] | dataframe['macd_reversal']) |
                 dataframe['freqai_entry']) &
                (dataframe['rsi'] > rsi_upper_adjusted * 0.95)           # RSI must be elevated - adjusted by FreqAI
            )
        else:
            dataframe['short_entry'] = (
                (dataframe['price_peak'] | dataframe['price_reversal'] | dataframe['macd_reversal']) &
                (dataframe['rsi'] > rsi_upper_adjusted * 0.95)           # RSI must be elevated - adjusted by FreqAI
            )
        
        # EXIT CONDITION: Only exit on profit or strong signal
        # Regular exit: Price below EMA AND RSI below midpoint (not waiting for oversold)
        dataframe['regular_exit'] = (
            (dataframe['close'] < dataframe['ema']) &
            (dataframe['rsi'] < rsi_lower_adjusted * 1.5)  # Use a more aggressive RSI threshold - adjusted by FreqAI
        )
        
        # Profit-taking exit: If we have profit and conditions favor exit
        dataframe['short_exit'] = dataframe['regular_exit']
        
        # Check for FreqAI exit signal
        if hasattr(self, 'freqai_info') and self.freqai_info is not None and "prediction" in dataframe.columns:
            if "&s-exit_signal" in self.freqai_info['feature_names']:
                idx = self.freqai_info['feature_names'].index('&s-exit_signal')
                dataframe['freqai_exit'] = dataframe['prediction'].apply(lambda x: x[idx] > 0.7)
                # Add FreqAI exit signal to exit conditions
                dataframe['short_exit'] = dataframe['short_exit'] | dataframe['freqai_exit']
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        # Apply short entry signal
        dataframe.loc[dataframe['short_entry'], 'enter_short'] = 1
        
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                           side: str, **kwargs) -> bool:
        # Cooldown period of 3 minutes
        cooldown_minutes = 3
        
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
                
        # Update the last seen time for this pair
        self._last_candle_seen_time[pair] = current_time
        
        return True

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Get coin from pair
        coin = self.get_coin_from_pair(metadata['pair'])
        
        # Get coin-specific profit_only parameter
        use_profit_only = self.get_param_value(coin, 'use_profit_only')
        
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        # Only apply exit signals if we're not using profit-only exits
        if use_profit_only == False:  # Using explicit comparison
            dataframe.loc[dataframe['short_exit'], 'exit_short'] = 1
        
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        if trade.is_short:
            try:
                # Get coin from pair
                coin = self.get_coin_from_pair(pair)
                
                # Get coin-specific parameters
                use_profit_only = self.get_param_value(coin, 'use_profit_only')
                
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if len(dataframe) > 0:
                    last_candle = dataframe.iloc[-1]
                    
                    # Check if FreqAI has a leverage recommendation
                    if hasattr(self, 'freqai_info') and self.freqai_info is not None and "prediction" in dataframe.columns:
                        if "&s-leverage" in self.freqai_info['feature_names']:
                            idx = self.freqai_info['feature_names'].index('&s-leverage')
                            freqai_leverage = last_candle['prediction'][idx]
                            # Adjust profit targets based on predicted leverage
                            profit_target = min(0.02 * freqai_leverage, 0.04)  # Cap at 4%
                            profit_min = min(0.01 * freqai_leverage, 0.02)     # Cap at 2%
                        else:
                            profit_target = 0.02
                            profit_min = 0.01
                    else:
                        profit_target = 0.02
                        profit_min = 0.01
                    
                    # Only exit on profit
                    if use_profit_only == True and current_profit <= 0:  # Using explicit comparison
                        return None
                    
                    # Take profit at target (adjusted by FreqAI if available)
                    if current_profit >= profit_target:
                        return 'short_profit_hit'
                    
                    # Take profit at minimum if held more than 5 minutes
                    if current_profit >= profit_min and (current_time - trade.open_date_utc) > timedelta(minutes=5):
                        return 'short_profit_timeout'
                    
                    # Exit on RSI below threshold if we have profit
                    if current_profit > 0 and 'rsi' in last_candle:
                        # Use FreqAI-adjusted RSI lower if available
                        if 'freqai_rsi_lower' in last_candle:
                            rsi_exit_threshold = last_candle['freqai_rsi_lower'] * 1.3  # More aggressive exit
                        else:
                            rsi_exit_threshold = 40
                            
                        if last_candle['rsi'] < rsi_exit_threshold:
                            return 'short_profit_rsi_exit'
                    
                    # Cut losses after 10 minutes
                    if current_profit < 0 and (current_time - trade.open_date_utc) > timedelta(minutes=10):
                        return 'short_loss_timeout'
                    
                    # Check FreqAI exit signal
                    if (hasattr(self, 'freqai_info') and self.freqai_info is not None and 
                        "prediction" in last_candle and "&s-exit_signal" in self.freqai_info['feature_names']):
                        idx = self.freqai_info['feature_names'].index('&s-exit_signal')
                        if last_candle['prediction'][idx] > 0.8:  # High confidence exit signal
                            return 'freqai_exit_signal'
                    
            except Exception as e:
                pass
        
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
                **kwargs) -> float:
        """Return leverage value based on coin-specific parameter or FreqAI prediction"""
        try:
            coin = self.get_coin_from_pair(pair)
            default_leverage = float(self.get_param_value(coin, 'leverage_param'))
            
            # Check if FreqAI has a leverage recommendation
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) > 0:
                last_candle = dataframe.iloc[-1]
                if (hasattr(self, 'freqai_info') and self.freqai_info is not None and 
                    "prediction" in last_candle and "&s-leverage" in self.freqai_info['feature_names']):
                    idx = self.freqai_info['feature_names'].index('&s-leverage')
                    freqai_leverage = last_candle['prediction'][idx]
                    # Apply limits to the prediction
                    freqai_leverage = max(1, min(freqai_leverage, 3))
                    return float(freqai_leverage)
                    
            return default_leverage
            
        except Exception as e:
            # Fall back to default leverage if any error occurs
            return 2.0

    def hyperopt_space(self) -> List[Dimension]:
        """Define hyperopt space for all coins with parameters"""
        space = []
        
        # First add default parameters
        space.extend([
            Integer(1, 3, name='default_leverage_param'),
            Integer(10, 20, name='default_rsi_period'),
            Integer(65, 85, name='default_rsi_upper'),
            Integer(20, 35, name='default_rsi_lower'),
            Integer(5, 20, name='default_ema_period'),
            Integer(8, 16, name='default_macd_fast'),
            Integer(18, 32, name='default_macd_slow'),
            Integer(6, 12, name='default_macd_signal'),
            Categorical([True, False], name='default_use_profit_only'),
        ])
        
        # Then add spaces for each coin
        for coin in self._supported_coins:
            space.extend([
                Integer(1, 3, name=f'{coin}_leverage_param'),
                Integer(10, 20, name=f'{coin}_rsi_period'),
                Integer(65, 85, name=f'{coin}_rsi_upper'),
                Integer(20, 35, name=f'{coin}_rsi_lower'),
                Integer(5, 20, name=f'{coin}_ema_period'),
                Integer(8, 16, name=f'{coin}_macd_fast'),
                Integer(18, 32, name=f'{coin}_macd_slow'),
                Integer(6, 12, name=f'{coin}_macd_signal'),
                Categorical([True, False], name=f'{coin}_use_profit_only'),
            ])
        
        return space
