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

class future29(IStrategy):
    # Slower profit-taking ROI - Allow profitable trades to run longer
    minimal_roi = {
        "0": 0.05,    # Take 5% profit immediately
        "10": 0.03,   # 3% after 10 minutes 
        "20": 0.02,   # 2% after 20 minutes
        "30": 0.01,   # 1% after 30 minutes
    }

    # Tighter risk parameters
    stoploss = -0.08  # Smaller stoploss
    trailing_stop = True
    trailing_stop_positive = 0.01  # Start trailing at 1%
    trailing_stop_positive_offset = 0.015  # Offset by 1.5%
    trailing_only_offset_is_reached = True  # Only trail after reaching the offset

    # Strategy settings
    timeframe = '1m'
    startup_candle_count = 30
    process_only_new_candles = True
    can_short = True
    can_long = False  # Focusing only on shorts

    # Default parameters
    default_leverage_param = IntParameter(2, 5, default=2, space="buy", optimize=True)  # Reduced maximum leverage
    default_rsi_period = IntParameter(10, 20, default=14, space="buy", optimize=True)
    default_rsi_upper = IntParameter(65, 85, default=61, space="sell", optimize=True)
    default_rsi_lower = IntParameter(20, 35, default=34, space="sell", optimize=True)
    default_ema_period = IntParameter(5, 20, default=10, space="both", optimize=True)
    default_macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    default_macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
    default_macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
    default_use_profit_only = CategoricalParameter([True, False], default=True, space="sell", optimize=True)
    
    # New entry filter parameters
    default_market_trend_ema = IntParameter(50, 200, default=100, space="buy", optimize=True)
    default_min_rsi_drop = IntParameter(3, 10, default=5, space="buy", optimize=True)
    
    # FreqAI settings
    freqai_conf = {
        "enabled": True,
        "purge_old_models": True,
        "train_period_days": 7,
        "backtest_period_days": 2,
        "identifier": "future29",
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
            params[f"{coin}_leverage_param"] = IntParameter(2, 5, default=2, space="buy", optimize=True)  # Reduced maximum leverage
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
            
            # Market trend filter parameters
            params[f"{coin}_market_trend_ema"] = IntParameter(50, 200, default=100, space="buy", optimize=True)
            params[f"{coin}_min_rsi_drop"] = IntParameter(3, 10, default=5, space="buy", optimize=True)
            
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
            "use_profit_only": True,
            "market_trend_ema": 100,
            "min_rsi_drop": 5
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
        
        # Market trend features
        dataframe[f'ema_long_{period}'] = ta.EMA(dataframe, timeperiod=100)
        dataframe[f'market_trend_{period}'] = (dataframe['close'] / dataframe[f'ema_long_{period}']) - 1
        
        # RSI change to detect momentum shifts
        dataframe[f'rsi_change_{period}'] = dataframe[f'rsi_{period}'] - dataframe[f'rsi_{period}'].shift(5)
        
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
        dataframe['%-close_over_ema_100'] = dataframe['close'] / ta.EMA(dataframe, timeperiod=100)
        
        # Market direction over multiple timeframes
        dataframe['%-trend_5m'] = (dataframe['close'] / dataframe['close'].shift(5)) - 1
        dataframe['%-trend_15m'] = (dataframe['close'] / dataframe['close'].shift(15)) - 1
        dataframe['%-trend_30m'] = (dataframe['close'] / dataframe['close'].shift(30)) - 1
        
        # Set target
        dataframe['&s-target'] = dataframe['close'].pct_change(periods=20).shift(-20)
        
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: Dict, **kwargs) -> DataFrame:
        """
        Set targets for FreqAI including risk-based leverage prediction
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
            
            # Calculate risk factors
            recent_volatility = dataframe['close'].pct_change().rolling(20).std()
            price_distance_from_ma = abs(dataframe['close'] / ta.EMA(dataframe, timeperiod=100) - 1)
            directional_confidence = abs(targets)  # How strong is the predicted move
            
            # Add trend direction - negative is downtrend (good for shorts)
            trend_direction = (dataframe['close'] / ta.EMA(dataframe, timeperiod=100)) - 1
            trend_strength = abs(trend_direction)
            
            # Create a composite risk score (0-1 scale, higher = more risky)
            risk_score = (
                (recent_volatility / recent_volatility.quantile(0.95)).clip(0, 1) * 0.3 +  # 30% weight to volatility
                (price_distance_from_ma / price_distance_from_ma.quantile(0.95)).clip(0, 1) * 0.2 +  # 20% to price deviation
                (1 - directional_confidence / directional_confidence.quantile(0.95)).clip(0, 1) * 0.2 +  # 20% to model confidence (inverted)
                (1 - trend_strength / trend_strength.quantile(0.95)).clip(0, 1) * 0.3  # 30% to trend strength (inverted)
            )
            
            # Adjust risk score for shorts - lower risk if in downtrend
            # For shorts, we want to reduce risk score (increase leverage) in downtrends
            if trend_direction.mean() < 0:  # Overall downtrend
                risk_score = risk_score * 0.8  # Reduce risk score by 20% in downtrends
            
            # Higher leverage for lower risk, lower leverage for higher risk (inverse relationship)
            # Scale from 2-5 based on risk (5 for very low risk, 2 for very high risk)
            dataframe['&s-leverage'] = 2 + (1 - risk_score) * 3
            
            # Add actual past performance as a feature for future leverage decisions
            # This allows the model to learn from its own mistakes
            entry_points = dataframe['&s-entry_signal'].shift(20) == 1  # Entry signals from 20 candles ago
            future_returns = dataframe['close'].pct_change(20)  # Actual returns over next 20 candles
            
            # When we had an entry signal, what was the actual outcome?
            dataframe['%-past_prediction_accuracy'] = 0.0
            mask = entry_points & (future_returns < 0)  # Correct predictions (price went down after short signal)
            if mask.any():
                dataframe.loc[mask, '%-past_prediction_accuracy'] = abs(future_returns[mask])
        
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
        market_trend_ema = self.get_param_value(coin, 'market_trend_ema')
        min_rsi_drop = self.get_param_value(coin, 'min_rsi_drop')
        
        # Basic indicators with coin-specific parameters
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=rsi_period)
        dataframe['ema'] = ta.EMA(dataframe, timeperiod=ema_period)
        
        # Longer-term EMA for market trend filter
        dataframe['market_ema'] = ta.EMA(dataframe, timeperiod=market_trend_ema)
        dataframe['market_trend'] = (dataframe['close'] / dataframe['market_ema']) - 1
        
        # Calculate price changes for volatility assessment
        dataframe['price_change'] = (dataframe['close'] - dataframe['close'].shift(1)) / dataframe['close'].shift(1)
        dataframe['volatility'] = dataframe['price_change'].rolling(5).std()
        
        # RSI changes to detect momentum shifts
        dataframe['rsi_prev'] = dataframe['rsi'].shift(1)
        dataframe['rsi_drop'] = dataframe['rsi_prev'] - dataframe['rsi']
        
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
            (dataframe['rsi'] > rsi_upper_adjusted) &                 # RSI overbought - adjusted by FreqAI if available
            (dataframe['market_trend'] < 0)                           # Market is in downtrend (good for shorts)
        )
        
        # Price reversal after a rise - more selective with stronger confirmation
        dataframe['price_reversal'] = (
            (dataframe['close'].shift(1) > dataframe['close'].shift(2)) &  # Prior candle was up
            (dataframe['close'] < dataframe['close'].shift(1) * 0.997) &    # Current candle is down significantly
            (dataframe['close'].shift(1) > dataframe['close'].shift(1).rolling(3).max().shift(1)) &  # Local high
            (dataframe['rsi'] > rsi_upper_adjusted * 0.95) &                # RSI elevated - adjusted by FreqAI if available
            (dataframe['rsi_drop'] >= min_rsi_drop) &                       # Significant RSI drop
            (dataframe['market_trend'] < 0)                                # Market is in downtrend (good for shorts)
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
        
        # MACD histogram reversal - additional confirmation with market trend filter
        dataframe['macd_reversal'] = (
            (dataframe['macdhist'] < dataframe['macdhist_prev1']) &    # Current MACD hist is falling
            (dataframe['macdhist_prev1'] > 0) &                       # Previous MACD hist was positive
            (dataframe['close'] > dataframe['ema']) &                  # Price above EMA
            (dataframe['market_trend'] < 0)                           # Market is in downtrend (good for shorts)
        )
        
        # COMBINED ENTRY SIGNAL - using original peak detection with improved logic
        # If FreqAI entry signal is available, use it to enhance decision
        if 'freqai_entry' in dataframe.columns:
            dataframe['short_entry'] = (
                ((dataframe['price_peak'] | dataframe['price_reversal'] | dataframe['macd_reversal']) &
                 dataframe['freqai_entry']) &
                (dataframe['rsi'] > rsi_upper_adjusted * 0.95) &        # RSI must be elevated - adjusted by FreqAI
                (dataframe['market_trend'] < 0)                        # Market must be in downtrend
            )
        else:
            dataframe['short_entry'] = (
                (dataframe['price_peak'] | dataframe['price_reversal'] | dataframe['macd_reversal']) &
                (dataframe['rsi'] > rsi_upper_adjusted * 0.95) &        # RSI must be elevated - adjusted by FreqAI
                (dataframe['market_trend'] < 0)                        # Market must be in downtrend
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
        
        # Apply short entry signal with a cooldown filter
        # Ensure we only enter when volatility is reasonable
        dataframe.loc[
            (dataframe['short_entry']) & 
            (dataframe['volatility'] < 0.005),  # Only enter when volatility is low
            'enter_short'
        ] = 1
        
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                           side: str, **kwargs) -> bool:
        # Cooldown period of 5 minutes (increased from 3)
        cooldown_minutes = 5
        
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
                
        # Additional confirmation check for short entries
        if side == "short":
            try:
                # Get fresh dataframe to check current market conditions
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                last_candle = dataframe.iloc[-1].squeeze()
                
                # Only enter shorts when market trend is negative (downtrend)
                if 'market_trend' in last_candle and last_candle['market_trend'] >= 0:
                    return False
                
                # Only enter when RSI is high enough
                if 'rsi' in last_candle and last_candle['rsi'] < 60:
                    return False
                    
                # Only enter when price is above EMA
                if 'ema' in last_candle and last_candle['close'] <= last_candle['ema']:
                    return False
            except Exception as e:
                # If we can't check conditions, better to skip the trade
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
                            profit_target = min(0.03 * freqai_leverage / 2, 0.05)  # Scale down for higher leverage
                            profit_min = min(0.015 * freqai_leverage / 2, 0.025)   # Scale down for higher leverage
                        else:
                            profit_target = 0.03
                            profit_min = 0.015
                    else:
                        profit_target = 0.03
                        profit_min = 0.015
                    
                    # Only exit on profit
                    if use_profit_only == True and current_profit <= 0:  # Using explicit comparison
                        # NEW: Emergency exit for deep losses regardless of profit_only setting
                        # Calculate how deep a loss we can tolerate based on leverage
                        trade_leverage = trade.leverage if hasattr(trade, 'leverage') else 2.0
                        max_loss = -0.02 / trade_leverage  # Lose at most 2% regardless of leverage
                        
                        # Exit on deep loss or if held too long with a losing position
                        if current_profit < max_loss:
                            return 'emergency_loss_exit'
                        
                        # MODIFIED: Less sensitive trend reversal detection to avoid premature exits
                        if (current_profit < -0.01 and  # Deeper loss before exiting
                            (current_time - trade.open_date_utc) > timedelta(minutes=5) and  # Give it some time
                            'price_change' in last_candle and 
                            last_candle['price_change'] > 0.002 and  # Stronger reversal signal required
                            'market_trend' in last_candle and
                            last_candle['market_trend'] > 0):  # Only exit if overall trend is changing too
                            return 'early_trend_reversal'
                            
                        # If no emergency, respect profit_only
                        return None
                    
                    # Take profit at target (adjusted by FreqAI if available)
                    if current_profit >= profit_target:
                        return 'short_profit_hit'
                    
                    # Take profit at minimum if held more than 5 minutes
                    if current_profit >= profit_min and (current_time - trade.open_date_utc) > timedelta(minutes=10):  # Extended from 5 to 10
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
                    
                    # Cut losses after 120 minutes instead of 5
                    if current_profit < 0 and (current_time - trade.open_date_utc) > timedelta(minutes=120):
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
        """Return leverage value based on AI risk assessment"""
        try:
            coin = self.get_coin_from_pair(pair)
            default_leverage = float(self.get_param_value(coin, 'leverage_param'))
            
            # Check if FreqAI has a leverage recommendation
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) > 0:
                last_candle = dataframe.iloc[-1]
                
                # Check for risk-based leverage from FreqAI
                if (hasattr(self, 'freqai_info') and self.freqai_info is not None and 
                    "prediction" in last_candle and "&s-leverage" in self.freqai_info['feature_names']):
                    idx = self.freqai_info['feature_names'].index('&s-leverage')
                    freqai_leverage = last_candle['prediction'][idx]
                    
                    # Apply stricter limits to the prediction - max 5 instead of 9
                    freqai_leverage = max(2, min(freqai_leverage, 5))
                    
                    # Additional safety check - reduce leverage for high volatility
                    if 'volatility' in last_candle and last_candle['volatility'] > 0.005:  # 0.5% volatility
                        # Scale leverage down based on volatility
                        volatility_factor = min(1.0, 0.005 / last_candle['volatility'])
                        adjusted_leverage = freqai_leverage * volatility_factor
                        return max(2.0, float(adjusted_leverage))
                    
                    # Further reduce leverage if market trend isn't strongly negative
                    if 'market_trend' in last_candle:
                        market_trend = last_candle['market_trend']
                        if market_trend > -0.01:  # Not a strong downtrend
                            freqai_leverage = max(2.0, freqai_leverage * 0.8)  # Reduce leverage by 20%
                    
                    return float(freqai_leverage)
                    
            # If we couldn't get a FreqAI recommendation, use the coin-specific parameter
            return default_leverage
            
        except Exception as e:
            # Fall back to default leverage if any error occurs
            return 2.0  # Minimum safe leverage as fallback

    def hyperopt_space(self) -> List[Dimension]:
        """Define hyperopt space for all coins with parameters"""
        space = []
        
        # First add default parameters
        space.extend([
            Integer(2, 5, name='default_leverage_param'),  # Reduced from 2-9 to 2-5
            Integer(10, 20, name='default_rsi_period'),
            Integer(65, 85, name='default_rsi_upper'),
            Integer(20, 35, name='default_rsi_lower'),
            Integer(5, 20, name='default_ema_period'),
            Integer(8, 16, name='default_macd_fast'),
            Integer(18, 32, name='default_macd_slow'),
            Integer(6, 12, name='default_macd_signal'),
            Categorical([True, False], name='default_use_profit_only'),
            Integer(50, 200, name='default_market_trend_ema'),
            Integer(3, 10, name='default_min_rsi_drop'),
        ])
        
        # Then add spaces for each coin
        for coin in self._supported_coins:
            space.extend([
                Integer(2, 8, name=f'{coin}_leverage_param'),  
                Integer(10, 20, name=f'{coin}_rsi_period'),
                Integer(65, 85, name=f'{coin}_rsi_upper'),
                Integer(20, 35, name=f'{coin}_rsi_lower'),
                Integer(5, 20, name=f'{coin}_ema_period'),
                Integer(8, 16, name=f'{coin}_macd_fast'),
                Integer(18, 32, name=f'{coin}_macd_slow'),
                Integer(6, 12, name=f'{coin}_macd_signal'),
                Categorical([True, False], name=f'{coin}_use_profit_only'),
                Integer(50, 200, name=f'{coin}_market_trend_ema'),
                Integer(3, 10, name=f'{coin}_min_rsi_drop'),
            ])
        
        return space
