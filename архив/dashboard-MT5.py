import streamlit as st
import pandas as pd
import plotly.express as px
import MetaTrader5 as mt5
from datetime import datetime, timedelta
import time

# ============================================================
# 1. НАСТРОЙКИ СТРАНИЦЫ И ПОДКЛЮЧЕНИЕ К MT5
# ============================================================
st.set_page_config(page_title="MT5 Live Martingale Dashboard", layout="wide")
st.title("📈 MT5 Live Martingale Analytics")

@st.cache_resource
def connect_mt5():
    """Подключение к MT5 с проверкой ошибок"""
    if not mt5.initialize():
        return False, f"Ошибка инициализации MT5: {mt5.last_error()}"
    
    account_info = mt5.account_info()
    if account_info is None:
        mt5.shutdown()
        return False, "Не удалось получить информацию о счете. Проверьте авторизацию."
        
    return True, {
        "login": account_info.login,
        "balance": account_info.balance,
        "currency": account_info.currency,
        "server": account_info.server
    }

success, data_or_error = connect_mt5()

if not success:
    st.error(data_or_error)
    st.stop()

st.sidebar.success(f"✅ Подключено к MT5\n Логин: {data_or_error['login']}\n💰 Баланс: {data_or_error['balance']} {data_or_error['currency']}")

# ============================================================
# 2. ЯДРО БЭКТЕСТА НА РЕАЛЬНЫХ ДАННЫХ
# ============================================================
def get_symbols_and_prices(months=3):
    """Получает список символов и цены за N месяцев"""
    date_to = datetime.now()
    date_from = date_to - timedelta(days=months * 30)
    
    all_symbols = mt5.symbols_get()
    if all_symbols is None:
        return []
        
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Берем только первые 50 символов для демо (чтобы не ждать час)
    # В продакшене можно убрать [:50] или добавить фильтр по группе
    symbols_to_test = [s.name for s in all_symbols if s.visible][:50] 
    
    for i, symbol in enumerate(symbols_to_test):
        status_text.text(f"Загрузка данных: {symbol} ({i+1}/{len(symbols_to_test)})")
        
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, date_from, date_to)
        if rates is not None and len(rates) > 100:
            prices = [float(r['close']) for r in rates]
            contract_size = mt5.symbol_info(symbol).trade_contract_size or 100000
            
            # Быстрый расчет метрик для H1
            metrics = calculate_martingale_metrics(prices, contract_size)
            metrics['symbol'] = symbol
            metrics['timeframe'] = 'H1'
            results.append(metrics)
            
        progress_bar.progress((i + 1) / len(symbols_to_test))
        
    status_text.text("✅ Загрузка завершена!")
    progress_bar.empty()
    return pd.DataFrame(results)

def calculate_martingale_metrics(prices, contract_size, start_lot=0.01, mult=1.5, max_pos=7):
    """Упрощенный расчет метрик для скорости дашборда"""
    equity = 0
    peak = 0
    max_dd = 0
    profit = 0
    wins = 0
    cycles = 0
    
    i = 0
    while i < len(prices) - max_pos:
        cycle_pnl = 0
        lot = start_lot
        direction = 1
        entry = prices[i]
        closed = False
        
        for j in range(max_pos):
            current_price = prices[i + j]
            pnl = (current_price - entry) * direction * lot * contract_size
            cycle_pnl += pnl
            
            if cycle_pnl > 0:
                profit += cycle_pnl
                equity += cycle_pnl
                wins += 1
                closed = True
                i += j + 1
                break
                
            if j == max_pos - 1:
                profit += cycle_pnl
                equity += cycle_pnl
                closed = True
                i += j + 1
                break
                
            lot *= mult
            direction *= -1
            entry = current_price
            
        if not closed: i += 1
        cycles += 1
        
        if equity > peak: peak = equity
        dd = peak - equity
        if dd > max_dd: max_dd = dd
        
    safety = (wins / cycles) / (max_dd + 1) if cycles > 0 else 0
    return {
        'total_profit': profit,
        'max_drawdown': max_dd,
        'safety_score': safety,
        'cycles': cycles,
        'win_rate': wins / cycles if cycles > 0 else 0
    }

# ============================================================
# 3. ЗАГРУЗКА И ФИЛЬТРАЦИЯ ДАННЫХ
# ============================================================
st.sidebar.header("️ Параметры анализа")
months_history = st.sidebar.slider("История (месяцев):", 1, 12, 3)
min_safety = st.sidebar.slider("Мин. Safety Score:", 0.0, 1.0, 0.0, 0.01)
max_dd_limit = st.sidebar.number_input("Макс. просадка ($):", min_value=0, value=5000, step=500)

if st.sidebar.button("🔄 Обновить данные из MT5"):
    st.cache_data.clear()
    st.rerun()

@st.cache_data(ttl=3600) # Кэш на 1 час
def load_live_data(m):
    return get_symbols_and_prices(m)

df = load_live_data(months_history)

# Применяем фильтры
filtered_df = df[
    (df['max_drawdown'] <= max_dd_limit) &
    (df['safety_score'] >= min_safety)
].sort_values('safety_score', ascending=False)

st.sidebar.metric("Найдено стратегий:", len(filtered_df))

# ============================================================
# 4. ВИЗУАЛИЗАЦИЯ
# ============================================================
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Средний профит", f"${filtered_df['total_profit'].mean():,.0f}")
with col2:
    st.metric("Средняя просадка", f"${filtered_df['max_drawdown'].mean():,.0f}", delta_color="inverse")
with col3:
    st.metric("Лучший Safety", f"{filtered_df['safety_score'].max():.4f}")

st.subheader("🎯 Карта риска и доходности (Live Data)")
if len(filtered_df) > 0:
    fig = px.scatter(
        filtered_df,
        x='max_drawdown', y='total_profit',
        color='safety_score', size='cycles',
        hover_name='symbol',
        labels={'max_drawdown': 'Max Drawdown ($)', 'total_profit': 'Profit ($)'},
        color_continuous_scale='RdYlGn'
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Нет данных, удовлетворяющих фильтрам. Попробуйте увеличить лимит просадки.")

st.subheader("🏆 Топ-10 безопасных инструментов")
st.dataframe(
    filtered_df.head(10)[['symbol', 'timeframe', 'cycles', 'total_profit', 'max_drawdown', 'safety_score']],
    column_config={
        "total_profit": st.column_config.NumberColumn(format="$%,.2f"),
        "max_drawdown": st.column_config.NumberColumn(format="$%,.2f")
    },
    hide_index=True
)