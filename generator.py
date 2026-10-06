#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generator.py
====================================
Генератор бота V3 (исправленный).
Используется как дашбордом (dashboard_v3.py), так и тестами (test_generator.py).

Исправления (критические, найдены при реальном запуске):
  1) БЕЗОПАСНЫЕ проверки MT5-массивов (нет "if not rates" для numpy-массива)
  2) SMA считается по истории СТРОГО ДО текущей свечи (нет look-ahead bias)
  3) Лот фиксированный 0.01 (multiplier=1.0, без мартингейла)
  4) Закрытие цикла, когда ОБЩИЙ P&L > 0; иначе хедж
"""
import hashlib
import datetime as dt


# ============================================================
# ШАБЛОН БОТА (BOT_TEMPLATE)
# Все плейсхолдеры подставляются через .format(...)
# Двойные фигурные скобки {{ }} -> после format станут одинарными { }
# ============================================================
BOT_TEMPLATE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MARTINGALE BOT V3: {symbol} | TF: {timeframe}
Сгенерирован: {gen_time}
Magic Number: {magic_number}

Lot: {start_lot} (фиксированный, БЕЗ мартингейла / multiplier=1.0)
Max positions: {max_positions}  |  SMA period: {sma_period}

Стратегия V3 (по свечам):
  - Пришла свеча -> открыли {start_lot} (по SMA = история ДО свечи)
  - Свеча закрылась: P&L>0 -> ЗАКРЫТЬ ВСЁ, иначе ХЕДЖ
  - Лот ВСЕГДА {start_lot}
"""
import time
import logging
import sys
import MetaTrader5 as mt5

BOT_CONFIG = {{
    "symbol": "{symbol}",
    "timeframe": {tf_code},
    "magic_number": {magic_number},
    "start_lot": {start_lot},
    "max_positions": {max_positions},
    "sma_period": {sma_period},
    "max_spread_points": 30,
    "check_interval": 0.5,
    "max_equity_dd_percent": 15.0,
}}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════
# БЕЗОПАСНАЯ проверка MT5-массивов (исправлено!)
#   Нельзя писать "if not rates" для numpy-массива -> ValueError
# ═════════════════════════════════════════════════════════
def _has_enough(rates, n):
    """Возвращает True, если массив не None и содержит >= n элементов."""
    return rates is not None and len(rates) >= n


def get_my_positions():
    positions = mt5.positions_get(symbol=BOT_CONFIG["symbol"])
    if not _has_enough(positions, 1):
        return []
    return [p for p in positions if p.magic == BOT_CONFIG["magic_number"]]


def get_cycle_profit():
    profit = 0.0
    for pos in get_my_positions():
        fee = getattr(pos, "fee", 0.0) or 0.0
        profit += pos.profit + pos.swap + fee
    return profit


def check_spread():
    tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
    info = mt5.symbol_info(BOT_CONFIG["symbol"])
    if tick is None or info is None:
        return False
    if info.point <= 0:
        return True
    return ((tick.ask - tick.bid) / info.point) <= BOT_CONFIG["max_spread_points"]


def open_position(order_type, lot, comment="Entry"):
    tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
    if tick is None:
        return False
    price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
    request = {{
        "action": mt5.TRADE_ACTION_DEAL, "symbol": BOT_CONFIG["symbol"],
        "volume": lot, "type": order_type, "price": price,
        "magic": BOT_CONFIG["magic_number"], "comment": comment, "deviation": 10,
    }}
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        rc = result.retcode if result is not None else "NONE"
        logger.error(f"Ошибка открытия: {{rc}}")
        return False
    side = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
    logger.info(f"Открыто: {{side}} | Lot: {{lot}} | {{comment}}")
    return True


def close_all_positions():
    closed = 0
    for pos in get_my_positions():
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
        if tick is None:
            continue
        price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
        request = {{
            "action": mt5.TRADE_ACTION_DEAL, "position": pos.ticket,
            "symbol": BOT_CONFIG["symbol"], "volume": pos.volume,
            "type": close_type, "price": price,
            "magic": BOT_CONFIG["magic_number"], "comment": "Cycle Close", "deviation": 10,
        }}
        res = mt5.order_send(request)
        if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
    return closed


# ═════════════════════════════════════════════════════════
# Работа по свечам
# ═════════════════════════════════════════════════════════
_last_candle_time = 0

def is_new_candle():
    global _last_candle_time
    rates = mt5.copy_rates_from_pos(BOT_CONFIG["symbol"], BOT_CONFIG["timeframe"], 0, 2)
    if not _has_enough(rates, 2):   # ✅ БЕЗОПАСНО (исправлено)
        return False
    ct = rates[-1]["time"]
    if ct > _last_candle_time:
        globals()["_last_candle_time"] = ct
        return True
    return False


