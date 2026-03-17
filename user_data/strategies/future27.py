from datetime import datetime, timedelta
from typing import Optional, List

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter
from skopt.space import Integer, Real, Categorical, Dimension

class future27(IStrategy):
    # Faster profit-taking ROI
    minimal_roi = {
        "0": 0.02,    # Take 2% profit immediately
        "5": 0.015,   # 1.5% after 5 minutes
        "10": 0.01,   # 1% after 10 minutes
        "15": 0.005,  # 0.5% after 15 minutes
    }

    # Tighter risk parameters
    stoploss = -0.23  # Smaller stoploss
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
    default_leverage_param = IntParameter(1, 3, default=2, space="buy", optimize=True)
    default_rsi_period = IntParameter(10, 20, default=14, space="buy", optimize=True)
    default_rsi_upper = IntParameter(65, 85, default=70, space="sell", optimize=True)
    default_rsi_lower = IntParameter(20, 35, default=30, space="sell", optimize=True)
    default_ema_period = IntParameter(5, 20, default=10, space="both", optimize=True)
    default_macd_fast = IntParameter(8, 16, default=12, space="both", optimize=True)
    default_macd_slow = IntParameter(18, 32, default=26, space="both", optimize=True)
    default_macd_signal = IntParameter(6, 12, default=9, space="both", optimize=True)
    default_use_profit_only = CategoricalParameter([True, False], default=True, space="sell", optimize=True)
    
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
        
        # ORIGINAL PEAK DETECTION - bringing back the more selective peak detection
        dataframe['price_peak'] = (
            (dataframe['high'] >= dataframe['high_last_3'] * 0.995) &  # Price near the highest point
            (dataframe['high'] > dataframe['high'].shift(1)) &         # Current high higher than previous
            (dataframe['close'] > dataframe['ema']) &                  # Price above EMA
            (dataframe['rsi'] > rsi_upper)                             # RSI overbought
        )
        
        # Price reversal after a rise - more selective
        dataframe['price_reversal'] = (
            (dataframe['close'].shift(1) > dataframe['close'].shift(2)) &  # Prior candle was up
            (dataframe['close'] < dataframe['close'].shift(1) * 0.997) &    # Current candle is down significantly
            (dataframe['close'].shift(1) > dataframe['close'].shift(1).rolling(3).max().shift(1)) &  # Local high
            (dataframe['rsi'] > rsi_upper * 0.95)                          # RSI elevated
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
        dataframe['short_entry'] = (
            (dataframe['price_peak'] | dataframe['price_reversal'] | dataframe['macd_reversal']) &
            (dataframe['rsi'] > rsi_upper * 0.95)                      # RSI must be elevated
        )
        
        # EXIT CONDITION: Only exit on profit or strong signal
        # Regular exit: Price below EMA AND RSI below midpoint (not waiting for oversold)
        dataframe['regular_exit'] = (
            (dataframe['close'] < dataframe['ema']) &
            (dataframe['rsi'] < 45)  # Use a more aggressive RSI threshold
        )
        
        # Profit-taking exit: If we have profit and conditions favor exit
        dataframe['short_exit'] = dataframe['regular_exit']
        
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
                rsi_lower = self.get_param_value(coin, 'rsi_lower')
                
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if len(dataframe) > 0:
                    last_candle = dataframe.iloc[-1]
                    
                    # Only exit on profit
                    if use_profit_only == True and current_profit <= 0:  # Using explicit comparison
                        return None
                    
                    # Take profit at 2%
                    if current_profit >= 0.02:
                        return 'short_profit_hit'
                    
                    # Take profit at 1% if held more than 5 minutes
                    if current_profit >= 0.01 and (current_time - trade.open_date_utc) > timedelta(minutes=5):
                        return 'short_profit_timeout'
                    
                    # Exit on RSI below threshold if we have profit
                    if current_profit > 0 and 'rsi' in last_candle and last_candle['rsi'] < 40:
                        return 'short_profit_rsi_exit'
                    
                    # Cut losses after 10 minutes
                    if current_profit < 0 and (current_time - trade.open_date_utc) > timedelta(minutes=10):
                        return 'short_loss_timeout'
                    
            except Exception as e:
                pass
        
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
                **kwargs) -> float:
        """Return leverage value based on coin-specific parameter"""
        coin = self.get_coin_from_pair(pair)
        return float(self.get_param_value(coin, 'leverage_param'))

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
