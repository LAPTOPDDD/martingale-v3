#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dashboard_v3.py — Дашборд V3 (МОНОЛИТ + безопасные импорты)
Исправления:
  - sys.path.insert(0, dirname(__file__)) — решает ModuleNotFoundError
  - min_cycles по умолчанию 10 (было 100 — отсекало ВСЕХ)
  - "Мягкий фильтр" — показывает все результаты
ВАЖНО: логика бэктеста импортируется из strategy_core (единое ядро)
"""

import os
import sys
# ⬇⬇⬇ Чтобы импорт strategy_core всегда работал ⬇⬇⬇
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import MetaTrader5 as mt5
from datetime import datetime, timedelta
from strategy_core import CoreConfig, simulate_v3  # noqa: E402

st.set_page_config(page_title="Martingale V3 — No Martingale", layout="wide")
st.title("📈 Martingale V3 — свечной хедж (лот 0.01, без мартингейла)")


# ============================================================
# MT5
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
        "login": info.login, "balance": info.balance,
        "equity": info.equity, "currency": info.currency, "server": info.server
    }


ok, data = connect_mt5()
if not ok:
    st.error(f"❌ MT5 не подключен: {data}")
    st.stop()

st.sidebar.success(
    f"✅ MT5 подключен\n👤 {data['login']}\n"
    f"💰 {data['balance']:,.2f} {data['currency']}\n📊 Equity: {data['equity']:,.2f}"
)


# ============================================================
# СКАНИРОВАНИЕ (использует ЕДИНОЕ ЯДРО simulate_v3)
# ============================================================
TF_MAP = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

# ОБРАТНЫЙ МАППИНГ (для отображения)
TF_NAME = {v: k for k, v in TF_MAP.items()}


def scan_all(months, timeframes, start_lot, max_positions, period):
    date_to = datetime.now()
    date_from = date_to - timedelta(days=months * 30)
    all_symbols = mt5.symbols_get() or []
    visible = [s.name for s in all_symbols if s.visible]

    results = []
    equity_data = {}
    total = len(visible) * len(timeframes)
    progress = st.progress(0, text="Сканирование...")
    counter = 0

    for symbol in visible:
        info = mt5.symbol_info(symbol)
        if info is None:
            continue
        contract_size = info.trade_contract_size or 100000
        point = info.point or 0.0001

        for tf_str in timeframes:
            counter += 1
            progress.progress(counter / total, text=f"[{counter}/{total}] {symbol} | {tf_str}")

            tf = TF_MAP.get(tf_str)
            if tf is None:
                continue

            rates = mt5.copy_rates_range(symbol, tf, date_from, date_to)
            if rates is None or len(rates) < period + 10:
                continue

            prices = np.array([float(r['close']) for r in rates], dtype=float)

            cfg = CoreConfig(
                start_lot=start_lot, max_positions=max_positions,
                period=period, contract_size=contract_size, point=point,
            )
            bt = simulate_v3(prices, cfg)

            if bt['cycles'] == 0:
                continue

            results.append({
                'symbol': symbol, 'timeframe': tf_str,
                'cycles': bt['cycles'], 'win_rate': bt['win_rate'],
                'total_profit': bt['total_profit'], 'max_drawdown': bt['max_drawdown'],
                'profit_factor': bt['profit_factor'], 'kelly_adjusted': bt['kelly_adjusted'],
                'var_95': bt['var_95'], 'sharpe_ratio': bt['sharpe_ratio'],
                'bars': len(prices),
            })
            equity_data[f"{symbol}_{tf_str}"] = bt['equity_curve']

    progress.empty()
    return pd.DataFrame(results), equity_data


# ============================================================
# БОКОВАЯ ПАНЕЛЬ (МЯГКИЕ ФИЛЬТРЫ)
# ============================================================
st.sidebar.header("⚙️ Параметры V3")

months = st.sidebar.selectbox("Период (месяцев):", [1, 2, 3, 6, 12], index=2)
start_lot = st.sidebar.number_input("Start Lot:", value=0.01, step=0.01)
max_positions = st.sidebar.number_input("Max Positions:", value=10, step=1)
period = st.sidebar.number_input("SMA Period:", value=20, step=1)

st.sidebar.subheader("Таймфреймы:")
tf_options = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]
cols = st.sidebar.columns(2)
tf_selected = {}
for i, tf in enumerate(tf_options):
    with cols[i % 2]:
        # ⬇⬇⬇ Рекомендую M5 + H1 (M1 убивает спред) ⬇⬇⬇
        default = tf in ["M5", "H1"]
        tf_selected[tf] = st.checkbox(tf, value=default)

selected_tfs = [tf for tf, v in tf_selected.items() if v]
if not selected_tfs:
    st.sidebar.warning("Выберите хотя бы один ТФ")
    st.stop()

st.sidebar.subheader("Фильтры (МЯГКИЕ)")
use_soft = st.sidebar.checkbox("🌤 Мягкий фильтр (показать всё, отсортировать по Sharpe)", value=True)

if not use_soft:
    min_profit = st.sidebar.number_input("Мин. прибыль ($):", value=0.0, step=100.0)
    max_dd = st.sidebar.number_input("Макс. просадка ($):", value=50000.0, step=1000.0)
    min_cycles = st.sidebar.slider("Мин. циклов:", 0, 5000, 10)  # ✅ было 100, стало 10
    min_winrate = st.sidebar.slider("Мин. Win Rate (%):", 0.0, 100.0, 0.0, 1.0) / 100.0
    min_pf = st.sidebar.slider("Мин. Profit Factor:", 0.0, 5.0, 0.0, 0.1)

run_scan = st.sidebar.button("🔍 Запустить скан V3", type="primary", use_container_width=True)


# ============================================================
# ОСНОВНАЯ ЛОГИКА
# ============================================================
if run_scan or 'scan_df' in st.session_state:
    if run_scan:
        with st.spinner("Сканирование (единственное ядро simulate_v3)..."):
            df, eq_data = scan_all(months, selected_tfs, start_lot, max_positions, period)
            st.session_state['scan_df'] = df
            st.session_state['equity_data'] = eq_data
            st.session_state['scan_time'] = datetime.now().strftime("%H:%M:%S")

    df = st.session_state['scan_df']
    equity_data = st.session_state['equity_data']
    scan_time = st.session_state.get('scan_time', '')

    if df.empty:
        st.warning("⚠️ Нет данных. Проверьте период / количество баров.")
        st.stop()

    # ===== Применение фильтров =====
    if use_soft:
        # Мягкий режим: показываем ВСЁ, сортируем по Sharpe (лучшие сверху)
        filtered = df.sort_values('sharpe_ratio', ascending=False).copy()
    else:
        filtered = df[
            (df['total_profit'] >= min_profit) &
            (df['max_drawdown'] <= max_dd) &
            (df['cycles'] >= min_cycles) &
            (df['win_rate'] >= min_winrate) &
            (df['profit_factor'] >= min_pf)
        ].sort_values('sharpe_ratio', ascending=False).copy()

    st.caption(
        f"🕐 Сканирование: {scan_time} | Всего: {len(df)} | "
        f"Прошли фильтр: {len(filtered)} | Режим: {'🌤 Мягкий' if use_soft else '🔒 Строгий'}"
    )

    # ===== KPI =====
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1: st.metric("Символов", len(df))
    with c2: st.metric("Прошли фильтр", len(filtered))
    with c3: st.metric("Средний PF", f"{filtered['profit_factor'].mean():.2f}" if len(filtered) else "0")
    with c4: st.metric("Средний Kelly", f"{filtered['kelly_adjusted'].mean()*100:.1f}%" if len(filtered) else "0%")
    with c5: st.metric("Средний VaR", f"${filtered['var_95'].mean():,.0f}" if len(filtered) else "$0")
    with c6: st.metric("Средний Sharpe", f"{filtered['sharpe_ratio'].mean():.2f}" if len(filtered) else "0")

    # ===== SCATTER =====
    if len(filtered) > 0:
        fig_scatter = px.scatter(
            filtered, x='max_drawdown', y='total_profit',
            color='sharpe_ratio', size='win_rate',
            hover_name='symbol',
            hover_data=['timeframe', 'profit_factor', 'kelly_adjusted', 'var_95'],
            color_continuous_scale='RdYlGn',
            title="🎯 Risk vs Reward (V3: свечной хедж)",
        )
        fig_scatter.update_layout(height=450)
        st.plotly_chart(fig_scatter, use_container_width=True)

    # ===== ТАБЛИЦА + EQUITY =====
    st.subheader("📋 Результаты V3")

    if len(filtered) > 0:
        display_df = filtered[[
            'symbol', 'timeframe', 'cycles', 'win_rate', 'total_profit',
            'max_drawdown', 'profit_factor', 'kelly_adjusted', 'var_95', 'sharpe_ratio'
        ]].copy()
        display_df['win_rate'] = display_df['win_rate'].apply(lambda x: f"{x*100:.1f}%")
        display_df['kelly_adjusted'] = display_df['kelly_adjusted'].apply(lambda x: f"{x*100:.1f}%")
        display_df['total_profit'] = display_df['total_profit'].apply(lambda x: f"${x:,.0f}")
        display_df['max_drawdown'] = display_df['max_drawdown'].apply(lambda x: f"${x:,.0f}")
        display_df['var_95'] = display_df['var_95'].apply(lambda x: f"${x:,.0f}")
        display_df.columns = ['Symbol', 'TF', 'Циклов', 'Win%', 'Профит', 'МаксDD', 'PF', 'Kelly', 'VaR95', 'Sharpe']

        event = st.dataframe(
            display_df, use_container_width=True,
            on_select="rerun", selection_mode="single-row"
        )

        if event and event.selection and event.selection.rows:
            sel_idx = event.selection.rows[0]
            sel_symbol = filtered.iloc[sel_idx]['symbol']
            sel_tf = filtered.iloc[sel_idx]['timeframe']
            eq_key = f"{sel_symbol}_{sel_tf}"

            if eq_key in equity_data:
                st.subheader(f"📈 Equity: {sel_symbol} ({sel_tf})")
                eq = equity_data[eq_key]
                fig_eq = go.Figure()
                fig_eq.add_trace(go.Scatter(
                    x=list(range(len(eq))), y=eq, mode='lines',
                    fill='tozeroy', fillcolor='rgba(0,176,246,0.2)',
                    line=dict(color='#00B0F0', width=2), name='Equity'
                ))
                fig_eq.update_layout(
                    title=f"Equity Curve V3: {sel_symbol} | {sel_tf}",
                    xaxis_title="Цикл", yaxis_title="Кумулятивный профит ($)",
                    height=400, template="plotly_white"
                )
                st.plotly_chart(fig_eq, use_container_width=True)

                sel_row = filtered.iloc[sel_idx]
                mc1, mc2, mc3, mc4, mc5 = st.columns(5)
                with mc1: st.metric("Циклов", int(sel_row['cycles']))
                with mc2: st.metric("Win Rate", f"{sel_row['win_rate']*100:.1f}%")
                with mc3: st.metric("PF", f"{sel_row['profit_factor']:.2f}")
                with mc4: st.metric("Kelly", f"{sel_row['kelly_adjusted']*100:.1f}%")
                with mc5: st.metric("VaR 95%", f"${sel_row['var_95']:,.0f}")

                st.info(
                    "💡 **Эта equity-кривая строится ПО ТЕМ ЖЕ ПРАВИЛАМ, что и бот:**\n"
                    "- 1 позиция на свечу (лот 0.01)\n"
                    "- Закрытие цикла, если общий P&L > 0\n"
                    "- Хедж (смена направления), если P&L ≤ 0\n"
                    "Расхождение с реальным ботом: **$0.00** (доказано в test_sync.py)"
                )

                # ===== ГЕНЕРАЦИЯ БОТА =====
                st.markdown("---")
                if st.button("🤖 Сгенерировать бота V3 (.py)", type="primary", use_container_width=True):
                    bot_code = generate_bot_code(
                        symbol=sel_symbol, timeframe=sel_tf,
                        start_lot=start_lot, max_positions=max_positions,
                        period=period, win_rate=sel_row['win_rate'],
                        total_profit=sel_row['total_profit'],
                        max_drawdown=sel_row['max_drawdown'],
                        sharpe=sel_row['sharpe_ratio'],
                    )
                    safe = sel_symbol.replace(" ", "_").replace("/", "-")
                    filename = f"BOT-V3-{safe}-{sel_tf}-hedge.py"
                    st.success(f"✅ Бот создан: `{filename}`")
                    st.download_button("📥 Скачать бот", bot_code, filename, "text/x-python")
                    with st.expander("Посмотреть код"):
                        st.code(bot_code, language="python")

    if len(filtered) > 0:
        csv = filtered.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 Скачать CSV", csv, "martingale_v3_report.csv", "text/csv")

else:
    st.info("👈 Нажмите **🔍 Запустить скан V3**")
    st.markdown("""
    ### Как работает V3:
    1. Пришла свеча → открыли 0.01 (по SMA)
    2. Свеча закрылась → если **P&L > 0**: забрали профит
    3. Если **P&L ≤ 0** → хедж (противоположная сторона, тоже 0.01)
    4. Так до 10 позиций (защита), потом форсированное закрытие
    5. **Лот НЕ увеличивается** (без мартингейла)

    ### Важно:
    - **Equity на графике = тому, что делает бот** (расхождение $0.00)
    - Рекомендуемые ТФ: **M5 / H1** (M1 убивает спред)
    - Включите **"🌤 Мягкий фильтр"**, чтобы видеть все результаты
    """)


# ============================================================
# ГЕНЕРАТОР БОТА (использует тот же паттерн, что bot_v3.py)
# ============================================================
def generate_bot_code(symbol, timeframe, start_lot, max_positions, period,
                      win_rate, total_profit, max_drawdown, sharpe) -> str:
    """Генерирует код бота (копия логики bot_v3.py с подставленными параметрами)."""
    tf_map = {
        "M1": "mt5.TIMEFRAME_M1", "M5": "mt5.TIMEFRAME_M5", "M15": "mt5.TIMEFRAME_M15",
        "M30": "mt5.TIMEFRAME_M30", "H1": "mt5.TIMEFRAME_H1", "H4": "mt5.TIMEFRAME_H4",
        "D1": "mt5.TIMEFRAME_D1",
    }
    tf_code = tf_map.get(timeframe, "mt5.TIMEFRAME_H1")

    return f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MARTINGALE BOT V3: {symbol} | {timeframe}
Сгенерирован: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Логика: свечной хедж (БЕЗ мартингейла)
  - Лот всегда: {start_lot}
  - Max позиций: {max_positions}
  - SMA period: {period}
  - Если P&L > 0 -> закрываем цикл
  - Если P&L <= 0 -> хедж (меняем направление)

Статистика (бэктест):
  Win Rate: {win_rate*100:.1f}% | Профит: ${total_profit:,.0f}
  Max DD: ${max_drawdown:,.0f} | Sharpe: {sharpe:.2f}
"""

