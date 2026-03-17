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

class future16(IStrategy):
    # Updated ROI table from hyperopt
    minimal_roi = {
        "0": 0.105,
        "8": 0.037,
        "17": 0.01,
        "22": 0
    }

    # Updated risk parameters
    stoploss = -0.35
    trailing_stop = True
    trailing_stop_positive = 0.237
    trailing_stop_positive_offset = 0.26
    trailing_only_offset_is_reached = True

    # Leverage parameter with optimized default
    leverage_param = IntParameter(1, 20, default=9, space="buy", optimize=True)
    
    # Hyperopt parameters with optimized defaults
    # RSI parameters
    buy_rsi = IntParameter(25, 50, default=46, space="buy", optimize=True)
    sell_rsi = IntParameter(65, 85, default=76, space="sell", optimize=True)
    
    # Stochastic parameters
    sell_stoch_k = IntParameter(60, 95, default=78, space="sell", optimize=True)
    sell_stoch_d = IntParameter(60, 95, default=95, space="sell", optimize=True)
    
    # Stochastic RSI parameters 
    sell_fastk = IntParameter(60, 95, default=72, space="sell", optimize=True)
    sell_fastd = IntParameter(60, 95, default=74, space="sell", optimize=True)
    
    # Volume multiplier for confirmation
    sell_volume_mult = DecimalParameter(0.5, 2.0, default=1.643, space="sell", optimize=True)
    
    # Price extension parameter
    sell_price_extension = DecimalParameter(1.0, 1.1, default=1.047, space="sell", optimize=True)
    
    # Toggles for entry conditions - allow hyperopt to disable conditions
    use_rsi_condition = CategoricalParameter([True, False], default=True, space="sell", optimize=True)
    use_stoch_condition = CategoricalParameter([True, False], default=True, space="sell", optimize=True)
    use_stoch_rsi_condition = CategoricalParameter([True, False], default=True, space="sell", optimize=True)
    use_volume_condition = CategoricalParameter([True, False], default=True, space="sell", optimize=True)
    use_price_extension_condition = CategoricalParameter([True, False], default=True, space="sell", optimize=True)
    
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

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ===== CORE TECHNICAL INDICATORS =====
        
        # RSI - key for overbought detection
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_short'] = ta.RSI(dataframe, timeperiod=6)  # Faster RSI
        
        # Stochastic RSI for overbought confirmations
        stoch_rsi = ta.STOCHRSI(dataframe, timeperiod=14, fastk_period=3, fastd_period=3)
        dataframe['fastk'] = stoch_rsi['fastk']
        dataframe['fastd'] = stoch_rsi['fastd']
        
        # Stochastic Oscillator for topping patterns
        stoch = ta.STOCH(dataframe, fastk_period=14, slowk_period=3, slowd_period=3)
        dataframe['slowk'] = stoch['slowk']
        dataframe['slowd'] = stoch['slowd']
        
        # MACD for trend/momentum
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Store previous values for pattern detection
        dataframe['macdhist_prev1'] = dataframe['macdhist'].shift(1)
        dataframe['macdhist_prev2'] = dataframe['macdhist'].shift(2)
        
        # Elder Ray Index for buying/selling pressure
        bull_power = dataframe['high'] - ta.EMA(dataframe, timeperiod=13)
        bear_power = dataframe['low'] - ta.EMA(dataframe, timeperiod=13)
        dataframe['bull_power'] = bull_power
        dataframe['bear_power'] = bear_power
        dataframe['bull_power_prev'] = bull_power.shift(1)
        
        # Rate of Change for momentum analysis
        dataframe['roc'] = ta.ROC(dataframe, timeperiod=5)
        dataframe['roc_prev'] = dataframe['roc'].shift(1)
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_width'] = (dataframe['bb_upperband'] - dataframe['bb_lowerband']) / dataframe['bb_middleband']
        
        # ADX for trend strength
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        dataframe['plus_di'] = ta.PLUS_DI(dataframe, timeperiod=14)
        dataframe['minus_di'] = ta.MINUS_DI(dataframe, timeperiod=14)
        
        # ===== PRICE PATTERNS & FORMATIONS =====
        
        # Store shifted prices for pattern detection
        for i in range(1, 8):
            dataframe[f'close_prev{i}'] = dataframe['close'].shift(i)
            dataframe[f'high_prev{i}'] = dataframe['high'].shift(i)
            dataframe[f'low_prev{i}'] = dataframe['low'].shift(i)
            dataframe[f'open_prev{i}'] = dataframe['open'].shift(i)
        
        # Detect price reversals - less strict for more signals
        dataframe['is_reversal'] = (
            (dataframe['close_prev1'] > dataframe['close_prev2']) &  # Previous candle was up
            (dataframe['close'] < dataframe['close_prev1']) &         # Current candle is down
            (dataframe['close_prev1'] > dataframe['close_prev3'])     # Local high (less strict)
        )
        
        # Detect doji patterns (indecision, often at tops)
        dataframe['doji'] = (
            (abs(dataframe['close'] - dataframe['open']) / (dataframe['high'] - dataframe['low'] + 0.0001) < 0.15) &  # Less strict
            (dataframe['high'] - dataframe['low'] > 0) &
            ((dataframe['high'] - np.maximum(dataframe['close'], dataframe['open'])) > 
             ((dataframe['high'] - dataframe['low']) * 0.5))  # Less strict
        )
        
        # Detect shooting star (bearish reversal pattern) - less strict
        dataframe['shooting_star'] = (
            (dataframe['close_prev1'] > dataframe['open_prev1']) &  # Previous candle was bullish
            (dataframe['high'] - np.maximum(dataframe['close'], dataframe['open']) > 
             (dataframe['high'] - dataframe['low'] + 0.0001) * 0.5) &  # Long upper shadow (less strict)
            (np.minimum(dataframe['close'], dataframe['open']) - dataframe['low'] < 
             (dataframe['high'] - dataframe['low'] + 0.0001) * 0.3)  # Small or no lower shadow (less strict)
        )
        
        # Detect bearish engulfing pattern - slightly less strict
        dataframe['bearish_engulfing'] = (
            (dataframe['close_prev1'] > dataframe['open_prev1']) &  # Previous candle was bullish
            (dataframe['open'] >= dataframe['close_prev1'] * 0.998) &  # Open near or higher than previous close
            (dataframe['close'] < dataframe['open_prev1'])          # Close lower than previous open
        )
        
        # ===== VOLUME ANALYSIS =====
        
        # Volume indicators
        dataframe['volume_ma'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / (dataframe['volume_ma'] + 0.0001)  # Avoid div by zero
        dataframe['volume_prev'] = dataframe['volume'].shift(1)
        
        # On-Balance Volume (OBV)
        dataframe['obv'] = ta.OBV(dataframe)
        
        # Volume increasing while price rising (climax) - less strict
        dataframe['volume_climax'] = (
            (dataframe['close'] > dataframe['close_prev1']) &
            (dataframe['volume'] > dataframe['volume_prev'] * 1.3) &  # Less strict
            (dataframe['volume'] > dataframe['volume_ma'])  # Less strict
        )
        
        # ===== TOP DETECTION COMPOSITE SIGNALS =====
        
        # RSI divergence (price making new highs but RSI not confirming) - less strict
        dataframe['rsi_divergence'] = (
            (dataframe['close'] > dataframe['close_prev1']) &
            (dataframe['rsi'] < dataframe['rsi'].shift(1)) &
            (dataframe['rsi'] > 60)  # Less strict
        )
        
        # Bull trap pattern (false breakout) - less strict
        dataframe['bull_trap'] = (
            (dataframe['close_prev1'] > dataframe['close_prev2']) &  # Previous candle was up
            (dataframe['high'] > dataframe['high_prev1']) &          # Made a new high
            (dataframe['close'] < dataframe['close_prev1']) &        # But closed lower
            (dataframe['volume'] > dataframe['volume_ma'] * 0.8)     # On decent volume (less strict)
        )
        
        # Elder Ray bearish signal (bull power dropping while price rising) - less strict
        dataframe['elder_ray_bearish'] = (
            (dataframe['close'] > dataframe['close_prev1']) &  # Price still rising
            (dataframe['bull_power'] < dataframe['bull_power_prev']) &  # But buying pressure decreasing
            (dataframe['rsi'] > 55)  # Market is not oversold (less strict)
        )
        
        # Strong overbought with reversal indication - using OR conditions instead of AND
        dataframe['strong_sell_signal'] = (
            ((dataframe['rsi'] > self.sell_rsi.value) | (dataframe['fastk'] > self.sell_fastk.value)) &  # Overbought (hyperopt)
            (
                (dataframe['close'] > dataframe['bb_upperband'] * 0.98) |  # Near upper Bollinger Band (less strict)
                (dataframe['is_reversal']) |
                (dataframe['doji']) |
                (dataframe['shooting_star']) |
                (dataframe['bearish_engulfing']) |
                (dataframe['bull_trap'])
            ) &
            (dataframe['volume'] > dataframe['volume_ma'] * self.sell_volume_mult.value)  # Volume confirmation (hyperopt)
        )
        
        # Near-term top pattern (combination of indicators) - using OR conditions more liberally
        dataframe['top_pattern'] = (
            (dataframe['close'] > dataframe['bb_middleband']) &  # Above middle band
            (
                (dataframe['rsi'] > self.sell_rsi.value) |  # RSI overbought (hyperopt)
                (dataframe['fastk'] > self.sell_fastk.value) |  # StochRSI overbought (hyperopt)
                (dataframe['slowk'] > self.sell_stoch_k.value)  # Stochastic overbought (hyperopt)
            ) &
            (
                (dataframe['macdhist'] < dataframe['macdhist_prev1']) |  # MACD hist declining
                (dataframe['roc'] < dataframe['roc_prev']) |             # ROC declining
                (dataframe['is_reversal']) |
                (dataframe['doji']) |
                (dataframe['shooting_star']) |
                (dataframe['bearish_engulfing']) |
                (dataframe['rsi_divergence']) |
                (dataframe['elder_ray_bearish'])
            )
        )
        
        # Calculate stochastic overbought (using hyperopt parameters)
        dataframe['stoch_overbought'] = (dataframe['slowk'] > self.sell_stoch_k.value) & (dataframe['slowd'] > self.sell_stoch_d.value)
        
        # Calculate stoch RSI overbought (using hyperopt parameters)
        dataframe['stoch_rsi_overbought'] = (dataframe['fastk'] > self.sell_fastk.value) & (dataframe['fastd'] > self.sell_fastd.value)
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry conditions with the ability to disable certain conditions via hyperopt"""
        # Initialize entry columns
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        # Base conditions always required
        base_conditions = [
            # Main signal: either strong sell signal or top pattern
            (dataframe['strong_sell_signal'] | dataframe['top_pattern'])
        ]
        
        # Optional conditions that can be disabled by hyperopt
        optional_conditions = []
        
        # RSI condition - can be disabled by hyperopt
        if self.use_rsi_condition.value:
            optional_conditions.append(dataframe['rsi'] > self.sell_rsi.value)
            
        # Stochastic condition - can be disabled by hyperopt
        if self.use_stoch_condition.value:
            optional_conditions.append(dataframe['stoch_overbought'])
            
        # Stochastic RSI condition - can be disabled by hyperopt
        if self.use_stoch_rsi_condition.value:
            optional_conditions.append(dataframe['stoch_rsi_overbought'])
            
        # Volume condition - can be disabled by hyperopt
        if self.use_volume_condition.value:
            optional_conditions.append(dataframe['volume'] > dataframe['volume_ma'] * self.sell_volume_mult.value)
            
        # Price extension condition - can be disabled by hyperopt
        if self.use_price_extension_condition.value:
            optional_conditions.append(dataframe['close'] > dataframe['close'].rolling(20).mean() * self.sell_price_extension.value)
        
        # If we have optional conditions, add them with OR logic
        if optional_conditions:
            # Need at least one of the optional conditions to be true
            base_conditions.append(reduce(lambda x, y: x | y, optional_conditions))
        
        # Apply entry signal using base conditions
        dataframe.loc[reduce(lambda x, y: x & y, base_conditions), 'enter_short'] = 1
            
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                             time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                             side: str, **kwargs) -> bool:
        """
        Execute cooldown logic here instead of in populate_entry_trend to maintain chart signals
        """
        # Check if we've seen this pair recently
        cooldown_minutes = 3  # Cooldown period in minutes
        
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            # Only allow trade if cooldown period has passed
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
                
        # Update the last seen time for this pair
        self._last_candle_seen_time[pair] = current_time
        return True

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit signals disabled - relying on ROI and custom_exit"""
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """Custom exit logic for shorts with profit targets aligned with ROI"""
        # Exit logic for shorts
        if trade.is_short:
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if len(dataframe) > 0:
                    last_candle = dataframe.iloc[-1]
                    
                    # Take profit at 10.5% (from optimized ROI)
                    if current_profit > 0.105:
                        return 'short_profit_target_reached'
                    
                    # Take smaller profit with bearish momentum exhaustion
                    if current_profit > 0.02 and 'rsi' in last_candle and last_candle['rsi'] < self.buy_rsi.value:
                        return 'short_profit_rsi_oversold'
                    
                    # Exit when price makes higher lows and RSI starts increasing (smaller profit)
                    if 'rsi' in last_candle and 'rsi_short' in last_candle and len(dataframe) > 1:
                        prev_candle = dataframe.iloc[-2]
                        if (current_profit > 0.01 and  # Profit threshold
                            last_candle['rsi_short'] > prev_candle['rsi_short'] and  # RSI rising
                            last_candle['low'] > prev_candle['low']):  # Higher low
                            return 'short_exit_momentum_shift'
                    
            except Exception as e:
                pass
        
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
                **kwargs) -> float:
        """Return leverage based on hyperopt parameter"""
        return float(self.leverage_param.value)

    def hyperopt_space(self) -> List[Dimension]:
        """Define hyperopt space with wider ranges"""
        return [
            Integer(1, 20, name='leverage_param'),
            Real(0.5, 2.0, name='sell_volume_mult'),
            Real(1.0, 1.1, name='sell_price_extension'),
            Integer(65, 85, name='sell_rsi'),
            Integer(60, 95, name='sell_stoch_k'),
            Integer(60, 95, name='sell_stoch_d'),
            Integer(60, 95, name='sell_fastk'),
            Integer(60, 95, name='sell_fastd'),
            Integer(25, 50, name='buy_rsi'),
            Categorical([True, False], name='use_rsi_condition'),
            Categorical([True, False], name='use_stoch_condition'),
            Categorical([True, False], name='use_stoch_rsi_condition'),
            Categorical([True, False], name='use_volume_condition'),
            Categorical([True, False], name='use_price_extension_condition'),
        ]
