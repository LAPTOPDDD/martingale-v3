#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MT5 REAL DATA CHAMPIONS FINDER
================================
Тянет реальные данные, находит ТОП-5 по Safety Score 
и строит графики эквити БЕЗ ошибок Excel.
"""

import os
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import MetaTrader5 as mt5
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime, timedelta

# ============================================================
# 1. КОНФИГУРАЦИЯ
# ============================================================
@dataclass
class Config:
    start_lot: float = 0.01
    multiplier: float = 1.5
    max_positions: int = 7
    spread_points: float = 2.0
    months_history: int = 3  # Тянем за 3 месяца

@dataclass
class ComboResult:
    symbol: str
    timeframe: str
    cycles_param: int
    total_profit: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    safety_score: float = 0.0
    wins: int = 0
    cycles_done: int = 0
    equity_curve: List[float] = field(default_factory=list)

# --- СПИСОК ИНСТРУМЕНТОВ (Можно сократить для скорости первого теста) ---
FOREX = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD', 
         'EURGBP', 'EURJPY', 'GBPJPY', 'AUDCAD', 'AUDCHF', 'AUDNZD', 'CADCHF', 
         'CADJPY', 'CHFJPY', 'EURAUD', 'EURCAD', 'EURCHF', 'EURNOK', 'EURNZD', 
         'EURSEK', 'EURSGD', 'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPNZD', 'GBPSGD', 
         'NZDCAD', 'NZDCHF', 'NZDJPY', 'NZDSGD', 'USDCNH', 'USDMXN', 'USDNOK', 
         'USDPLN', 'USDSEK', 'USDSGD', 'USDTRY', 'USDZAR', 'USDTHB', 'USDHKD', 
         'USDAED', 'EURTRY']

INDICES = ['US30', 'NAS100', 'SP500', 'GER40', 'CN50', 'FRA40', 'SPN35', 'UK100', 
           'AU200', 'EU50', 'HK50', 'JP225', 'NETH25', 'RUS2000', 'US400', 'CHINAH', 
           'SG20', 'TWN', 'USDInd']

STOCKS = ['APPLE', 'TESLA', 'AMAZON', 'MICROSOFT', 'NVIDIA', 'ALPHABET INC-C', 
          'META PLATFORMS', 'NETFLIX', 'ADOBE', 'AMD', 'INTEL', 'IBM', 'ORACLE', 
          'SALESFORCE', 'PAYPAL', 'UBER', 'LYFT', 'AIRBNB', 'COINBASE', 'ROBINHOOD',
          'BOEING CO/THE', 'CATERPILLAR', 'JOHNSON&JOHNSON', 'PFIZER', 'MODERNA INC',
          'COCA-COLA CO/THE', 'PEPSICO', 'MCDONALDS', 'NIKE --B', 'STARBUCKS',
          'BANK OF AMERICA', 'JPMORGAN CHASE', 'GOLDMAN SACHS GP', 'VISA -CLASS A',
          'MASTERCARD-A', 'BLACKROCK', 'DISNEY', 'SONY GROUP CORP']

ACTIVE_SYMBOLS = FOREX + INDICES + STOCKS
TIMEFRAMES_MAP = {"M1": mt5.TIMEFRAME_M1, "M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4}
CYCLES_RANGE = range(5, 11) 

# ============================================================
# 2. ЯДРО БЭКТЕСТА НА РЕАЛЬНЫХ ДАННЫХ
# ============================================================
def get_mt5_prices(symbol: str, tf_str: str, cfg: Config) -> Optional[List[float]]:
    """Получает реальные цены закрытия из MT5. Быстрая проверка перед полной загрузкой."""
    if not mt5.initialize():
        print(f"❌ Не удалось подключиться к MT5")
        return None
        
    tf_enum = TIMEFRAMES_MAP.get(tf_str)
    date_to = datetime.now()
    date_from = date_to - timedelta(days=cfg.months_history * 30)
    
    # Проверяем доступность символа и объем данных
    rates = mt5.copy_rates_range(symbol, tf_enum, date_from, date_to)
    
    if rates is None or len(rates) < 500:
        return None  # Пропускаем инструменты без достаточной истории
        
    return [float(r["close"]) for r in rates]

def run_backtest_real(prices: List[float], symbol: str, timeframe: str, cfg: Config) -> ComboResult:
    """Прогон мартингейла с сохранением реальной кривой эквити"""
    result = ComboResult(symbol=symbol, timeframe=timeframe, cycles_param=cfg.max_positions)
    i = 0
    current_equity = 0.0
    peak_equity = 0.0
    equity_curve = [0.0]
    
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
                equity_curve.append(current_equity)
                result.wins += 1
                break
            
            if len(positions) >= cfg.max_positions:
                closed_this_cycle = True
                result.total_profit += total_profit
                current_equity += total_profit
                equity_curve.append(current_equity)
                break
            
            sum_volumes = sum(v for v, _, _ in positions)
            new_lot = round(sum_volumes * cfg.multiplier, 2)
            positions.append((new_lot, -direction, current_price))
            i += 1
            
        result.cycles_done += 1
        peak_equity = max(peak_equity, current_equity)
        drawdown = peak_equity - current_equity
        result.max_drawdown = max(result.max_drawdown, drawdown)
        
        if not closed_this_cycle: 
            i += 1

    gross_profit = max(0.0, result.total_profit)
    gross_loss = abs(min(0.0, result.total_profit))
    result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    
    win_rate = (result.wins / result.cycles_done) if result.cycles_done > 0 else 0.0
    result.safety_score = (win_rate * result.profit_factor) / (result.max_drawdown + 1.0)
    result.equity_curve = equity_curve
    
    return result

# ============================================================
# 3. АВТОМАТИЧЕСКИЙ ПОИСК ЧЕМПИОНОВ И ВИЗУАЛИЗАЦИЯ
# ============================================================
def analyze_and_visualize(results: List[ComboResult]):
    df = pd.DataFrame([asdict(r) for r in results])
    
    # Фильтруем только прибыльные стратегии
    positive_df = df[df['total_profit'] > 0].copy()
    
    if positive_df.empty:
        print("❌ Нет положительных результатов на реальных данных.")
        return
        
    # Сортируем по Safety Score (чем выше, тем лучше баланс риска/дохода)
    champions = positive_df.sort_values('safety_score', ascending=False).head(5)
    
    output_dir = "mt5_champions_analysis"
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\n🏆 ТОП-5 ЧЕМПИОНОВ (Реальные данные MT5):")
    print("-" * 90)
    print(f"{'Rank':<5} {'Symbol':<15} {'TF':<6} {'Depth':<6} {'Safety':<10} {'Profit':<15} {'Max DD':<15}")
    print("-" * 90)
    
    fig, axes = plt.subplots(len(champions), 1, figsize=(16, 5 * len(champions)))
    if len(champions) == 1:
        axes = [axes]
        
    for idx, (_, row) in enumerate(champions.iterrows()):
        print(f"{idx+1:<5} {row['symbol']:<15} {row['timeframe']:<6} {row['cycles_param']:<6} "
              f"{row['safety_score']:<10.4f} {row['total_profit']:<15,.2f} {row['max_drawdown']:<15,.2f}")
              
        ax = axes[idx]
        eq = row['equity_curve']
        x_axis = range(len(eq))
        
        ax.plot(x_axis, eq, color='#2ecc71', linewidth=2)
        ax.fill_between(x_axis, eq, alpha=0.15, color='#2ecc71')
        
        min_eq = min(eq)
        ax.axhline(y=min_eq, color='#e74c3c', linestyle='--', alpha=0.8, label=f'Max DD: {row["max_drawdown"]:,.0f}')
        
        ax.set_title(f"#{idx+1} {row['symbol']} ({row['timeframe']}) | Depth: {row['cycles_param']} | "
                     f"Profit: {row['total_profit']:,.0f} | Safety: {row['safety_score']:.4f}", fontsize=12)
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        ax.set_ylabel("Equity")
        
    plt.tight_layout()
    chart_path = os.path.join(output_dir, "champions_equity_curves.png")
    plt.savefig(chart_path, dpi=150)
    plt.show()
    
    # Сохраняем ТОЛЬКО статистику в Excel (без длинных массивов!)
    excel_path = os.path.join(output_dir, "mt5_full_report.xlsx")
    df.drop(columns=['equity_curve'], errors='ignore').to_excel(excel_path, index=False)
    
    print(f"\n✅ График сохранен: {chart_path}")
    print(f"✅ Чистый отчет Excel: {excel_path}")

# ============================================================
# 4. MAIN EXECUTION
# ============================================================
def main():
    cfg = Config()
    results = []
    
    print(f" ЗАПУСК АНАЛИЗА НА РЕАЛЬНЫХ ДАННЫХ MT5")
    print(f"📅 Период: последние {cfg.months_history} месяцев")
    print(f"🛠️ Инструменты: {len(ACTIVE_SYMBOLS)} | ТФ: {list(TIMEFRAMES_MAP.keys())} | Глубина: {list(CYCLES_RANGE)}")
    print("-" * 60)
    
    if not mt5.initialize():
        print("❌ Ошибка подключения к MetaTrader 5. Запустите терминал!")
        return

    total_combinations = len(ACTIVE_SYMBOLS) * len(TIMEFRAMES_MAP) * len(list(CYCLES_RANGE))
    current = 0
    skipped = 0
    
    for symbol in ACTIVE_SYMBOLS:
        for tf_str, tf_enum in TIMEFRAMES_MAP.items():
            prices = get_mt5_prices(symbol, tf_str, cfg)
            if not prices:
                skipped += 1
                continue
                
            for cycles in CYCLES_RANGE:
                cfg.max_positions = cycles
                res = run_backtest_real(prices, symbol, tf_str, cfg)
                results.append(res)
                
                current += 1
                if current % 50 == 0:
                    progress = (current / total_combinations) * 100
                    print(f"⏳ Прогресс: {progress:.1f}% | {symbol} {tf_str} C:{cycles} "
                          f"Profit:{res.total_profit:.0f} DD:{res.max_drawdown:.0f}")

    mt5.shutdown()
    print(f"\nℹ️ Пропущено инструментов без данных: {skipped}")
    print("-" * 60)
    analyze_and_visualize(results)

if __name__ == "__main__":
    main()