from functools import reduce
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter

class future61a(IStrategy):
    """
    Trend-following strategy optimized for leveraged futures trading
    - Properly applies leverage to all trades
    - Better exit logic to avoid premature exits
    - Dynamic position sizing based on leverage
    """
    
    # --- Strategy Configuration ---
    minimal_roi = {
        "0": 0.10,      # 30% at start (achievable with 6x leverage)
        "30": 0.05,     # 20% after 30 minutes
        "90": 0.03,     # 10% after 1.5 hours
        "180": 0.01,    # 5% after 3 hours
        "360": 0.005,    # 2% after 6 hours
        "720": 0        # Exit after 12 hours
    }
    
    # Wider stop loss for leveraged positions (account for leverage multiplier)
    stoploss = -0.25  # 10% stop loss
    
    # Trailing stop configuration
    trailing_stop = True
    trailing_stop_positive = 0.015  # Start trailing at 1.5% profit
    trailing_stop_positive_offset = 0.03  # Trail after 3% profit
    trailing_only_offset_is_reached = True
    
    use_exit_signal = True
    exit_profit_only = False  # Allow exits even at loss if signal is strong
    exit_profit_offset = 0.01
    ignore_roi_if_entry_signal = False
    
    process_only_new_candles = True
    max_open_trades = 4
    timeframe = '5m'
    startup_candle_count = 200
    
    # CRITICAL: Enable futures trading
    can_short = True
    trading_mode = "futures"
    margin_mode = "isolated"
    
    # --- Leveraged Parameters (4x to 8x as requested) ---
    leverage_long = IntParameter(4, 8, default=6, space="buy", optimize=True)
    leverage_short = IntParameter(4, 8, default=6, space="sell", optimize=True)
    
    # Trend Detection
    ema_fast = IntParameter(8, 15, default=10, space="both", optimize=True)
    ema_medium = IntParameter(20, 35, default=26, space="both", optimize=True)
    ema_slow = IntParameter(40, 60, default=50, space="both", optimize=True)
    
    # ADX for trend strength
    adx_period = IntParameter(12, 20, default=14, space="both", optimize=True)
    adx_threshold = IntParameter(20, 30, default=23, space="both", optimize=True)
    
    # RSI parameters
    rsi_period = IntParameter(12, 18, default=14, space="both", optimize=True)
    rsi_bull_min = IntParameter(45, 55, default=50, space="buy", optimize=True)
    rsi_bull_max = IntParameter(65, 75, default=70, space="buy", optimize=True)
    rsi_bear_min = IntParameter(25, 35, default=30, space="sell", optimize=True)
    rsi_bear_max = IntParameter(45, 55, default=50, space="sell", optimize=True)
    
    # Volume confirmation
    volume_ma_period = IntParameter(15, 25, default=20, space="both", optimize=True)
    volume_threshold = DecimalParameter(1.1, 2.0, default=1.3, space="both", optimize=True)
    
    # MACD parameters
    macd_fast = IntParameter(10, 14, default=12, space="both", optimize=True)
    macd_slow = IntParameter(24, 28, default=26, space="both", optimize=True)
    macd_signal = IntParameter(8, 10, default=9, space="both", optimize=True)
    
    # ATR for volatility
    atr_period = IntParameter(12, 18, default=14, space="both", optimize=True)
    atr_multiplier_sl = DecimalParameter(1.5, 2.5, default=2.0, space="both", optimize=True)
    
    # Exit parameters
    exit_profit_threshold = DecimalParameter(0.005, 0.02, default=0.01, space="sell", optimize=True)
    exit_trend_reversal_strength = IntParameter(1, 3, default=2, space="sell", optimize=True)

    def informative_pairs(self):
        """Get additional data for market context"""
        pairs = self.dp.current_whitelist()
        informative_pairs = [
            ("BTC/USDT:USDT", "5m"),
            ("BTC/USDT:USDT", "15m"),
        ]
        for pair in pairs:
            informative_pairs.append((pair, "15m"))
        return list(set(informative_pairs))  # Remove duplicates

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all technical indicators"""
        
        # EMAs for trend
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.ema_fast.value)
        dataframe['ema_medium'] = ta.EMA(dataframe, timeperiod=self.ema_medium.value)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.ema_slow.value)
        
        # Trend determination
        dataframe['uptrend'] = (
            (dataframe['ema_fast'] > dataframe['ema_medium']) & 
            (dataframe['ema_medium'] > dataframe['ema_slow']) &
            (dataframe['close'] > dataframe['ema_fast'])
        )
        
        dataframe['downtrend'] = (
            (dataframe['ema_fast'] < dataframe['ema_medium']) & 
            (dataframe['ema_medium'] < dataframe['ema_slow']) &
            (dataframe['close'] < dataframe['ema_fast'])
        )
        
        # ADX for trend strength
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=self.adx_period.value)
        dataframe['plus_di'] = ta.PLUS_DI(dataframe, timeperiod=self.adx_period.value)
        dataframe['minus_di'] = ta.MINUS_DI(dataframe, timeperiod=self.adx_period.value)
        dataframe['trend_strength'] = dataframe['adx'] > self.adx_threshold.value
        
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.rsi_period.value)
        
        # MACD
        macd = ta.MACD(dataframe, 
                      fastperiod=self.macd_fast.value,
                      slowperiod=self.macd_slow.value,
                      signalperiod=self.macd_signal.value)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_hist'] = macd['macdhist']
        
        # Volume
        dataframe['volume_ma'] = ta.SMA(dataframe['volume'], timeperiod=self.volume_ma_period.value)
        dataframe['volume_ok'] = dataframe['volume'] > (dataframe['volume_ma'] * self.volume_threshold.value)
        
        # ATR for volatility
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=self.atr_period.value)
        dataframe['atr_percent'] = (dataframe['atr'] / dataframe['close']) * 100
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        dataframe['bb_lower'] = bollinger['lower']
        dataframe['bb_middle'] = bollinger['mid']
        dataframe['bb_upper'] = bollinger['upper']
        dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
        
        # Price momentum
        dataframe['momentum'] = dataframe['close'].pct_change(periods=10) * 100
        
        # Support and Resistance (no future bias)
        dataframe['resistance'] = dataframe['high'].rolling(window=20).max()
        dataframe['support'] = dataframe['low'].rolling(window=20).min()
        
        # Add higher timeframe confirmation
        dataframe = self.add_higher_tf_trend(dataframe, metadata)
        
        # Add BTC trend
        dataframe = self.add_btc_trend(dataframe)
        
        return dataframe

    def add_higher_tf_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add 15m timeframe trend confirmation"""
        try:
            inf_tf = self.dp.get_pair_dataframe(metadata['pair'], '15m')
            if not inf_tf.empty:
                inf_tf['ema_fast_15m'] = ta.EMA(inf_tf, timeperiod=9)
                inf_tf['ema_slow_15m'] = ta.EMA(inf_tf, timeperiod=21)
                inf_tf['trend_15m'] = np.where(
                    inf_tf['ema_fast_15m'] > inf_tf['ema_slow_15m'], 1, -1
                )
                dataframe = merge_informative_pair(
                    dataframe, inf_tf[['date', 'trend_15m']], 
                    self.timeframe, '15m', ffill=True
                )
            else:
                dataframe['trend_15m'] = 0
        except:
            dataframe['trend_15m'] = 0
        
        return dataframe
    
    def add_btc_trend(self, dataframe: DataFrame) -> DataFrame:
        """Add BTC market trend"""
        try:
            btc_5m = self.dp.get_pair_dataframe("BTC/USDT:USDT", "5m")
            if not btc_5m.empty:
                btc_5m['btc_ema_fast'] = ta.EMA(btc_5m, timeperiod=9)
                btc_5m['btc_ema_slow'] = ta.EMA(btc_5m, timeperiod=21)
                btc_5m['btc_trend'] = np.where(
                    btc_5m['btc_ema_fast'] > btc_5m['btc_ema_slow'], 1, -1
                )
                dataframe = merge_informative_pair(
                    dataframe, btc_5m[['date', 'btc_trend']], 
                    self.timeframe, "5m", ffill=True
                )
            else:
                dataframe['btc_trend_5m'] = 0
        except:
            dataframe['btc_trend_5m'] = 0
            
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Entry signals for long and short positions"""
        
        # LONG CONDITIONS
        long_conditions = [
            dataframe['uptrend'],  # EMAs aligned bullish
            dataframe['trend_strength'],  # ADX confirms trend
            (dataframe['rsi'] > self.rsi_bull_min.value),  # RSI not oversold
            (dataframe['rsi'] < self.rsi_bull_max.value),  # RSI not overbought
            (dataframe['macd'] > dataframe['macd_signal']),  # MACD bullish
            dataframe['volume_ok'],  # Volume confirmation
            (dataframe['plus_di'] > dataframe['minus_di']),  # DI+ > DI-
            (dataframe.get('trend_15m', 0) >= 0),  # 15m not bearish
            (dataframe['momentum'] > -1),  # Not in strong decline
        ]
        
        # SHORT CONDITIONS
        short_conditions = [
            dataframe['downtrend'],  # EMAs aligned bearish
            dataframe['trend_strength'],  # ADX confirms trend
            (dataframe['rsi'] < self.rsi_bear_max.value),  # RSI not overbought
            (dataframe['rsi'] > self.rsi_bear_min.value),  # RSI not oversold
            (dataframe['macd'] < dataframe['macd_signal']),  # MACD bearish
            dataframe['volume_ok'],  # Volume confirmation
            (dataframe['minus_di'] > dataframe['plus_di']),  # DI- > DI+
            (dataframe.get('trend_15m', 0) <= 0),  # 15m not bullish
            (dataframe['momentum'] < 1),  # Not in strong rise
        ]
        
        # Apply conditions
        if long_conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, long_conditions),
                'enter_long'] = 1
                
        if short_conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, short_conditions),
                'enter_short'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit signals - more conservative to avoid premature exits"""
        
        # Exit LONG conditions (need strong bearish reversal)
        exit_long_conditions = []
        
        if self.exit_trend_reversal_strength.value >= 1:
            # Level 1: Basic trend reversal
            exit_long_conditions.append(
                dataframe['downtrend'] &  # Full downtrend confirmed
                (dataframe['rsi'] < 40) &  # RSI showing weakness
                (dataframe['minus_di'] > dataframe['plus_di'] * 1.5)  # Strong bearish DI
            )
        
        if self.exit_trend_reversal_strength.value >= 2:
            # Level 2: Add MACD confirmation
            exit_long_conditions.append(
                (dataframe['macd'] < dataframe['macd_signal']) &
                (dataframe['macd_hist'] < 0) &
                (dataframe['momentum'] < -2)
            )
        
        if self.exit_trend_reversal_strength.value >= 3:
            # Level 3: Only exit on very strong signals
            exit_long_conditions.append(
                (dataframe['close'] < dataframe['ema_slow']) &
                (dataframe['volume'] > dataframe['volume_ma'] * 2)
            )
        
        # Exit SHORT conditions (need strong bullish reversal)
        exit_short_conditions = []
        
        if self.exit_trend_reversal_strength.value >= 1:
            # Level 1: Basic trend reversal
            exit_short_conditions.append(
                dataframe['uptrend'] &  # Full uptrend confirmed
                (dataframe['rsi'] > 60) &  # RSI showing strength
                (dataframe['plus_di'] > dataframe['minus_di'] * 1.5)  # Strong bullish DI
            )
        
        if self.exit_trend_reversal_strength.value >= 2:
            # Level 2: Add MACD confirmation
            exit_short_conditions.append(
                (dataframe['macd'] > dataframe['macd_signal']) &
                (dataframe['macd_hist'] > 0) &
                (dataframe['momentum'] > 2)
            )
        
        if self.exit_trend_reversal_strength.value >= 3:
            # Level 3: Only exit on very strong signals
            exit_short_conditions.append(
                (dataframe['close'] > dataframe['ema_slow']) &
                (dataframe['volume'] > dataframe['volume_ma'] * 2)
            )
        
        # Apply exit conditions only if we have them
        if exit_long_conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, exit_long_conditions),
                'exit_long'] = 1
                
        if exit_short_conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, exit_short_conditions),
                'exit_short'] = 1

        return dataframe
    
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """
        CRITICAL: Return leverage for the position
        This determines the actual leverage used in trading
        """
        if side == "long":
            return min(self.leverage_long.value, max_leverage)
        else:  # short
            return min(self.leverage_short.value, max_leverage)

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: Optional[float], max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """
        Custom position sizing that accounts for leverage
        This ensures we don't over-leverage our positions
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return proposed_stake
            
        last_candle = dataframe.iloc[-1]
        
        # Get the leverage we're using
        actual_leverage = self.leverage_long.value if side == "long" else self.leverage_short.value
        
        # Adjust stake based on volatility (ATR)
        atr_percent = last_candle.get('atr_percent', 1)
        if atr_percent > 3:  # High volatility
            stake_multiplier = 0.5  # Use half stake
        elif atr_percent > 2:  # Medium volatility
            stake_multiplier = 0.75
        else:  # Low volatility
            stake_multiplier = 1.0
        
        # Adjust stake based on trend strength
        if last_candle.get('adx', 0) > 30:  # Strong trend
            stake_multiplier *= 1.2
        elif last_candle.get('adx', 0) < 20:  # Weak trend
            stake_multiplier *= 0.8
        
        # Calculate final stake
        custom_stake = proposed_stake * stake_multiplier
        
        # Make sure we don't exceed max stake with leverage
        max_position_value = max_stake * actual_leverage
        max_allowed_stake = max_position_value / actual_leverage
        
        # Return the minimum of our custom stake and max allowed
        return min(custom_stake, max_allowed_stake, max_stake)

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                       current_rate: float, current_profit: float,
                       after_fill: bool, **kwargs) -> Optional[float]:
        """
        Dynamic stop loss based on ATR and profit
        Accounts for leverage in the calculation
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return None
            
        last_candle = dataframe.iloc[-1]
        trade_leverage = trade.leverage or 1.0
        
        # Base stoploss adjusted for leverage
        # Higher leverage = tighter stop to protect capital
        leverage_adjusted_stop = self.stoploss / trade_leverage
        
        # ATR-based stop loss
        atr = last_candle.get('atr', 0)
        if atr > 0:
            atr_stop = (atr * self.atr_multiplier_sl.value) / current_rate
            # For leveraged positions, use tighter of the two
            dynamic_stop = max(min(-atr_stop, leverage_adjusted_stop), -0.15)
        else:
            dynamic_stop = leverage_adjusted_stop
        
        # Profit-based stop adjustment
        if current_profit > 0.20:
            return max(dynamic_stop, -0.02)  # 2% stop at 20%+ profit
        elif current_profit > 0.15:
            return max(dynamic_stop, -0.03)  # 3% stop at 15%+ profit
        elif current_profit > 0.10:
            return max(dynamic_stop, -0.04)  # 4% stop at 10%+ profit
        elif current_profit > 0.05:
            return max(dynamic_stop, -0.05)  # 5% stop at 5%+ profit
        
        return dynamic_stop

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                       time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                       side: str, **kwargs) -> bool:
     dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
     if dataframe.empty:
         return False
        
     last_candle = dataframe.iloc[-1]
    
     # Avoid low volatility or volume conditions
     if last_candle.get('bb_width', 1) < 0.005:
         return False
     if last_candle.get('volume', 0) < last_candle.get('volume_ma', 1) * 0.3:
         return False
        
     # Avoid extreme RSI
     rsi = last_candle.get('rsi', 50)
     if side == "long" and rsi > 80:
         return False
     elif side == "short" and rsi < 20:
         return False
        
     # Check spread with error handling
     try:
        if self.dp._exchange is not None:  # Ensure exchange is available
            ticker = self.dp.ticker(pair)
            if ticker and ticker.get('bid') and ticker.get('ask'):
                spread = (ticker['ask'] - ticker['bid']) / ticker['bid']
                if spread > 0.002:
                    return False
     except AttributeError:
        # Log warning if desired
        pass
        
     return True

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, 
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """
        Custom exit logic for emergency situations
        Especially important for leveraged positions
        """
        if trade.calc_profit_ratio(current_rate) < -0.08:
            # Emergency exit if approaching stop loss with leverage
            # This prevents complete liquidation
            return 'emergency_exit'
        
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe.empty:
            return None
            
        last_candle = dataframe.iloc[-1]
        
        # Exit if momentum completely reverses
        if trade.is_short:
            if (last_candle.get('momentum', 0) > 3 and 
                last_candle.get('rsi', 50) > 70 and
                last_candle.get('macd', 0) > last_candle.get('macd_signal', 0)):
                return 'strong_reversal'
        else:  # Long
            if (last_candle.get('momentum', 0) < -3 and 
                last_candle.get('rsi', 50) < 30 and
                last_candle.get('macd', 0) < last_candle.get('macd_signal', 0)):
                return 'strong_reversal'
        
        # Take profit if we have exceptional gains (important with leverage)
        if current_profit > 0.25:  # 25% profit with leverage is excellent
            return 'take_profit'
        
        return None

    def custom_exit_price(self, pair: str, trade: Trade, current_time: datetime,
                         proposed_rate: float, current_profit: float, exit_tag: Optional[str],
                         **kwargs) -> float:
        """
        Custom exit price - can help with slippage in leveraged positions
        """
        # For emergency exits, accept a slightly worse price to ensure fill
        if exit_tag == 'emergency_exit':
            if trade.is_short:
                return proposed_rate * 1.002  # Pay 0.2% more to exit short
            else:
                return proposed_rate * 0.998  # Accept 0.2% less to exit long
        
        return proposed_rate
