#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BOT V3 (автогенерация): SOLANA | H1
Стратегия: Свечной Хедж-Конвейер (БЕЗ мартингейла, лот 0.01)
Magic: 560695
Статистика бэктеста: WinRate 76.0%, Profit $50,482, DD $5,350
"""
import MetaTrader5 as mt5
import time, logging, sys

BOT_CONFIG = {
    "symbol": "SOLANA",
    "timeframe": mt5.TIMEFRAME_H1,
    "magic_number": 560695,
    "start_lot": 0.01,
    "max_positions": 10,
    "sma_period": 20,
    "max_equity_dd_percent": 20.0,
    "spread_filter": True,
    "max_spread_points": 30,
    "check_interval": 0.5,
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)
_last_candle_time = 0

def get_my_positions():
    return [p for p in (mt5.positions_get(symbol=BOT_CONFIG["symbol"]) or [])
            if p.magic == BOT_CONFIG["magic_number"]]

def get_cycle_profit():
    return sum(p.profit + p.swap for p in (mt5.positions_get(symbol=BOT_CONFIG["symbol"]) or [])
               if p.magic == BOT_CONFIG["magic_number"])

def check_spread():
    if not BOT_CONFIG["spread_filter"]: return True
    tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
    info = mt5.symbol_info(BOT_CONFIG["symbol"])
    if not tick or not info or info.point == 0: return True
    return ((tick.ask - tick.bid) / info.point) <= BOT_CONFIG["max_spread_points"]

def open_position(order_type, lot, comment):
    tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
    if not tick: return False
    price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
    r = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": BOT_CONFIG["symbol"],
                         "volume": lot, "type": order_type, "price": price,
                         "magic": BOT_CONFIG["magic_number"], "comment": comment, "deviation": 10})
    if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Ошибка открытия: {r.retcode if r else 'None'}"); return False
    logger.info(f"Открыто: {'BUY' if order_type == mt5.ORDER_TYPE_BUY else 'SELL'} | Lot {lot}")
    return True

def close_all_positions():
    closed = 0
    for p in mt5.positions_get(symbol=BOT_CONFIG["symbol"]) or []:
        if p.magic != BOT_CONFIG["magic_number"]: continue
        ct = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
        if not tick: continue
        price = tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask
        res = mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "position": p.ticket,
                               "symbol": BOT_CONFIG["symbol"], "volume": p.volume,
                               "type": ct, "price": price,
                               "magic": BOT_CONFIG["magic_number"], "comment": "Cycle Close", "deviation": 10})
        if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE: closed += 1
    return closed

def is_new_candle():
    global _last_candle_time
    rates = mt5.copy_rates_from_pos(BOT_CONFIG["symbol"], BOT_CONFIG["timeframe"], 0, 2)
    if not rates or len(rates) < 2: return False
    cur = rates[-1]['time']
    if cur > _last_candle_time:
        _last_candle_time = cur; return True
    return False

def get_direction_from_sma():
    period = BOT_CONFIG["sma_period"]
    rates = mt5.copy_rates_from_pos(BOT_CONFIG["symbol"], BOT_CONFIG["timeframe"], 0, period + 2)
    if not rates or len(rates) < period: return mt5.ORDER_TYPE_BUY
    closes = [r['close'] for r in rates]
    sma = sum(closes[-period:]) / period
    return mt5.ORDER_TYPE_BUY if closes[-1] > sma else mt5.ORDER_TYPE_SELL

def run_bot():
    logger.info(f"Запуск V3: {BOT_CONFIG['symbol']} | Magic {BOT_CONFIG['magic_number']}")
    if not mt5.initialize(): logger.critical("MT5 error"); return
    peak = (mt5.account_info().equity if mt5.account_info() else 0.0)
    try:
        while True:
            ai = mt5.account_info(); equity = ai.equity if ai else 0.0
            if peak > 0:
                dd = ((peak - equity) / peak) * 100
                if dd >= BOT_CONFIG["max_equity_dd_percent"]:
                    logger.warning(f"ПРОСАДКА {dd:.2f}%"); close_all_positions(); time.sleep(60); peak = (mt5.account_info().equity if mt5.account_info() else 0.0); continue
            if equity > peak: peak = equity

            my = get_my_positions()
            if not my:
                if not check_spread() or not is_new_candle():
                    time.sleep(BOT_CONFIG["check_interval"]); continue
                open_position(get_direction_from_sma(), BOT_CONFIG["start_lot"], "Entry")
                continue

            if not is_new_candle():
                time.sleep(BOT_CONFIG["check_interval"]); continue
            cp = get_cycle_profit()
            if cp > 0:
                close_all_positions(); logger.info(f"Профит ${cp:.2f} — закрыто")
            elif len(my) < BOT_CONFIG["max_positions"]:
                lt = my[-1].type
                open_position(mt5.ORDER_TYPE_SELL if lt == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                              BOT_CONFIG["start_lot"], f"Hedge {len(my)+1}")
            else:
                close_all_positions(); logger.warning(f"{BOT_CONFIG['max_positions']} поз, убыток ${cp:.2f} — FORCE CLOSE")
    except KeyboardInterrupt:
        logger.info("Стоп")
    finally:
        close_all_positions(); mt5.shutdown()

if __name__ == "__main__":
    run_bot()
