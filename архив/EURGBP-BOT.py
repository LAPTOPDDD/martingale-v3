#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MARTINGALE BOT TEMPLATE FOR PYTHON + MT5
==========================================
Универсальный бот с изоляцией через MagicNumber.
Запускай копии с разными параметрами для параллельной работы.
"""

import MetaTrader5 as mt5
import time
import logging
from datetime import datetime

# ============================================================
# ⚙️ НАСТРОЙКИ БОТА (МЕНЯТЬ В КАЖДОЙ КОПИИ!)
# ============================================================
BOT_CONFIG = {
    "symbol": "EURGBP",          # Торговый инструмент
    "timeframe": mt5.TIMEFRAME_H1, # Таймфрейм для проверки спреда и тренда
    "magic_number": 100003,      # УНИКАЛЬНЫЙ ID ДЛЯ ЭТОГО БОТА
    "start_lot": 0.01,           # Начальный лот
    "multiplier": 1.5,           # Множитель мартингейла
    "max_positions": 6,          # Максимальная глубина серии (оптимум по Safety)
    "target_profit": 12.0,       # Цель прибыли за цикл ($)
    "max_equity_dd_percent": 20.0, # Стоп по просадке equity (%)
    "spread_filter": True,       # Фильтр высокого спреда
    "max_spread_points": 30      # Макс допустимый спред
}

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(f"bot_{BOT_CONFIG['symbol']}_{BOT_CONFIG['magic_number']}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# 🔧 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def get_my_positions(symbol, magic):
    """Получает только позиции текущего бота"""
    positions = []
    for pos in mt5.positions_get(symbol=symbol):
        if pos.magic == magic:
            positions.append(pos)
    return sorted(positions, key=lambda x: x.time)

def get_cycle_profit(symbol, magic):
    """Считает текущий P&L всех позиций бота"""
    profit = 0.0
    for pos in mt5.positions_get(symbol=symbol):
        if pos.magic == magic:
            profit += pos.profit + pos.swap + pos.commission
    return profit

def check_spread(symbol, max_points):
    """Проверяет, не слишком ли высок спред"""
    tick = mt5.symbol_info_tick(symbol)
    spread = tick.ask - tick.bid
    point = mt5.symbol_info(symbol).point
    return (spread / point) <= max_points

def open_position(symbol, order_type, lot, magic, comment="Martingale"):
    """Открывает позицию с уникальным комментарием и магиком"""
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": mt5.symbol_info_tick(symbol).ask if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).bid,
        "magic": magic,
        "comment": comment,
        "deviation": 10
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"❌ Ошибка открытия: {result.retcode} - {result.comment}")
        return False
    logger.info(f"✅ Открыта позиция: {symbol} | Lot: {lot} | Magic: {magic}")
    return True

def close_all_my_positions(symbol, magic):
    """Закрывает все позиции конкретного бота"""
    closed = 0
    for pos in mt5.positions_get(symbol=symbol):
        if pos.magic == magic:
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": pos.ticket,
                "symbol": symbol,
                "volume": pos.volume,
                "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                "price": mt5.symbol_info_tick(symbol).bid if pos.type == mt5.POSITION_TYPE_BUY else mt5.symbol_info_tick(symbol).ask,
                "magic": magic,
                "comment": "Cycle Close",
                "deviation": 10
            }
            res = mt5.order_send(request)
            if res.retcode == mt5.TRADE_RETCODE_DONE:
                closed += 1
    if closed > 0:
        logger.info(f" Закрыто позиций: {closed} | Magic: {magic}")
    return closed

# ============================================================
# 🤖 ОСНОВНАЯ ЛОГИКА БОТА
# ============================================================
def run_bot():
    cfg = BOT_CONFIG
    logger.info(f"🚀 Запуск бота: {cfg['symbol']} | Magic: {cfg['magic_number']}")
    
    if not mt5.initialize():
        logger.critical("❌ Не удалось подключиться к MT5!")
        return

    peak_equity = mt5.account_info().equity
    
    try:
        while True:
            # 1. ПРОВЕРКА КРИТИЧЕСКОЙ ПРОСАДКИ
            current_equity = mt5.account_info().equity
            dd_pct = ((peak_equity - current_equity) / peak_equity) * 100
            
            if dd_pct >= cfg["max_equity_dd_percent"]:
                logger.warning(f" ДОСТИГНУТ ЛИМИТ ПРОСАДКИ: {dd_pct:.2f}%")
                close_all_my_positions(cfg["symbol"], cfg["magic_number"])
                time.sleep(60) # Пауза перед перезапуском логики
                continue
                
            if current_equity > peak_equity:
                peak_equity = current_equity

            my_pos = get_my_positions(cfg["symbol"], cfg["magic_number"])
            
            # 2. ЕСЛИ НЕТ ПОЗИЦИЙ - ОТКРЫВАЕМ НОВЫЙ ЦИКЛ
            if len(my_pos) == 0:
                if cfg["spread_filter"] and not check_spread(cfg["symbol"], cfg["max_spread_points"]):
                    time.sleep(1)
                    continue
                    
                # Простая логика входа: можно заменить на любой индикатор
                # Здесь открываем BUY, если цена выше SMA(20), иначе SELL
                rates = mt5.copy_rates_from_pos(cfg["symbol"], cfg["timeframe"], 0, 20)
                sma = sum(r['close'] for r in rates) / len(rates)
                last_close = rates[-1]['close']
                
                order_type = mt5.ORDER_TYPE_BUY if last_close > sma else mt5.ORDER_TYPE_SELL
                open_position(cfg["symbol"], order_type, cfg["start_lot"], cfg["magic_number"])
                
            # 3. МАРТИНГЕЙЛ И ЗАКРЫТИЕ
            else:
                cycle_profit = get_cycle_profit(cfg["symbol"], cfg["magic_number"])
                
                # Закрытие по цели
                if cycle_profit >= cfg["target_profit"]:
                    logger.info(f"💰 Цель достигнута: ${cycle_profit:.2f}")
                    close_all_my_positions(cfg["symbol"], cfg["magic_number"])
                    
                # Усреднение (Мартингейл)
                elif len(my_pos) < cfg["max_positions"]:
                    last_pos = my_pos[-1]
                    current_price = mt5.symbol_info_tick(cfg["symbol"]).bid
                    
                    # Шаг усреднения зависит от номера колена
                    step_multiplier = 1.5 ** (len(my_pos) - 1)
                    min_step = 100 * step_multiplier * mt5.symbol_info(cfg["symbol"]).point
                    
                    should_add = False
                    if last_pos.type == mt5.POSITION_TYPE_BUY and (last_pos.price_open - current_price) >= min_step:
                        should_add = True
                    elif last_pos.type == mt5.POSITION_TYPE_SELL and (current_price - last_pos.price_open) >= min_step:
                        should_add = True
                        
                    if should_add:
                        new_lot = round(cfg["start_lot"] * (cfg["multiplier"] ** len(my_pos)), 2)
                        # Хеджирование/усреднение против последней позиции
                        hedge_type = mt5.ORDER_TYPE_SELL if last_pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
                        open_position(cfg["symbol"], hedge_type, new_lot, cfg["magic_number"])

            time.sleep(0.5) # Защита от перегрузки API
            
    except KeyboardInterrupt:
        logger.info(" Бот остановлен пользователем")
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    run_bot()