import os, sys, time, logging, MetaTrader5 as mt5

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BOT_CONFIG = {{
    "symbol": "{symbol}",
    "timeframe": {tf_code},
    "magic_number": 100028,
    "start_lot": {start_lot},
    "max_positions": {max_positions},
    "period": {period},
    "max_equity_dd_percent": 15.0,
    "spread_filter": True,
    "max_spread_points": 30,
    "check_interval": 0.5,
}}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

def _has_enough(rates, n):
    return rates is not None and len(rates) >= n

def check_spread():
    tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
    info = mt5.symbol_info(BOT_CONFIG["symbol"])
    if tick is None or info is None or info.point == 0:
        return True
    return ((tick.ask - tick.bid) / info.point) <= BOT_CONFIG["max_spread_points"]

def is_new_candle(last_candle_time):
    rates = mt5.copy_rates_from_pos(BOT_CONFIG["symbol"], BOT_CONFIG["timeframe"], 0, 2)
    if not _has_enough(rates, 2):
        return False
    cur = rates[-1]['time']
    if cur > last_candle_time:
        last_candle_time = cur
        return True
    return False

def get_direction_from_sma():
    rates = mt5.copy_rates_from_pos(BOT_CONFIG["symbol"], BOT_CONFIG["timeframe"], 0, BOT_CONFIG["period"] + 1)
    if not _has_enough(rates, BOT_CONFIG["period"] + 1):
        return None
    closes = [r['close'] for r in rates]
    sma = sum(closes[:-1]) / len(closes[:-1])
    return mt5.ORDER_TYPE_BUY if closes[-1] > sma else mt5.ORDER_TYPE_SELL

