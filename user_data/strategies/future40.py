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
from collections import defaultdict

class future40(IStrategy):
    """
    Enhanced future33 strategy with new14 features for improved performance
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
    
    # New14 features - BB multiplier for precise entry
    bb_multiplier = DecimalParameter(1.0, 1.05, default=1.025, space="buy", optimize=True)
    
    # New14 volume threshold for entries
    volume_ma_multiplier = DecimalParameter(0.8, 2.0, default=1.0, space="buy", optimize=True)
    
    # New14 exit parameters
    exit_volume_multiplier = DecimalParameter(1.0, 2.0, default=1.2, space="sell", optimize=True)
    profit_threshold = DecimalParameter(0.008, 0.02, default=0.012, space="sell", optimize=True)
    
    # Stoploss - exact same as future33
    stoploss = -0.09
    
    # Trailing stoploss - fixed values
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
        # Track loss times for post-loss cooldown (from new14)
        self.last_loss_time = defaultdict(lambda: datetime.min)
        
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
            
            # New14 parameters
            setattr(self, f"{coin}_bb_multiplier", 
                    DecimalParameter(1.0, 1.05, default=1.025, space="buy", optimize=True))
            setattr(self, f"{coin}_volume_ma_multiplier", 
                    DecimalParameter(0.8, 2.0, default=1.0, space="buy", optimize=True))
            setattr(self, f"{coin}_profit_threshold", 
                    DecimalParameter(0.008, 0.02, default=0.012, space="sell", optimize=True))
            
            # Sell parameters
            setattr(self, f"{coin}_sell_rsi", 
                    IntParameter(60, 90, default=70, space="sell", optimize=True))
            setattr(self, f"{coin}_sell_bb_upperband_mult", 
                    DecimalParameter(0.8, 1.0, default=0.9, space="sell", optimize=True))
            setattr(self, f"{coin}_sell_close_mult", 
                    DecimalParameter(0.97, 0.995, default=0.985, space="sell", optimize=True))
            setattr(self, f"{coin}_sell_bb_upperband_high_mult", 
                    DecimalParameter(1.0, 1.2, default=1.1, space="sell", optimize=True))
            setattr(self, f"{coin}_exit_volume_multiplier", 
                    DecimalParameter(1.0, 2.0, default=1.2, space="sell", optimize=True))
            
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

    def get_coin_params(self, coin: str) -> dict:
        """Get all parameters for a specific coin"""
        params = {}
        
        # Basic parameters that should exist for every coin
        param_names = [
            "leverage", "buy_rsi", "buy_macd_threshold", "buy_bb_middleband_mult", 
            "buy_price_lower_pct_mult", "sell_rsi", "sell_bb_upperband_mult", 
            "sell_close_mult", "sell_bb_upperband_high_mult", "stoploss",
            "ts_positive", "ts_offset", "bb_multiplier", "volume_ma_multiplier",
            "exit_volume_multiplier", "profit_threshold"
        ]
        
        for param in param_names:
            coin_param = f"{coin}_{param}"
            if hasattr(self, coin_param):
                params[param] = getattr(self, coin_param).value
            elif hasattr(self, param):
                # Fall back to strategy-level parameter if it exists
                if hasattr(self, f"{param}_param"):
                    params[param] = getattr(self, f"{param}_param").value
                else:
                    params[param] = getattr(self, param).value
        
        return params

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
        Enhanced indicators combining future33 and new14
        """
        # MACD - adjusted for 1m timeframe
        macd = ta.MACD(dataframe, fastperiod=6, slowperiod=14, signalperiod=3)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Track MACD histogram trends (from new14)
        dataframe['hist_trend'] = dataframe['macdhist'] > dataframe['macdhist'].shift(1)
        dataframe['hist_peak'] = (
            (dataframe['macdhist'] > dataframe['macdhist'].shift(1)) & 
            (dataframe['macdhist'] > dataframe['macdhist'].shift(2))
        )

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
        
        # Price movement tracking (from new14)
        dataframe['price_dropped'] = dataframe['close'] < dataframe['close'].shift(1)
        dataframe['sequential_drops'] = (
            dataframe['price_dropped'] & 
            dataframe['price_dropped'].shift(1) & 
            dataframe['price_dropped'].shift(2)
        )
        
        # Local peak detection (from new14)
        dataframe['local_peak'] = (
            (dataframe['close'] > dataframe['close'].shift(2)) &
            (dataframe['close'] > dataframe['close'].shift(1)) &
            (dataframe['close'] > dataframe['close'].shift(-1)) &
            (dataframe['close'] > dataframe['close'].shift(-2))
        )
        
        # Upper wick analysis (from new14)
        dataframe['upper_wick'] = (dataframe['high'] - dataframe[['close', 'open']].max(axis=1)) / dataframe['high']

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Enhanced entry signals combining future33 and new14
        """
        coin = metadata['pair'].split('/')[0]
        pair = metadata['pair']
        params = self.get_coin_params(coin)
        
        # Initialize columns
        dataframe['enter_long'] = 0
        
        conditions = []

        # MACD conditions from future33
        conditions.append(
            (dataframe['macdhist'] > params['buy_macd_threshold']) | 
            qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal'])
        )

        # Price conditions from future33
        conditions.append(dataframe['close'] <= dataframe['bb_middleband'] * params['buy_bb_middleband_mult'])
        conditions.append(dataframe['close'] <= dataframe['price_lower_20pct'] * params['buy_price_lower_pct_mult'])
        
        # Additional BB precision from new14
        conditions.append(dataframe['close'] < dataframe['bb_lowerband'] * params['bb_multiplier'])

        # RSI condition from future33
        conditions.append(dataframe['rsi'] < params['buy_rsi'])

        # Volume condition with enhanced multiplier from new14
        conditions.append(dataframe['volume'] > dataframe['volume_ma'] * params['volume_ma_multiplier'])

        # EMA condition from future33
        conditions.append(dataframe['ema_short'] > dataframe['ema_long'])
        
        # MACD histogram trend from new14
        conditions.append(dataframe['macdhist'] > dataframe['macdhist'].shift(1))

        # Apply cooldown after losses (from new14)
        last_loss = self.last_loss_time[pair]
        if last_loss > datetime.min:
            cooldown_end = last_loss + timedelta(hours=1)
            dataframe['cooldown_mask'] = dataframe['date'].apply(
                lambda x: x >= last_loss and x <= cooldown_end)
            conditions.append(~dataframe['cooldown_mask'])

        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Enhanced exit signals combining future33 and new14
        """
        coin = metadata['pair'].split('/')[0]
        params = self.get_coin_params(coin)
        
        # Initialize columns
        dataframe['exit_long'] = 0
        
        conditions = []

        # Technical indicator exits from future33
        conditions.append(
            (
                (dataframe['close'] >= dataframe['bb_upperband'] * params['sell_bb_upperband_mult']) |
                (qtpylib.crossed_below(dataframe['ema_short'], dataframe['ema_long'])) |
                (dataframe['stoch_rsi_k'] > 80) |
                (dataframe['stoch_rsi_k'] < dataframe['stoch_rsi_d'])
            )
        )

        # RSI exit from future33
        conditions.append(dataframe['rsi'] > params['sell_rsi'])

        # Volume-based exit with enhanced multiplier from new14
        conditions.append(
            (dataframe['volume'] > dataframe['volume_ma'] * params['exit_volume_multiplier']) &
            (dataframe['close'] < dataframe['close'].shift(1))
        )

        # Profit protection from future33
        conditions.append(
            (dataframe['close'] < dataframe['close'].shift(1) * params['sell_close_mult']) |
            (dataframe['close'] > dataframe['bb_upperband'] * params['sell_bb_upperband_high_mult'])
        )
        
        # Local peak detection from new14
        conditions.append(dataframe['local_peak'])

        if conditions:
            dataframe.loc[
                reduce(lambda x, y: x & y, conditions),
                'exit_long'] = 1

        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                          time_in_force: str, current_time: datetime, entry_tag: Optional[str]=None, 
                          side: str="long", **kwargs) -> bool:
        """
        Enhanced confirmation logic combining best practices
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) == 0:
            return False
            
        last_candle = dataframe.iloc[-1].squeeze()

        # Volume confirmation from future33
        if last_candle['volume'] < last_candle['volume_ma'] * 0.8:
            return False

        # Volatility check from future33
        if last_candle['atr'] > last_candle['close'] * 0.015:
            return False
            
        # Sequential drops check from new14 - don't enter when price is falling rapidly
        if 'sequential_drops' in last_candle and last_candle['sequential_drops']:
            return False

        return True
    
    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """
        Enhanced exit logic with profit protection from new14
        """
        if not trade.is_short:  # For longs
            coin = pair.split('/')[0]
            params = self.get_coin_params(coin)
            
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) == 0:
                return None
                
            last_candle = dataframe.iloc[-1]
            
            # Take profit based on threshold from new14
            if current_profit >= params['profit_threshold']:
                # Exit if we have an exit signal
                if 'exit_long' in last_candle and last_candle['exit_long'] == 1:
                    return 'roi_with_signal'
                
                # Exit on sequential price drops
                if 'sequential_drops' in last_candle and last_candle['sequential_drops']:
                    return 'roi_with_drops'
            
            # Exit on high RSI with profit
            if current_profit > 0.01 and last_candle['rsi'] > params['sell_rsi']:
                return 'exit_high_rsi_profit'
            
            # Exit on MACD crossing down with profit
            if current_profit > 0.01 and 'macd' in last_candle and 'macdsignal' in last_candle:
                if (last_candle['macd'] < last_candle['macdsignal'] and 
                    dataframe['macd'].iloc[-2] > dataframe['macdsignal'].iloc[-2]):
                    return 'exit_macd_cross_profit'
        
        return None
    
    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                          rate: float, time_in_force: str, exit_reason: str,
                          current_time: datetime, **kwargs) -> bool:
        """Track losses for cooldown periods (from new14)"""
        if exit_reason == 'stop_loss':
            self.last_loss_time[pair] = current_time
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
