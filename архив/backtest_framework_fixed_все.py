#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================3
MARTINGALE UNIVERSAL BACKTEST FRAMEWORK  v2 (FIXED)
============================================================
Прогоняет систему "мартингейл от 0.01 лота, ×1.5, до 10 позиций"
на ВСЕХ инструментах × ВСЕХ таймфреймах и ищет самую безопасную комбинацию.

ИСПРАВЛЕНО В v2:
  - Сохранение JSON в текущую папку (работает на Windows и Linux)
  - Фильтрация по датам (можно указать период истории)
  - Вывод топ-5 комбинаций
  - Защита от деления на ноль в SafetyScore

ЛОГИКА СИСТЕМЫ:
  Бар 1:   покупка 0.01 лота
  Бар 2:   если профит > 0 -> закрыть; иначе продать (сумма_объёмов × 1.5)
  Бар 3-10: если суммарный профит > 0 -> закрыть всё
           иначе открыть в противоположную сторону (сумма_объёмов × 1.5)
  После закрытия -> новый цикл (покупка 0.01)

ЗАПУСК:
  python backtest_framework_fixed.py
  (выберите 1 = быстрый тест, 2 = полный тест, 3 = реальные данные MT5)
============================================================
"""

import os
import sys
import json
import random
import statistics
import matplotlib.pyplot as plt # <--- Added
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Optional

# ============================================================
#  КОНФИГУРАЦИЯ
# ============================================================
@dataclass
class Config:
    start_lot: float = 0.01
    multiplier: float = 1.5
    max_positions: int = 10
    spread_points: float = 2.0       # спред в пунктах (для синтетики)
    commission_per_lot: float = 0.0  # комиссия за лот (в валюте счёта)
    slippage_points: float = 0.0
    # Период для реальных данных MT5 (если None -> весь доступный)
    history_from: Optional[str] = None   # "YYYY-MM-DD"
    history_to:   Optional[str] = None   # "YYYY-MM-DD"

# ============================================================
#  МОДЕЛИ РЕЗУЛЬТАТОВ
# ============================================================
@dataclass
class CycleResult:
    symbol: str
    timeframe: str
    bars_to_close: int
    total_profit: float
    max_drawdown: float
    positions_count: int

@dataclass
class ComboResult:
    symbol: str
    timeframe: str
    cycles: int = 0
    wins: int = 0
    total_profit: float = 0.0
    max_drawdown: float = 0.0
    max_equity_drop: float = 0.0
    profit_factor: float = 0.0
    safety_score: float = 0.0
    history_bars: int = 0
    equity_history: List[float] = field(default_factory=list) # <--- Added

# ============================================================
#  ГЕНЕРАТОР СИНТЕТИЧЕСКИХ ДАННЫХ
# ============================================================
def generate_synthetic_prices(n: int, volatility: float = 0.0005,
                              drift: float = 0.0, seed: int = 42) -> List[float]:
    """Генерирует случайные цены методом геометрического блуждания."""
    random.seed(seed)
    prices = [1.0]
    for _ in range(n - 1):
        change = random.gauss(drift, volatility)
        prices.append(max(0.0001, prices[-1] * (1 + change)))
    return prices

# ============================================================
#  ОДИН БЭКТЕСТ (ядро логики)
# ============================================================
def run_backtest(prices: List[float], symbol: str, timeframe: str,
                 cfg: Config) -> ComboResult:
    """
    Прогоняет мартингейл-циклы на массиве цен.
    Возвращает ComboResult с агрегированной статистикой.
    """
    result = ComboResult(symbol=symbol, timeframe=timeframe, history_bars=len(prices))

    i = 0
    current_equity = 0.0
    equity_history = [0.0]
    peak_equity = 0.0
    result.equity_history = equity_history

    while i < len(prices) - 1:
        # ---------- НАЧАЛО ЦИКЛА ----------
        positions = []          # (volume, direction, open_price)
        cycle_profit = 0.0
        cycle_peak = 0.0
        closed_this_cycle = False

        # БАР 1: покупаем 0.01
        entry_price = prices[i]
        lot = cfg.start_lot
        direction = 1  # 1 = buy, -1 = sell
        positions.append((lot, direction, entry_price))
        i += 1

        # ---------- ВНУТРИ ЦИКЛА ----------
        while i < len(prices) and len(positions) <= cfg.max_positions and not closed_this_cycle:
            current_price = prices[i]
            spread = cfg.spread_points * 0.0001  # упрощённо в "ценаx"
            
            # Считаем текущий профит по всем позициям
            total_profit = 0.0
            for vol, dirn, open_px in positions:
                price_diff = (current_price - open_px) * dirn
                total_profit += price_diff * vol * 100000  # нормировка под "валюту"
            # Вычитаем спред и комиссию (при открытии каждой новой)
            total_profit -= cfg.commission_per_lot * sum(v for v, _, _ in positions)
            
            cycle_profit = total_profit
            cycle_peak = max(cycle_peak, cycle_profit)

            # --- ПРАВИЛО ЗАКРЫТИЯ: сумма > 0 -> закрыть всё ---
            if total_profit > 0:
                closed_this_cycle = True
                result.total_profit += total_profit
                current_equity += total_profit
                equity_history.append(current_equity)
                if total_profit > 0:
                    result.wins += 1
                break

            # --- ИНАЧЕ: открываем в противоположную сторону (×1.5) ---
            if len(positions) >= cfg.max_positions:
                # Достигли лимита -> принудительно закрываем с текущим профитом
                closed_this_cycle = True
                result.total_profit += total_profit
                current_equity += total_profit
                equity_history.append(current_equity)
                break


            # Считаем сумму объёмов и умножаем на 1.5
            sum_volumes = sum(v for v, _, _ in positions)
            new_lot = sum_volumes * cfg.multiplier
            new_lot = round(new_lot, 2)

            direction = -direction  # меняем сторону
            entry_price = current_price
            positions.append((new_lot, direction, entry_price))
            i += 1

        # ---------- КОНЕЦ ЦИКЛА ----------
        result.cycles += 1

        # Отслеживаем просадку equity
        peak_equity = max(peak_equity, current_equity)
        result.max_equity_drop = max(result.max_equity_drop, peak_equity - current_equity)

        if not closed_this_cycle:
            i += 1  # двигаем бар, если цикл не закрылся естественно

    # ---------- ФИНАЛЬНЫЕ МЕТРИКИ ----------
    result.max_drawdown = result.max_equity_drop

    # Profit Factor (защита от деления на ноль)
    gross_profit = max(0.0, result.total_profit) if result.total_profit > 0 else 0.0
    gross_loss = abs(min(0.0, result.total_profit)) if result.total_profit < 0 else 0.0
    if gross_loss > 0:
        result.profit_factor = gross_profit / gross_loss
    else:
        result.profit_factor = 999.0  # все циклы в плюсе -> PF = бесконечность (обозначаем 999)

    # Safety Score = win_rate × profit_factor / (maxDD + epsilon)
    win_rate = (result.wins / result.cycles) if result.cycles > 0 else 0.0
    dd_safe = result.max_drawdown + 1.0  # защита от деления на ноль
    result.safety_score = (win_rate * result.profit_factor) / dd_safe

    return result

# ============================================================
#  ПОЛУЧЕНИЕ ДАННЫХ (MT5 или синтетика)
# ============================================================
def get_prices_mt5(symbol: str, timeframe: str, cfg: Config) -> Optional[List[float]]:
    """Пытается получить реальные данные из MT5. Возвращает None при ошибке."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            print("   ⚠️ MT5 не инициализирован, используем синтетику")
            return None

        # Маппинг таймфреймов
        tf_map = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
        }
        tf = tf_map.get(timeframe)
        if tf is None:
            return None

        # Определяем диапазон дат
        to_date = datetime.now()
        if cfg.history_to:
            to_date = datetime.strptime(cfg.history_to, "%Y-%m-%d")
        from_date = to_date - timedelta(days=90)  # последние 90 дней по умолчанию
        if cfg.history_from:
            from_date = datetime.strptime(cfg.history_from, "%Y-%m-%d")

        rates = mt5.copy_rates_range(symbol, tf, from_date, to_date)
        mt5.shutdown()

        if rates is None or len(rates) == 0:
            return None

        return [float(r["close"]) for r in rates]

    except Exception as e:
        print(f"   ⚠️ Ошибка MT5: {e}")
        return None

