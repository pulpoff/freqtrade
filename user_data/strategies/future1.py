from collections import defaultdict
from datetime import datetime, timedelta
from functools import reduce
from typing import Optional, List, Tuple, Dict
from skopt.space import Dimension, Real

import pandas as pd
import talib.abstract as ta
from pandas import DataFrame
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy
from freqtrade.strategy.parameters import IntParameter, DecimalParameter, CategoricalParameter

class future1(IStrategy):
    # ROI table adjusted for futures
    minimal_roi = {
        "0": 0.05,    # Take profits faster in futures
        "5": 0.025,
        "10": 0.01,
        "20": 0
    }

    # Static parameters with strict risk limits for futures
    stoploss = -0.05  # Tighter stoploss for futures (5%)
    trailing_stop = True
    trailing_stop_positive = 0.02  # Reduced to 2% for futures
    trailing_stop_positive_offset = 0.03  # Reduced to 3% for futures
    trailing_only_offset_is_reached = True

    # Leverage parameter - renamed to avoid conflict
    leverage_param = IntParameter(2, 10, default=3, space="buy", optimize=True)
    
    # Position sizing (% of capital to risk per trade)
    max_risk_per_trade = DecimalParameter(0.5, 5.0, default=1.0, space="buy", optimize=True)

    # Hyperopt parameters with updated default values
    # BB parameters
    bb_multiplier = DecimalParameter(0.985, 1.005, default=0.996, space="buy", optimize=True)
    buy_bb_width_threshold = DecimalParameter(0.25, 0.35, default=0.297, space="buy", optimize=True)
    
    # RSI parameters
    buy_rsi_threshold = IntParameter(35, 50, default=42, space="buy", optimize=True)
    exit_rsi_threshold = IntParameter(70, 85, default=78, space="sell", optimize=True)
    
    # Volume parameters 
    volume_ma_multiplier_min = DecimalParameter(2.0, 3.5, default=2.78, space="buy", optimize=True)
    volume_ma_multiplier_max = DecimalParameter(8.0, 12.0, default=9.477, space="buy", optimize=True)
    exit_volume_multiplier = DecimalParameter(2.5, 4.0, default=3.178, space="sell", optimize=True)
    
    # MACD parameters
    macd_hist_threshold = DecimalParameter(-0.04, -0.01, default=-0.029, space="buy", optimize=True)
    
    # Exit parameters - adjusted for futures
    profit_threshold = DecimalParameter(0.01, 0.03, default=0.015, space="sell", optimize=True)
    emergency_exit_threshold = DecimalParameter(-0.03, -0.01, default=-0.02, space="sell", optimize=True)
    funding_guard = DecimalParameter(0.0001, 0.001, default=0.0005, space="sell", optimize=True)
    
    # Sequential drops parameters
    sequential_drop_count = IntParameter(1, 3, default=1, space="buy", optimize=True)
    
    # Boolean parameters to enable/disable features
    use_48h_avg = CategoricalParameter([True, False], default=False, space="buy", optimize=True)
    use_macd_cross = CategoricalParameter([True, False], default=False, space="buy", optimize=True)
    
    # Other strategy parameters
    timeframe = '1m'
    startup_candle_count = 300
    process_only_new_candles = True
    use_exit_signal = True
    can_short = False  # Set to True if you want to allow shorting

    # Cooldown settings
    cooldown_period = timedelta(hours=3)  # Shorter cooldown for futures

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._last_stoploss_time = {}
        self.funding_rates = {}
        self.max_drawdown = {}
        self.entry_prices = {}
        self.trade_sizes = {}

    def get_strategy_name(self) -> str:
        return self.__class__.__name__

    def stoploss_reached(self, current_rate: float, current_profit: float, **kwargs) -> bool:
        """
        Custom stoploss logic, returning True if stoploss should be triggered
        """
        # Force stoploss at max 5% loss for futures
        if current_profit <= -0.05:
            return True
        return False

    def leverage(self, pair: str, current_time: datetime, **kwargs) -> float:
        """Return the leverage to use for this pair"""
        return float(self.leverage_param.value)

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                           proposed_stake: float, min_stake: float, max_stake: float,
                           leverage: float, entry_tag: Optional[str], side: str,
                           **kwargs) -> float:
        """
        Adjust position size based on risk per trade
        """
        # Calculate position size based on risk
        risk_amount = self.wallets.get_total_stake_amount() * (self.max_risk_per_trade.value / 100)
        risk_per_unit = abs(current_rate * (1 - self.stoploss))
        
        # Calculate number of units we can buy with our risk amount
        # Adjusted for leverage
        position_size = (risk_amount / risk_per_unit) * leverage
        
        # Convert to stake amount
        stake_amount = position_size * current_rate / leverage
        
        # Make sure we stay within allowed limits
        stake_amount = min(max_stake, max(min_stake, stake_amount))
        
        # Store trade size for this pair
        self.trade_sizes[pair] = stake_amount
        
        return stake_amount

    def hyperopt_space(self) -> List[Dimension]:
        return [
            Real(-0.05, -0.02, name='stoploss'),  # Limited to 5% max stoploss for futures
            Real(0.01, 0.03, name='trailing_stop_positive'),  # Limited to 3% max trailing stop
            Real(0.01, 0.04, name='trailing_stop_positive_offset'),  # Adjusted accordingly
        ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # MACD
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_hist'] = macd['macdhist']
        
        dataframe['hist_trend'] = dataframe['macd_hist'] > dataframe['macd_hist'].shift(1)
        dataframe['hist_peak'] = (
            (dataframe['macd_hist'] > dataframe['macd_hist'].shift(1)) & 
            (dataframe['macd_hist'] > dataframe['macd_hist'].shift(2))
        )
        dataframe['macd_cross'] = qtpylib.crossed_above(dataframe['macd'], dataframe['macd_signal'])

        # Bollinger Bands - 100 periods for 1m timeframe
        bollinger = qtpylib.bollinger_bands(dataframe['close'], window=100, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        dataframe['bb_width'] = (dataframe['bb_upperband'] - dataframe['bb_lowerband']) / dataframe['bb_middleband']
        
        # RSI - 70 periods for 1m timeframe
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=70)
        
        # Volume MA - 100 periods for 1m timeframe
        dataframe['volume_ma'] = dataframe['volume'].rolling(window=100).mean()
        
        # 48-hour average price (2880 periods for 1m timeframe)
        dataframe['avg_price_48h'] = dataframe['close'].rolling(window=2880).mean()
        dataframe['price_lower_20pct'] = dataframe['avg_price_48h'] * 0.9
        dataframe['price_upper_20pct'] = dataframe['avg_price_48h'] * 1.1
        
        # Volatility indicators
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_percent'] = dataframe['atr'] / dataframe['close'] * 100
        
        dataframe['upper_wick'] = (dataframe['high'] - dataframe[['close', 'open']].max(axis=1)) / dataframe['high']
        dataframe['price_dropped'] = dataframe['close'] < dataframe['close'].shift(1)
        
        # Make sequential drops configurable
        for i in range(1, 4):
            dataframe[f'sequential_drops_{i}'] = True
            for j in range(i):
                dataframe[f'sequential_drops_{i}'] &= dataframe['price_dropped'].shift(j)
        
        # Futures-specific indicators
        # Add a proxy for potential funding rates (this would need to be replaced with actual exchange data in live trading)
        dataframe['funding_rate_proxy'] = 0.0001 * (dataframe['rsi'] - 50) / 50
        
        # Add a momentum-based entry/exit filter
        dataframe['momentum'] = dataframe['close'].pct_change(10) * 100
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata['pair']
        
        conditions = []
        
        # Base conditions
        bb_condition = (
            (dataframe['close'] <= dataframe['bb_lowerband'] * self.bb_multiplier.value) &
            (dataframe['bb_width'] < self.buy_bb_width_threshold.value)
        )
        conditions.append(bb_condition)
        
        # RSI condition
        conditions.append(dataframe['rsi'] < self.buy_rsi_threshold.value)
        
        # Volume condition with min and max thresholds
        volume_condition = (
            (dataframe['volume'] > dataframe['volume_ma'] * self.volume_ma_multiplier_min.value) &
            (dataframe['volume'] < dataframe['volume_ma'] * self.volume_ma_multiplier_max.value)
        )
        conditions.append(volume_condition)
        
        # MACD conditions - configurable
        macd_conditions = []
        macd_conditions.append(dataframe['macd_hist'] > self.macd_hist_threshold.value)
        
        if self.use_macd_cross.value:
            macd_conditions.append(dataframe['macd_cross'])
            
        conditions.append(reduce(lambda x, y: x | y, macd_conditions))
        
        # 48h average condition - optional
        if self.use_48h_avg.value:
            conditions.append(dataframe['close'] < dataframe['avg_price_48h'])
            
        # Futures-specific conditions
        # Check that volatility isn't too high for our leverage
        conditions.append(dataframe['atr_percent'] < 1.0 / self.leverage_param.value * 100)
        
        # Check that funding rate isn't too negative for longs (replace with actual funding data in live trading)
        conditions.append(dataframe['funding_rate_proxy'] > -self.funding_guard.value)
        
        # Add a momentum filter
        conditions.append(dataframe['momentum'] < 0)  # Price is pulling back
        
        # Check cooldown period after stoploss
        if pair in self._last_stoploss_time:
            cooldown_end = self._last_stoploss_time[pair] + self.cooldown_period
            dataframe['cooldown_mask'] = dataframe['date'].apply(lambda x: x < cooldown_end)
            conditions.append(~dataframe['cooldown_mask'])
        
        dataframe.loc[reduce(lambda x, y: x & y, conditions), 'enter_long'] = 1
        
        # Store entry price
        if 'enter_long' in dataframe.columns and dataframe['enter_long'].any():
            self.entry_prices[pair] = dataframe.loc[dataframe['enter_long'] == 1, 'close'].iloc[-1]
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'exit_long'] = 0
        
        bb = qtpylib.bollinger_bands(dataframe['close'], window=100, stds=2)
        dataframe['bb_upper'] = bb['upper']
        
        dataframe['local_peak'] = (
            (dataframe['close'] > dataframe['close'].shift(2)) &
            (dataframe['close'] > dataframe['close'].shift(1)) &
            (dataframe['close'] > dataframe['close'].shift(-1)) &
            (dataframe['close'] > dataframe['close'].shift(-2))
        )
        
        exit_conditions = [
            dataframe['local_peak'],
            dataframe['rsi'] > self.exit_rsi_threshold.value,
            dataframe['macd_hist'] > dataframe['macd_hist'].shift(2),
            dataframe['volume'] > dataframe['volume_ma'] * self.exit_volume_multiplier.value,
            # Parameterized upper BB threshold
            dataframe['close'] >= dataframe['bb_upperband'] * 0.942
        ]
        
        # Futures-specific exit conditions
        # Exit if funding rate becomes too unfavorable (proxy - replace with actual data in live trading)
        funding_exit = dataframe['funding_rate_proxy'] < -self.funding_guard.value * 2
        exit_conditions.append(funding_exit)
        
        dataframe.loc[reduce(lambda x, y: x | y, exit_conditions), 'exit_long'] = 1
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                   current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]

        # Emergency exit with adjusted threshold for futures
        if current_profit <= self.emergency_exit_threshold.value:
            return 'emergency_exit'

        # Track max drawdown for this trade
        if pair not in self.max_drawdown:
            self.max_drawdown[pair] = 0
        
        if current_profit < self.max_drawdown[pair]:
            self.max_drawdown[pair] = current_profit
            
        # If we've recovered significantly from max drawdown, consider taking profit
        if self.max_drawdown[pair] < -0.02 and current_profit > 0.01:
            return 'drawdown_recovery'

        # More aggressive exit for leveraged positions
        if current_profit >= self.profit_threshold.value * (1 + (self.leverage_param.value - 2) * 0.1):
            if last_candle['exit_long']:
                return 'leveraged_roi_with_signal'
                
            if last_candle[f'sequential_drops_{self.sequential_drop_count.value}']:
                return 'leveraged_roi_with_drops'
            
        # Funding rate check (in live trading, replace this with actual exchange data)
        # Example: if funding_rate > 0.0005 and we've been in the trade > 6 hours, consider exit
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        if trade_duration > 6 and last_candle['funding_rate_proxy'] > self.funding_guard.value:
            return 'funding_rate_protection'
                
        return None

    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                          rate: float, time_in_force: str, exit_reason: str,
                          current_time: datetime, **kwargs) -> bool:
        if exit_reason == 'stop_loss':
            self._last_stoploss_time[pair] = current_time
            
            # Reset max drawdown tracking
            if pair in self.max_drawdown:
                del self.max_drawdown[pair]
        return True
