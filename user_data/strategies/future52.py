from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.strategy import DecimalParameter, IntParameter, RealParameter
from typing import Dict, List, Optional, Tuple, Any
import talib.abstract as ta
import pandas as pd
from pandas import DataFrame
import numpy as np
from functools import reduce
from datetime import datetime, timedelta
from freqtrade.persistence import Trade

class future52(IStrategy):
    timeframe = '5m'
    can_short = True
    can_long = False
    use_custom_stoploss = True
    process_only_new_candles = True
    use_exit_signal = True
    ignore_roi_if_entry_signal = False

    minimal_roi = {
      "0": 0.02,
      "3": 0.015,
      "15": 0.007,
      "34": 0,
      "60": -0.01
      }

    stoploss = -0.05

    # Base parameters (used as defaults)
    base_buy_rsi = IntParameter(30, 50, default=47, space='buy')
    base_sell_rsi_upper = IntParameter(60, 85, default=79, space='sell')
    base_sell_rsi_lower = IntParameter(20, 40, default=21, space='sell')
    base_ema_short = IntParameter(5, 15, default=8, space='buy')
    base_ema_long = IntParameter(15, 30, default=21, space='buy')
    base_macd_fast = IntParameter(8, 16, default=12, space='buy')
    base_macd_slow = IntParameter(18, 32, default=26, space='buy')
    base_macd_signal = IntParameter(6, 12, default=9, space='buy')
    base_price_extension_pct = DecimalParameter(0.4, 1.0, default=0.6, decimals=1, space='buy')
    base_leverage_param = IntParameter(1, 5, default=2, space='buy')

    # Coin-specific parameters storage
    _coin_parameters = {}
    _coin_list = []
    _last_candle_seen_time = {}

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._coin_parameters = {}
        self._coin_list = []
        self._last_candle_seen_time = {}
        
        # Initialize coin list from pair whitelist
        if 'exchange' in config and 'pair_whitelist' in config['exchange']:
            for pair in config['exchange']['pair_whitelist']:
                coin = self.get_coin_from_pair(pair)
                if coin not in self._coin_list:
                    self._coin_list.append(coin)
        
        # Create dynamic parameters for each coin
        self.initialize_coin_parameters()

    def get_coin_from_pair(self, pair: str) -> str:
        return pair.split('/')[0]

    def initialize_coin_parameters(self):
        """Dynamically create parameters for each coin"""
        for coin in self._coin_list:
            self._coin_parameters[coin] = {}
            
            # Create coin-specific parameters
            params = {
                'buy_rsi': IntParameter(30, 50, default=47, space='buy'),
                'sell_rsi_upper': IntParameter(60, 85, default=79, space='sell'),
                'sell_rsi_lower': IntParameter(20, 40, default=21, space='sell'),
                'ema_short': IntParameter(5, 15, default=8, space='buy'),
                'ema_long': IntParameter(15, 30, default=21, space='buy'),
                'macd_fast': IntParameter(8, 16, default=12, space='buy'),
                'macd_slow': IntParameter(18, 32, default=26, space='buy'),
                'macd_signal': IntParameter(6, 12, default=9, space='buy'),
                'price_extension_pct': DecimalParameter(0.4, 1.0, default=0.6, decimals=1, space='buy'),
                'leverage_param': IntParameter(1, 5, default=2, space='buy')
            }
            
            # Register parameters with coin prefix
            for param_name, param in params.items():
                full_name = f"{coin}_{param_name}"
                setattr(self, full_name, param)
                self._coin_parameters[coin][param_name] = getattr(self, full_name)

    def get_param(self, coin: str, param_name: str):
        """Get parameter value with fallback to base"""
        if coin in self._coin_parameters and param_name in self._coin_parameters[coin]:
            return self._coin_parameters[coin][param_name].value
        else:
            return getattr(self, f"base_{param_name}").value

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        coin = self.get_coin_from_pair(metadata['pair'])
        
        # Get parameters for this coin
        buy_rsi = self.get_param(coin, 'buy_rsi')
        sell_rsi_upper = self.get_param(coin, 'sell_rsi_upper')
        ema_short = self.get_param(coin, 'ema_short')
        ema_long = self.get_param(coin, 'ema_long')
        macd_fast = self.get_param(coin, 'macd_fast')
        macd_slow = self.get_param(coin, 'macd_slow')
        macd_signal = self.get_param(coin, 'macd_signal')
        price_extension_pct = self.get_param(coin, 'price_extension_pct')

        # Indicator calculations using coin-specific parameters
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=ema_short)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=ema_long)
        
        macd = ta.MACD(dataframe, fastperiod=macd_fast, slowperiod=macd_slow, signalperiod=macd_signal)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        dataframe['price_extension'] = (dataframe['close'] - dataframe['ema_short']) / dataframe['ema_short']
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        coin = self.get_coin_from_pair(metadata['pair'])
        buy_rsi = self.get_param(coin, 'buy_rsi')
        price_extension_pct = self.get_param(coin, 'price_extension_pct')

        dataframe['enter_short'] = 0
        conditions = [
            (dataframe['rsi'] > buy_rsi) &
            (dataframe['price_extension'] >= price_extension_pct) &
            (dataframe['close'] > dataframe['ema_short'])
        ]
        
        if conditions:
            dataframe.loc[reduce(lambda x, y: x & y, conditions), 'enter_short'] = 1
            
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        coin = self.get_coin_from_pair(metadata['pair'])
        sell_rsi_lower = self.get_param(coin, 'sell_rsi_lower')

        dataframe['exit_short'] = 0
        dataframe.loc[
            (dataframe['rsi'] < sell_rsi_lower) |
            (dataframe['macd'] > dataframe['macdsignal']),
            'exit_short'
        ] = 1
        return dataframe

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
               proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], 
               side: str, **kwargs) -> float:
        coin = self.get_coin_from_pair(pair)
        return float(self.get_param(coin, 'leverage_param'))

    def get_strategy_parameters(self) -> Dict[str, Any]:
        """Export all parameters including coin-specific ones"""
        params = {
            'base_buy_rsi': self.base_buy_rsi.value,
            'base_sell_rsi_upper': self.base_sell_rsi_upper.value,
            'base_sell_rsi_lower': self.base_sell_rsi_lower.value,
            'base_ema_short': self.base_ema_short.value,
            'base_ema_long': self.base_ema_long.value,
            'base_macd_fast': self.base_macd_fast.value,
            'base_macd_slow': self.base_macd_slow.value,
            'base_macd_signal': self.base_macd_signal.value,
            'base_price_extension_pct': self.base_price_extension_pct.value,
            'base_leverage_param': self.base_leverage_param.value
        }
        
        # Add coin-specific parameters
        for coin in self._coin_list:
            for param_name in self._coin_parameters.get(coin, {}):
                param_value = self._coin_parameters[coin][param_name].value
                params[f"{coin}_{param_name}"] = param_value
                
        return params

    def hyperopt_space(self):
        """Auto-generated by Freqtrade, no need to modify"""
        return super().hyperopt_space()