def get_prices(symbol: str, timeframe: str, cfg: Config, use_real: bool) -> List[float]:
    """Возвращает цены (реальные или синтетические)."""
    if use_real:
        prices = get_prices_mt5(symbol, timeframe, cfg)
        if prices:
            return prices
        print(f"   → переход на синтетику для {symbol} {timeframe}")

    # Синтетические данные
    volatility = 0.0005

    # Количество баров зависит от таймфрейма
    bars_map = {"M1": 5000, "M5": 3000, "M15": 2000, "M30": 1500, "H1": 1000}
    n = bars_map.get(timeframe, 2000)

    return generate_synthetic_prices(n, volatility=volatility, seed=hash(symbol + timeframe) % 10000)

# ============================================================
#  РЕЙТИНГ И ОТЧЁТ
# ============================================================
def save_all_equity_plots(results: List[ComboResult], output_dir: str):
    """Сохраняет графики эквити для всех результатов."""
    print("\n📈 Сохранение графиков эквити для всех комбинаций...")
    os.makedirs(output_dir, exist_ok=True)
    for r in results:
        if r.equity_history:
            plt.figure(figsize=(10, 6))
            plt.plot(r.equity_history)
            plt.title(f"Equity Curve: {r.symbol} {r.timeframe}")
            plt.xlabel("Cycle")
            plt.ylabel("Equity")
            plt.grid(True)
            plot_path = os.path.join(output_dir, f"equity_{r.symbol}_{r.timeframe}.png")
            plt.savefig(plot_path)
            plt.close()
    print(f"✅ Графики сохранены в {output_dir}")