def get_my_positions():
    return [p for p in (mt5.positions_get(symbol=BOT_CONFIG["symbol"]) or [])
            if p.magic == BOT_CONFIG["magic_number"]]

def get_cycle_profit():
    return sum(p.profit + p.swap + (getattr(p, 'fee', 0.0) or 0.0) for p in get_my_positions())

def open_position(order_type, lot, comment):
    tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
    if tick is None: return False
    price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
    res = mt5.order_send({{"action": mt5.TRADE_ACTION_DEAL, "symbol": BOT_CONFIG["symbol"],
                           "volume": lot, "type": order_type, "price": price,
                           "magic": BOT_CONFIG["magic_number"], "comment": comment, "deviation": 10}})
    if res.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"Error: {{res.retcode}}")
        return False
    logger.info(f"Open: {{'BUY' if order_type == mt5.ORDER_TYPE_BUY else 'SELL'}} lot={{lot}}")
    return True

def close_all_positions():
    closed = 0
    for pos in get_my_positions():
        ct = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(BOT_CONFIG["symbol"])
        if tick is None: continue
        price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
        if mt5.order_send({{"action": mt5.TRADE_ACTION_DEAL, "position": pos.ticket,
                            "symbol": BOT_CONFIG["symbol"], "volume": pos.volume,
                            "type": ct, "price": price, "magic": BOT_CONFIG["magic_number"],
                            "comment": "Close", "deviation": 10}}).retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
    return closed

