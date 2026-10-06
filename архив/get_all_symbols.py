import MetaTrader5 as mt5

def get_all_symbols():
    if not mt5.initialize():
        print("MT5 не инициализирован")
        return []

    # Получаем все символы
    all_symbols = mt5.symbols_get()
    
    # Собираем список всех имен
    symbol_names = [s.name for s in all_symbols]
            
    mt5.shutdown()
    return symbol_names

if __name__ == "__main__":
    symbols = get_all_symbols()
    print(f"Всего найдено символов: {len(symbols)}")
    print(symbols)