def rank_and_report(results: List[ComboResult], output_dir: str):
    """Сортирует результаты по SafetyScore и выводит отчёт + сохраняет JSON."""
    # Фильтруем те, что успели отработать хотя бы несколько циклов
    valid = [r for r in results if r.cycles >= 5]
    valid.sort(key=lambda x: x.safety_score, reverse=True)

    print("\n" + "=" * 80)
    print("🏆 РЕЙТИНГ БЕЗОПАСНОСТИ (по возрастанию Safety Score)")
    print("=" * 80)
    print(f"{'#':>2} {'Символ':<10} {'ТФ':<5} {'Циклов':>7} {'Win%':>7} {'PF':>8} {'MaxDD':>10} {'Total':>10} {'Score':>8}")
    print("-" * 80)

    for idx, r in enumerate(valid[:15], 1):
        win_pct = (r.wins / r.cycles * 100) if r.cycles > 0 else 0.0
        print(f"{idx:>2} {r.symbol:<10} {r.timeframe:<5} {r.cycles:>7} "
              f"{win_pct:>7.1f} {r.profit_factor:>8.2f} {r.max_drawdown:>10.1f} "
              f"{r.total_profit:>10.1f} {r.safety_score:>8.4f}")

    # ---------- ТОП-1 ----------
    if valid:
        best = valid[0]
        print("\n" + "⭐" * 70)
        print("🥇 САМАЯ БЕЗОПАСНАЯ КОМБИНАЦИЯ:")
        print(f"   Инструмент : {best.symbol}")
        print(f"   Таймфрейм  : {best.timeframe}")
        print(f"   Win Rate   : {(best.wins / best.cycles * 100):.1f}%")
        print(f"   Profit Fact: {best.profit_factor:.2f}")
        print(f"   Max DD     : {best.max_drawdown:.1f}")
        print(f"   SafetyScore: {best.safety_score:.4f}")
        print("⭐" * 70)

        # Графики эквити теперь сохраняются для всех комбинаций в save_all_equity_plots

    # ---------- ТОП-5 ----------
    print("\n📌 ТОП-5 КОМБИНАЦИЙ ДЛЯ ТОРГОВЛИ:")
    for idx, r in enumerate(valid[:5], 1):
        win_pct = (r.wins / r.cycles * 100) if r.cycles > 0 else 0.0
        verdict = "✅" if r.total_profit > 0 else "❌"
        print(f"  {idx}. {r.symbol:<10} {r.timeframe:<5} win={win_pct:.1f}%  DD={r.max_drawdown:.0f}  total={r.total_profit:+.0f}  {verdict}")

    # ---------- СРЕДНЕЕ ПО ИНСТРУМЕНТАМ ----------
    print("\n📊 СРЕДНЕЕ ПО ИНСТРУМЕНТАМ (все таймфреймы):")
    symbols = sorted(set(r.symbol for r in results))
    for sym in symbols:
        sym_results = [r for r in results if r.symbol == sym and r.cycles >= 5]
        if sym_results:
            avg_dd = statistics.mean(r.max_drawdown for r in sym_results)
            avg_safety = statistics.mean(r.safety_score for r in sym_results)
            avg_win = statistics.mean((r.wins / r.cycles * 100) for r in sym_results if r.cycles > 0)
            print(f"   {sym:<10}: win={avg_win:>5.1f}%  avgDD={avg_dd:>8.1f}  safety={avg_safety:>8.4f}")

    # ---------- СРЕДНЕЕ ПО ТАЙМФРЕЙМАМ ----------
    print("\n📊 СРЕДНЕЕ ПО ТАЙМФРЕЙМАМ (все инструменты):")
    timeframes = sorted(set(r.timeframe for r in results))
    for tf in timeframes:
        tf_results = [r for r in results if r.timeframe == tf and r.cycles >= 5]
        if tf_results:
            avg_dd = statistics.mean(r.max_drawdown for r in tf_results)
            avg_safety = statistics.mean(r.safety_score for r in tf_results)
            avg_win = statistics.mean((r.wins / r.cycles * 100) for r in tf_results if r.cycles > 0)
            print(f"   {tf:<5}: win={avg_win:>5.1f}%  avgDD={avg_dd:>8.1f}  safety={avg_safety:>8.4f}")

    # ---------- СОХРАНЕНИЕ JSON ----------
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "backtest_results.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in results], f, ensure_ascii=False, indent=2)
        print(f"\n💾 Результаты сохранены: {json_path}")
    except Exception as e:
        print(f"\n⚠️ Не удалось сохранить JSON: {e}")

# ============================================================
#  ГЛАВНАЯ ФУНКЦИЯ
# ============================================================
def main():
    cfg = Config()

    # По умолчанию MT5
