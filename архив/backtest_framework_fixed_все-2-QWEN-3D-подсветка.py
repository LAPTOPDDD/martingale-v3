#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INTERACTIVE 3D MARTINGALE ANALYTICS (PLOTLY)
============================================================
Теперь график интерактивный: вращай, зумь и наводи мышку на точки!
"""

import os
import random
import numpy as np
import pandas as pd
import plotly.express as px
from dataclasses import dataclass, field, asdict
from typing import List

# ============================================================
#  КОНФИГУРАЦИЯ И ДАННЫЕ
# ============================================================
@dataclass
class Config:
    start_lot: float = 0.01
    multiplier: float = 1.5
    max_positions: int = 7
    spread_points: float = 2.0

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

# --- ГРУППЫ ИНСТРУМЕНТОВ (Сокращенный список для скорости теста) ---
FOREX = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY']
INDICES = ['US30', 'NAS100', 'SP500', 'GER40']
STOCKS = ['APPLE', 'TESLA', 'AMAZON', 'MICROSOFT', 'NVIDIA']

ACTIVE_SYMBOLS = FOREX + INDICES + STOCKS
TIMEFRAMES = ["M1", "M15", "H1", "H4"]
CYCLES_RANGE = range(5, 11) 

# ============================================================
#  ЯДРО БЭКТЕСТА (Упрощенное для примера)
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
                result.wins += 1
                break
            
            if len(positions) >= cfg.max_positions:
                closed_this_cycle = True
                result.total_profit += total_profit
                current_equity += total_profit
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
    # Safety Score: баланс между доходностью и риском
    result.safety_score = (win_rate * result.profit_factor) / (result.max_drawdown + 1.0)
    return result

# ============================================================
#  ИНТЕРАКТИВНАЯ 3D ВИЗУАЛИЗАЦИЯ (PLOTLY)
# ============================================================
def create_interactive_3d(results: List[ComboResult], output_dir: str):
    df = pd.DataFrame([asdict(r) for r in results])
    
    # Создаем интерактивный 3D scatter plot
    fig = px.scatter_3d(
        df, 
        x='timeframe',          # Ось X: Таймфреймы
        y='cycles_param',       # Ось Y: Число циклов
        z='safety_score',       # Ось Z: Безопасность (высота)
        color='total_profit',   # Цвет: Прибыль
        hover_data=['symbol', 'profit_factor', 'max_drawdown'], # Данные при наведении
        title="Interactive 3D Strategy Landscape: Hover to see Symbol!",
        labels={'timeframe': 'Timeframe', 'cycles_param': 'Max Positions', 'safety_score': 'Safety Score'},
        color_continuous_scale='Viridis',
        size_max=10
    )
    
    # Настройки внешнего вида
    fig.update_layout(
        scene=dict(
            xaxis_title='Timeframe',
            yaxis_title='Cycles (Positions)',
            zaxis_title='Safety Score (Risk/Reward)'
        ),
        width=1200,
        height=800
    )
    
    # Сохраняем в HTML (чтобы открывать в браузере) и показываем
    html_path = os.path.join(output_dir, "interactive_3d_map.html")
    fig.write_html(html_path)
    fig.show()
    print(f"✅ Интерактивный график сохранен: {html_path}")
    print("💡 Наведи мышку на любую точку, чтобы увидеть название инструмента!")

# ============================================================
#  MAIN
# ============================================================
def main():
    cfg = Config()
    results = []
    output_dir = "results_interactive"
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n🚀 ЗАПУСК ИНТЕРАКТИВНОГО АНАЛИЗА ({len(ACTIVE_SYMBOLS)} инструментов)")
    
    for symbol in ACTIVE_SYMBOLS:
        for tf in TIMEFRAMES:
            prices = generate_synthetic_prices(2000, seed=hash(symbol+tf)%10000)
            
            for cycles in CYCLES_RANGE:
                cfg.max_positions = cycles
                res = run_backtest(prices, symbol, tf, cfg)
                results.append(res)
                # Прогресс-бар в консоль
                if res.total_profit > 0:
                    print(f"[OK] {symbol} | {tf} | C:{cycles} | Profit: {res.total_profit:.0f}")

    create_interactive_3d(results, output_dir)

if __name__ == "__main__":
    main()