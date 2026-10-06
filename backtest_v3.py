#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_v3.py
====================================
БЭКТЕСТ V3 - использует ЕДИНОЕ ЯДРО (strategy_core.simulate_v3).
Теперь equity строится ТОЧНО так же, как бот торгует:
  - 1 свеча = 1 действие (открытие / хедж / закрытие)
  - лот всегда 0.01 (multiplier=1.0)
  - закрытие цикла, когда ОБЩИЙ P&L > 0
  - хедж (смена направления) при P&L <= 0

Самотест внутри: запускайте `python backtest_v3.py`
"""

import sys
import os

# Обеспечиваем импорт общего ядра
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except Exception:  # pragma: no cover
    HAS_MT5 = False

import numpy as np
from strategy_core import CoreConfig, simulate_v3, compute_metrics


# ---------------------------------------------------------------------------
# Безопасная работа с MT5-массивами (numpy structured arrays)
# ---------------------------------------------------------------------------
def _has_enough(rates, n: int) -> bool:
    """Проверяет, что массив от MT5 не None и содержит >= n элементов."""
    return rates is not None and len(rates) >= n


def get_prices_from_mt5(symbol: str, timeframe, bars: int = 5000) -> list:
    """Загружает цены закрытия из MT5. Возвращает [] при ошибке."""
    if not HAS_MT5 or not mt5.initialize():
        return []
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if not _has_enough(rates, 2):
        return []
    return [float(r["close"]) for r in rates]


def run_backtest_equity(prices, cfg: CoreConfig = None, timeframe_bars: int = 1) -> dict:
    """
    Публичная обёртка для совместимости со старым кодом / дашбордом.
    Делегирует всю логику в strategy_core.simulate_v3 + compute_metrics.
    """
    if cfg is None:
        cfg = CoreConfig()
    result = simulate_v3(prices, cfg, timeframe_bars)
    metrics = compute_metrics(result)
    # Объединяем результат + метрики (имена полей как в вашем дашборде)
    out = dict(result)
    out.update(metrics)
    return out


# ---------------------------------------------------------------------------
# Самотест (sideways + trend), без MT5
# ---------------------------------------------------------------------------
def _gen_sideways(n: int = 500, seed: int = 42) -> list:
    rng = np.random.default_rng(seed)
    prices = [1.0]
    for _ in range(n):
        prices.append(prices[-1] + rng.normal(0, 0.0005))
    return prices


def _gen_trend(n: int = 500, seed: int = 7) -> list:
    rng = np.random.default_rng(seed)
    prices = [1.0]
    for i in range(n):
        prices.append(prices[-1] + 0.0003 + rng.normal(0, 0.0003))
    return prices


def self_test():
    print("=" * 60)
    print("BACKTEST V3 - SELF TEST")
    print("=" * 60)

    cfg = CoreConfig(start_lot=0.01, max_positions=10, sma_period=20)

    for name, prices in [("SIDEWAYS (боковик)", _gen_sideways()),
                         ("TREND (тренд вверх)", _gen_trend())]:
        print(f"\n--- {name} ---")
        for tf_bars in [1, 5]:
            res = simulate_v3(prices, cfg, timeframe_bars=tf_bars)
            m = compute_metrics(res)
            print(
                f"  [timeframe_bars={tf_bars}] "
                f"cycles={res['cycles']:4d}  "
                f"win_rate={m['win_rate']*100:5.1f}%  "
                f"profit=${res['total_profit']:8.2f}  "
                f"maxDD=${res['max_drawdown']:7.2f}  "
                f"PF={m['profit_factor']:.2f}  "
                f"Sharpe={m['sharpe_ratio']:.2f}"
            )

    print("\n[OK] Самотест завершён.")


if __name__ == "__main__":
    self_test()