#    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "ETHUSD"]
    symbols = ['XAGUSD', 'XAUUSD', 'XAGAUD', 'XAGEUR', 'XAUAUD', 'XAUEUR', 'XAUGBP', 'XAUJPY', 'XAUCNH', 
               'XAGJPY', 'AUDCAD', 'AUDCHF', 'AUDJPY', 'AUDNZD', 'AUDUSD', 'CADCHF', 'CADJPY', 'CHFJPY', 
               'EURAUD', 'EURCAD', 'EURCHF', 'EURGBP', 'EURJPY', 'EURNOK', 'EURNZD', 'EURSEK', 'EURSGD', 
               'EURUSD', 'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPJPY', 'EURTRY', 'GBPNZD', 'GBPSGD', 'GBPUSD', 
               'NZDCAD', 'NZDCHF', 'NZDJPY', 'NZDSGD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDCNH', 'USDJPY', 
               'USDMXN', 'USDNOK', 'USDPLN', 'USDSEK', 'USDSGD', 'USDTRY', 'USDZAR', 'USDTHB', 'USDHKD', 
               'USDUSC', 'USDAED', 'SPCUSD', 'USOUSD', 'JPCUSD', 'GLDUSD', 'BRN', 'NG', 'USDInd', 'WTI', 
               'ARABICA', 'COCOA', 'COPPER', 'CORN', 'COTTON', 'ROBUSTA', 'SOYBEAN', 'SUGAR', 'USAHO', 'WHEAT', 
               'GOLDInd', 'GER40', 'CN50', 'FRA40', 'NAS100', 'SPN35', 'UK100', 'US30', 'AU200', 'EU50', 'HK50',
                 'US500', 'JP225', 'NETH25', 'RUS2000', 'US400', 'CHINAH', 'SG20', 'TWN', 'AAVE', 'BITCOIN', 
                 'BITCOIN CASH', 'CARDANO', 'CHAINLINK', 'DOGECOIN', 'ETHEREUM', 'LITECOIN', 'POLKADOT', 'POLYGON',
                   'RIPPLE', 'SOLANA', 'STELLAR', 'TRON', 'UNISWAP', 'AVALANCH', 'AXS', 'BNB', 'COSMOS', 'PYTH', 
                   'ILLUVIUM', 'INJ', 'RENDER', 'TRUMP', 'SUI', 'HEDERA', 'NEAR', 'APTOS', 'ARBITRUM', 'PAXG', 
                   'GRAM', '3D SYSTEMS CORP CFD', '3M CO CFD', 'ABBOTT LABS CFD', 'ABBVIE CFD', 'ACCENTURE PLC-A CFD',
                     'ADOBE CFD', 'ADT CFD', 'ADV MICRO DEVICE CFD', 'ADVANCE AUTO PAR CFD', 'AES CORP CFD',
                       'AFLAC CFD', 'AGILENT TECH CFD', 'AIR PRODS & CHEM CFD', 'AIRBNB CFD', 
                       'AKAMAI TECHNOLOG CFD', 'ALASKA AIR GROUP CFD', 'ALBEMARLE CORP CFD',
                         "ALEXANDER'S INC CFD", 'ALEXANDRIA REAL CFD', 'ALIBABA GRP-ADR CFD',
                           'ALIGN TECHNOLOGY CFD', 'ALLEGION PLC CFD', 'ALLIANT ENERGY CFD',
                             'ALLSTATE CFD', 'ALPHABET INC-C CFD', 'ALPHABET-A CFD', 'ALTICE USA-A CFD',
                               'ALTRIA GROUP CFD', 'AMAZON CFD', 'AMC ENT CFD', 'AMCOR PLC CFD', 
                               'AMEREN CFD', 'AMERICAN AIRLINES CFD', 'AMERICAN ELECTRI CFD', 
                               'AMERICAN EXPRESS CFD', 'AMERICAN INTERNA CFD', 'AMERICAN TOWER C CFD',
                                 'AMERICAN WATER W CFD', 'AMERIPRISE FINAN CFD', 'AMETEK CFD', 'AMGEN CFD',
                                   'AMPHENOL-A CFD', 'AMPLIFY ENERGY C CFD', 'ANALOG DEVICES CFD', 'AON PLC CFD',
                                     'APA CORP CFD', 'APPLE CFD', 'APPLIED MATERIAL CFD', 'ARCHER-DANIELS CFD',
  'ARGO BLOCKCHAIN CFD', 'ARISTA NETWORKS CFD', 'ARTHUR J GALLAGH CFD', 'ASML HOLDING CFD', 'ASSURANT INC CFD',
    'ASTRAZENECA-ADR CFD', 'AT&T CFD', 'ATLASSIAN-A CFD', 'ATMOS ENERGY CFD', 'AURORA CANNABIS CFD', 'AUTODESK CFD',
      'AUTOMATIC DATA CFD', 'AUTOZONE CFD', 'AVERY DENNISON CFD', 'BAIDU -SP ADR CFD', 'BAKER HUGHES CO CFD', 'BALL CFD',
        'BANK NY MELLON CFD', 'BANK OF AMERICA CFD', 'BARCLAYS PLC CFD', 'BATH & BODY WORK CFD', 'BAXTER INTL CFD', 
        'BECTON DICKINSON CFD', 'BEST BUY CO CFD', 'BEYOND MEAT CFD', 'BIO-RAD LABS-A CFD', 'BIO-TECHNE CORP CFD', 
        'BIOGEN CFD', 'BIOMARIN PHARMAC CFD', 'BIONTECH CFD', 'BIT MINING CFD', 'BLACKBERRY LTD CFD', 'BLACKROCK CFD',
          'BLACKSTONE GRO-A CFD', 'BLOOM ENERGY CFD', 'BOEING CO/THE CFD', 'BOOKING HOLDINGS CFD', 'BORGWARNER INC CFD',
            'BOSTON SCIENTIFC CFD', 'BOXLIGHT CORP CFD', 'BRISTOL-MYER SQB CFD', 'BROADCOM CFD', 'BROOKFIELD INFRA CFD',
              'BROWN & BROWN CFD', 'BUMBLE INC CFD', 'BUNGE LIMITED CFD', 'CADENCE DESIGN CFD', 'CAESARS ENTERTAI CFD', 
              'CAMDEN PROP TR CFD', 'CANAAN CFD', 'CANOPY GROWTH CORP CFD', 'CAPITAL ONE FINA CFD', 'CARDINAL HEALTH CFD',
                'CARMAX INC CFD', 'CARNIVAL CORP CFD', 'CARRIER GLOB CFD', 'CATERPILLAR CFD', 'CBRE GROUP INC-A CFD',
                  'CDW CORP/DE CFD', 'CELANESE CORP CFD', 'CENCORA CFD', 'CENTENE CFD', 'CENTERPOINT ENER CFD',
                    'CF INDUSTRIES HO CFD', 'CH ROBINSON CFD', 'CHARGEPOINT HLDG CFD', 'CHARLES RIVER LA CFD', 
                    'CHARTER COMMUN-A CFD', 'CHECK POINT SOFT CFD', 'CHEGG CFD', 'CHEVRON CFD', 'CHIPOTLE MEXICAN CFD',
                      'CHUBB LTD CFD', 'CHURCH & DWIGHT CFD', 'CIGNA CFD', 'CINCINNATI FIN CFD', 'CINTAS CFD', 
                      'CIPHER MINING CFD', 'CISCO SYSTEMS CFD', 'CITIGROUP CFD', 'CITIZENS FINANCI CFD', 
                      'CLEAN ENERGY FUELS CFD', 'CLEAN HARBORS CFD', 'CLEANSPARK CFD', 'CLOROX CO CFD', 'CLOUDFARE INC CFD',
                        'CME GROUP CFD', 'CMS ENERGY CFD', 'COCA-COLA CO/THE CFD', 'COCA-COLA EUROPE CFD',
   'COGNIZANT TECH-A CFD', 'COINBASE CFD', 'COLGATE-PALMOLIV CFD', 'COMCAST-A CFD', 'CONAGRA BRANDS CFD', 
   'CONOCOPHILLIPS CFD', 'CONS EDISON CFD', 'CONSTELLATION-A CFD', 'COOPER COS CFD', 'COPART CFD', 'CORNING CFD',
     'CORTEVA CFD', 'COSTAR GROUP CFD', 'COSTCO WHOLESALE CFD', 'CRISPR THERAPAUTICS CFD', 'CRONOS GROUP CFD',
       'CROWDSTRIKE HO-A CFD', 'CROWN CASTLE INT CFD', 'CSX CFD', 'CUMMINS CFD', 'CVS HEALTH CFD', 'DANAHER CFD',
         'DARDEN RESTAURAN CFD', 'DATADOG INC-A CFD', "DAVE & BUSTER'S CFD", 'DAVITA INC CFD', 'DEERE & CO CFD',
           'DELL TECHN-C CFD', 'DELTA AIR LI CFD', 'DENTSPLY SIRONA CFD', 'DEVON ENERGY CO CFD', 'DEXCOM CFD', 
           'DIAMONDBACK ENER CFD', 'DIGITAL REALTY CFD', 'DOCUSIGN CFD', 'DOLLAR GENERAL C CFD', 'DOLLAR TREE CFD',
             'DOMINION ENERGY CFD', "DOMINO'S PIZZA CFD", 'DOVER CORP CFD', 'DOW CFD', 'DR HORTON CFD',
               'DRAFTKINGS INC CFD', 'DTE ENERGY CO CFD', 'DUKE ENERGY CFD', 'DUPONT DE NEMOUR CFD', 
               'DXC TECHNOLOGY C CFD', 'EASTMAN CHEMICAL CFD', 'EATON  PLC CFD', 'EBANG INTERNATIONAL CFD',
                 'EBAY CFD', 'ECOLAB CFD', 'EDISON INTL CFD', 'EDWARDS LIFE CFD', 'ELEVANCE HEALTH CFD',
                   'ELI LILLY & CO CFD', 'EMERSON ELEC CO CFD', 'ENPHASE ENERGY INC CFD', 'ENTERGY CFD',
                     'ENTERPRISE PRODU CFD', 'EOG RESOURCES CFD', 'EPAM SYSTEMS INC CFD', 'EQUIFAX CFD',
                       'EQUINIX CFD', 'EQUITY RESIDENTI CFD', 'ESSEX PROPERTY CFD', 'ESTEE LAUDER CFD', 
                       'ETSY INC CFD', 'EVEREST GROUP CFD', 'EVERGY INC CFD', 'EVERSOURCE ENERG CFD',
                         'EXELON CFD', 'EXPEDIA GROUP IN CFD', 'EXPEDITORS INTL CFD', 'EXTRA SPACE STOR CFD',
  'EXXON MOBIL CFD', 'F5 INC CFD', 'FACTSET RESEARCH CFD', 'FASTENAL CO CFD', 'FASTLY INC CFD', 'FED REALTY INVS CFD',
    'FEDEX CFD', 'FERRARI NV CFD', 'FIDELITY NATIONA CFD', 'FIFTH THIRD BANC CFD', 'FIRSTENERGY CFD', 'FISERV CFD',
      'FMC CORP CFD', 'FORD MOTOR CO CFD', 'FORTINET CFD', 'FORTUNE BRANDS INNO CFD', 'FOX  - A CFD', 'FOX CORP - B CFD',
        'FRANKLIN RES INC CFD', 'FREEPORT-MCMORAN CFD', 'FUTU HOLDINGS CFD', 'GAMESTOP CFD', 'GARMIN LTD CFD',
          'GARTNER INC CFD', 'GE AEROSPACE CFD', 'GE HEALTH TECH CFD', 'GEN DIGITAL CFD', 'GENERAL DYNAMICS CFD',
            'GENERAL MILLS IN CFD', 'GENERAL MOTORS C CFD', 'GENUINE PARTS CO CFD', 'GILEAD SCIENCES CFD', 
            'GLOBAL PAYMENTS CFD', 'GLOBE LIFE INC CFD', 'GOLDMAN SACHS GP CFD', 'GREENIDGE GENE CFD', 'HALLIBURTON CO CFD',
              'HARTFORD FINL SV CFD', 'HASBRO INC CFD', 'HCA HEALTHCARE I CFD', 'HENRY SCHEIN INC CFD', 'HERSHEY CO/THE CFD',
                'HERTZ CFD', 'HEWLETT PACKA CFD', 'HILTON WORLDWIDE CFD', 'HIVE BLOCKCHAIN CFD', 'HOME DEPOT CFD', 
                'HONEYWELL INTL CFD', 'HORMEL FOODS CRP CFD', 'HOST HOTELS & RE CFD', 'HOWMET AEROSPACE CFD', 'HP CFD',
                  'HUMANA CFD', 'HUNT (JB) TRANS CFD', 'HUNTINGTON BANC CFD', 'HUNTINGTON INGAL CFD', 'IAC/INTERACTIVEC CFD',
                    'IBM CFD', 'IDEXX LABS CFD', 'ILLINOIS TOOL WO CFD', 'ILLUMINA CFD', 'INGERSOLL-RAND I CFD', 
                    'INGREDION INCORPORATED CFD', 'INNOVATIVE CFD', 'INOVIO PHARM CFD', 'INTEL CFD', 'INTERACTIVE BROK CFD',
                      'INTERCONTINENTAL CFD', 'INTL FLVR & FRAG CFD', 'INTL PAPER CO CFD', 'INTUIT CFD',
                        'INTUITIVE SURGIC CFD', 'INVESCO LTD CFD', 'IPG PHOTONICS CFD', 'IQIYI-ADR CFD', 'IQVIA HOLDINGS I CFD', 'IRON MOUNTAIN CFD', 'JACK HENRY CFD', 'JACOBS SOLUTIONS CFD', 'JD-ADR CFD', 'JM SMUCKER CO CFD', 'JOHNSON CONTROLS CFD', 'JOHNSON&JOHNSON CFD', 'JOYY INC CFD', 'JPMORGAN CHASE CFD', 'K12 CFD', 'KEURIG DR PEPPER CFD', 'KEYCORP CFD', 'KEYSIGHT TEC CFD', 'KIMBERLY-CLARK CFD', 'KIMCO REALTY CFD', 'KINDER MORGAN IN CFD', 'KKR & CO-A CFD', 'KLA CFD', 'KONINKLIJKE PHILIPS CFD', 'KRAFT HEINZ CO/T CFD', 'KROGER CO CFD', 'KYNDRYL HOLD CFD', 'L3HARRIS TECHNOL CFD', 'LAM RESEARCH CFD', 'LAS VEGAS SANDS CFD', 'LEIDOS HOLDINGS CFD', 'LEMONADE INC CFD', 'LINCOLN NATL CRP CFD', 'LIVE NATION ENTE CFD', 'LKQ CORP CFD', 'LOCKHEED MARTIN CFD', 'LOEWS CORP CFD', "LOWE'S COS CFD", 'LUCID GROUP CFD', 'LULULEMON ATH CFD', 'LUMEN TECHNOLOGI CFD', 'LYONDELLBASELL-A CFD', 'M&T BANK CFD', 'MARATHON DIGITAL CFD', 'MARATHON PETROLE CFD', 'MARKETAXESS CFD', 'MARRIOTT INTL-A CFD', 'MARSH & MCLENNAN CFD', 'MARTIN MAR MTLS CFD', 'MARVELL TECH GRP CFD', 'MASCO CORP CFD', 'MASTERCARD-A CFD', 'MATCH GROUP INC CFD', 'MAWSON INFRASTR CFD', 'MCCORMICK-N/V CFD', 'MCDONALDS CFD', 'MCKESSON CFD', 'MEDTRONIC PLC CFD', 'MERCADOLIBRE CFD', 'MERCK & CO CFD', 'META PLATFORMS CFD', 'METLIFE CFD', 'METTLER-TOLEDO CFD', 'MGM RESORTS INTE CFD', 'MICROCHIP TECH CFD', 'MICRON TECH CFD', 'MICROSOFT CFD', 'MID-AMERICA APAR CFD', 'MODERNA INC CFD', 'MOHAWK INDS CFD', 'MOLINA HEALTHCAR CFD', 'MOLSON COORS-B CFD', 'MONDELEZ INTER-A CFD', 'MONOLITHIC POWER CFD', 'MONSTER BEVERAGE CFD', "MOODY'S CFD", 'MORGAN STANLEY CFD', 'MOSAIC CO/THE CFD', 'MOTOROLA SOLUTIO CFD', 'MSCI CFD', 'NASDAQ CFD', 'NEOGEN CFD', 'NETAPP INC CFD', 'NETEASE-ADR CFD', 'NETFLIX CFD', 'NEW ORIENTAL-ADR CFD', 'NEWELL BRANDS IN CFD', 'NEWMONT CFD', 'NEWS CORP-CL A CFD', 'NEWS CORP-CL B CFD', 'NEXTERA ENERGY CFD', 'NIKE  --B CFD', 'NIO INC CFD', 'NISOURCE INC CFD', 'NOKIA OYJ CFD', 'NORDSON CORP CFD', 'NORFOLK SOUTHERN CFD', 'NORTHERN TRUST CFD', 'NORTHROP GRUMMAN CFD', 'NORWEGIAN CRUISE CFD', 'NOVAVAX CFD', 'NRG ENERGY CFD', 'NUCOR CORP CFD', 'NVIDIA CFD', 'NVR INC CFD', 'NXP SEMICONDUCTO CFD', "O'REILLY AUTOMOT CFD", 'OATLY GROUP CFD', 'OCCIDENTAL PETE CFD', 'OKTA CFD', 'OLD DOMINION FRT CFD', 'OMNICOM GROUP CFD', 'ONEOK INC CFD', 'ORACLE CFD', 'ORGANON & CO CFD', 'OTIS WORLDWI CFD', 'PACCAR CFD', 'PACIFIC BIOSCIENCES CFD', 'PACKAGING CORP CFD', 'PALANTIR TECH CFD', 'PALO ALTO NETWOR CFD', 'PARAMOUNT GLOB-B CFD', 'PARKER HANNIFIN CFD', 'PAYCHEX CFD', 'PAYCOM SOFTWARE CFD', 'PAYPAL HOLDINGS CFD', 'PENN NATL GAMING CFD', 'PENTAIR PLC CFD', 'PEPSICO CFD', 'PFIZER CFD', 'PHILIP MORRIS IN CFD', 'PHILLIPS 66 CFD', 'PINDUODUO CFD', 'PINNACLE WEST CFD', 'PINTEREST CFD', 'PNC FINANCIAL SE CFD', 'POOL CORP CFD', 'PPG INDS CFD', 'PPL CFD', 'PRINCIPAL FINL CFD', 'PROCTER & GAMBLE CFD', 'PROGRESSIVE CFD', 'PROLOGIS CFD', 'PRUDENTL FINL CFD', 'PTC INC CFD', 'PUB SERV ENTERP CFD', 'PUBLIC STORAGE CFD', 'PULTEGROUP INC CFD', 'PVH CORP CFD', 'QORVO CFD', 'QUALCOMM CFD', 'QUANTA SERVICES CFD', 'QUANTUMSCAPE CFD', 'QUEST DIAGNOSTIC CFD', 'RALPH LAUREN COR CFD', 'RAYMOND JAMES CFD', 'RAYTHEON CO CFD', 'REALTY OME CFD', 'REGENERON PHARM CFD', 'REGIONS FINANCIA CFD', 'REPUBLIC SVCS CFD', 'RESMED CFD', 'REVVITY INC CFD', 'RINGCENTRAL IN-A CFD', 'RIOT BLOCKCHAIN CFD', 'RIVIAN AUTO CFD', 'ROBERT HALF INTL CFD', 'ROBINHOOD CFD', 'ROBLOX CFD', 'ROCKWELL AUTOMAT CFD', 'ROLLINS INC CFD', 'ROPER TECHNOLOGI CFD', 'ROSS STORES CFD', 'ROYAL CARIBBEAN CFD', 'S&P GLOBAL CFD', 'SALESFORCE CFD', 'SBA COMM CFD', 'SCHLUMBERGER LTD CFD', 'SCHRODINGER INC CFD', 'SCHWAB (CHARLES) CFD', 'SEA LTD-ADR CFD', 'SEAGATE TECHNOLO CFD', 'SEMPRA ENERGY CFD', 'SERVICENOW CFD', 'SHERWIN-WILLIAMS CFD', 'SHOPIFY CFD', 'SIMON PROPERTY CFD', 'SIRIUS XM HOLDIN CFD', 'SKYWORKS SOLUTIO CFD', 'SMITH AO CORP CFD', 'SNAP  - A CFD', 'SNOWFLAKE INC CFD', 'SOLAREDGE TECHNO CFD', 'SOUTHERN CO CFD', 'SOUTHERN COPPER CFD', 'SOUTHWEST AIR CFD', 'SPHERE 3D CORP CFD', 'SPOTIFY TECHNOLO CFD', 'STANLEY BLACK & CFD', 'STARBUCKS CFD', 'STATE ST CFD', 'STERIS PLC CFD', 'STRYKER CFD', 'SYNCHRONY FINANC CFD', 'SYSCO CFD', 'T-MOBILE US CFD', 'TAKE-TWO INTERAC CFD', 'TAL EDUCATIO-ADR CFD', 'TAPESTRY INC CFD', 'TARGET CFD', 'TE CONNECTIVITY CFD', 'TELADOC HEALTH CFD', 'TELEDYNE TECH CFD', 'TELEFLEX INC CFD', 'TENCENT MUSI-ADR CFD', 'TERADYNE INC CFD', 'TESLA CFD', 'TEXAS INSTRUMENT CFD', 'TEXTRON INC CFD', 'THERMO FISHER CFD', 'TILRAY INC CFD', 'TJX COS CFD', 'TRACTOR SUPPLY CFD', 'TRANE TECHNOLOGI CFD', 'TRANSDIGM GROUP CFD', 'TRAVELERS COS IN CFD', 'TRIMBLE INC CFD', 'TRIP GRO-ADR CFD', 'TRUIST FINANCIAL CFD', 'TSM CFD', 'TYLER TECHNOLOG CFD', 'TYSON FOODS-A CFD', 'UBER TECHNOLOGIE CFD', 'UDR INC CFD', 'ULTA BEAUTY INC CFD', 'UNDER ARMO-C CFD', 'UNDER ARMOUR-A CFD', 'UNILEVER CFD', 'UNION PAC CFD', 'UNITED AIRLINES CFD', 'UNITED PARCEL-B CFD', 'UNITED RENTALS CFD', 'UNITEDHEALTH GRP CFD', 'UP FINTECH HOLDING CFD', 'UPSTART HOLDINGS CFD', 'US BAN CFD', 'VALERO ENERGY CFD', 'VEEVA SYSTEMS-A CFD', 'VENTAS INC CFD', 'VERISIGN CFD', 'VERISK ANALYTI CFD', 'VERIZON COMMUNIC CFD', 'VERTEX PHARM CFD', 'VF CFD', 'VIASAT CFD', 'VIATRIS CFD', 'VIPSHOP HOLD CFD', 'VISA -CLASS A CFD', 'VORNADO RLTY TST CFD', 'VULCAN MATERIALS CFD', 'WABTEC CORP CFD', 'WALMART CFD', 'WALT DISNEY CO CFD', 'WARNER BROS CFD', 'WASTE MANAGEMENT CFD', 'WATERS CORP CFD', 'WEC ENERGY GROUP CFD', 'WEIBO CFD', 'WELLS FARGO & CO CFD', 'WELLTOWER CFD', 'WEST PHARMACEUT CFD', 'WESTERN DIGITAL CFD', 'WEYERHAEUSER CFD', 'WHIRLPOOL CORP CFD', 'WILLIAMS COS CFD', 'WILLIS TOWERS WA CFD', 'WIMI HOLOGRAM CFD', 'WORKDAY-A CFD', 'WR BERKLEY CORP CFD', 'WW GRAINGER INC CFD', 'WYNN RESORTS LTD CFD', 'XCEL ENERGY CFD', 'XPENG INC - ADR CFD', 'XYLEM INC CFD', 'YTE CFD', 'YUM CHINA HO CFD', 'YUM! BRANDS CFD', 'ZEBRA TECH CORP CFD', 'ZILLOW GROUP CFD', 'ZIMMER BIOMET HO CFD', 'ZIONS BANCORP NA CFD', 'ZOETIS CFD', 'ZOOM VIDEO COM-A CFD', 'ZSCALER INC CFD', 'ZTO EXPRESS-ADR CFD', 'MICROSTRATEGY CFD', 'BXP INC CFD', 'BAOZUN INC CFD', 'DAQO NEW ENERGY CFD', 'AMC NETWORKS CFD', 'ARM HOLDINGS CFD', 'MOBILEYE GLOBAL CFD', 'TRIPADVISOR INC CFD', 'SONY GROUP CORP CFD', 'ALCOA CORP CFD', 'LI AUTO CFD', 'ORASURE TECH CFD', 'SOHU COM LTD CFD', 'HERBALIFE LTD CFD', 'CLIFFS NAT CFD', 'CEMEX SAB DE CV CFD', 'DROPBOX INC CFD', 'GOODYEAR TIRE CFD', 'HARLEY-DAVIDSON CFD', 'JEFFERIES FIN CFD', 'NOV INC CFD', 'OWEN ILLINOIS CFD', 'PITNEY BOWES CFD', 'PG&E CORP CFD', 'TENET HEALTH CFD', 'WESTERN UNION CFD', 'FRESH DEL MONTE CFD', 'TEVA CFD', 'AUTOHOME CFD', 'GODADDY CFD', 'MANPOWER INC CFD', 'HELLO GROUP CFD', 'UNIVERSAL PLAY CFD', 'PETROLEO BRASIL CFD', 'PLUG POWER CFD', 'PELOTON INTERAC CFD', 'VIRGIN GALACTIC CFD', 'ULTRAPRO QQQ CFD', 'TWILIO INC CFD', 'WAYFAIR CFD', 'WIX COM LTD CFD', 'YELP INC CFD', 'AFFI MANAGERS CFD', 'ARCH CAPITAL CFD', 'AGIOS PHARMA CFD', 'AGNC INVESTMENT CFD', 'ALNYLAM PHARMA CFD', 'ANGI INC CFD', 'AMERICAN O CFD', 'AGORA INC CFD', 'DIGITAL TURBINE CFD', 'ARES CAPITAL CFD', 'ATOMERA INC CFD', 'AURINIA PHARMA CFD', 'AXON ENTERPRISE CFD', 'BEIGENE LTD CFD', 'BALLARD POWER CFD', 'BLACKBAUD INC CFD', 'BLINK CHARGING CFD', 'BOK FINANCIAL CFD', 'BRUKER CORP CFD', 'CRED ACCEPTANCE CFD', 'CARGURUS INC CFD', 'CASEYS GENERAL CFD', 'CRACKER BARREL CFD', 'COMMERCE BANC CFD', 'CONSTELL ENERGY CFD', 'COGNEX CORP CFD', 'CARLYLE GROUP CFD', 'CHURCHILL DOWNS CFD', 'CENTURY CASINOS CFD', 'COLUMBIA SPORTS CFD', 'CRESUD SACIF CFD', 'CRITEO SA CFD', 'EURONET CFD', 'ELBIT SYSTEMS CFD', 'EAST WEST CFD', 'FUELCELL CFD', 'FIRSTCASH INC CFD', 'FIBROGEN INC CFD', 'FIVE BELOW INC CFD', 'FUNKO INC CFD', 'GDS HOLDINGS CFD', 'GILAT SATELLITE CFD', 'GAMING & L CFD', 'GENTEX CORP CFD', 'GRAND CANYON CFD', 'BANK OZK CFD', 'ECHOSTAR CORP CFD', 'CASSAVA SCI CFD', 'VNET GROUP CFD', 'GENERAC CFD', 'REGENCY CFD', 'TARGA RESOURCES CFD', 'ENOVIX CORP CFD', 'UIPATH INC CFD', 'SIGMA LITHIUM CFD', 'SOLID POWER CFD', 'DIAGEO PLC CFD', 'EQUINOR ASA CFD', 'LM ERICSSON CFD', 'FRESENIUS MEDI CFD', 'GREIF INC CFD', 'GENMAB A/S CFD', 'GSK PLC CFD', 'HEICO CORP CFD', 'HALEON PLC CFD', 'HARMONY GOLD CFD', 'HSBC HOLDINGS CFD', 'INTERCON HOTELS CFD', 'LIB LATIN CL C CFD', 'LIB LATIN CL A CFD', 'LLOYDS CFD', 'NOVO NORDISK CFD', 'NATWEST GROUP CFD', 'OVINTIV INC CFD', 'PEARSON PLC CFD', 'RES BRANDS CFD', 'RELX PLC CFD', 'SHELL PLC CFD', 'SASOL LTD CFD', 'THOMSON REUT CFD', 'TENARIS SA CFD', 'VIKING THERA CFD', 'ADEIA INC CFD', 'ALPHA METALLUR CFD', 'BROWN-FORMAN CFD', 'BUILDERS FIRST CFD', 'CECO ENV CORP CFD', 'ENTEGRIS INC CFD', 'EQT CORP CFD', 'FIRST SOLAR CFD', 'NEOGENOMICS CFD', 'SNDL INC CFD', 'UNI HEALTH CFD', 'RAPID7 INC CFD', 'ALBERTSONS COS CFD', 'MEDICAL PROP CFD', 'MARAVAI CFD', 'ARCHER AVIATION CFD', 'VICI PROPERTIES CFD', 'INVITATION HOME CFD', 'FAIR ISAAC CORP CFD', 'INSULET CORP CFD', 'BROADRIDGE FIN CFD', 'LAMB WESTO CFD', 'IDEX CORP CFD', 'CHEESECAKEF CFD', 'CAMECO CORP CFD', 'REDDIT INC CFD', 'MANCHESTER CFD', 'NEXGEN ENERGY CFD', 'ROKU INC CFD', 'SOCIEDAD QUI CFD', 'TRADE DESK CFD', 'SILVER WHEATON CFD', 'TOTALENERGIES CFD', 'GRAB HOLDINGS CFD', 'EQUINOX GOLD CORP CFD', 'HYPERSCALE DATA CFD', 'BLOCK - A CFD', "CAMPBELL'S CO CFD", 'LYFT INC CFD', 'SPACEX CFD', 'NAS100U6', 'GER40U6', 'US30U6', 'SP500U6', 'GOLDZ6', 'CHCJPC', 'DJCGLD', 'DJCJPC', 'DJCSPC', 'NACJPC', 'SPCJPC']
    timeframes = ["M1", "M5", "M15", "M30", "H1"]
    use_real = True
    print("\n🚀 ЗАПУСК: РЕАЛЬНЫЕ ДАННЫЕ MT5 (все инструменты × все ТФ)")

    print(f"   Логика: старт {cfg.start_lot} лот, ×{cfg.multiplier}, до {cfg.max_positions} позиций")
    print("=" * 80)

    print(f"   Логика: старт {cfg.start_lot} лот, ×{cfg.multiplier}, до {cfg.max_positions} позиций")
    print("=" * 80)

    results: List[ComboResult] = []
    total = len(symbols) * len(timeframes)

    for idx, symbol in enumerate(symbols, 1):
        for tf in timeframes:
            print(f"[{symbol:<10}| {tf:<4}] ", end="", flush=True)
            t0 = datetime.now()

            prices = get_prices(symbol, tf, cfg, use_real)
            if not prices or len(prices) < 100:
                print("недостаточно данных, пропуск")
                continue

            result = run_backtest(prices, symbol, tf, cfg)
            results.append(result)

            elapsed = (datetime.now() - t0).total_seconds()
            win_pct = (result.wins / result.cycles * 100) if result.cycles > 0 else 0.0
            print(f"циклов: {result.cycles:>4} win: {win_pct:>5.1f}% "
                  f"pf: {result.profit_factor:>6.2f} maxDD: {result.max_drawdown:>8.1f} "
                  f"total: {result.total_profit:>8.1f} score:{result.safety_score:.4f} ({elapsed:.1f}с)")

    # ---------- ОТЧЁТ ----------
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    
    # Сохраняем все графики эквити
    save_all_equity_plots(results, output_dir)
    
    rank_and_report(results, output_dir)

    print("\n✅ БЭКТЕСТ ЗАВЕРШЁН")

# ============================================================
#  ТОЧКА ВХОДА
# ============================================================
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹ Прервано пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n👋 Выход")
