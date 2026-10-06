import MetaTrader5 as mt5

def get_categorized_symbols():
    if not mt5.initialize():
        print("MT5 не инициализирован")
        return

    all_symbols = mt5.symbols_get()
    
    categories = {
        "Forex": [],
        "Metals": [],
        "Crypto": []
    }
    
    # Регулярные выражения или простые проверки путей символов
    # Брокеры называют категории по-разному, поэтому используем гибкий подход
    for s in all_symbols:
        path = s.path.lower()
        
        if "forex" in path:
            categories["Forex"].append(s.name)
        elif "metal" in path:
            categories["Metals"].append(s.name)
        elif "crypto" in path or "coin" in path:
            categories["Crypto"].append(s.name)
            
    mt5.shutdown()
    
    for cat, syms in categories.items():
        print(f"\n--- {cat} ({len(syms)}) ---")
        print(syms)

if __name__ == "__main__":
    get_categorized_symbols()
