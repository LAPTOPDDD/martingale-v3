#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
strategy_core.py — Единое ядро логики V3 (ИСПРАВЛЕНО: добавлено поле period)
"""

from dataclasses import dataclass
import numpy as np


@dataclass
class CoreConfig:
    start_lot: float = 0.01
    max_positions: int = 10
    period: int = 20              # ✅ ИСПРАВЛЕНО — было пропущено
    contract_size: float = 100000
    point: float = 0.0001
    commission_per_lot: float = 0.0


def _sma(closes: np.ndarray, period: int, idx: int) -> float:
    """SMA без look-ahead bias (окно [idx-period ... idx-1])."""
    if idx <= 0 or len(closes) < period + 1:
        return float(closes[0]) if len(closes) > 0 else 0.0
    window = closes[max(0, idx - period):idx]
    if len(window) == 0:
        return float(closes[0])
    return float(np.mean(window))


def simulate_v3(prices: np.ndarray, cfg: CoreConfig) -> dict:
    n = len(prices)
    if n < cfg.period + 4:
        return _empty_result()

    equity = 0.0
    equity_curve = [0.0]
    positions = []          # [lot, direction, open_price]
    wins = 0
    losses = 0
    cycles = 0
    sum_win = 0.0
    sum_loss_abs = 0.0

    i = cfg.period  # начинаем, когда есть история для SMA

    while i < n - 1:
        candle_open = prices[i]
        candle_close_next = prices[i + 1]

        # ===== НОВЫЙ ЦИКЛ =====
        if len(positions) == 0:
            sma_val = _sma(prices, cfg.period, i)
            direction = 1 if candle_open > sma_val else -1
            positions.append([cfg.start_lot, direction, candle_open])
            i += 1
            continue

        # ===== ОЦЕНКА P&L =====
        total_pnl = 0.0
        for lot, direction, open_px in positions:
            total_pnl += (candle_close_next - open_px) * direction * lot * cfg.contract_size
        total_pnl -= cfg.commission_per_lot * cfg.start_lot * len(positions)

        # ===== Если в плюсе — закрываем ВЕСЬ цикл =====
        if total_pnl > 0:
            equity += total_pnl
            wins += 1
            sum_win += total_pnl
            cycles += 1
            positions = []
            equity_curve.append(equity)
            i += 1
            continue

        # ===== В минусе — ХЕДЖ =====
        if len(positions) < cfg.max_positions:
            last_dir = positions[-1][1]
            positions.append([cfg.start_lot, -last_dir, candle_close_next])
            i += 1
        else:
            # FORCE CLOSE (защита)
            equity += total_pnl
            losses += 1
            sum_loss_abs += abs(total_pnl)
            cycles += 1
            positions = []
            equity_curve.append(equity)
            i += 1

    # ===== Метрики =====
    win_rate = wins / cycles if cycles > 0 else 0.0
    avg_win = sum_win / wins if wins > 0 else 0.0
    avg_loss = sum_loss_abs / losses if losses > 0 else 1.0
    profit_factor = avg_win / avg_loss if avg_loss > 0 else 999.0
    win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

    kelly = (win_rate - (1 - win_rate)) / win_loss_ratio if (win_rate > 0 and win_loss_ratio > 0) else 0.0
    kelly_adj = kelly * 0.25

    returns = np.diff(np.array(equity_curve, dtype=float)) if len(equity_curve) > 1 else np.array([0.0])
    var_95 = float(np.percentile(returns, 5)) if len(returns) > 0 else 0.0
    std = float(np.std(returns)) if len(returns) > 1 else 0.0
    sharpe = float(np.mean(returns) / std) if std > 0 else 0.0

    peak = 0.0
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_dd:
            max_dd = dd

    return {
        'equity_curve': equity_curve,
        'total_profit': equity,
        'max_drawdown': max_dd,
        'win_rate': win_rate,
        'cycles': cycles,
        'profit_factor': profit_factor,
        'kelly_adjusted': kelly_adj,
        'var_95': var_95,
        'sharpe_ratio': sharpe,
    }


def _empty_result() -> dict:
    return {
        'equity_curve': [0.0], 'total_profit': 0.0, 'max_drawdown': 0.0,
        'win_rate': 0.0, 'cycles': 0, 'profit_factor': 0.0,
        'kelly_adjusted': 0.0, 'var_95': 0.0, 'sharpe_ratio': 0.0,
    }


def compute_metrics(equity_curve, profit, cycles):
    return {'total_profit': profit, 'cycles': cycles, 'win_rate': 0.0}