def get_direction_from_sma(period):
    """
    SMA считается по истории СТРОГО ДО текущей свечи (нет look-ahead).
    Загружаем period+1 баров: последний - текущая формирующаяся свеча,
    исключаем его -> берём предыдущие `period` баров.
    """
    rates = mt5.copy_rates_from_pos(BOT_CONFIG["symbol"], BOT_CONFIG["timeframe"], 0, period + 1)
    if not _has_enough(rates, period + 1):
        return 1
    closes = [float(r["close"]) for r in rates]
    window = closes[-(period + 1):-1] if len(closes) >= period + 1 else closes[:-1]
    if not window:
        return 1
    sma_val = sum(window) / len(window)
    return 1 if closes[-1] > sma_val else -1


# ═════════════════════════════════════════════════════════
# Основной цикл (логика V3)
# ═════════════════════════════════════════════════════════
def run_bot():
    cfg = BOT_CONFIG
    logger.info(f"Запуск V3: {{cfg['symbol']}} | Magic {{cfg['magic_number']}}")
    logger.info(f"Lot: {{cfg['start_lot']}} (фиксированный, БЕЗ мартингейла)")
    if not mt5.initialize():
        logger.critical(f"MT5 error: {{mt5.last_error()}}")
        return
    peak = (mt5.account_info().equity if mt5.account_info() else 0.0) or 0.0
    cycle_count = 0
    try:
        while True:
            acc = mt5.account_info()
            equity = acc.equity if acc else 0.0
            # Аварийный стоп по просадке депозита
            if peak > 0 and equity > 0:
                dd = ((peak - equity) / peak) * 100
                if dd >= cfg["max_equity_dd_percent"]:
                    logger.warning(f"ПРОСАДКА {{dd:.2f}}%")
                    close_all_positions()
                    time.sleep(60)
                    peak = equity
                    continue
            if equity > peak:
                peak = equity

            my_pos = get_my_positions()

            # ═══ НОВЫЙ ЦИКЛ ═══
            if len(my_pos) == 0:
                if not check_spread():
                    time.sleep(1); continue
                if not is_new_candle():
                    time.sleep(0.1); continue
                direction = get_direction_from_sma(cfg["sma_period"])
                ot = mt5.ORDER_TYPE_BUY if direction == 1 else mt5.ORDER_TYPE_SELL
                if open_position(ot, cfg["start_lot"], "Entry"):
                    cycle_count += 1
                    logger.info(f"Цикл #{{cycle_count}}")

            # ═══ ЕСТЬ ПОЗИЦИИ — ЖДЁМ ЗАКРЫТИЯ СВЕЧИ ═══
            else:
                if not is_new_candle():
                    time.sleep(0.05); continue
                cp = get_cycle_profit()

                # ✅ P&L > 0 -> ЗАКРЫТЬ ВСЁ
                if cp > 0:
                    logger.info(f"Профит ${{cp:.2f}} -> закрыть цикл")
                    close_all_positions()
                    continue

                # ❌ УБЫТОК -> ХЕДЖ
                if len(my_pos) < cfg["max_positions"]:
                    last = my_pos[-1]
                    hedge = mt5.ORDER_TYPE_SELL if last.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
                    open_position(hedge, cfg["start_lot"], "Hedge")
                    logger.info(f"Хедж #{{len(my_pos)+1}}")
                else:
                    logger.warning(f"Лимит {{cfg['max_positions']}}, убыток ${{cp:.2f}} -> FORCE CLOSE")
                    close_all_positions()

            time.sleep(cfg["check_interval"])
    except KeyboardInterrupt:
        logger.info("Остановлен")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    run_bot()
'''


TF_MAP = {
    "M1": "mt5.TIMEFRAME_M1", "M5": "mt5.TIMEFRAME_M5", "M15": "mt5.TIMEFRAME_M15",
    "M30": "mt5.TIMEFRAME_M30", "H1": "mt5.TIMEFRAME_H1", "H4": "mt5.TIMEFRAME_H4",
    "D1": "mt5.TIMEFRAME_D1",
}


def generate_bot_code(symbol: str, timeframe: str, **kwargs) -> tuple:
    """
    Генерирует исправленный бот V3 (безопасные проверки массивов, SMA без look-ahead).
    Возвращает (code: str, filename: str).
    """
    start_lot = kwargs.get("start_lot", 0.01)
    max_positions = kwargs.get("max_positions", 10)
    sma_period = kwargs.get("sma_period", 20)

    seed = f"{symbol}{timeframe}V3{dt.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    magic_number = int(hashlib.md5(seed.encode()).hexdigest()[:6], 16) % 900_000 + 100_000

    tf_code = TF_MAP.get(timeframe, "mt5.TIMEFRAME_H1")
    safe_symbol = symbol.replace(" ", "_").replace("/", "-")
    filename = f"BOT-V3-{safe_symbol}-{timeframe}-hedge.py"

    code = BOT_TEMPLATE.format(
        symbol=symbol,
        timeframe=timeframe,
        gen_time=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        magic_number=magic_number,
        start_lot=start_lot,
        max_positions=max_positions,
        sma_period=sma_period,
        tf_code=tf_code,
    )
    return code, filename


if __name__ == "__main__":
    # Быстрая проверка шаблона (без MT5)
    code, fn = generate_bot_code("CARDANO", "H1")
    print(f"OK: {fn} ({len(code.splitlines())} lines)")
