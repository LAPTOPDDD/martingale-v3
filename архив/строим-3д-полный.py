#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MARTINGALE 3D ANALYTICS FRAMEWORK v2.0
========================================
Полный перезапуск анализа с интерактивной 3D визуализацией.
Ось Y теперь показывает реальную ГЛУБИНУ МАТИНГЕЙЛА (Max Positions).
"""

import os
import random
import pandas as pd
import plotly.express as px
from dataclasses import dataclass, field, asdict
from typing import List

# ============================================================
# 1. КОНФИГУРАЦИЯ И ГРУППЫ ИНСТРУМЕНТОВ
# ============================================================
@dataclass
class Config:
    start_lot: float = 0.01
    multiplier: float = 1.5
    max_positions: int = 7  # Будет меняться в цикле
    spread_points: float = 2.0
    commission_per_lot: float = 0.0

@dataclass
class ComboResult:
    symbol: str
    timeframe: str
    cycles_param: int     # Параметр глубины мартингейла (ось Y)
    total_profit: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    safety_score: float = 0.0
    wins: int = 0
    cycles_done: int = 0

# --- ГРУППЫ ИНСТРУМЕНТОВ ---
FOREX = [
    'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD', 
    'EURGBP', 'EURJPY', 'GBPJPY', 'AUDCAD', 'AUDCHF', 'AUDNZD', 'CADCHF', 
    'CADJPY', 'CHFJPY', 'EURAUD', 'EURCAD', 'EURCHF', 'EURNOK', 'EURNZD', 
    'EURSEK', 'EURSGD', 'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPNZD', 'GBPSGD', 
    'NZDCAD', 'NZDCHF', 'NZDJPY', 'NZDSGD', 'USDCNH', 'USDMXN', 'USDNOK', 
    'USDPLN', 'USDSEK', 'USDSGD', 'USDTRY', 'USDZAR', 'USDTHB', 'USDHKD', 
    'USDAED', 'EURTRY'
]

# METALS_COMMODITIES = [
#     'XAUUSD', 'XAGUSD', 'XAGAUD', 'XAGEUR', 'XAUAUD', 'XAUEUR', 'XAUGBP', 
#     'XAUJPY', 'XAUCNH', 'XAGJPY', 'SPCUSD', 'USOUSD', 'JPCUSD', 'GLDUSD', 
#     'BRN', 'NG', 'WTI', 'ARABICA', 'COCOA', 'COPPER', 'CORN', 'COTTON', 
#     'ROBUSTA', 'SOYBEAN', 'SUGAR', 'WHEAT', 'GOLDInd', 'PAXG'
# ]

# CRYPTO = [
#     'BITCOIN', 'BITCOIN CASH', 'CARDANO', 'CHAINLINK', 'DOGECOIN', 'ETHEREUM', 
#     'LITECOIN', 'POLKADOT', 'POLYGON', 'RIPPLE', 'SOLANA', 'STELLAR', 'TRON', 
#     'UNISWAP', 'AVALANCH', 'BNB', 'COSMOS', 'GRAM', 'TRUMP', 'SUI', 'HEDERA', 
#     'NEAR', 'APTOS', 'ARBITRUM', 'ILLUVIUM', 'INJ', 'RENDER', 'PYTH', 'AAVE', 
#     'AXS', 'MICROSTRATEGY'
# ]

INDICES = [
    'US30', 'NAS100', 'SP500', 'GER40', 'CN50', 'FRA40', 'SPN35', 'UK100', 
    'AU200', 'EU50', 'HK50', 'JP225', 'NETH25', 'RUS2000', 'US400', 'CHINAH', 
    'SG20', 'TWN', 'NAS100U6', 'GER40U6', 'US30U6', 'SP500U6', 'GOLDZ6', 
    'DJCGLD', 'DJCJPC', 'DJCSPC', 'NACJPC', 'SPCJPC', 'USDInd'
]

STOCKS = [
    'APPLE', 'TESLA', 'AMAZON', 'MICROSOFT', 'NVIDIA', 'ALPHABET INC-C', 
    'META PLATFORMS', 'NETFLIX', 'ADOBE', 'AMD', 'INTEL', 'IBM', 'ORACLE', 
    'SALESFORCE', 'PAYPAL', 'UBER', 'LYFT', 'AIRBNB', 'COINBASE', 'ROBINHOOD',
    'BOEING CO/THE', 'CATERPILLAR', 'JOHNSON&JOHNSON', 'PFIZER', 'MODERNA INC',
    'COCA-COLA CO/THE', 'PEPSICO', 'MCDONALDS', 'NIKE --B', 'STARBUCKS',
    'BANK OF AMERICA', 'JPMORGAN CHASE', 'GOLDMAN SACHS GP', 'VISA -CLASS A',
    'MASTERCARD-A', 'BLACKROCK', 'BERKSHIRE HATHAWAY', 'DISNEY', 'SONY GROUP CORP'
]

# АКТИВНАЯ ВЫБОРКА (Металлы и Крипта закомментированы)
ACTIVE_SYMBOLS = FOREX + INDICES + STOCKS
# ACTIVE_SYMBOLS = FOREX + METALS_COMMODITIES + CRYPTO + INDICES + STOCKS 

TIMEFRAMES = ["M1", "M5","M15", "M30","H1", "H4"]
CYCLES_RANGE = range(5, 11)  # Проверяем глубину от 5 до 10 позиций

# ============================================================
# 2. ЯДРО БЭКТЕСТА (Синтетика для скорости и автономности)
# ============================================================
def generate_synthetic_prices(n: int, volatility: float = 0.0005, seed: int = 42) -> List[float]:
    """Генератор цен с заданным сидом для воспроизводимости"""
    random.seed(seed)
    prices = [1.0]
    for _ in range(n - 1):
        change = random.gauss(0, volatility)
        prices.append(max(0.0001, prices[-1] * (1 + change)))
    return prices

def run_backtest(prices: List[float], symbol: str, timeframe: str, cfg: Config) -> ComboResult:
    """Быстрый прогон мартингейла на массиве цен"""
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
            # Расчет P&L текущей серии
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
            
            # Добавляем колено мартингейла
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

    # Расчет метрик
    gross_profit = max(0.0, result.total_profit)
    gross_loss = abs(min(0.0, result.total_profit))
    result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    
    win_rate = (result.wins / result.cycles_done) if result.cycles_done > 0 else 0.0
    # Safety Score: чем выше, тем лучше баланс риска и доходности
    result.safety_score = (win_rate * result.profit_factor) / (result.max_drawdown + 1.0)
    
    return result

# ============================================================
# 3. ИНТЕРАКТИВНАЯ 3D ВИЗУАЛИЗАЦИЯ (PLOTLY)
# ============================================================
def create_interactive_3d(results: List[ComboResult]):
    df = pd.DataFrame([asdict(r) for r in results])
    
    print(f"\n📊 Построение графика для {len(df)} комбинаций...")
    
    fig = px.scatter_3d(
        df,
        x='timeframe',          # Ось X: Таймфреймы
        y='cycles_param',       # Ось Y: ГЛУБИНА МАТИНГЕЙЛА (5-10)
        z='safety_score',       # Ось Z: Безопасность (высота точки)
        color='total_profit',   # Цвет: Прибыль (Viridis шкала)
        hover_data={            # Данные при наведении мыши
            'symbol': True,     # Самое важное: название инструмента!
            'total_profit': ':,.2f',
            'max_drawdown': ':,.2f',
            'profit_factor': True,
            'wins': True
        },
        title="Interactive 3D Strategy Landscape: Hover to see Symbol!",
        labels={
            'timeframe': 'Timeframe',
            'cycles_param': 'Martingale Depth (Positions)',
            'safety_score': 'Safety Score (Risk/Reward)',
            'total_profit': 'Total Profit'
        },
        color_continuous_scale='Viridis',
        size_max=12,
        opacity=0.85
    )
    
    fig.update_layout(
        scene=dict(
            xaxis_title='Timeframe',
            yaxis_title='Max Positions (Cycles)',
            zaxis_title='Safety Score',
            aspectmode='manual',
            aspectratio=dict(x=1.2, y=1, z=0.8)
        ),
        width=1400,
        height=900,
        font=dict(size=12, family="Arial")
    )
    
    html_path = "3d_martingale_landscape.html"
    fig.write_html(html_path)
    print(f"✅ График сохранен: {os.path.abspath(html_path)}")
    print("💡 Открой файл в браузере. ЛКМ - вращать | Колесико - зум | Наведи на точку!")
    
    try:
        import webbrowser
        webbrowser.open('file://' + os.path.realpath(html_path))
    except Exception:
        pass

# ============================================================
# 4. MAIN EXECUTION
# ============================================================
def main():
    cfg = Config()
    results = []
    
    print(f"🚀 ЗАПУСК ПОЛНОГО АНАЛИЗА ({len(ACTIVE_SYMBOLS)} инструментов)")
    print(f"⏳ Таймфреймы: {TIMEFRAMES} | Циклы: {list(CYCLES_RANGE)}")
    print("-" * 60)
    
    total_combinations = len(ACTIVE_SYMBOLS) * len(TIMEFRAMES) * len(list(CYCLES_RANGE))
    current = 0
    
    for symbol in ACTIVE_SYMBOLS:
        for tf in TIMEFRAMES:
            # Генерируем данные один раз для пары символ/ТФ
            prices = generate_synthetic_prices(3000, seed=hash(symbol + tf) % 100000)
            
            for cycles in CYCLES_RANGE:
                cfg.max_positions = cycles
                res = run_backtest(prices, symbol, tf, cfg)
                results.append(res)
                
                current += 1
                if current % 100 == 0 or current == total_combinations:
                    progress = (current / total_combinations) * 100
                    print(f"Прогресс: {progress:.1f}% ({current}/{total_combinations}) | "
                          f"Последний: {symbol} {tf} C:{cycles} Profit:{res.total_profit:.0f}")

    print("-" * 60)
    create_interactive_3d(results)

if __name__ == "__main__":
    main()