import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

# ============================================================
# 1. НАСТРОЙКИ И ЗАГРУЗКА ДАННЫХ
# ============================================================
st.set_page_config(page_title="Martingale Analytics Dashboard", layout="wide")
st.title("📊 Martingale Strategy Analytics Dashboard")

EXCEL_FILE = "positive_backtest_results.xlsx"

if not Path(EXCEL_FILE).exists():
    st.error(f"❌ Файл {EXCEL_FILE} не найден! Положите его в папку со скриптом.")
    st.stop()

@st.cache_data
def load_data():
    """Загружает данные и добавляет расчетные метрики"""
    df = pd.read_excel(EXCEL_FILE)
    # Добавляем Recovery Factor (Профит / Просадка)
    df['recovery_factor'] = df['total_profit'] / (df['max_drawdown'] + 1)
    return df

df = load_data()

# ============================================================
# 2. БОКОВАЯ ПАНЕЛЬ (ФИЛЬТРЫ)
# ============================================================
st.sidebar.header("️ Фильтры анализа")

# Кнопка сброса всех фильтров
if st.sidebar.button("🔄 Сбросить все фильтры"):
    st.session_state.clear()
    st.rerun()

# Выбор инструментов (по умолчанию берем первые 20 для скорости, или все)
all_symbols = sorted(df['symbol'].unique())
# По умолчанию выбираем только Forex и Indices, чтобы не перегружать интерфейс акциями с huge DD
default_symbols = [s for s in all_symbols if any(x in s for x in ['USD', 'EUR', 'GBP', 'NAS', 'US30', 'GER'])][:30]

selected_symbols = st.sidebar.multiselect(
    "Инструменты:", 
    all_symbols, 
    default=default_symbols
)

# Выбор таймфреймов
all_tfs = sorted(df['timeframe'].unique())
selected_tfs = st.sidebar.multiselect("Таймфреймы:", all_tfs, default=all_tfs)

# Ползунок циклов
min_cycles = st.sidebar.slider("Минимум циклов:", 100, int(df['cycles'].max()), 500)

# Лимит просадки (Критически важно!)
# Устанавливаем разумный дефолт, но позволяем менять
max_dd_limit = st.sidebar.number_input("Макс. просадка ($):", min_value=0, value=10000, step=1000)

# Минимальный Safety Score
min_safety = st.sidebar.slider("Мин. Safety Score:", 0.0, float(df['safety_score'].max()), 0.0, 0.01)

# Применяем фильтры
filtered_df = df[
    (df['symbol'].isin(selected_symbols)) &
    (df['timeframe'].isin(selected_tfs)) &
    (df['cycles'] >= min_cycles) &
    (df['max_drawdown'] <= max_dd_limit) &
    (df['safety_score'] >= min_safety)
].copy()

st.sidebar.metric("Найдено стратегий:", len(filtered_df))

# Предупреждение, если ничего не найдено
if len(filtered_df) == 0:
    st.warning("⚠️ Нет данных, удовлетворяющих текущим фильтрам. Попробуйте увеличить 'Макс. просадка' или сбросить фильтры.")

# ============================================================
# 3. ВЕРХНИЕ МЕТРИКИ (KPI)
# ============================================================
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Всего стратегий", f"{len(filtered_df):,}")
with col2:
    avg_profit = filtered_df['total_profit'].mean() if len(filtered_df) > 0 else 0
    st.metric("Средний профит", f"${avg_profit:,.0f}")
with col3:
    avg_dd = filtered_df['max_drawdown'].mean() if len(filtered_df) > 0 else 0
    st.metric("Средняя просадка", f"${avg_dd:,.0f}", delta_color="inverse")
with col4:
    best_recovery = filtered_df['recovery_factor'].max() if len(filtered_df) > 0 else 0
    st.metric("Лучший Recovery Factor", f"{best_recovery:.2f}")

# ============================================================
# 4. ГРАФИК 1: РИСК vs ДОХОДНОСТЬ (Scatter Plot)
# ============================================================
st.subheader("🎯 Карта риска и доходности")
st.caption("Идеальные стратегии находятся в ЛЕВОМ ВЕРХНЕМ углу (высокий профит, низкая просадка)")

if len(filtered_df) > 0:
    fig_scatter = px.scatter(
        filtered_df,
        x='max_drawdown',
        y='total_profit',
        color='safety_score',
        size='cycles',
        hover_name='symbol',
        hover_data=['timeframe', 'profit_factor', 'recovery_factor'],
        labels={
            'max_drawdown': 'Max Drawdown ($)',
            'total_profit': 'Total Profit ($)',
            'safety_score': 'Safety Score'
        },
        color_continuous_scale='RdYlGn',
        title="Risk/Reward Matrix"
    )
    fig_scatter.update_layout(height=500)
    st.plotly_chart(fig_scatter, use_container_width=True)
else:
    st.info("График пуст. Измените фильтры слева.")

# ============================================================
# 5. ГРАФИК 2: ТЕПЛОВАЯ КАРТА БЕЗОПАСНОСТИ
# ============================================================
st.subheader("🔥 Тепловая карта Safety Score")
st.caption("Показывает, какие инструменты и таймфреймы наиболее стабильны")

if len(filtered_df) > 0:
    pivot_safety = filtered_df.pivot_table(
        values='safety_score', 
        index='symbol', 
        columns='timeframe', 
        aggfunc='mean'
    )

    # Показываем только топ-20 инструментов, чтобы график был читаемым
    top_symbols = filtered_df.groupby('symbol')['safety_score'].mean().nlargest(20).index
    pivot_safety_top = pivot_safety.loc[pivot_safety.index.isin(top_symbols)]

    fig_heatmap = px.imshow(
        pivot_safety_top,
        labels=dict(x="Timeframe", y="Symbol", color="Safety Score"),
        x=pivot_safety_top.columns,
        y=pivot_safety_top.index,
        color_continuous_scale='Viridis',
        aspect='auto'
    )
    fig_heatmap.update_layout(height=600)
    st.plotly_chart(fig_heatmap, use_container_width=True)

# ============================================================
# 6. ТАБЛИЦА ТОП-ЧЕМПИОНОВ
# ============================================================
st.subheader("🏆 Топ-10 безопасных стратегий")

if len(filtered_df) > 0:
    top_champions = filtered_df.sort_values('safety_score', ascending=False).head(10)
    st.dataframe(
        top_champions[['symbol', 'timeframe', 'cycles', 'total_profit', 'max_drawdown', 'safety_score', 'recovery_factor']],
        column_config={
            "total_profit": st.column_config.NumberColumn("Profit", format="$%,.2f"),
            "max_drawdown": st.column_config.NumberColumn("Max DD", format="$%,.2f"),
            "safety_score": st.column_config.NumberColumn("Safety", format="%.4f"),
            "recovery_factor": st.column_config.NumberColumn("Recovery", format="%.2f")
        },
        hide_index=True,
        use_container_width=True
    )

    # Кнопка скачивания
    csv = filtered_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 Скачать отфильтрованный отчет (CSV)",
        data=csv,
        file_name="filtered_martingale_report.csv",
        mime="text/csv"
    )