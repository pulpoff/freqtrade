from freqtrade.strategy.interface import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib
import pandas as pd
pd.options.mode.chained_assignment = None
from functools import reduce
import numpy as np
from freqtrade.strategy import DecimalParameter, IntParameter, CategoricalParameter
from datetime import datetime, timedelta
from typing import Dict, Optional
from freqtrade.persistence import Trade

class future39(IStrategy):
    """
    Exact replication of future33 strategy with per-coin parameters
    """
    # Strategy parameters
    timeframe = '1m'
    startup_candle_count = 100
    process_only_new_candles = False
    
    # Hyperopt parameters for leverage
    leverage_param = DecimalParameter(2.0, 9.0, decimals=1, default=5.0, space="buy", optimize=True)
    
    # Buy hyperspace params - exact same defaults as future33
    buy_rsi = IntParameter(30, 70, default=50, space="buy", optimize=True)
    buy_macd_threshold = DecimalParameter(-0.05, 0, default=-0.02, space="buy", optimize=True)
    buy_bb_middleband_mult = DecimalParameter(1.0, 1.5, default=1.2, space="buy", optimize=True)
    buy_price_lower_pct_mult = DecimalParameter(1.0, 1.2, default=1.1, space="buy", optimize=True)
    
    # Sell hyperspace params - exact same defaults as future33
    sell_rsi = IntParameter(60, 90, default=70, space="sell", optimize=True)
    sell_bb_upperband_mult = DecimalParameter(0.8, 1.0, default=0.9, space="sell", optimize=True)
    sell_close_mult = DecimalParameter(0.97, 0.995, default=0.985, space="sell", optimize=True)
    sell_bb_upperband_high_mult = DecimalParameter(1.0, 1.2, default=1.1, space="sell", optimize=True)
    
    # Stoploss - exact same as future33
    stoploss = -0.15
    
    # IMPORTANT FIX: Use regular values for these parameters instead of DecimalParameter objects
    # Trailing stoploss - exact same defaults as future33
    trailing_stop = True
    trailing_stop_positive = 0.005  # Default value as a float
    trailing_stop_positive_offset = 0.01  # Default value as a float
    trailing_only_offset_is_reached = True
    
    # Parameters for hyperopt to optimize trailing stop
    ts_positive_param = DecimalParameter(0.001, 0.01, default=0.005, space="sell", optimize=True)
    ts_offset_param = DecimalParameter(0.005, 0.02, default=0.01, space="sell", optimize=True)
    stoploss_param = DecimalParameter(0.05, 0.25, default=0.15, space="sell", optimize=True)
    
    # Optimizable hyperparameters for ROI - exact same defaults as future33
    roi_t1 = IntParameter(5, 20, default=10, space="roi", optimize=True)
    roi_t2 = IntParameter(15, 40, default=20, space="roi", optimize=True)
    roi_t3 = IntParameter(25, 60, default=30, space="roi", optimize=True)
    
    roi_p1 = DecimalParameter(0.01, 0.03, default=0.015, space="roi", optimize=True)
    roi_p2 = DecimalParameter(0.005, 0.015, default=0.01, space="roi", optimize=True)
    roi_p3 = DecimalParameter(0.001, 0.01, default=0.005, space="roi", optimize=True)
    
    # Futures specific settings - exactly like future33
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    can_short = False
    
    minimal_roi = {
        "0": 0.015,
        "10": 0.01,
        "20": 0.005,
        "30": 0
    }
    
    def __init__(self, config: dict) -> None:
        """Initialize strategy with per-coin parameters"""
        super().__init__(config)
        self.dp = None
        
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
                    DecimalParameter(2.0, 9.0, decimals=1, default=5.0, space="buy", optimize=True))
            
            # Buy parameters
            setattr(self, f"{coin}_buy_rsi", 
                    IntParameter(30, 70, default=50, space="buy", optimize=True))
            setattr(self, f"{coin}_buy_macd_threshold", 
                    DecimalParameter(-0.05, 0, default=-0.02, space="buy", optimize=True))
            setattr(self, f"{coin}_buy_bb_middleband_mult", 
                    DecimalParameter(1.0, 1.5, default=1.2, space="buy", optimize=True))
            setattr(self, f"{coin}_buy_price_lower_pct_mult", 
                    DecimalParameter(1.0, 1.2, default=1.1, space="buy", optimize=True))
            
            # Sell parameters
            setattr(self, f"{coin}_sell_rsi", 
                    IntParameter(60, 90, default=70, space="sell", optimize=True))
            setattr(self, f"{coin}_sell_bb_upperband_mult", 
                    DecimalParameter(0.8, 1.0, default=0.9, space="sell", optimize=True))
            setattr(self, f"{coin}_sell_close_mult", 
                    DecimalParameter(0.97, 0.995, default=0.985, space="sell", optimize=True))
            setattr(self, f"{coin}_sell_bb_upperband_high_mult", 
                    DecimalParameter(1.0, 1.2, default=1.1, space="sell", optimize=True))
            
            # Stoploss 
            setattr(self, f"{coin}_stoploss", 
                    DecimalParameter(0.05, 0.25, default=0.15, space="sell", optimize=True))
            
            # Trailing stop parameters
            setattr(self, f"{coin}_ts_positive", 
                    DecimalParameter(0.001, 0.01, default=0.005, space="sell", optimize=True))
            setattr(self, f"{coin}_ts_offset", 
                    DecimalParameter(0.005, 0.02, default=0.01, space="sell", optimize=True))
            
            # ROI parameters
            setattr(self, f"{coin}_roi_t1", 
                    IntParameter(5, 20, default=10, space="roi", optimize=True))
            setattr(self, f"{coin}_roi_t2", 
                    IntParameter(15, 40, default=20, space="roi", optimize=True))
            setattr(self, f"{coin}_roi_t3", 
                    IntParameter(25, 60, default=30, space="roi", optimize=True))
            
            setattr(self, f"{coin}_roi_p1", 
                    DecimalParameter(0.01, 0.03, default=0.015, space="roi", optimize=True))
            setattr(self, f"{coin}_roi_p2", 
                    DecimalParameter(0.005, 0.015, default=0.01, space="roi", optimize=True))
            setattr(self, f"{coin}_roi_p3", 
                    DecimalParameter(0.001, 0.01, default=0.005, space="roi", optimize=True))
    
    def custom_roi(self) -> Dict[str, float]:
        """
        Dynamically calculate ROI table values based on hyperopt parameters
        - Exact replication of future33 method
        """
        roi_table = {
            "0": self.roi_p1.value,
            str(self.roi_t1.value): self.roi_p2.value,
            str(self.roi_t2.value): self.roi_p3.value,
            str(self.roi_t3.value): 0
        }
        return roi_table

    def coin_custom_roi(self, coin: str) -> Dict[str, float]:
        """
        Coin-specific ROI calculation
        """
        if not hasattr(self, f"{coin}_roi_p1"):
            return self.custom_roi()
            
        roi_table = {
            "0": getattr(self, f"{coin}_roi_p1").value,
            str(getattr(self, f"{coin}_roi_t1").value): getattr(self, f"{coin}_roi_p2").value,
            str(getattr(self, f"{coin}_roi_t2").value): getattr(self, f"{coin}_roi_p3").value,
            str(getattr(self, f"{coin}_roi_t3").value): 0
        }
        return roi_table

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime, 
                       current_rate: float, current_profit: float, **kwargs) -> float:
        """Apply coin-specific stoploss"""
        coin = pair.split('/')[0]
        
        # Use coin-specific stoploss if available
        if hasattr(self, f"{coin}_stoploss"):
            return -getattr(self, f"{coin}_stoploss").value
        
        # Fallback to default
        return self.stoploss

    def custom_minimal_roi(self, pair: str, current_profit: float, current_time: datetime, trade: 'Trade') -> float:
        """Apply coin-specific ROI"""
        coin = pair.split('/')[0]
        
        # Use coin-specific ROI if available
        coin_roi = self.coin_custom_roi(coin)
        
        # Find appropriate ROI based on trade duration
        elapsed_minutes = (current_time - trade.open_date).total_seconds() / 60
        for roi_time, roi_value in sorted(coin_roi.items(), key=lambda x: int(x[0]) if x[0] != "0" else 0):
            if roi_time == "0" or elapsed_minutes >= int(roi_time):
                roi = roi_value
            else:
                break
        return roi
        
    def custom_trailing_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float, **kwargs) -> float:
        """Apply coin-specific trailing stop"""
        coin = pair.split('/')[0]
        
        # Use coin-specific trailing stop if available
        if hasattr(self, f"{coin}_ts_positive") and hasattr(self, f"{coin}_ts_offset"):
            ts_offset = getattr(self, f"{coin}_ts_offset").value
            if current_profit > ts_offset:
                return getattr(self, f"{coin}_ts_positive").value
        
        # Fallback to strategy parameters
        if current_profit > self.ts_offset_param.value:
            return self.ts_positive_param.value
            
        return None

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Calculate indicators based on future33 strategy
        - Exact replication of the original calculations
        """
        # MACD - adjusted for 1m timeframe
        macd = ta.MACD(dataframe, fastperiod=6, slowperiod=14, signalperiod=3)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']

        # Bollinger Bands - adjusted for 1m
        bollinger = qtpylib.bollinger_bands(dataframe['close'], window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']

        # Moving averages - adjusted for 1m
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=5)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=12)
        dataframe['avg_price_8h'] = dataframe['close'].rolling(window=480).mean()  # 8 hours in 1m
        dataframe['price_lower_20pct'] = dataframe['avg_price_8h'] * 0.9
        dataframe['price_upper_20pct'] = dataframe['avg_price_8h'] * 1.1

        # RSI & Stochastic RSI - adjusted for 1m
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=10)
        stoch_rsi = ta.STOCHRSI(dataframe, timeperiod=10, fastk_period=3, fastd_period=3)
        dataframe['stoch_rsi_k'] = stoch_rsi['fastk']
        dataframe['stoch_rsi_d'] = stoch_rsi['fastd']

        # Volume
        dataframe['volume_ma'] = dataframe['volume'].rolling(window=20).mean()
        
        # ATR
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Define entry signals - exact replication from future33
        """
        coin = metadata['pair'].split('/')[0]
        
        # Initialize columns
        dataframe['enter_long'] = 0
        
        # Get parameters - either coin-specific or default
        if hasattr(self, f"{coin}_buy_rsi"):
            buy_rsi = getattr(self, f"{coin}_buy_rsi").value
            buy_macd_threshold = getattr(self, f"{coin}_buy_macd_threshold").value
            buy_bb_middleband_mult = getattr(self, f"{coin}_buy_bb_middleband_mult").value
            buy_price_lower_pct_mult = getattr(self, f"{coin}_buy_price_lower_pct_mult").value
        else:
            buy_rsi = self.buy_rsi.value
            buy_macd_threshold = self.buy_macd_threshold.value
            buy_bb_middleband_mult = self.buy_bb_middleband_mult.value
            buy_price_lower_pct_mult = self.buy_price_lower_pct_mult.value
        
        conditions = []

        # MACD conditions
        conditions.append(
            (dataframe['macdhist'] > buy_macd_threshold) | 
            qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal'])
        )

        # Price conditions
        conditions.append(dataframe['close'] <= dataframe['bb_middleband'] * buy_bb_middleband_mult)
        conditions.append(dataframe['close'] <= dataframe['price_lower_20pct'] * buy_price_lower_pct_mult)

        # RSI condition
        conditions.append(dataframe['rsi'] < buy_rsi)

        # Volume condition
        conditions.append(dataframe['volume'] > dataframe['volume_ma'])

        # EMA condition
        conditions.append(dataframe['ema_short'] > dataframe['ema_long'])

        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Define exit signals - exact replication from future33
        """
        coin = metadata['pair'].split('/')[0]
        
        # Initialize columns
        dataframe['exit_long'] = 0
        
        # Get parameters - either coin-specific or default
        if hasattr(self, f"{coin}_sell_rsi"):
            sell_rsi = getattr(self, f"{coin}_sell_rsi").value
            sell_bb_upperband_mult = getattr(self, f"{coin}_sell_bb_upperband_mult").value
            sell_close_mult = getattr(self, f"{coin}_sell_close_mult").value
            sell_bb_upperband_high_mult = getattr(self, f"{coin}_sell_bb_upperband_high_mult").value
        else:
            sell_rsi = self.sell_rsi.value
            sell_bb_upperband_mult = self.sell_bb_upperband_mult.value
            sell_close_mult = self.sell_close_mult.value
            sell_bb_upperband_high_mult = self.sell_bb_upperband_high_mult.value
        
        conditions = []

        # Technical indicator exits
        conditions.append(
            (
                (dataframe['close'] >= dataframe['bb_upperband'] * sell_bb_upperband_mult) |
                (qtpylib.crossed_below(dataframe['ema_short'], dataframe['ema_long'])) |
                (dataframe['stoch_rsi_k'] > 80) |
                (dataframe['stoch_rsi_k'] < dataframe['stoch_rsi_d'])
            )
        )

        # RSI exit
        conditions.append(dataframe['rsi'] > sell_rsi)

        # Volume-based exit
        conditions.append(
            (dataframe['volume'] > dataframe['volume_ma'] * 1.5) &
            (dataframe['close'] < dataframe['close'].shift(1))
        )

        # Profit protection
        conditions.append(
            (dataframe['close'] < dataframe['close'].shift(1) * sell_close_mult) |
            (dataframe['close'] > dataframe['bb_upperband'] * sell_bb_upperband_high_mult)
        )

        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'exit_long'] = 1

        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                          time_in_force: str, current_time: datetime, entry_tag: Optional[str]=None, 
                          side: str="long", **kwargs) -> bool:
        """
        Exact replication of future33 confirm_trade_entry
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) == 0:
            return False
            
        last_candle = dataframe.iloc[-1].squeeze()

        # Additional volume confirmation
        if last_candle['volume'] < last_candle['volume_ma'] * 0.8:
            return False

        # Prevent entry if ATR is too high (volatile) - more conservative for futures
        if last_candle['atr'] > last_candle['close'] * 0.015:
            return False

        return True
    
    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                proposed_leverage: float, max_leverage: float, entry_tag: Optional[str]=None, 
                side: str="long", **kwargs) -> float:
        """Use coin-specific leverage or default"""
        coin = pair.split('/')[0]
        
        if hasattr(self, f"{coin}_leverage"):
            return float(getattr(self, f"{coin}_leverage").value)
        
        # Fallback to default
        return float(self.leverage_param.value)
