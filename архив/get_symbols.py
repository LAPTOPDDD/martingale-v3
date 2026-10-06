import MetaTrader5 as mt5

def get_symbols():
    if not mt5.initialize():
        print("MT5 не инициализирован")
        return []

    # Группы символов, которые нас интересуют
    groups = ["*EURUSD*", "*GBPUSD*", "*USDJPY*", "*XAUUSD*", "*BTCUSD*", "*ETHUSD*"]
    
    symbols = []
    
    # Получаем все символы
    all_symbols = mt5.symbols_get()
    
    # Фильтруем (упрощенный пример - можно настроить точнее)
    # В реальности лучше использовать группы или конкретные названия
    target_symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD"]
    
    found_symbols = []
    for s in all_symbols:
        if s.name in target_symbols:
            found_symbols.append(s.name)
            
    mt5.shutdown()
    return found_symbols

if __name__ == "__main__":
    print(get_symbols())
