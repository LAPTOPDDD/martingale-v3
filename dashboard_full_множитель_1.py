#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MARTINGALE DASHBOARD - Полный сканер MT5
Сканирует все инструменты за N месяцев, фильтрует лучшие,
при клике строит кривую эквити.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import MetaTrader5 as mt5
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional
import hashlib

# ============================================================
# ГЕНЕРАТОР БОТА
# ============================================================
def generate_bot_code(symbol: str, timeframe: str, start_lot: float, multiplier: float,
                      max_positions: int, win_rate: float, total_profit: float,
                      max_drawdown: float, safety_score: float) -> str:
    """Генерирует код бота для MT5 с уникальным маджиком"""

    # Уникальный маджик на основе имени + таймфрейма
    magic_seed = f"{symbol}{timeframe}{datetime.now().strftime('%Y%m%d%H%M%S')}"
    magic_number = int(hashlib.md5(magic_seed.encode()).hexdigest()[:6], 16) % 900000 + 100000

    # Маппинг таймфреймов для кода
    tf_map = {
        "M1": "mt5.TIMEFRAME_M1", "M5": "mt5.TIMEFRAME_M5",
        "M15": "mt5.TIMEFRAME_M15", "M30": "mt5.TIMEFRAME_M30",
        "H1": "mt5.TIMEFRAME_H1", "H4": "mt5.TIMEFRAME_H4",
        "D1": "mt5.TIMEFRAME_D1",
    }
    tf_code = tf_map.get(timeframe, "mt5.TIMEFRAME_H1")

    # Имя файла
    safe_symbol = symbol.replace(" ", "_").replace("/", "-")
    filename = f"BOT-{safe_symbol}-{timeframe}-lot{start_lot}-x{multiplier}-d{max_positions}.py"

    code = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
MARTINGALE BOT: {symbol} | TF: {timeframe}
============================================================
Сгенерирован: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Magic Number: {magic_number}

Параметры:
  Symbol:          {symbol}
  Timeframe:       {timeframe}
  Start Lot:       {start_lot}
  Multiplier:      {multiplier}
  Max Positions:   {max_positions}

Статистика (на момент генерации):
  Win Rate:        {win_rate*100:.1f}%
  Total Profit:    ${total_profit:,.0f}
  Max Drawdown:    ${max_drawdown:,.0f}
  Safety Score:    {safety_score:.4f}

ЗАПУСК:
  python {filename}
