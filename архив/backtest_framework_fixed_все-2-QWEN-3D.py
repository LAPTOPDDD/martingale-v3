
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MARTINGALE 3D ANALYTICS FRAMEWORK
============================================================
Групповой анализ инструментов с 3D-визуализацией риска и доходности.
"""

import os
import random
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import pandas as pd
from dataclasses import dataclass, field, asdict
from typing import List, Optional

# ============================================================
#  КОНФИГУРАЦИЯ И ДАННЫЕ
# ============================================================
@dataclass
class Config:
    start_lot: float = 0.01
    multiplier: float = 1.5
    max_positions: int = 7 # Будет меняться в цикле
    spread_points: float = 2.0
    commission_per_lot: float = 0.0

@dataclass
class ComboResult:
    symbol: str
    timeframe: str
    cycles_param: int # Параметр, который мы меняем
    cycles_done: int = 0
    wins: int = 0
    total_profit: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    safety_score: float = 0.0
    equity_history: List[float] = field(default_factory=list)

# --- ГРУППЫ ИНСТРУМЕНТОВ ---
# ============================================================
#  ГРУППЫ ИНСТРУМЕНТОВ (ПОЛНЫЙ СПИСОК)
# ============================================================

# 1. FOREX (Основные и кросс-курсы)
FOREX = [
    'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD', 
    'EURGBP', 'EURJPY', 'GBPJPY', 'AUDCAD', 'AUDCHF', 'AUDNZD', 'CADCHF', 
    'CADJPY', 'CHFJPY', 'EURAUD', 'EURCAD', 'EURCHF', 'EURNOK', 'EURNZD', 
    'EURSEK', 'EURSGD', 'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPNZD', 'GBPSGD', 
    'NZDCAD', 'NZDCHF', 'NZDJPY', 'NZDSGD', 'USDCNH', 'USDMXN', 'USDNOK', 
    'USDPLN', 'USDSEK', 'USDSGD', 'USDTRY', 'USDZAR', 'USDTHB', 'USDHKD', 
    'USDAED', 'EURTRY'
]

# 2. METALS & COMMODITIES (Закомментировано по запросу)
# METALS_COMMODITIES = [
#     'XAUUSD', 'XAGUSD', 'XAGAUD', 'XAGEUR', 'XAUAUD', 'XAUEUR', 'XAUGBP', 
#     'XAUJPY', 'XAUCNH', 'XAGJPY', 'SPCUSD', 'USOUSD', 'JPCUSD', 'GLDUSD', 
#     'BRN', 'NG', 'WTI', 'ARABICA', 'COCOA', 'COPPER', 'CORN', 'COTTON', 
#     'ROBUSTA', 'SOYBEAN', 'SUGAR', 'WHEAT', 'GOLDInd', 'PAXG'
# ]

# 3. CRYPTO (Закомментировано по запросу)
# CRYPTO = [
#     'BITCOIN', 'BITCOIN CASH', 'CARDANO', 'CHAINLINK', 'DOGECOIN', 'ETHEREUM', 
#     'LITECOIN', 'POLKADOT', 'POLYGON', 'RIPPLE', 'SOLANA', 'STELLAR', 'TRON', 
#     'UNISWAP', 'AVALANCH', 'BNB', 'COSMOS', 'GRAM', 'TRUMP', 'SUI', 'HEDERA', 
#     'NEAR', 'APTOS', 'ARBITRUM', 'ILLUVIUM', 'INJ', 'RENDER', 'PYTH', 'AAVE', 
#     'AXS', 'MICROSTRATEGY'
# ]

# 4. INDICES (Мировые индексы)
INDICES = [
    'US30', 'NAS100', 'SP500', 'GER40', 'CN50', 'FRA40', 'SPN35', 'UK100', 
    'AU200', 'EU50', 'HK50', 'JP225', 'NETH25', 'RUS2000', 'US400', 'CHINAH', 
    'SG20', 'TWN', 'NAS100U6', 'GER40U6', 'US30U6', 'SP500U6', 'GOLDZ6', 
    'DJCGLD', 'DJCJPC', 'DJCSPC', 'NACJPC', 'SPCJPC', 'USDInd'
]

# 5. STOCKS CFD (Акции США и мира)
STOCKS = [
    'APPLE', 'TESLA', 'AMAZON', 'MICROSOFT', 'NVIDIA', 'ALPHABET INC-C', 
    'META PLATFORMS', 'NETFLIX', 'ADOBE', 'AMD', 'INTEL', 'IBM', 'ORACLE', 
    'SALESFORCE', 'PAYPAL', 'UBER', 'LYFT', 'AIRBNB', 'COINBASE', 'ROBINHOOD',
    'BOEING CO/THE', 'CATERPILLAR', 'JOHNSON&JOHNSON', 'PFIZER', 'MODERNA INC',
    'COCA-COLA CO/THE', 'PEPSICO', 'MCDONALDS', 'NIKE --B', 'STARBUCKS',
    'BANK OF AMERICA', 'JPMORGAN CHASE', 'GOLDMAN SACHS GP', 'VISA -CLASS A',
    'MASTERCARD-A', 'BLACKROCK', 'BERKSHIRE HATHAWAY', 'DISNEY', 'SONY GROUP CORP'
]

# --- АКТИВНАЯ ВЫБОРКА ДЛЯ ТЕСТА ---
# Сейчас включены только Форекс, Индексы и Акции. 
# Чтобы включить всё, раскомментируй строки ниже и добавь группы в список:
ACTIVE_SYMBOLS = FOREX 
#ACTIVE_SYMBOLS = FOREX + INDICES + STOCKS
# ACTIVE_SYMBOLS = FOREX + METALS_COMMODITIES + CRYPTO + INDICES + STOCKS

TIMEFRAMES = ["M1" , "M5" , "M15",  "M30" ,  "H1"]
CYCLES_RANGE = range(5, 11) # Проверяем глубину мартингейла от 5 до 10 позиций

# ============================================================
#  ЯДРО БЭКТЕСТА
# ============================================================
def generate_synthetic_prices(n: int, volatility: float = 0.0005, seed: int = 42) -> List[float]:
    random.seed(seed)
    prices = [1.0]
    for _ in range(n - 1):
        change = random.gauss(0, volatility)
        prices.append(max(0.0001, prices[-1] * (1 + change)))
    return prices

def run_backtest(prices: List[float], symbol: str, timeframe: str, cfg: Config) -> ComboResult:
    result = ComboResult(symbol=symbol, timeframe=timeframe, cycles_param=cfg.max_positions)
    i = 0
    current_equity = 0.0
    equity_history = [0.0]
    peak_equity = 0.0
    
    while i < len(prices) - 1:
        positions = []
        closed_this_cycle = False
        entry_price = prices[i]
        lot = cfg.start_lot
        direction = 1
        positions.append((lot, direction, entry_price))
        i += 1
        
        while i < len(prices) and len(positions) <= cfg.max_positions and not closed_this_cycle:
            current_price = prices[i]
            total_profit = sum(((current_price - open_px) * dirn) * vol * 100000 
                               for vol, dirn, open_px in positions)
            
            if total_profit > 0:
                closed_this_cycle = True
                result.total_profit += total_profit
                current_equity += total_profit
                equity_history.append(current_equity)
                result.wins += 1
                break
            
            if len(positions) >= cfg.max_positions:
                closed_this_cycle = True
                result.total_profit += total_profit
                current_equity += total_profit
                equity_history.append(current_equity)
                break
            
            sum_volumes = sum(v for v, _, _ in positions)
            new_lot = round(sum_volumes * cfg.multiplier, 2)
            positions.append((new_lot, -direction, current_price))
            i += 1
            
        result.cycles_done += 1
        peak_equity = max(peak_equity, current_equity)
        result.max_drawdown = max(result.max_drawdown, peak_equity - current_equity)
        if not closed_this_cycle: i += 1

    gross_profit = max(0.0, result.total_profit)
    gross_loss = abs(min(0.0, result.total_profit))
    result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    
    win_rate = (result.wins / result.cycles_done) if result.cycles_done > 0 else 0.0
    result.safety_score = (win_rate * result.profit_factor) / (result.max_drawdown + 1.0)
    result.equity_history = equity_history
    return result

# ============================================================
#  3D ВИЗУАЛИЗАЦИЯ
# ============================================================
def create_3d_dashboard(results: List[ComboResult], output_dir: str):
    df = pd.DataFrame([asdict(r) for r in results])
    
    # Маппинг ТФ в числа для оси X
    tf_unique = sorted(df['timeframe'].unique())
    tf_map = {tf: i for i, tf in enumerate(tf_unique)}
    df['tf_num'] = df['timeframe'].map(tf_map)

    fig = plt.figure(figsize=(16, 10))
    ax = fig.add_subplot(111, projection='3d')

    # Цвет точек зависит от профита
    scatter = ax.scatter(df['tf_num'], df['cycles_param'], df['safety_score'], 
                         c=df['total_profit'], cmap='viridis', s=80, depthshade=True, edgecolors='k', alpha=0.8)

    ax.set_xlabel('Timeframe')
    ax.set_ylabel('Max Positions (Cycles)')
    ax.set_zlabel('Safety Score (Risk/Reward)')
    ax.set_title('3D Strategy Landscape: Find the Peak')
    
    # Настройка меток на осях
    ax.set_xticks(list(tf_map.values()))
    ax.set_xticklabels(tf_unique)
    
    fig.colorbar(scatter, shrink=0.5, aspect=10, label='Total Profit')
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "3d_strategy_map.png"), dpi=150)
    plt.show()
    print("✅ 3D график готов к вращению!")

# ============================================================
#  MAIN
# ============================================================
def main():
    cfg = Config()
    results = []
    output_dir = "results_3d"
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n🚀 ЗАПУСК 3D АНАЛИЗА ({len(ACTIVE_SYMBOLS)} инструментов)")
    
    for symbol in ACTIVE_SYMBOLS:
        for tf in TIMEFRAMES:
            # Генерируем данные один раз для символа/ТФ
            prices = generate_synthetic_prices(3000, seed=hash(symbol+tf)%10000)
            
            for cycles in CYCLES_RANGE:
                cfg.max_positions = cycles
                res = run_backtest(prices, symbol, tf, cfg)
                results.append(res)
                print(f"[{symbol:<8}| {tf:<4}| C:{cycles}] Profit: {res.total_profit:.1f} | DD: {res.max_drawdown:.1f}")

    create_3d_dashboard(results, output_dir)

if __name__ == "__main__":
    main()