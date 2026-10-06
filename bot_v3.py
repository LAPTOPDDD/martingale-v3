#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot_v3.py
====================================
MARTINGALE BOT V3 — БЕЗ МАРТИНГЕЙЛА (multiplier=1.0, лот всегда 0.01)
Использует ТОЧНО те же правила, что и бэктест (strategy_core.simulate_v3):

  ✅ Пришла свеча -> открыли 0.01 (по SMA)
  ✅ Свеча закрылась:
        - P&L > 0  -> ЗАКРЫЛИ ВСЁ (забрали профит)
        - P&L <= 0 -> ХЕДЖ (противоположная сторона, тоже 0.01)
  ✅ 10 позиций и всё в минусе -> FORCE CLOSE (защита)
  ✅ Лот ВСЕГДА 0.01

ВСЕ проверки MT5-массивов - БЕЗОПАСНЫЕ (исправлена ошибка
"ValueError: truth value of array...").
"""

import time
import logging
import sys
from datetime import datetime

try:
    import MetaTrader5 as mt5
except Exception as e:  # pragma: no cover
    print(f"[FATAL] MetaTrader5 недоступен: {e}")
    sys.exit(1)


# ============================================================
# КОНФИГУРАЦИЯ (поменяйте под свой инструмент)
# ============================================================
BOT_CONFIG = {
    "symbol": "CARDANO",           # <-- ваш инструмент
    "timeframe": mt5.TIMEFRAME_H1, # <-- таймфрейм (H1)
    "magic_number": 100028,
    "start_lot": 0.01,
    "max_positions": 10,           # защита
    "sma_period": 20,
    "max_spread_points": 30,
    "check_interval": 0.5,         # секунд между проверками
    "max_equity_dd_percent": 15.0, # аварийный стоп по депозиту
}


# ============================================================
# ЛОГИРОВАНИЕ
# ============================================================
log_file = f"bot_{BOT_CONFIG['symbol']}_{BOT_CONFIG['magic_number']}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ============================================================
# БЕЗОПАСНЫЕ ХЕЛПЕРЫ ДЛЯ MT5-МАССИВОВ
# ============================================================
def _has_enough(rates, n: int) -> bool:
    """Проверяет массив от MT5: не None и длина >= n.
    Исправляет ошибку 'truth value of array is ambiguous'."""
    return rates is not None and len(rates) >= n


def get_my_positions():
    """Свои открытые позиции (по magic_number). Всегда возвращает список."""
    positions = mt5.positions_get(symbol=BOT_CONFIG["symbol"])
    if not _has_enough(positions, 1):
        return []
    return [p for p in positions if p.magic == BOT_CONFIG["magic_number"]]


def get_cycle_profit() -> float:
    """Общий P&L всех своих позиций (profit + swap + fee)."""
    profit = 0.0
    for pos in get_my_positions():
        fee = getattr(pos, "fee", 0.0) or 0.0
        profit += pos.profit + pos.swap + fee
    return profit


def check_spread() -> bool:
    """True, если спред в допустимых пределах."""
    tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
    info = mt5.symbol_info(BOT_CONFIG["symbol"])
    if tick is None or info is None:
        return False
    point = info.point
    if point <= 0:
        return True
    spread_points = (tick.ask - tick.bid) / point
    return spread_points <= BOT_CONFIG["max_spread_points"]


def open_position(order_type, lot: float, comment: str = "Entry") -> bool:
    tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
    if tick is None:
        return False
    price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": BOT_CONFIG["symbol"],
        "volume": lot,
        "type": order_type,
        "price": price,
        "magic": BOT_CONFIG["magic_number"],
        "comment": comment,
        "deviation": 10,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        rc = result.retcode if result is not None else "NONE"
        logger.error(f"Ошибка открытия: {rc}")
        return False
    side = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
    logger.info(f"Открыто: {side} | Lot: {lot} | {comment}")
    return True


def close_all_positions() -> int:
    closed = 0
    for pos in get_my_positions():
        close_type = (
            mt5.ORDER_TYPE_SELL
            if pos.type == mt5.POSITION_TYPE_BUY
            else mt5.ORDER_TYPE_BUY
        )
        tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
        if tick is None:
            continue
        price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": pos.ticket,
            "symbol": BOT_CONFIG["symbol"],
            "volume": pos.volume,
            "type": close_type,
            "price": price,
            "magic": BOT_CONFIG["magic_number"],
            "comment": "Cycle Close",
            "deviation": 10,
        }
        res = mt5.order_send(request)
        if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
    return closed


# ============================================================
# РАБОТА ПО СВЕЧАМ (как в бэктесте)
# ============================================================
_last_candle_time = 0


def is_new_candle() -> bool:
    """True, если закрылась новая свеча (обновилось время бара)."""
    global _last_candle_time
    rates = mt5.copy_rates_from_pos(BOT_CONFIG["symbol"], BOT_CONFIG["timeframe"], 0, 2)
    if not _has_enough(rates, 2):   # <-- БЕЗОПАСНАЯ проверка (исправлено!)
        return False
    current_candle_time = rates[-1]["time"]
    if current_candle_time > _last_candle_time:
        _last_candle_time = current_candle_time
        return True
    return False


def get_direction_from_sma(period: int = 20) -> int:
    """
    Направление по SMA: +1 BUY, -1 SELL.
    SMA считается по истории СТРОГО ДО текущей (формирующейся) свечи -
    ровно как в бэктесте (strategy_core.simulate_v3). Никакого look-ahead.
    """
    # period+1: последний бар = текущая незавершённая свеча (исключаем её)
    rates = mt5.copy_rates_from_pos(
        BOT_CONFIG["symbol"], BOT_CONFIG["timeframe"], 0, period + 1
    )
    if not _has_enough(rates, period + 1):   # <-- БЕЗОПАСНАЯ проверка
        return 1
    closes = [float(r["close"]) for r in rates]
    # Берём `period` баров, предшествующих текущему (исключаем closes[-1])
    window = closes[-(period + 1):-1] if len(closes) >= period + 1 else closes[:-1]
    if not window:
        return 1
    sma_val = sum(window) / len(window)
    last = closes[-1]  # цена открытия текущей свечи
    return 1 if last > sma_val else -1


# ============================================================
# ОСНОВНОЙ ЦИКЛ (логика V3)
# ============================================================
def run_bot():
    cfg = BOT_CONFIG
    logger.info("=" * 60)
    logger.info(f"Запуск V3: {cfg['symbol']} | Magic {cfg['magic_number']}")
    logger.info(f"Lot: {cfg['start_lot']} (фиксированный, БЕЗ мартингейла)")
    logger.info(f"Max positions: {cfg['max_positions']}")
    logger.info("Стратегия: 1 свеча = 1 действие | P&L>0 -> закрыть | иначе хедж")
    logger.info("=" * 60)

    if not mt5.initialize():
        logger.critical(f"Ошибка MT5: {mt5.last_error()}")
        return

    account = mt5.account_info()
    if account is not None:
        logger.info(f"Счет: {account.login} | {account.balance} {account.currency}")

    peak_equity = (account.equity if account is not None else 0.0) or 0.0
    cycle_count = 0

    try:
        while True:
            account = mt5.account_info()
            current_equity = account.equity if account is not None else 0.0

            # ---- Аварийный стоп по просадке депозита ----
            if peak_equity > 0 and current_equity > 0:
                dd_pct = ((peak_equity - current_equity) / peak_equity) * 100
                if dd_pct >= cfg["max_equity_dd_percent"]:
                    logger.warning(f"ПРОСАДКА {dd_pct:.2f}%! Закрываю ВСЁ и пауза 60с")
                    close_all_positions()
                    time.sleep(60)
                    peak_equity = current_equity
                    continue
            if current_equity > peak_equity:
                peak_equity = current_equity

            my_pos = get_my_positions()

            # ═══════════════════════════════════════════════
            # НЕТ ПОЗИЦИЙ -> НОВЫЙ ЦИКЛ
            # ═══════════════════════════════════════════════
            if len(my_pos) == 0:
                if not check_spread():
                    time.sleep(1)
                    continue
                if not is_new_candle():
                    time.sleep(0.1)
                    continue

                direction = get_direction_from_sma(cfg["sma_period"])
                order_type = mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL
                if open_position(order_type, cfg["start_lot"], "Entry"):
                    cycle_count += 1
                    logger.info(f"Цикл #{cycle_count} | start")

            # ═══════════════════════════════════════════════
            # ЕСТЬ ПОЗИЦИИ -> ЖДЁМ ЗАКРЫТИЯ СВЕЧИ
            # ═══════════════════════════════════════════════
            else:
                if not is_new_candle():
                    time.sleep(0.05)
                    continue

                cycle_profit = get_cycle_profit()

                # ✅ ВАШЕ ПРАВИЛО: P&L > 0 -> ЗАКРЫВАЕМ ВСЁ
                if cycle_profit > 0:
                    logger.info(f"Профит ${cycle_profit:.2f} -> закрываем цикл")
                    close_all_positions()
                    continue

                # ❌ УБЫТОК -> ХЕДЖ (меняем направление)
                if len(my_pos) < cfg["max_positions"]:
                    last_pos = my_pos[-1]
                    hedge_type = (
                        mt5.ORDER_TYPE_SELL
                        if last_pos.type == mt5.POSITION_TYPE_BUY
                        else mt5.ORDER_TYPE_BUY
                    )
                    open_position(hedge_type, cfg["start_lot"], "Hedge")
                    logger.info(f"Хедж #{len(my_pos)+1}")
                else:
                    # 10 позиций и всё в минусе -> FORCE CLOSE (защита)
                    logger.warning(
                        f"Лимит {cfg['max_positions']} позиций, "
                        f"убыток ${cycle_profit:.2f} -> FORCE CLOSE"
                    )
                    close_all_positions()

            time.sleep(cfg["check_interval"])

    except KeyboardInterrupt:
        logger.info("Бот остановлен (Ctrl+C)")
    except Exception as e:  # pragma: no cover
        logger.error(f"Ошибка: {e}")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    print("=" * 60)
    print(f"MARTINGALE V3: {BOT_CONFIG['symbol']}")
    print(f"Magic: {BOT_CONFIG['magic_number']}")
    print("Lot: фиксированный 0.01 (без мартингейла)")
    print("=" * 60)
    print("Для остановки нажмите Ctrl+C\n")
    run_bot()