============================================================
"""

import MetaTrader5 as mt5
import time
import logging
import sys
from datetime import datetime

# ============================================================
# КОНФИГУРАЦИЯ БОТА
# ============================================================
BOT_CONFIG = {{
    "symbol": "{symbol}",
    "timeframe": {tf_code},
    "magic_number": {magic_number},
    "start_lot": {start_lot},
    "multiplier": {multiplier},
    "max_positions": {max_positions},
    "target_profit": {max(total_profit / 100, 1.0):.2f},
    "max_equity_dd_percent": 15.0,
    "spread_filter": True,
    "max_spread_points": 30,
    "check_interval": 0.5,
}}

# ============================================================
# ЛОГИРОВАНИЕ
# ============================================================
log_file = f"bot_{{BOT_CONFIG['symbol']}}_{{BOT_CONFIG['magic_number']}}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def get_my_positions():
    positions = []
    for pos in mt5.positions_get(symbol=BOT_CONFIG["symbol"]):
        if pos.magic == BOT_CONFIG["magic_number"]:
            positions.append(pos)
    return sorted(positions, key=lambda x: x.time)

def get_cycle_profit():
    profit = 0.0
    positions = mt5.positions_get(symbol=BOT_CONFIG["symbol"])
    if positions is None:
        return 0.0
    for pos in positions:
        if pos.magic == BOT_CONFIG["magic_number"]:
            fee = getattr(pos, 'fee', 0.0) or 0.0
            profit += pos.profit + pos.swap + fee
    return profit

def check_spread():
    tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
    if tick is None:
        return False
    spread = tick.ask - tick.bid
    point = mt5.symbol_info(BOT_CONFIG["symbol"]).point
    if point == 0:
        return True
    return (spread / point) <= BOT_CONFIG["max_spread_points"]

def open_position(order_type, lot, comment="Martingale"):
    tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
    if tick is None:
        return False
    price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
    request = {{
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": BOT_CONFIG["symbol"],
        "volume": lot,
        "type": order_type,
        "price": price,
        "magic": BOT_CONFIG["magic_number"],
        "comment": comment,
        "deviation": 10
    }}
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Ошибка открытия: {{result.retcode}} - {{result.comment}}")
        return False
    logger.info(f"Открыта позиция: {{BOT_CONFIG['symbol']}} | Lot: {{lot}} | Type: {{'BUY' if order_type == mt5.ORDER_TYPE_BUY else 'SELL'}}")
    return True

def close_all_positions():
    closed = 0
    positions = mt5.positions_get(symbol=BOT_CONFIG["symbol"])
    if positions is None:
        return 0
    for pos in positions:
        if pos.magic == BOT_CONFIG["magic_number"]:
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
            if tick is None:
                continue
            price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
            request = {{
                "action": mt5.TRADE_ACTION_DEAL,
                "position": pos.ticket,
                "symbol": BOT_CONFIG["symbol"],
                "volume": pos.volume,
                "type": close_type,
                "price": price,
                "magic": BOT_CONFIG["magic_number"],
                "comment": "Cycle Close",
                "deviation": 10
            }}
            res = mt5.order_send(request)
            if res.retcode == mt5.TRADE_RETCODE_DONE:
                closed += 1
    if closed > 0:
        logger.info(f"Закрыто позиций: {{closed}}")
    return closed

def get_lot_for_position(position_index):
    """Рассчитывает лот для позиции с учетом множителя"""
    lot = BOT_CONFIG["start_lot"] * (BOT_CONFIG["multiplier"] ** position_index)
    return round(lot, 2)

# ============================================================
# ОСНОВНАЯ ЛОГИКА
# ============================================================
def run_bot():
    cfg = BOT_CONFIG
    logger.info(f"Запуск бота: {{cfg['symbol']}} | Magic: {{cfg['magic_number']}}")
    logger.info(f"Параметры: lot={{cfg['start_lot']}}, mult={{cfg['multiplier']}}, max_pos={{cfg['max_positions']}}")

    if not mt5.initialize():
        logger.critical(f"Ошибка MT5: {{mt5.last_error()}}")
        return

    account = mt5.account_info()
    logger.info(f"Счет: {{account.login}} | Баланс: {{account.balance}} {{account.currency}}")

    peak_equity = mt5.account_info().equity
    cycle_count = 0
    last_candle_time = 0  # Время последней обработанной свечи

    # Таймфрейм в секундах для проверки закрытия
    tf_seconds = {{
        mt5.TIMEFRAME_M1: 60, mt5.TIMEFRAME_M5: 300,
        mt5.TIMEFRAME_M15: 900, mt5.TIMEFRAME_M30: 1800,
        mt5.TIMEFRAME_H1: 3600, mt5.TIMEFRAME_H4: 14400,
    }}
    candle_period = tf_seconds.get(cfg["timeframe"], 3600)

    def is_new_candle():
        """Проверяет, закрылась ли новая свеча"""
        nonlocal last_candle_time
        rates = mt5.copy_rates_from_pos(cfg["symbol"], cfg["timeframe"], 0, 2)
        if rates is None or len(rates) < 2:
            return False
        current_candle_time = rates[-1]['time']
        if current_candle_time > last_candle_time:
            last_candle_time = current_candle_time
            return True
        return False

    def get_candle_result():
        """Возвращает результат последней закрытой свечи: 1=Buy win, -1=Sell win, 0=nothing"""
        rates = mt5.copy_rates_from_pos(cfg["symbol"], cfg["timeframe"], 0, 2)
        if rates is None or len(rates) < 2:
            return 0
        prev = rates[-2]
        # Свеча закрылась выше открытия = бычья, ниже = медвежья
        if prev['close'] > prev['open']:
            return 1  # Buy свеча
        elif prev['close'] < prev['open']:
            return -1  # Sell свеча
        return 0

    try:
        while True:
            current_equity = mt5.account_info().equity
            if current_equity is None:
                time.sleep(1)
                continue

            # ПРОСАДКА
            dd_pct = ((peak_equity - current_equity) / peak_equity) * 100 if peak_equity > 0 else 0
            if dd_pct >= cfg["max_equity_dd_percent"]:
                logger.warning(f"ПРОСАДКА {{dd_pct:.2f}}% >= {{cfg['max_equity_dd_percent']}}%. Закрытие!")
                close_all_positions()
                time.sleep(60)
                peak_equity = mt5.account_info().equity
                continue

            if current_equity > peak_equity:
                peak_equity = current_equity

            my_pos = get_my_positions()

            # НЕТ ПОЗИЦИЙ -> НОВЫЙ ЦИКЛ
            if len(my_pos) == 0:
                if cfg["spread_filter"] and not check_spread():
                    time.sleep(1)
                    continue

                # Вход по SMA
                rates = mt5.copy_rates_from_pos(cfg["symbol"], cfg["timeframe"], 0, 20)
                if rates is None or len(rates) < 20:
                    time.sleep(1)
                    continue

                sma = sum(r['close'] for r in rates) / len(rates)
                last_close = rates[-1]['close']

                order_type = mt5.ORDER_TYPE_BUY if last_close > sma else mt5.ORDER_TYPE_SELL
                if open_position(order_type, cfg["start_lot"]):
                    cycle_count += 1
                    logger.info(f"Цикл #{{cycle_count}} | Начало | Тип: {{'BUY' if order_type == mt5.ORDER_TYPE_BUY else 'SELL'}}")

            # ЕСТЬ ПОЗИЦИИ -> МАРТИНГЕЙЛ / ЗАКРЫТИЕ
            else:
                cycle_profit = get_cycle_profit()

                # === ГЛАВНАЯ ЛОГИКА: ЗАКРЫТИЕ НА СВЕЧКЕ ===
                # Если пришла новая свеча - проверяем результат
                if is_new_candle():
                    candle_result = get_candle_result()
                    num_positions = len(my_pos)
                    first_pos_type = my_pos[0].type  # 0=BUY, 1=SELL

                    # 1 ПОЗИЦИЯ: закрываем если свеча в нашу сторону
                    if num_positions == 1:
                        if (first_pos_type == mt5.POSITION_TYPE_BUY and candle_result == 1) or \\
                           (first_pos_type == mt5.POSITION_TYPE_SELL and candle_result == -1):
                            if cycle_profit > 0:
                                logger.info(f"1 поза + свеча в нашу сторону: ${{cycle_profit:.2f}}")
                                close_all_positions()
                                continue

                    # ГРУППА ПОЗИЦИЙ: закрываем если группа в плюсе на новой свече
                    else:
                        if cycle_profit > 0:
                            logger.info(f"Группа ({{num_positions}} поз) в плюсе: ${{cycle_profit:.2f}}")
                            close_all_positions()
                            continue

                # Закрытие по цели (дополнительная страховка)
                if cycle_profit >= cfg["target_profit"]:
                    logger.info(f"ЦЕЛЬ: ${{cycle_profit:.2f}} >= ${{cfg['target_profit']}}")
                    close_all_positions()

                # Усреднение
                elif len(my_pos) < cfg["max_positions"]:
                    last_pos = my_pos[-1]
                    current_price = mt5.symbol_info_tick(cfg["symbol"]).bid
                    point = mt5.symbol_info(cfg["symbol"]).point

                    step_multiplier = cfg["multiplier"] ** (len(my_pos) - 1)
                    min_step = 50 * step_multiplier * point

                    should_add = False
                    if last_pos.type == mt5.POSITION_TYPE_BUY and (last_pos.price_open - current_price) >= min_step:
                        should_add = True
                    elif last_pos.type == mt5.POSITION_TYPE_SELL and (current_price - last_pos.price_open) >= min_step:
                        should_add = True

                    if should_add:
                        new_lot = get_lot_for_position(len(my_pos))
                        hedge_type = mt5.ORDER_TYPE_SELL if last_pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
                        open_position(hedge_type, new_lot)
                        logger.info(f"Усреднение #{{len(my_pos)+1}} | Lot: {{new_lot}}")

            time.sleep(0.5)

    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {{e}}")
    finally:
        mt5.shutdown()
        logger.info("MT5 отключен")

# ============================================================
# ТОЧКА ВХОДА
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print(f"MARTINGALE BOT: {{BOT_CONFIG['symbol']}}")
    print(f"Magic: {{BOT_CONFIG['magic_number']}}")
    print(f"Timeframe: {{BOT_CONFIG['timeframe']}}")
    print("=" * 60)
    print("Для остановки нажмите Ctrl+C")
    print()
    run_bot()
'''
    return code, filename

# ============================================================
# НАСТРОЙКИ СТРАНИЦЫ
# ============================================================
st.set_page_config(page_title="Martingale Scanner Dashboard", layout="wide")
st.title("📈 Martingale Scanner - MT5 Live")

# ============================================================
# КОНФИГУРАЦИЯ СТРАТЕГИИ
# ============================================================
@dataclass
class StrategyConfig:
    start_lot: float = 0.01
    multiplier: float = 1.0
    max_positions: int = 10

CFG = StrategyConfig()

# ============================================================
# ПОДКЛЮЧЕНИЕ К MT5
# ============================================================
@st.cache_resource
def connect_mt5():
    if not mt5.initialize():
        return False, str(mt5.last_error())
    info = mt5.account_info()
    if info is None:
        mt5.shutdown()
        return False, "Нет доступа к MT5"
    return True, {
        "login": info.login,
        "balance": info.balance,
        "currency": info.currency,
        "server": info.server,
        "company": info.company
    }

ok, data = connect_mt5()
if not ok:
    st.error(f"❌ MT5 не подключен: {data}")
    st.stop()

st.sidebar.success(
    f"✅ MT5 подключен\n"
    f"👤 {data['login']}\n"
    f"💰 {data['balance']:,.2f} {data['currency']}\n"
    f"🖥 {data['server']}"
)

# ============================================================
# ЯДРО БЭКТЕСТА - ВЫСТАВЛЯЕТ КРИВУЮ ЭКВИТИ
# ============================================================
def run_backtest_equity(prices: List[float], cfg: StrategyConfig, contract_size: float = 100000):
    """
    Прогоняет мартингейл и возвращает:
    - equity_curve (список значений эквити)
    - метрики: profit, max_dd, win_rate, cycles, safety_score
    """
    equity_curve = [0.0]
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    profit = 0.0
    wins = 0
    cycles = 0
    i = 0

    while i < len(prices) - 1:
        positions = []  # (volume, direction, open_price)
        closed = False

        entry_price = prices[i]
        lot = cfg.start_lot
        direction = 1
        positions.append((lot, direction, entry_price))
        i += 1

        while i < len(prices) and len(positions) <= cfg.max_positions and not closed:
            current_price = prices[i]

            total_pnl = 0.0
            for vol, dirn, open_px in positions:
                total_pnl += (current_price - open_px) * dirn * vol * contract_size

            if total_pnl > 0:
                equity += total_pnl
                profit += total_pnl
                wins += 1
                closed = True
                break

            if len(positions) >= cfg.max_positions:
                equity += total_pnl
                profit += total_pnl
                closed = True
                break

            sum_vol = sum(v for v, _, _ in positions)
            new_lot = round(sum_vol * cfg.multiplier, 2)
            positions.append((new_lot, -direction, current_price))
            i += 1

        cycles += 1
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
        equity_curve.append(equity)

        if not closed:
            i += 1

    win_rate = wins / cycles if cycles > 0 else 0
    safety = (win_rate) / (max_dd / 1000 + 1) if cycles > 0 else 0

    return {
        'equity_curve': equity_curve,
        'total_profit': profit,
        'max_drawdown': max_dd,
        'win_rate': win_rate,
        'cycles': cycles,
        'safety_score': safety
    }

# ============================================================
# ЗАГРУЗКА ДАННЫХ ИЗ MT5
# ============================================================
TF_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

def scan_all_symbols(months: int, timeframes: List[str]):
    """Сканирует все видимые символы MT5 за N месяцев на выбранных ТФ"""
    date_to = datetime.now()
    date_from = date_to - timedelta(days=months * 30)

    all_symbols = mt5.symbols_get()
    if all_symbols is None:
        return pd.DataFrame(), {}

    visible = [s.name for s in all_symbols if s.visible]
    results = []
    equity_data = {}

    total_tasks = len(visible) * len(timeframes)
    progress = st.progress(0, text="Сканирование...")
    counter = 0

    for symbol in visible:
        info = mt5.symbol_info(symbol)
        if info is None:
            continue
        contract_size = info.trade_contract_size or 100000

        for tf_str in timeframes:
            counter += 1
            progress.progress(
                counter / total_tasks,
                text=f"[{counter}/{total_tasks}] {symbol} | {tf_str}"
            )

            tf = TF_MAP.get(tf_str)
            if tf is None:
                continue

            rates = mt5.copy_rates_range(symbol, tf, date_from, date_to)
            if rates is None or len(rates) < 200:
                continue

            prices = [float(r['close']) for r in rates]
            bt = run_backtest_equity(prices, CFG, contract_size)

            results.append({
                'symbol': symbol,
                'timeframe': tf_str,
                'cycles': bt['cycles'],
                'win_rate': bt['win_rate'],
                'total_profit': bt['total_profit'],
                'max_drawdown': bt['max_drawdown'],
                'safety_score': bt['safety_score'],
                'bars': len(prices)
            })
            equity_data[f"{symbol}_{tf_str}"] = bt['equity_curve']

    progress.empty()
    return pd.DataFrame(results), equity_data

# ============================================================
# БОКОВАЯ ПАНЕЛЬ
# ============================================================
st.sidebar.header("⚙️ Параметры скана")

months = st.sidebar.selectbox("Период (месяцев):", [1, 2, 3, 6, 12], index=2)

st.sidebar.subheader("Таймфреймы:")
tf_options = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
tf_selected = {}
col_a, col_b = st.sidebar.columns(2)
for i, tf in enumerate(tf_options):
    with col_a if i % 2 == 0 else col_b:
        tf_selected[tf] = st.checkbox(tf, value=(tf in ["M15", "H1"]))

selected_tfs = [tf for tf, checked in tf_selected.items() if checked]

if not selected_tfs:
    st.sidebar.warning("Выберите хотя бы один ТФ")
    st.stop()

st.sidebar.caption(f"Выбрано: {', '.join(selected_tfs)}")

st.sidebar.subheader("Фильтры")
min_profit = st.sidebar.number_input("Мин. прибыль ($):", value=0.0, step=100.0)
max_dd = st.sidebar.number_input("Макс. просадка ($):", value=50000.0, step=1000.0)
min_cycles = st.sidebar.slider("Мин. циклов:", 10, 5000, 100)
min_winrate = st.sidebar.slider("Мин. Win Rate (%):", 0.0, 100.0, 50.0, 1.0) / 100.0

run_scan = st.sidebar.button("🔍 Запустить скан", type="primary", use_container_width=True)

# ============================================================
# ОСНОВНАЯ ЛОГИКА
# ============================================================
if run_scan or 'scan_results' in st.session_state:
    if run_scan:
        with st.spinner("Подключение к MT5 и загрузка данных..."):
            df, equity_data = scan_all_symbols(months, selected_tfs)
            st.session_state['scan_results'] = df
            st.session_state['equity_data'] = equity_data
            st.session_state['scan_time'] = datetime.now().strftime("%H:%M:%S")

    df = st.session_state['scan_results']
    equity_data = st.session_state['equity_data']
    scan_time = st.session_state.get('scan_time', '')

    if df.empty:
        st.warning("⚠️ Нет данных. Проверьте подключение к MT5.")
        st.stop()

    # Фильтрация
    filtered = df[
        (df['total_profit'] > min_profit) &
        (df['max_drawdown'] <= max_dd) &
        (df['cycles'] >= min_cycles) &
        (df['win_rate'] >= min_winrate)
    ].sort_values('safety_score', ascending=False).copy()

    # ============================================================
    # KPI МЕТРИКИ
    # ============================================================
    st.caption(f"🕐 Последнее сканирование: {scan_time} | Всего проанализировано: {len(df)} | Проходит фильтры: {len(filtered)}")

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Всего символов", len(df))
    with c2:
        st.metric("Прошли фильтр", len(filtered))
    with c3:
        avg_p = filtered['total_profit'].mean() if len(filtered) > 0 else 0
        st.metric("Средний профит", f"${avg_p:,.0f}")
    with c4:
        avg_dd = filtered['max_drawdown'].mean() if len(filtered) > 0 else 0
        st.metric("Средняя просадка", f"${avg_dd:,.0f}")
    with c5:
        best_s = filtered['safety_score'].max() if len(filtered) > 0 else 0
        st.metric("Лучший Safety", f"{best_s:.4f}")

    # ============================================================
    # ГРАФИК 1: RISK vs REWARD
    # ============================================================
    if len(filtered) > 0:
        fig_scatter = px.scatter(
            filtered,
            x='max_drawdown',
            y='total_profit',
            color='safety_score',
            size='cycles',
            hover_name='symbol',
            hover_data=['timeframe', 'win_rate', 'cycles'],
            color_continuous_scale='RdYlGn',
            title="🎯 Risk vs Reward (нажмите на точку для эквити)"
        )
        fig_scatter.update_layout(height=450)
        st.plotly_chart(fig_scatter, use_container_width=True)

    # ============================================================
    # ГРАФИК 2: ТЕПЛОВАЯ КАРТА WIN RATE
    # ============================================================
    if len(filtered) > 0:
        top20 = filtered.groupby('symbol')['safety_score'].mean().nlargest(20).index
        pivot = filtered[filtered['symbol'].isin(top20)].pivot_table(
            values='win_rate', index='symbol', columns='timeframe', aggfunc='mean'
        )
        if not pivot.empty:
            fig_heat = px.imshow(
                pivot, color_continuous_scale='RdYlGn',
                labels=dict(x="TF", y="Symbol", color="Win Rate"),
                title="🔥 Win Rate по инструментам"
            )
            fig_heat.update_layout(height=400)
            st.plotly_chart(fig_heat, use_container_width=True)

    # ============================================================
    # ТАБЛИЦА + КЛИК ДЛЯ ЭКВИТИ
    # ============================================================
    st.subheader("📋 Результаты скана (нажмите строку для эквити)")

    if len(filtered) > 0:
        display_df = filtered[['symbol', 'timeframe', 'cycles', 'win_rate',
                               'total_profit', 'max_drawdown', 'safety_score']].copy()
        display_df['win_rate'] = display_df['win_rate'].apply(lambda x: f"{x*100:.1f}%")
        display_df['total_profit'] = display_df['total_profit'].apply(lambda x: f"${x:,.0f}")
        display_df['max_drawdown'] = display_df['max_drawdown'].apply(lambda x: f"${x:,.0f}")
        display_df['safety_score'] = display_df['safety_score'].apply(lambda x: f"{x:.4f}")

        event = st.dataframe(
            display_df,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row"
        )

        # Эквити для выбранного
        if event and event.selection and event.selection.rows:
            sel_idx = event.selection.rows[0]
            sel_symbol = filtered.iloc[sel_idx]['symbol']
            sel_tf = filtered.iloc[sel_idx]['timeframe']
            eq_key = f"{sel_symbol}_{sel_tf}"

            if eq_key in equity_data:
                st.subheader(f"📈 Кривая эквити: {sel_symbol} ({sel_tf})")

                eq = equity_data[eq_key]
                x = list(range(len(eq)))

                fig_eq = go.Figure()
                fig_eq.add_trace(go.Scatter(
                    x=x, y=eq,
                    mode='lines',
                    fill='tozeroy',
                    fillcolor='rgba(0,176,246,0.2)',
                    line=dict(color='#00B0F0', width=2),
                    name='Equity'
                ))
                fig_eq.update_layout(
                    title=f"Equity Curve: {sel_symbol} | TF: {sel_tf}",
                    xaxis_title="Цикл",
                    yaxis_title="Кумулятивный профит ($)",
                    height=400,
                    template="plotly_white"
                )
                st.plotly_chart(fig_eq, use_container_width=True)

                # Метрики выбранного
                sel_row = filtered.iloc[sel_idx]
                mc1, mc2, mc3, mc4 = st.columns(4)
                with mc1:
                    st.metric("Циклов", int(sel_row['cycles']))
                with mc2:
                    st.metric("Win Rate", f"{sel_row['win_rate']*100:.1f}%")
                with mc3:
                    st.metric("Профит", f"${sel_row['total_profit']:,.0f}")
                with mc4:
                    st.metric("Просадка", f"${sel_row['max_drawdown']:,.0f}")

                # КНОПКА ГЕНЕРАЦИИ БОТА
                st.markdown("---")
                bc1, bc2, bc3 = st.columns([1, 2, 1])
                with bc2:
                    if st.button("🤖 Сгенерировать бота для этого инструмента",
                                 type="primary", use_container_width=True):
                        bot_code, bot_filename = generate_bot_code(
                            symbol=sel_symbol,
                            timeframe=sel_tf,
                            start_lot=CFG.start_lot,
                            multiplier=CFG.multiplier,
                            max_positions=CFG.max_positions,
                            win_rate=sel_row['win_rate'],
                            total_profit=sel_row['total_profit'],
                            max_drawdown=sel_row['max_drawdown'],
                            safety_score=sel_row['safety_score']
                        )
                        # Сохраняем файл
                        import os
                        bots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots")
                        os.makedirs(bots_dir, exist_ok=True)
                        bot_path = os.path.join(bots_dir, bot_filename)
                        with open(bot_path, "w", encoding="utf-8") as f:
                            f.write(bot_code)
                        st.success(f"Бот создан: `{bot_filename}`")
                        st.download_button(
                            label="📥 Скачать бот (.py)",
                            data=bot_code,
                            file_name=bot_filename,
                            mime="text/x-python"
                        )
                        st.code(f"python {bot_path}", language="bash")

    else:
        st.info("Нет результатов по заданным фильтрам. Попробуйте изменить параметры.")

    # Кнопка экспорта
    if len(filtered) > 0:
        csv = filtered.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Скачать CSV", csv, "martingale_scan.csv", "text/csv")

else:
    st.info("👈 Нажмите **🔍 Запустить скан** слева для начала анализа всех инструментов MT5")
    st.markdown("""
    ### Как использовать:
    1. Выберите параметры сканирования слева
    2. Нажмите **Запустить скан**
    3. Дождитесь загрузки (может занять 1-5 минут)
    4. Используйте фильтры для настройки
    5. **Кликните по строке** в таблице для построения эквити
    """)
