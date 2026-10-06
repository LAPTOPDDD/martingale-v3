import pandas as pd
import plotly.express as px
import os

# ============================================================
#  НАСТРОЙКИ
# ============================================================
EXCEL_FILE = "positive_backtest_results.xlsx"
OUTPUT_HTML = "3d_strategy_landscape.html"

def create_interactive_3d():
    # 1. Проверяем наличие файла
    if not os.path.exists(EXCEL_FILE):
        print(f"❌ Файл {EXCEL_FILE} не найден! Положи его в папку со скриптом.")
        return

    # 2. Загружаем данные
    print(f" Загрузка данных из {EXCEL_FILE}...")
    df = pd.read_excel(EXCEL_FILE)
    
    # Очищаем от пустых строк на всякий случай
    df.dropna(subset=['symbol', 'timeframe', 'safety_score'], inplace=True)
    
    print(f"✅ Загружено {len(df)} комбинаций стратегий.")
    print(f" Диапазон Safety Score: {df['safety_score'].min():.2f} - {df['safety_score'].max():.2f}")

    # 3. Строим интерактивный 3D график
    fig = px.scatter_3d(
        df,
        x='timeframe',          # Ось X: Таймфреймы
        y='cycles',             # Ось Y: Глубина мартингейла
        z='safety_score',       # Ось Z: Безопасность (чем выше, тем лучше)
        color='total_profit',   # Цвет: Прибыль (зеленый/желтый = хорошо)
        hover_data={            # Данные при наведении мыши
            'symbol': True,     # Название инструмента
            'total_profit': ':,.2f', # Форматирование прибыли
            'max_drawdown': ':,.2f', # Просадка
            'profit_factor': True,
            'wins': True,
            'timeframe': False, # Скрываем дублирующиеся данные в тултипе
            'cycles': False
        },
        title="3D Strategy Landscape: Hover to see Symbol!",
        labels={
            'timeframe': 'Timeframe',
            'cycles': 'Cycles (Positions)',
            'safety_score': 'Safety Score (Risk/Reward)',
            'total_profit': 'Total Profit'
        },
        color_continuous_scale='Viridis', # Красивая цветовая шкала
        size_max=15,
        opacity=0.8
    )

    # 4. Улучшаем внешний вид
    fig.update_layout(
        scene=dict(
            xaxis_title='Timeframe',
            yaxis_title='Max Positions (Cycles)',
            zaxis_title='Safety Score',
            aspectmode='manual',
            aspectratio=dict(x=1, y=1, z=0.8) # Делаем график более "плоским" для удобства обзора
        ),
        width=1400,
        height=900,
        font=dict(size=12)
    )

    # 5. Сохраняем и открываем
    fig.write_html(OUTPUT_HTML)
    print(f"\n🚀 График сохранен: {os.path.abspath(OUTPUT_HTML)}")
    print(" Открой этот файл в браузере (Chrome/Firefox).")
    print("💡 ЛКМ - вращать | Колесико - зум | ПКМ - двигать")
    print("💡 Наведи на любую точку, чтобы увидеть SYMBOL!")
    
    # Пытаемся открыть автоматически
    try:
        import webbrowser
        webbrowser.open('file://' + os.path.realpath(OUTPUT_HTML))
    except:
        pass

if __name__ == "__main__":
    create_interactive_3d()