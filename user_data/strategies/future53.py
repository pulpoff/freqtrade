from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.strategy import (DecimalParameter, IntParameter, RealParameter, CategoricalParameter)
from typing import Dict, List, Optional, Tuple, Any
import talib.abstract as ta
import pandas as pd
from pandas import DataFrame
import numpy as np
from functools import reduce
from datetime import datetime, timedelta
from freqtrade.persistence import Trade
from qtpylib.indicators import bollinger_bands, typical_price
from skopt.space import Integer, Real, Categorical

class future53(IStrategy):
    timeframe = '5m'
    can_short = True
    can_long = False
    use_custom_stoploss = True
    process_only_new_candles = True
    use_exit_signal = True
    ignore_roi_if_entry_signal = False

    minimal_roi = {
        "0": 0.02,
        "15": 0.015,
        "34": 0.007,
        "60": 0
    }

    stoploss = -0.05

    buy_rsi = IntParameter(30, 50, default=47, space='buy')
    sell_rsi_upper = IntParameter(60, 85, default=79, space='sell')
    sell_rsi_lower = IntParameter(20, 40, default=21, space='sell')
    ema_short = IntParameter(5, 15, default=8, space='buy')
    ema_long = IntParameter(15, 30, default=21, space='buy')
    macd_fast = IntParameter(8, 16, default=12, space='buy')
    macd_slow = IntParameter(18, 32, default=26, space='buy')
    macd_signal = IntParameter(6, 12, default=9, space='buy')
    price_extension_pct = DecimalParameter(0.4, 1.0, default=0.6, decimals=1, space='buy')
    exit_rsi_threshold = IntParameter(15, 30, default=20, space='sell')
    trailing_stop_p = DecimalParameter(0.10, 0.20, default=0.16, space='sell')
    trailing_stop_offset = DecimalParameter(0.15, 0.25, default=0.213, space='sell')
    quick_profit_pct = DecimalParameter(0.01, 0.03, default=0.02, space='sell')
    medium_profit_pct = DecimalParameter(0.01, 0.02, default=0.015, space='sell')
    long_profit_pct = DecimalParameter(0.005, 0.015, default=0.01, space='sell')
    
    atr_period = IntParameter(10, 25, default=14, space='both')
    atr_stop_multiplier = DecimalParameter(1.5, 4.0, default=2.5, space='sell')
    volatility_lookback = IntParameter(20, 100, default=50, space='both')
    market_regime_threshold = IntParameter(90, 160, default=120, space='both')
    max_volatility_pct = DecimalParameter(0.5, 3.0, default=1.5, space='buy')
    adaptive_vol_stop_scaling = DecimalParameter(0.5, 2.0, default=1.0, space='sell')
    leverage_param = IntParameter(1, 5, default=2, space='buy')
    
    exit_cooldown_period = IntParameter(5, 20, default=12, space='sell')

    informative_timeframes = ['1h', '4h', '1d']
    
    _coin_parameters = {}
    _market_regimes = {}
    _volatility_metrics = {}
    _max_profits = {}
    _last_candle_seen_time = {}
    _exit_cooldown = {}

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._coin_parameters = {}
        self._market_regimes = {}
        self._volatility_metrics = {}
        self._max_profits = {}
        self._last_candle_seen_time = {}
        self._exit_cooldown = {}

    def initialize_coin_parameters(self):
        if not hasattr(self, 'dp') or self.dp is None:
            return
            
        try:
            pairs = self.dp.current_whitelist()
            for pair in pairs:
                coin = self.get_coin_from_pair(pair)
                self._coin_parameters[coin] = {
                    'leverage': self.leverage_param.value,
                    'rsi_upper': self.sell_rsi_upper.value,
                    'rsi_lower': self.sell_rsi_lower.value,
                    'atr_multiplier': self.atr_stop_multiplier.value,
                    'quick_profit': self.quick_profit_pct.value,
                    'medium_profit': self.medium_profit_pct.value,
                    'long_profit': self.long_profit_pct.value,
                    'price_extension': self.price_extension_pct.value
                }
        except Exception as e:
            pass
    
    def get_coin_from_pair(self, pair: str) -> str:
        if '/' in pair:
            return pair.split('/')[0]
        return "UNKNOWN"
        
    def calculate_choppiness(self, dataframe: DataFrame, period: int = 14) -> pd.Series:
        try:
            high_max = dataframe['high'].rolling(period).max()
            low_min = dataframe['low'].rolling(period).min()
            
            atr = ta.ATR(dataframe, timeperiod=period)
            atr_sum = atr * period
                
            denominator = high_max - low_min
            denominator = np.where(denominator == 0, 0.000001, denominator)
            
            result = 100 * np.log10(atr_sum / denominator) / np.log10(period)
            return pd.Series(result).fillna(50)
        except Exception:
            return pd.Series([50] * len(dataframe))

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        informative_pairs = []
        
        for pair in pairs:
            for tf in self.informative_timeframes:
                informative_pairs.append((pair, tf))
                
        return informative_pairs

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if len(self._coin_parameters) == 0:
            self.initialize_coin_parameters()
            
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['ema_short'] = ta.EMA(dataframe, timeperiod=self.ema_short.value)
        dataframe['ema_long'] = ta.EMA(dataframe, timeperiod=self.ema_long.value)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        macd = ta.MACD(
            dataframe,
            fastperiod=self.macd_fast.value,
            slowperiod=self.macd_slow.value,
            signalperiod=self.macd_signal.value
        )
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        dataframe['typical_price'] = typical_price(dataframe)
        bb = bollinger_bands(dataframe['typical_price'], window=20, stds=2)
        dataframe['bb_upper'] = bb['upper']
        dataframe['bb_middle'] = bb['mid']
        dataframe['bb_lower'] = bb['lower']
        dataframe['bb_width'] = (bb['upper'] - bb['lower']) / bb['mid']
        
        dataframe['volume_ma'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['price_extension'] = (dataframe['close'] - dataframe['ema_short']) / dataframe['ema_short']
        
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=self.atr_period.value)
        dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']
        
        try:
            dataframe['historical_volatility'] = dataframe['close'].pct_change().rolling(self.volatility_lookback.value).std() * np.sqrt(365 * 24 * 12)
        except Exception:
            dataframe['historical_volatility'] = 0.1
        
        try:
            dataframe['choppiness'] = self.calculate_choppiness(dataframe, 14)
            dataframe['volatility_regime'] = dataframe['close'].pct_change().rolling(10).std() / dataframe['close'].pct_change().rolling(50).std()
            dataframe['volatility_regime'] = dataframe['volatility_regime'].fillna(1.0)
            dataframe['is_trending'] = (dataframe['choppiness'] < 61.8) & (abs(dataframe['close'] - dataframe['ema_long']) / dataframe['close'] > 0.01)
        except Exception:
            dataframe['choppiness'] = 50
            dataframe['volatility_regime'] = 1.0
            dataframe['is_trending'] = False
        
        if self.dp and hasattr(self.dp, 'get_pair_dataframe'):
            if '1h' in self.informative_timeframes:
                try:
                    informative_1h = self.dp.get_pair_dataframe(metadata['pair'], '1h')
                    informative_1h['ema_200'] = ta.EMA(informative_1h, timeperiod=200)
                    informative_1h['market_phase'] = (informative_1h['close'] > informative_1h['ema_200']).astype(float)
                    informative_1h['atr'] = ta.ATR(informative_1h, timeperiod=self.atr_period.value)
                    informative_1h['historical_volatility'] = informative_1h['close'].pct_change().rolling(self.volatility_lookback.value // 12).std() * np.sqrt(365 * 24)
                    
                    dataframe = merge_informative_pair(
                        dataframe, 
                        informative_1h[['market_phase', 'atr', 'historical_volatility']], 
                        self.timeframe, 
                        '1h', 
                        ffill=True
                    )
                except Exception:
                    pass
                    
            if '4h' in self.informative_timeframes:
                try:
                    informative_4h = self.dp.get_pair_dataframe(metadata['pair'], '4h')
                    informative_4h['atr'] = ta.ATR(informative_4h, timeperiod=self.atr_period.value)
                    informative_4h['rma_close'] = ta.SMA(informative_4h['close'], timeperiod=self.market_regime_threshold.value)
                    
                    informative_4h['choppiness'] = self.calculate_choppiness(informative_4h, 14)
                    
                    informative_4h['historical_volatility'] = informative_4h['close'].pct_change().rolling(self.volatility_lookback.value // 4).std() * np.sqrt(365 * 6)
                    
                    informative_4h['trend_strength'] = abs(informative_4h['close'] - informative_4h['rma_close']) / (informative_4h['atr'] * 5)
                    informative_4h['is_trending'] = (informative_4h['trend_strength'] > 0.5) & (informative_4h['choppiness'] < 61.8).astype(float)
                    informative_4h['is_chopping'] = (informative_4h['choppiness'] > 61.8).astype(float)
                    
                    informative_4h['volatility_regime'] = informative_4h['historical_volatility'].rolling(10).mean() / informative_4h['historical_volatility'].rolling(30).mean()
                    informative_4h['volatility_regime'] = informative_4h['volatility_regime'].fillna(1.0)
                    
                    dataframe = merge_informative_pair(
                        dataframe, 
                        informative_4h[['atr', 'choppiness', 'historical_volatility', 'is_trending', 'is_chopping', 'volatility_regime']], 
                        self.timeframe, 
                        '4h', 
                        ffill=True
                    )
                except Exception:
                    pass
                    
            if '1d' in self.informative_timeframes:
                try:
                    informative_1d = self.dp.get_pair_dataframe(metadata['pair'], '1d')
                    informative_1d['atr'] = ta.ATR(informative_1d, timeperiod=self.atr_period.value)
                    informative_1d['historical_volatility'] = informative_1d['close'].pct_change().rolling(self.volatility_lookback.value // 12).std() * np.sqrt(365)
                    informative_1d['yearly_volatility'] = informative_1d['historical_volatility'] * 100
                    
                    dataframe = merge_informative_pair(
                        dataframe, 
                        informative_1d[['atr', 'historical_volatility', 'yearly_volatility']], 
                        self.timeframe, 
                        '1d', 
                        ffill=True
                    )
                except Exception:
                    pass
                    
        dataframe['local_peak'] = (
            (dataframe['high'] > dataframe['high'].shift(1)) &
            (dataframe['high'] > dataframe['high'].shift(2)) &
            (dataframe['high'] > dataframe['high'].shift(3))
        )
        
        dataframe['local_valley'] = (
            (dataframe['low'] < dataframe['low'].shift(1)) &
            (dataframe['low'] < dataframe['low'].shift(2)) &
            (dataframe['low'] < dataframe['low'].shift(-1)) &
            (dataframe['low'] < dataframe['low'].shift(-2))
        )
        
        dataframe['significant_valley'] = (
            (dataframe['low'] < dataframe['low'].shift(1)) &
            (dataframe['low'] < dataframe['low'].shift(2)) &
            (dataframe['low'] < dataframe['low'].shift(3)) &
            (dataframe['low'] < dataframe['low'].shift(-1)) &
            (dataframe['low'] < dataframe['low'].shift(-2)) &
            (dataframe['low'] < dataframe['low'].shift(-3)) &
            (dataframe['volume'] > dataframe['volume_ma'] * 1.2)
        )

        dataframe['macdhist_prev'] = dataframe['macdhist'].shift(1)
        dataframe['macdhist_prev2'] = dataframe['macdhist'].shift(2)
        dataframe['macd_cross_above'] = (dataframe['macd'].shift(1) < dataframe['macdsignal'].shift(1)) & (dataframe['macd'] > dataframe['macdsignal'])
        
        dataframe['price_increased'] = dataframe['close'] > dataframe['close'].shift(1)
        dataframe['sequential_rises_3'] = (
            dataframe['price_increased'] & 
            dataframe['price_increased'].shift(1) & 
            dataframe['price_increased'].shift(2)
        )
        
        pair_key = f"{metadata['pair']}_market_regime"
        self._market_regimes[pair_key] = "unknown"
        
        if 'is_trending_4h' in dataframe.columns and 'is_chopping_4h' in dataframe.columns and len(dataframe) > 0:
            try:
                is_trending = dataframe['is_trending_4h'].iloc[-1] > 0.5
                is_chopping = dataframe['is_chopping_4h'].iloc[-1] > 0.5
                vol_regime = dataframe['volatility_regime_4h'].iloc[-1] if 'volatility_regime_4h' in dataframe.columns else 1.0
                
                if is_trending and vol_regime > 1.1:
                    self._market_regimes[pair_key] = "trending_volatile"
                elif is_trending:
                    self._market_regimes[pair_key] = "trending_normal"
                elif is_chopping and vol_regime < 0.9:
                    self._market_regimes[pair_key] = "choppy_lowvol"
                elif is_chopping:
                    self._market_regimes[pair_key] = "choppy_normal"
                else:
                    self._market_regimes[pair_key] = "neutral"
                    
                dataframe['market_regime'] = self._market_regimes[pair_key]
            except Exception:
                dataframe['market_regime'] = "unknown"
        
        pair_key = f"{metadata['pair']}_volatility"
        
        if 'historical_volatility_1d' in dataframe.columns and len(dataframe) > 0:
            try:
                base_volatility = dataframe['historical_volatility_1d'].iloc[-1]
                self._volatility_metrics[pair_key] = base_volatility
            except Exception:
                self._volatility_metrics[pair_key] = 0.5
        else:
            self._volatility_metrics[pair_key] = 0.5

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0
        
        conditions = []
        
        coin = self.get_coin_from_pair(metadata['pair'])
        rsi_upper = self._coin_parameters.get(coin, {}).get('rsi_upper', self.sell_rsi_upper.value)
        price_ext = self._coin_parameters.get(coin, {}).get('price_extension', self.price_extension_pct.value) / 100
        
        if price_ext > 0.1 or price_ext < 0.001:
            price_ext = 0.006
        
        base_cond = (
            (dataframe['rsi'] > rsi_upper * 0.95) &
            (dataframe['price_extension'] >= price_ext * 0.9)
        )
        
        conditions.append(base_cond & dataframe['local_peak'] & (dataframe['close'] > dataframe['ema_short']))
        
        conditions.append(base_cond &
            (dataframe['close'].shift(2) < dataframe['close'].shift(1)) &
            (dataframe['close'] < dataframe['close'].shift(1)) &
            (dataframe['high'].shift(1) >= dataframe['high'].rolling(3).max().shift(1) * 0.998))
        
        conditions.append(base_cond &
            (dataframe['macdhist_prev'] >= dataframe['macdhist_prev2'] * 0.98) &
            (dataframe['macdhist'] < dataframe['macdhist_prev']) &
            (dataframe['macdhist_prev'] > -0.001) &
            (dataframe['close'] > dataframe['ema_short'] * 0.995))

        if conditions:
            entry_mask = reduce(lambda x, y: x | y, conditions)
            
            if 'yearly_volatility_1d' in dataframe.columns:
                try:
                    max_vol = self.max_volatility_pct.value * 100
                    volatility_filter = dataframe['yearly_volatility_1d'] < max_vol * 1.5
                    entry_mask = entry_mask & volatility_filter
                except Exception:
                    pass
            
            if 'is_chopping_4h' in dataframe.columns and 'historical_volatility_4h' in dataframe.columns:
                try:
                    avoid_chop = ~(dataframe['is_chopping_4h'] > 0.8 & dataframe['historical_volatility_4h'] < 0.2)
                    entry_mask = entry_mask & avoid_chop
                except Exception:
                    pass
                
            if 'volatility_regime_4h' in dataframe.columns:
                try:
                    avoid_extreme_vol = dataframe['volatility_regime_4h'] < 2.0
                    entry_mask = entry_mask & avoid_extreme_vol
                except Exception:
                    pass
            
            dataframe.loc[entry_mask, 'enter_short'] = 1

        if 'enter_short' not in dataframe.columns or dataframe['enter_short'].sum() == 0:
            fallback_cond = (
                (dataframe['rsi'] > rsi_upper * 0.9) &
                (dataframe['close'] > dataframe['ema_short'] * 1.005)
            )
            dataframe.loc[fallback_cond, 'enter_short'] = 1
            
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0
        
        coin = self.get_coin_from_pair(metadata['pair'])
        rsi_lower = self._coin_parameters.get(coin, {}).get('rsi_lower', self.sell_rsi_lower.value)
        
        # Create a series of candle indices for tracking
        dataframe['candle_index'] = np.arange(len(dataframe))
        
        # Create sequential groups to avoid excessive signals
        exit_cooldown = self.exit_cooldown_period.value
        dataframe['exit_group'] = dataframe['candle_index'] // exit_cooldown
        
        # Define strong exit conditions - highly selective
        strong_exit = (
            dataframe['significant_valley'] &
            (dataframe['rsi'] < rsi_lower * 1.1) &
            (dataframe['close'] < dataframe['bb_lower'] * 1.02)
        )
        
        # Only select the first signal in each group
        strong_exit_idx = strong_exit.groupby(dataframe['exit_group']).idxmax()
        strong_exit_mask = pd.Series(False, index=dataframe.index)
        strong_exit_mask.loc[strong_exit_idx] = True
        strong_exit = strong_exit & strong_exit_mask
        
        # Apply exit signals - using the filtered signals only
        dataframe.loc[strong_exit, 'exit_short'] = 1
        
        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float, 
                          time_in_force: str, current_time: datetime, entry_tag: Optional[str], 
                          side: str, **kwargs) -> bool:
        if side != 'short':
            return True
            
        coin = self.get_coin_from_pair(pair)
        
        cooldown_minutes = 5
        if pair in self._last_candle_seen_time:
            last_time = self._last_candle_seen_time[pair]
            if current_time - last_time < timedelta(minutes=cooldown_minutes):
                return False
        
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            
            if len(dataframe) > 0:
                if 'yearly_volatility_1d' in dataframe.columns:
                    max_volatility_pct = self.max_volatility_pct.value * 100
                    if dataframe['yearly_volatility_1d'].iloc[-1] > max_volatility_pct:
                        return False
                        
                if 'is_chopping_4h' in dataframe.columns and 'historical_volatility_4h' in dataframe.columns:
                    if dataframe['is_chopping_4h'].iloc[-1] > 0.5 and dataframe['historical_volatility_4h'].iloc[-1] < 0.3:
                        return False
        except Exception:
            pass
        
        self._last_candle_seen_time[pair] = current_time
        
        return True

    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                           rate: float, time_in_force: str, exit_reason: str,
                           current_time: datetime, **kwargs) -> bool:
    
        # Only filter exit_signal exits
        if exit_reason != 'exit_signal':
            return True
        
        # Implement exit cooldown
        cooldown_key = f"{pair}_exit_cooldown"
        if cooldown_key in self._exit_cooldown:
            last_exit = self._exit_cooldown[cooldown_key]
            min_time_between_exits = timedelta(minutes=self.exit_cooldown_period.value)
            if current_time - last_exit < min_time_between_exits:
                return False
        
        # Always allow profitable exits
        current_profit = trade.calc_profit_ratio(rate)
        if current_profit > 0.01:
            self._exit_cooldown[cooldown_key] = current_time
            return True
        
        # For unprofitable trades, be more selective
        try:
            dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
            if len(dataframe) > 0:
                last_candle = dataframe.iloc[-1]
                
                # Only allow exit on significant valleys with high volume
                if 'significant_valley' in last_candle:
                    if last_candle['significant_valley']:
                        self._exit_cooldown[cooldown_key] = current_time
                        return True
        except Exception:
            pass
            
        return False

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        if not trade.is_short:
            return None
            
        coin = self.get_coin_from_pair(pair)
        
        quick_profit = self._coin_parameters.get(coin, {}).get('quick_profit', self.quick_profit_pct.value)
        medium_profit = self._coin_parameters.get(coin, {}).get('medium_profit', self.medium_profit_pct.value)
        long_profit = self._coin_parameters.get(coin, {}).get('long_profit', self.long_profit_pct.value)
        
        time_delta = (current_time - trade.open_date_utc).total_seconds() / 60
        
        if time_delta < 15 and current_profit >= quick_profit:
            return 'quick_profit'
        elif 15 <= time_delta < 60 and current_profit >= medium_profit:
            return 'medium_profit'
        elif time_delta >= 60 and current_profit >= long_profit:
            return 'long_profit'

        if current_profit > 0:
            max_profit_key = f"{pair}_max_profit"
            if max_profit_key not in self._max_profits:
                self._max_profits[max_profit_key] = current_profit
            elif current_profit > self._max_profits[max_profit_key]:
                self._max_profits[max_profit_key] = current_profit
                
            max_profit = self._max_profits[max_profit_key]
            drawdown = (max_profit - current_profit) / max_profit if max_profit != 0 else 0
            
            volatility_adjusted_drawdown = 0.1
            
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if len(dataframe) > 0:
                    adaptive_vol_stop_scaling = self.adaptive_vol_stop_scaling.value
                    
                    if 'historical_volatility_1h' in dataframe.columns:
                        current_volatility = dataframe['historical_volatility_1h'].iloc[-1]
                        base_vol = 0.5
                        vol_ratio = current_volatility / base_vol
                        
                        vol_adjusted_factor = np.sqrt(vol_ratio) * adaptive_vol_stop_scaling
                        volatility_adjusted_drawdown = min(0.2, max(0.05, 0.1 * vol_adjusted_factor))
                        
                        if time_delta < 30:
                            volatility_adjusted_drawdown *= 0.8
                        elif time_delta > 120:
                            volatility_adjusted_drawdown *= 1.2
            except Exception:
                pass
                
            if max_profit > quick_profit:
                if time_delta > 60 and drawdown > volatility_adjusted_drawdown * 1.5:
                    return 'vol_adj_drawdown_protection_long'
                elif time_delta > 30 and drawdown > volatility_adjusted_drawdown * 1.2:
                    return 'vol_adj_drawdown_protection_medium'
                elif drawdown > volatility_adjusted_drawdown:
                    return 'vol_adj_drawdown_protection_quick'
            
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if len(dataframe) > 0:
                    if 'market_regime' in dataframe.columns:
                        market_regime = dataframe['market_regime'].iloc[-1]
                        if market_regime == "choppy_lowvol" and current_profit > long_profit * 0.7 and time_delta > 30:
                            return 'regime_choppy_lowvol_exit'
            except Exception:
                pass
                
            try:
                dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
                if len(dataframe) > 0 and current_profit > 0.008:
                    last_candle = dataframe.iloc[-1]
                    
                    if 'significant_valley' in last_candle and last_candle['significant_valley']:
                        return 'significant_valley_exit'
                    
                    if 'local_valley' in last_candle and 'macd_cross_above' in last_candle:
                        if last_candle['local_valley'] and last_candle['macd_cross_above']:
                            return 'valley_with_macd_cross'
                    
                    if 'volume' in last_candle and 'volume_ma' in last_candle and 'rsi' in last_candle:
                        if last_candle['volume'] > 1.5 * last_candle['volume_ma'] and last_candle['rsi'] < self.exit_rsi_threshold.value:
                            return 'volume_spike_with_profit'
            except Exception:
                pass

        return None

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                       current_rate: float, current_profit: float, **kwargs) -> float:
        coin = self.get_coin_from_pair(pair)
        atr_multiplier = self._coin_parameters.get(coin, {}).get('atr_multiplier', self.atr_stop_multiplier.value)
        
        base_stoploss = self.stoploss
       
        if current_profit > self.trailing_stop_offset.value:
           trailing_sl = -abs(self.trailing_stop_p.value) + current_profit
           base_stoploss = max(base_stoploss, trailing_sl)
       
        try:
           dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
           
           if len(dataframe) > 0:
               if 'atr' in dataframe.columns and trade.is_short:
                   last_atr = dataframe['atr'].iloc[-1]
                   entry_price = trade.open_rate
                   atr_stop_pct = (last_atr * atr_multiplier) / entry_price
                   
                   atr_stoploss = -1 * atr_stop_pct
                   
                   return max(atr_stoploss, base_stoploss)
        except Exception:
           pass
       
        return base_stoploss

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
              proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
              **kwargs) -> float:
       coin = self.get_coin_from_pair(pair)
       base_leverage = self._coin_parameters.get(coin, {}).get('leverage', self.leverage_param.value)
       
       pair_key = f"{pair}_market_regime"
       market_regime = self._market_regimes.get(pair_key, "unknown")
       
       regime_leverage_modifiers = {
           "trending_volatile": 0.8,
           "trending_normal": 1.0,
           "neutral": 0.9,
           "choppy_normal": 0.7,
           "choppy_lowvol": 0.6,
           "unknown": 0.8
       }
       
       vol_pair_key = f"{pair}_volatility"
       vol_metric = self._volatility_metrics.get(vol_pair_key, 0.5)
       
       try:
           dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
           if len(dataframe) > 0:
               if 'historical_volatility_1d' in dataframe.columns:
                   current_vol = dataframe['historical_volatility_1d'].iloc[-1]
                   max_vol_pct = self.max_volatility_pct.value
                   
                   vol_scaling = min(max_vol_pct / current_vol, 1.0) if current_vol > 0 else 0.8
                   
                   adjusted_leverage = base_leverage * regime_leverage_modifiers.get(market_regime, 0.8) * vol_scaling
                   return float(max(min(round(adjusted_leverage), 5), 1))
       except Exception:
           pass
           
       return float(max(min(round(base_leverage * regime_leverage_modifiers.get(market_regime, 0.8)), 5), 1))
       
    def feature_engineering_expand_all(self, dataframe: DataFrame, **kwargs) -> DataFrame:
       try:
           dataframe['hour'] = dataframe['date'].dt.hour
           dataframe['dayofweek'] = dataframe['date'].dt.dayofweek
           dataframe['price_change'] = dataframe['close'].pct_change()
           dataframe['volatility'] = dataframe['close'].rolling(20).std()
           dataframe['atr'] = ta.ATR(dataframe, timeperiod=self.atr_period.value)
           dataframe['atr_pct'] = dataframe['atr'] / dataframe['close']
           
           windows = [10, 20, 50]
           for window in windows:
               dataframe[f'volatility_{window}'] = dataframe['close'].pct_change().rolling(window).std()
               dataframe[f'volume_change_{window}'] = dataframe['volume'].pct_change().rolling(window).mean()
           
           if 'ema_short' in dataframe.columns and 'ema_long' in dataframe.columns:
               dataframe['dist_from_ema_short'] = (dataframe['close'] / dataframe['ema_short']) - 1
               dataframe['dist_from_ema_long'] = (dataframe['close'] / dataframe['ema_long']) - 1
           
           if all(x in dataframe.columns for x in ['bb_upper', 'bb_lower', 'bb_middle']):
               dataframe['bb_width'] = (dataframe['bb_upper'] - dataframe['bb_lower']) / dataframe['bb_middle']
               dataframe['bb_position'] = (dataframe['close'] - dataframe['bb_lower']) / (dataframe['bb_upper'] - dataframe['bb_lower'])
           
           if 'ema_short' in dataframe.columns and 'atr' in dataframe.columns:
               dataframe['mean_reversion_potential'] = (dataframe['ema_short'] - dataframe['close']) / dataframe['atr']
           
           if 'macd' in dataframe.columns and 'macdsignal' in dataframe.columns:
               dataframe['macd_diff'] = dataframe['macd'] - dataframe['macdsignal']
               dataframe['macd_diff_change'] = dataframe['macd_diff'] - dataframe['macd_diff'].shift(1)
           
           for n in range(1, 5):
               dataframe[f'close_change_{n}'] = dataframe['close'].pct_change(n)
               dataframe[f'high_change_{n}'] = dataframe['high'].pct_change(n)
               dataframe[f'low_change_{n}'] = dataframe['low'].pct_change(n)
       
       except Exception:
           pass
           
       return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, **kwargs) -> DataFrame:
       try:
           dataframe['&-s_close'] = (-1 * (dataframe['close'].shift(-20) - dataframe['close']) / dataframe['close']).clip(lower=0, upper=1)
           
           dataframe['&-market_trend'] = (dataframe['close'].shift(-10) < dataframe['close']).astype(float)
           
           if 'atr_pct' in dataframe.columns:
               dataframe['&-volatility'] = dataframe['atr_pct']
           
           dataframe['&-movement_magnitude'] = (abs(dataframe['close'].shift(-20) - dataframe['close']) / dataframe['close']).clip(upper=0.5)
           
           peak_in_next_10 = (dataframe['high'].rolling(10).max().shift(-10) - dataframe['close']) / dataframe['close']
           valley_in_next_10 = (dataframe['close'] - dataframe['low'].rolling(10).min().shift(-10)) / dataframe['close']
           dataframe['&-time_to_reversal'] = (peak_in_next_10 > 0.02) | (valley_in_next_10 > 0.02)
           
           future_low = dataframe['low'].rolling(20).min().shift(-20)
           potential_stop_price = dataframe['close'] * (1 + self.stoploss)
           dataframe['&-stop_hit'] = (future_low < potential_stop_price).astype(float)
           
       except Exception:
           dataframe['&-s_close'] = (-1 * (dataframe['close'].shift(-20) - dataframe['close']) / dataframe['close']).clip(lower=0, upper=1)
           
       return dataframe

    def hyperopt_space(self):
       return {
           'buy_rsi': Integer(30, 50, default=47),
           'sell_rsi_upper': Integer(60, 85, default=79),
           'sell_rsi_lower': Integer(20, 40, default=21),
           'ema_short': Integer(5, 15, default=8),
           'ema_long': Integer(15, 30, default=21),
           'macd_fast': Integer(8, 16, default=12),
           'macd_slow': Integer(18, 32, default=26),
           'macd_signal': Integer(6, 12, default=9),
           'price_extension_pct': Real(0.4, 1.0, default=0.6),
           'exit_rsi_threshold': Integer(15, 30, default=20),
           'trailing_stop_p': Real(0.10, 0.20, default=0.16),
           'trailing_stop_offset': Real(0.15, 0.25, default=0.213),
           'quick_profit_pct': Real(0.01, 0.03, default=0.02),
           'medium_profit_pct': Real(0.01, 0.02, default=0.015),
           'long_profit_pct': Real(0.005, 0.015, default=0.01),
           'stoploss': Real(-0.07, -0.03, default=-0.05),
           'atr_period': Integer(10, 25, default=14),
           'atr_stop_multiplier': Real(1.5, 4.0, default=2.5),
           'volatility_lookback': Integer(20, 100, default=50),
           'market_regime_threshold': Integer(90, 160, default=120),
           'max_volatility_pct': Real(0.5, 3.0, default=1.5),
           'adaptive_vol_stop_scaling': Real(0.5, 2.0, default=1.0),
           'leverage_param': Integer(1, 5, default=2),
           'exit_cooldown_period': Integer(5, 20, default=12)
       }