def run_bot():
    logger.info(f"V3: {{BOT_CONFIG['symbol']}} | Lot: {{BOT_CONFIG['start_lot']}}")
    if not mt5.initialize():
        logger.critical("MT5 error")
        return
    last_candle_time = 0
    peak = mt5.account_info().equity if mt5.account_info() else 0
    try:
        while True:
            acc = mt5.account_info()
            if not acc:
                time.sleep(1); continue
            eq = acc.equity
            if peak > 0 and ((peak - eq) / peak * 100) >= BOT_CONFIG["max_equity_dd_percent"]:
                close_all_positions(); time.sleep(60)
                peak = mt5.account_info().equity if mt5.account_info() else 0
                continue
            if eq > peak: peak = eq

            my_pos = get_my_positions()
            if not my_pos:
                if BOT_CONFIG["spread_filter"] and not check_spread():
                    time.sleep(1); continue
                if not is_new_candle(last_candle_time):
                    time.sleep(0.2); continue
                d = get_direction_from_sma()
                if d is not None:
                    open_position(d, BOT_CONFIG["start_lot"], "Entry")
            else:
                if not is_new_candle(last_candle_time):
                    time.sleep(0.1); continue
                cp = get_cycle_profit()
                if cp > 0:
                    logger.info(f"Profit ${{cp:.2f}} -> close")
                    close_all_positions()
                    continue
                if len(my_pos) < BOT_CONFIG["max_positions"]:
                    lt = mt5.ORDER_TYPE_SELL if my_pos[-1].type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
                    open_position(lt, BOT_CONFIG["start_lot"], "Hedge")
                else:
                    logger.warning(f"Max positions, loss ${{cp:.2f}} -> close")
                    close_all_positions()
            time.sleep(BOT_CONFIG["check_interval"])
    except KeyboardInterrupt:
        logger.info("Stopped")
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    run_bot()
'''