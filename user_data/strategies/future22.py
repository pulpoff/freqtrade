from functools import reduce
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter
from freqtrade.enums import RunMode

class future22(IStrategy):
    minimal_roi = {
        "0": 0.066,
        "2": 0.028,
        "5": 0.01,
        "46": 0
    }

    stoploss = -0.06
    trailing_stop = True
    trailing_stop_positive = 0.143
    trailing_stop_positive_offset = 0.216
    trailing_only_offset_is_reached = True

    # Base timeframe for exits
    timeframe = '1m'
    informative_timeframes = ['1m', '5m', '15m', '30m']
    
    startup_candle_count = 100
    process_only_new_candles = True
    can_short = True
    can_long = False

    _last_candle_seen_time = {}
    _entry_signals = {}  # Track entry signals with timestamps and prices

    # General parameters for hyperopt
    leverage_param = IntParameter(1, 9, default=2, space="buy", optimize=True)
    buy_rsi = IntParameter(20, 50, default=31, space="buy", optimize=True)
    sell_rsi_upper = IntParameter(60, 95, default=85, space="sell", optimize=True)
    sell_rsi_lower = IntParameter(10, 40, default=26, space="sell", optimize=True)
    price_extension_pct = DecimalParameter(0.001, 0.01, default=0.004, space="sell", optimize=True)
    
    # MACD parameters
    macd_fast = IntParameter(8, 20, default=12, space="both", optimize=True)
    macd_slow = IntParameter(15, 40, default=26, space="both", optimize=True)
    macd_signal = IntParameter(5, 15, default=9, space="both", optimize=True)
    
    # MA parameters
    ema_short_period = IntParameter(3, 15, default=8, space="both", optimize=True)
    ema_long_period = IntParameter(15, 35, default=21, space="both", optimize=True)
    
    # Default entry wait time parameter
    entry_wait_time = IntParameter(0, 90, default=1, space="buy", optimize=True)
    
    # ROI parameters
    roi_t0 = DecimalParameter(0.03, 0.1, default=0.066, space="sell", optimize=True)
    roi_t1 = DecimalParameter(0.01, 0.05, default=0.028, space="sell", optimize=True)
    roi_t2 = DecimalParameter(0.003, 0.02, default=0.007, space="sell", optimize=True)
    roi_t3 = IntParameter(1, 5, default=2, space="sell", optimize=True)
    roi_t4 = IntParameter(3, 10, default=5, space="sell", optimize=True)
    roi_t5 = IntParameter(15, 40, default=26, space="sell", optimize=True)

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_candle_seen_time = {}
        self._entry_signals = {}  # Initialize entry signals tracking dictionary
        self.coin_roi = {}
        self.dp = None  # Data provider will be set by Freqtrade
        
        # Get all coins from whitelist
        self.coins = []
        if 'exchange' in config and 'pair_whitelist' in config['exchange']:
            for pair in config['exchange']['pair_whitelist']:
                coin = pair.split('/')[0]
                self.coins.append(coin)
        
        # Define coin-specific parameters
        for coin in self.coins:
            # Leverage
            setattr(self, f"{coin}_leverage", 
                    IntParameter(1, 9, default=4, space="buy", optimize=True))
            
            # Timeframe selection
            setattr(self, f"{coin}_timeframe", 
                    CategoricalParameter(['1m', '5m', '15m', '30m'], default='1m', space="buy", optimize=True))
            
            # RSI
            setattr(self, f"{coin}_buy_rsi", 
                    IntParameter(20, 50, default=31, space="buy", optimize=True))
            setattr(self, f"{coin}_sell_rsi_upper", 
                    IntParameter(60, 95, default=85, space="sell", optimize=True))
            setattr(self, f"{coin}_sell_rsi_lower", 
                    IntParameter(10, 40, default=26, space="sell", optimize=True))
            
            # MACD
            setattr(self, f"{coin}_macd_fast", 
                    IntParameter(8, 20, default=12, space="both", optimize=True))
            setattr(self, f"{coin}_macd_slow", 
                    IntParameter(15, 40, default=26, space="both", optimize=True))
            setattr(self, f"{coin}_macd_signal", 
                    IntParameter(5, 15, default=9, space="both", optimize=True))
            
            # MA
            setattr(self, f"{coin}_ema_short", 
                    IntParameter(3, 15, default=8, space="both", optimize=True))
            setattr(self, f"{coin}_ema_long", 
                    IntParameter(15, 35, default=21, space="both", optimize=True))
            
            # Price extension
            setattr(self, f"{coin}_price_ext", 
                    DecimalParameter(0.001, 0.01, default=0.004, space="sell", optimize=True))
            
            # Add the entry wait time parameter for each coin
            setattr(self, f"{coin}_entry_wait", 
                    IntParameter(1, 15, default=5, space="buy", optimize=True))
            
            # ROI
            setattr(self, f"{coin}_roi_t0", 
                    DecimalParameter(0.03, 0.1, default=0.066, space="sell", optimize=True))
            setattr(self, f"{coin}_roi_t1", 
                    DecimalParameter(0.01, 0.05, default=0.028, space="sell", optimize=True))
            setattr(self, f"{coin}_roi_t2", 
                    DecimalParameter(0.003, 0.02, default=0.007, space="sell", optimize=True))
            setattr(self, f"{coin}_roi_t1_time", 
                    IntParameter(1, 5, default=2, space="sell", optimize=True))
            setattr(self, f"{coin}_roi_t2_time", 
                    IntParameter(3, 10, default=5, space="sell", optimize=True))
            setattr(self, f"{coin}_roi_t3_time", 
                    IntParameter(15, 40, default=26, space="sell", optimize=True))
            
            # Initialize ROI for this coin
            self.update_coin_roi(coin)

    def informative_pairs(self):
        pairs = []
        for pair in self.dp.current_whitelist():
            for timeframe in self.informative_timeframes:
                if timeframe != self.timeframe:  # Skip base timeframe
                    pairs.append((pair, timeframe))
        return pairs

    def update_coin_roi(self, coin: str) -> None:
        """Update coin-specific ROI"""
        if hasattr(self, f"{coin}_roi_t0"):
            self.coin_roi[coin] = {
                "0": getattr(self, f"{coin}_roi_t0").value,
                str(getattr(self, f"{coin}_roi_t1_time").value): getattr(self, f"{coin}_roi_t1").value,
                str(getattr(self, f"{coin}_roi_t2_time").value): getattr(self, f"{coin}_roi_t2").value,
                str(getattr(self, f"{coin}_roi_t3_time").value): 0
            }

    def get_params_for_coin(self, coin: str) -> dict:
        """Get parameters for a specific coin"""
        result = {}
        
        # Try to get coin-specific parameters first
        if hasattr(self, f"{coin}_leverage"):
            result = {
                'leverage': getattr(self, f"{coin}_leverage"),
                'timeframe': getattr(self, f"{coin}_timeframe"),
                'buy_rsi': getattr(self, f"{coin}_buy_rsi"),
                'sell_rsi_upper': getattr(self, f"{coin}_sell_rsi_upper"),
                'sell_rsi_lower': getattr(self, f"{coin}_sell_rsi_lower"),
                'macd_fast': getattr(self, f"{coin}_macd_fast"),
                'macd_slow': getattr(self, f"{coin}_macd_slow"),
                'macd_signal': getattr(self, f"{coin}_macd_signal"),
                'ema_short': getattr(self, f"{coin}_ema_short"),
                'ema_long': getattr(self, f"{coin}_ema_long"),
                'price_ext': getattr(self, f"{coin}_price_ext"),
                'entry_wait': getattr(self, f"{coin}_entry_wait"),
                'roi_t0': getattr(self, f"{coin}_roi_t0"),
                'roi_t1': getattr(self, f"{coin}_roi_t1"),
                'roi_t2': getattr(self, f"{coin}_roi_t2"),
            }
        else:
            # Fallback to general parameters
            result = {
                'leverage': self.leverage_param,
                'timeframe': CategoricalParameter(['1m', '5m', '15m', '30m'], default='1m', space="buy", optimize=False),
                'buy_rsi': self.buy_rsi,
                'sell_rsi_upper': self.sell_rsi_upper,
                'sell_rsi_lower': self.sell_rsi_lower,
                'macd_fast': self.macd_fast,
                'macd_slow': self.macd_slow,
                'macd_signal': self.macd_signal,
                'ema_short': self.ema_short_period,
                'ema_long': self.ema_long_period,
                'price_ext': self.price_extension_pct,
                'entry_wait': self.entry_wait_time,
                'roi_t0': self.roi_t0,
                'roi_t1': self.roi_t1,
                'roi_t2': self.roi_t2,
            }
        
        return result

    def custom_minimal_roi(self, pair: str, current_profit: float, current_time: datetime, trade: 'Trade') -> float:
        """Override minimal ROI for specific coins"""
        coin = pair.split('/')[0]
        
        # Update coin-specific ROI
        self.update_coin_roi(coin)
        
        if coin in self.coin_roi:
            # Find appropriate ROI based on trade duration
            elapsed_minutes = (current_time - trade.open_date).total_seconds() / 60
            for roi_time, roi_value in sorted(self.coin_roi[coin].items(), key=lambda x: int(x[0]) if x[0] != "0" else 0):
                if roi_time == "0" or elapsed_minutes >= int(roi_time):
                    roi = roi_value
                else:
                    break
            return roi
        
        # Fallback to default
        return None

    def get_informative_indicators(self, metadata: dict):
        """Get data at the coin's optimal timeframe for entry decisions"""
        coin = metadata['pair'].split('/')[0]
        pair = metadata['pair']
        
        # Get preferred timeframe for this coin
        params = self.get_params_for_coin(coin)
        preferred_timeframe = params['timeframe'].value
        
        # Skip if using base timeframe or dataframe not available
        if preferred_timeframe == self.timeframe:
            return None
            
        # Get dataframe for the preferred timeframe
        informative = self.dp.get_pair_dataframe(pair, preferred_timeframe)
        if len(informative) == 0:
            return None
            
        # Calculate indicators on the preferred timeframe
        # RSI indicator
        informative['rsi'] = ta.RSI(informative, timeperiod=14)
        
        # Stochastic
        stoch = ta.STOCH(informative, fastk_period=14, slowk_period=3, slowd_period=3)
        informative['slowk'] = stoch['slowk']
        informative['slowd'] = stoch['slowd']
        
        # MACD with parameters
        macd = ta.MACD(informative, 
                      fastperiod=params['macd_fast'].value,
                      slowperiod=params['macd_slow'].value, 
                      signalperiod=params['macd_signal'].value)
        informative['macd'] = macd['macd']
        informative['macdsignal'] = macd['macdsignal']
        informative['macdhist'] = macd['macdhist']
        
        # Store shifted values
        informative['macdhist_prev1'] = informative['macdhist'].shift(1)
        informative['macdhist_prev2'] = informative['macdhist'].shift(2)
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(informative), window=20, stds=2)
        informative['bb_upperband'] = bollinger['upper']
        informative['bb_middleband'] = bollinger['mid']
        informative['bb_lowerband'] = bollinger['lower']
        
        # Moving averages
        informative['ema_short'] = ta.EMA(informative, timeperiod=params['ema_short'].value)
        informative['ema_long'] = ta.EMA(informative, timeperiod=params['ema_long'].value)
        
        # Store shifted prices
        for i in range(1, 4):
            informative[f'close_prev{i}'] = informative['close'].shift(i)
            informative[f'high_prev{i}'] = informative['high'].shift(i)
            informative[f'low_prev{i}'] = informative['low'].shift(i)
        
        # Detect peaks
        informative['high_last_3'] = informative['high'].rolling(3).max()
        
        # Price is at a local peak
        informative['price_peak'] = (
            (informative['high'] >= informative['high_last_3'] * 0.995) &
            (informative['high'] > informative['high_prev1']) &
            (informative['close'] > informative['ema_short']) &
            (informative['rsi'] > params['sell_rsi_upper'].value)
        )
        
        # Price reversal after a rise
        informative['price_reversal'] = (
            (informative['close_prev2'] < informative['close_prev1']) &
            (informative['close'] < informative['close_prev1']) &
            (informative['close_prev1'] > informative['close_prev1'].rolling(3).max().shift(1)) &
            (informative['rsi'] > params['sell_rsi_upper'].value * 0.9)
        )
        
        # MACD histogram reversal
        informative['macd_reversal'] = (
            (informative['macdhist_prev2'] < informative['macdhist_prev1']) &
            (informative['macdhist'] < informative['macdhist_prev1']) &
            (informative['macdhist_prev1'] > 0) &
            (informative['close'] > informative['ema_short'])
        )
        
        # Combined entry signal
        informative['short_entry_signal'] = (
            (informative['price_peak'] | informative['price_reversal'] | informative['macd_reversal']) &
            (informative['rsi'] > params['sell_rsi_upper'].value * 0.9) &
            (informative['close'] > informative['ema_short'] * (1 + params['price_ext'].value))
        )
        
        # Add prefix to all columns
        informative.columns = [f"{preferred_timeframe}_{col}" for col in informative.columns]
        
        return informative

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
     """Calculate indicators on 1m timeframe and merge higher timeframe indicators"""
     coin = metadata['pair'].split('/')[0]
     params = self.get_params_for_coin(coin)
    
     # RSI indicator
     dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
    
     # Stochastic
     stoch = ta.STOCH(dataframe, fastk_period=14, slowk_period=3, slowd_period=3)
     dataframe['slowk'] = stoch['slowk']
     dataframe['slowd'] = stoch['slowd']
    
     # MACD with parameters
     macd = ta.MACD(dataframe, 
                  fastperiod=params['macd_fast'].value,
                  slowperiod=params['macd_slow'].value, 
                  signalperiod=params['macd_signal'].value)
     dataframe['macd'] = macd['macd']
     dataframe['macdsignal'] = macd['macdsignal']
     dataframe['macdhist'] = macd['macdhist']
    
     # Store shifted values
     dataframe['macdhist_prev1'] = dataframe['macdhist'].shift(1)
     dataframe['macdhist_prev2'] = dataframe['macdhist'].shift(2)
    
     # Bollinger Bands
     bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
     dataframe['bb_upperband'] = bollinger['upper']
     dataframe['bb_middleband'] = bollinger['mid']
     dataframe['bb_lowerband'] = bollinger['lower']
    
     # Moving averages
     dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=params['ema_short'].value)
     dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=params['ema_long'].value)
    
     # Store shifted prices
     for i in range(1, 4):
        dataframe[f'close_prev{i}'] = dataframe['close'].shift(i)
        dataframe[f'high_prev{i}'] = dataframe['high'].shift(i)
        dataframe[f'low_prev{i}'] = dataframe['low'].shift(i)
    
     # *** IMPORTANT FIX: Always initialize short_entry_signal column to prevent KeyError ***
     dataframe['short_entry_signal'] = False
    
     # Get preferred timeframe indicators
     informative = self.get_informative_indicators(metadata)
     if informative is not None:
        # Merge with original dataframe
        dataframe = pd.merge(dataframe, informative, left_index=True, right_index=True, how='left')
        # Forward-fill NaN values to handle different timeframes
        dataframe = dataframe.ffill()
    
     # For 1m timeframe, calculate entry signals directly
     if params['timeframe'].value == self.timeframe:
        # Detect peaks
        dataframe['high_last_3'] = dataframe['high'].rolling(3).max()
        
        # Price is at a local peak
        dataframe['price_peak'] = (
            (dataframe['high'] >= dataframe['high_last_3'] * 0.995) &
            (dataframe['high'] > dataframe['high_prev1']) &
            (dataframe['close'] > dataframe['ema_short']) &
            (dataframe['rsi'] > params['sell_rsi_upper'].value)
        )
        
        # Price reversal after a rise
        dataframe['price_reversal'] = (
            (dataframe['close_prev2'] < dataframe['close_prev1']) &
            (dataframe['close'] < dataframe['close_prev1']) &
            (dataframe['close_prev1'] > dataframe['close_prev1'].rolling(3).max().shift(1)) &
            (dataframe['rsi'] > params['sell_rsi_upper'].value * 0.9)
        )
        
        # MACD histogram reversal
        dataframe['macd_reversal'] = (
            (dataframe['macdhist_prev2'] < dataframe['macdhist_prev1']) &
            (dataframe['macdhist'] < dataframe['macdhist_prev1']) &
            (dataframe['macdhist_prev1'] > 0) &
            (dataframe['close'] > dataframe['ema_short'])
        )
        
        # Combined entry signal
        dataframe['short_entry_signal'] = (
            (dataframe['price_peak'] | dataframe['price_reversal'] | dataframe['macd_reversal']) &
            (dataframe['rsi'] > params['sell_rsi_upper'].value * 0.9) &
            (dataframe['close'] > dataframe['ema_short'] * (1 + params['price_ext'].value))
        )
    
     # Calculate exit signals - always on 1m timeframe
     # Oversold condition for exits
     dataframe['deep_oversold'] = (
        (dataframe['rsi'] < params['sell_rsi_lower'].value * 0.9) &
        (dataframe['close'] < dataframe['bb_lowerband'] * 1.01) &
        (dataframe['close'] < dataframe['ema_short'] * 0.99)
     )
    
     # Major trend reversal
     dataframe['major_trend_reversal'] = (
        qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal']) &
        (dataframe['macd'] < 0) &
        (dataframe['macdhist'] > dataframe['macdhist'].shift(1) * 1.2) &
        (dataframe['close'] < dataframe['ema_short'])
     )
    
     # Combined exit signal
     dataframe['short_exit_signal'] = (
        dataframe['deep_oversold'] | 
        dataframe['major_trend_reversal']
     )
    
     return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
     """Entry signals based on coin's preferred timeframe"""
     coin = metadata['pair'].split('/')[0]
     params = self.get_params_for_coin(coin)
     preferred_timeframe = params['timeframe'].value
    
     dataframe['enter_long'] = 0
     dataframe['enter_short'] = 0
    
     # Ensure short_entry_signal exists before using it
     if 'short_entry_signal' not in dataframe.columns:
        dataframe['short_entry_signal'] = False
        
     # If using base timeframe
     if preferred_timeframe == self.timeframe:
        dataframe.loc[dataframe['short_entry_signal'], 'enter_short'] = 1
     else:
        # Use signals from the preferred timeframe
        column_name = f"{preferred_timeframe}_short_entry_signal"
        if column_name in dataframe.columns:
            dataframe.loc[dataframe[column_name], 'enter_short'] = 1
    
     return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                           time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                           side: str, **kwargs) -> bool:
        """
        Enhanced confirmation logic with wait time before entry
        """
        # Get the coin name from pair
        coin = pair.split('/')[0]
        
        # Get coin-specific parameters
        params = self.get_params_for_coin(coin)
        wait_time_minutes = params['entry_wait'].value
        
        # Create a unique key for this pair and side
        signal_key = f"{pair}_{side}"
        
        # If we haven't seen this signal before, record it
        if signal_key not in self._entry_signals:
            self._entry_signals[signal_key] = {
                'timestamp': current_time,
                'price': rate
            }
            return False  # Don't enter yet, wait for the time period
        
        # Get stored signal data
        entry_signal = self._entry_signals[signal_key]
        elapsed_minutes = (current_time - entry_signal['timestamp']).total_seconds() / 60
        
        # If we haven't waited long enough, reject
        if elapsed_minutes < wait_time_minutes:
            return False
        
        # If we've waited enough, check price action
        original_price = entry_signal['price']
        
        # For shorts, we want price to have held or gone up
        if side == 'short':
            # If price went down, reject the trade
            if rate < original_price:
                # Clear the signal since it didn't work out
                del self._entry_signals[signal_key]
                return False
        else:  # For longs (if implemented in future)
            # If price went up, reject the trade
            if rate > original_price:
                # Clear the signal since it didn't work out
                del self._entry_signals[signal_key]
                return False
        
        # Check cooldown period (3 minutes between trades of same pair)
        cooldown_minutes = 3
        
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
                
        # Update the last seen time for this pair
        self._last_candle_seen_time[pair] = current_time
        
        # Clear the entry signal since we're entering the trade
        del self._entry_signals[signal_key]
        
        return True

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit signals - always on 1m timeframe"""
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        dataframe.loc[dataframe['short_exit_signal'], 'exit_short'] = 1
        
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """Custom exit logic"""
        if trade.is_short:
            coin = pair.split('/')[0]
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if len(dataframe) > 0:
                    last_candle = dataframe.iloc[-1]
                    
                    params = self.get_params_for_coin(coin)
                    
                    roi_t0 = params['roi_t0'].value
                    if current_profit > roi_t0:
                        return 'short_profit_target_reached'
                    
                    sell_rsi_lower = params['sell_rsi_lower'].value
                    if current_profit > roi_t0/2.5 and 'rsi' in last_candle and last_candle['rsi'] < sell_rsi_lower:
                        return 'short_profit_extreme_oversold'
            except Exception:
                pass
        
        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
                **kwargs) -> float:
        """Get coin-specific leverage"""
        coin = pair.split('/')[0]
        
        if hasattr(self, f"{coin}_leverage"):
            return float(getattr(self, f"{coin}_leverage").value)
        
        return float(self.leverage_param.value)
